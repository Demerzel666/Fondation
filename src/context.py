# src/context.py
# =============================================================================
# Gestion du contexte conversationnel pour Fondation-IA
# Assemble : historique SQLite + fichiers chargés + contexte RAG → Prompt complet
# =============================================================================

import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.rag import search_context, format_context, detect_domain
from src.db import get_messages, add_message, get_conversation_summary

MAX_HISTORY_TOKENS = 24000
MAX_HISTORY_MESSAGES = 10
MAX_CHARS_PER_MESSAGE = 600
MAX_LOADED_FILES = 15
MAX_CHARS_PER_FILE = 8000


def _load_system_prompt(mode):
    """Charge le system prompt depuis les fichiers prompts/."""
    if mode == "code":
        prompt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts", "code.txt")
    else:
        prompt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts", "politique.txt")
    
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"[WARNING] System prompt introuvable: {prompt_path}")
        return f"Vous êtes un assistant Fondation-IA en mode {mode}. Utilisez vos capacités standards."


def build_prompt(conversation_id, user_input, mode="auto", loaded_files=None):
    """Construit le prompt complet prêt à envoyer au modèle.

    Args:
        conversation_id: ID de la conversation dans SQLite
        user_input: Question/texte de l'utilisateur
        mode: 'code', 'politique', ou 'auto'
        loaded_files: dict {filename: content} injecté dans le contexte
    """

    # ── Détection auto par mots-clés si mode='auto' ──────────────
    if mode == "auto":
        mode = "politique"

    # 1. Système selon le mode (chargé depuis fichiers)
    system_prompt = _load_system_prompt(mode)

    # 1.5. Contexte global + contexte projet
    from src.db import get_global_context, get_project_context
    from src.db import get_conn

    global_ctx = get_global_context()
    if global_ctx:
        system_prompt += f"\n\n--- CONTEXTE GLOBAL ---\n{global_ctx}"

    # Récupérer le project_id depuis la conversation
    conn = get_conn()
    conv_row = conn.execute(
        "SELECT project_id FROM conversations WHERE id = ?", (conversation_id,)
    ).fetchone()
    conn.close()

    if conv_row:
        project_ctx = get_project_context(conv_row['project_id'])
        if project_ctx:
            system_prompt += f"\n\n--- CONTEXTE PROJET ---\n{project_ctx}"

    # 2. Historique récent (limité à MAX_HISTORY_MESSAGES)
    messages = get_messages(conversation_id, limit=MAX_HISTORY_MESSAGES)
    history_lines = []
    for msg in messages:
        role = "human" if msg["role"] == "user" else "assistant"
        content = msg['content'][:MAX_CHARS_PER_MESSAGE]
        history_lines.append(f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}")

    history_combined = ""
    if history_lines:
        history_combined = "\n".join(history_lines) + "<|eot_id|>"

    # 3. Fichiers chargés via /load
    files_context = ""
    if loaded_files:
        files_parts = []
        for fname, fcontent in loaded_files.items():
            truncated = fcontent[:MAX_CHARS_PER_FILE]
            if len(fcontent) > MAX_CHARS_PER_FILE:
                truncated += f"\n... [tronqué, {len(fcontent)} chars total]"
            files_parts.append(f"[FICHIER: {fname}]\n{truncated}")
        files_context = f"\n--- Fichiers projet chargés ---\n" + "\n\n".join(files_parts) + "\n"

    # 4. Contexte RAG
    rag_text = ""
    rag_sources = []

    contexts = search_context(user_input, top_k=5, domain="auto", mode=mode, threshold=0.5)
    if contexts:
        rag_text = f"\n--- Connaissances Pertinentes ---\n{format_context(contexts)}"
        rag_sources = [{"id": c["id"], "source": c["source"], "domain": c.get("domain", "")} for c in contexts]

    # 4.5. Project index (mode code seulement)
    project_index = ""
    if mode == "code":
        index_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "project_index.txt")
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                project_index = f"\n--- Structure du projet ---\n{f.read()}\n"
        except FileNotFoundError:
            pass

    # 5. Prompt final assemblé
    full_prompt = (
        f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
        f"{system_prompt}{project_index}<|eot_id|>"
        f"{history_combined}"
        f"{files_context}"
        f"\n<|start_header_id|>user<|end_header_id|>\n\n"
        f"{user_input}{rag_text}<|eot_id|>\n"
        f"<|start_header_id|>assistant<|end_header_id|>\n\n"
    )

    return {
        "full_prompt": full_prompt,
        "mode_used": mode,
        "domain_used": contexts[0]["domain"] if contexts else "none",
        "history_used": len(messages),
        "rag_sources": rag_sources,
        "loaded_files": len(loaded_files) if loaded_files else 0,
        "estimated_tokens": len(full_prompt.split()),
    }


def save_response(conversation_id, content, rag_sources=[]):
    """Sauvegarde la réponse de l'IA dans SQLite."""
    from datetime import datetime
    try:
        token_count = len(content.split())
        import json

        safe_sources = []
        for rs in (rag_sources or []):
            if isinstance(rs, dict):
                safe_sources.append({k: str(v)[:50] if isinstance(v, str) else v for k, v in rs.items()})

        mid = add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            rag_sources=json.dumps(safe_sources),
            token_count=token_count
        )
        print(f"[SAVED] Réponse sauvegardée #{mid}")
        return mid
    except Exception as e:
        print(f"[ERROR Sauvegarde] {e}")
        return None


# ── TEST ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from src.db import init_db, create_project, create_conversation, delete_project

    init_db()
    pid = create_project("test-context", "Test", "code")
    cid = create_conversation(pid, "Test context")

    print("\n[TEST 1] Prompt technique sans fichiers...")
    result1 = build_prompt(cid, "Comment créer une classe Python SQLAlchemy avec foreign keys ?", mode="code")
    print(f"Prompt length: {len(result1['full_prompt'])} chars")
    print(f"Mode: {result1['mode_used']}, Domain: {result1.get('domain_used', 'N/A')}")
    print(f"Sources RAG: {len(result1['rag_sources'])}")

    print("\n[TEST 2] Prompt technique AVEC fichiers chargés...")
    test_files = {
        "db.py": "import sqlite3\n\ndef init_db():\n    conn = sqlite3.connect('fondation.db')\n    # ... schema ...",
        "rag.py": "import chromadb\n\ndef search_context(query, top_k=5):\n    # ... recherche vectorielle ..."
    }
    result3 = build_prompt(cid, "Ajoute une table projects à mon schéma existant", mode="code", loaded_files=test_files)
    print(f"Prompt length: {len(result3['full_prompt'])} chars")
    print(f"Fichiers chargés: {result3.get('loaded_files', 0)}")

    print("\n[TEST 3] Prompt politique...")
    result2 = build_prompt(cid, "Quelle est la différence entre réforme et révolution selon Luxemburg ?", mode="politique")
    print(f"Prompt length: {len(result2['full_prompt'])} chars")
    print(f"Mode: {result2['mode_used']}, Domain: {result2.get('domain_used', 'N/A')}")
    print(f"Sources RAG: {len(result2['rag_sources'])}")

    delete_project(pid)
    print("\n[Test] OK!")
