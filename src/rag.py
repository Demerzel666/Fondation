# src/rag.py
# =============================================================================
# RAG - Retrieval Augmented Generation pour Fondation-IA
# Collections multiples : politique + code
# =============================================================================

import chromadb
from sentence_transformers import SentenceTransformer
import numpy as np

# ═══════ SOURDISSEMENT LOGS EMBEDDINGS ═══════
import os
import logging

os.environ['TOKENIZERS_PARALLELISM'] = 'false'
logging.getLogger('sentence_transformers').setLevel(logging.ERROR)
logging.getLogger('chromadb').setLevel(logging.ERROR)
logging.getLogger('transformers').setLevel(logging.ERROR)
# ──────────────────────────────────────────────

CHROMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rag", "chroma_db")
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"

COLLECTIONS = {
    "politique": "fondation_knowledge",   # 8610 chunks existants
    "code": "fondation_code",             # nouveau, à remplir
}

_clients = {}
_collections = {}
_embeddings_model = None


def get_embedding_model():
    """Lazy loading du modèle d'embeddings."""
    global _embeddings_model
    if _embeddings_model is None:
        print(f"[RAG] Chargement embeddings: {EMBEDDING_MODEL}")
        _embeddings_model = SentenceTransformer(EMBEDDING_MODEL, device='cpu')
    return _embeddings_model


def get_collection(domain="politique"):
    """Récupère la collection ChromaDB selon le domaine.
    
    Args:
        domain: 'politique' ou 'code'
    """
    global _clients, _collections
    
    coll_name = COLLECTIONS.get(domain, COLLECTIONS["politique"])
    
    if domain not in _collections:
        _clients[domain] = chromadb.PersistentClient(path=CHROMA_PATH)
        try:
            _collections[domain] = _clients[domain].get_or_create_collection(coll_name)
        except Exception:
            _collections[domain] = _clients[domain].create_collection(coll_name)
        print(f"[RAG] Collection '{coll_name}' : {_collections[domain].count()} chunks")
    
    return _collections[domain]


def detect_domain(query, mode="auto"):
    """Détecte le domaine approprié selon la question et le mode.
    
    Args:
        query: texte de l'utilisateur
        mode: 'code', 'politique', ou 'auto'
    
    Returns:
        'code' ou 'politique'
    """
    if mode == "code":
        return "code"
    if mode == "politique":
        return "politique"
    
    # Mode auto : détection par mots-clés
    keywords_code = ["python", "sql", "table", "fonction", "module", "script",
                     "installer", "git", "api", "bug", "erreur", "compile",
                     "command", "bash", "shell", "linux", "code", "variable",
                     "classe", "import", "pip", "systemd", "nginx", "docker",
                     "flask", "django", "fastapi", "asyncio", "thread", "socket",
                     "json", "csv", "regex", "algorithm", "database", "query",
                     "sqlalchemy", "chromadb", "llama", "rocm", "gguf", "tensor"]
    keywords_politique = ["révolution", "lutte", "capitalisme", "état", "militant",
                          "organisation", "rojava", "fédéralisme", "libertaire",
                          "écologie", "féminisme", "antifascisme", "impérialisme",
                          "classe", "ouvrier", "manifestation", "grève", "anarchie",
                          "marx", "luxemburg", "bakounine", "kropotkine", "bookchin",
                          "ocalan", "colonialisme", "exploitation", "bolchevik"]
    
    input_lower = query.lower()
    code_hits = sum(1 for kw in keywords_code if kw in input_lower)
    pol_hits = sum(1 for kw in keywords_politique if kw in input_lower)
    
    if code_hits > pol_hits:
        return "code"
    return "politique"


def search_context(query, top_k=5, domain="auto", mode="auto", threshold=0.5):
    """Recherche avec embeddings et filtrage intelligent.
    
    Args:
        query: question de l'utilisateur
        top_k: nombre de résultats à retourner
        domain: 'code', 'politique', ou 'auto' (détecte automatiquement)
        mode: mode passé par le CLI ('code', 'politique', 'auto')
        threshold: score minimum pour filtrer le bruit
    
    Returns:
        Liste de dicts avec: text, source, title, score
    """
    # Déterminer le domaine
    if domain == "auto":
        domain = detect_domain(query, mode=mode)
    
    collection = get_collection(domain)
    model = get_embedding_model()

    # Générer embedding avec prefix 'query:' requis par e5
    emb_raw = model.encode(["query: " + query])

    if isinstance(emb_raw, np.ndarray):
        emb_list = emb_raw.tolist()
    else:
        emb_list = list(emb_raw)

    query_emb = [float(x) for x in emb_list[0]]

    # Récupérer plus de candidats qu'on en a besoin pour mieux filtrer
    fetch_k = min(top_k * 4, 20)
    results = collection.query(
        query_embeddings=[query_emb],
        n_results=fetch_k
    )

    contexts = []
    ids = results.get("ids", [[]])
    if not ids or not ids[0]:
        return []

    for i in range(len(ids[0])):
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        score = 1.0 - float(dists[i]) if i < len(dists) else 0.0

        contexts.append({
            "id": ids[0][i],
            "text": docs[i] if i < len(docs) else "",
            "source": (metas[i] or {}).get("source", "inconnu"),
            "title": (metas[i] or {}).get("title", ""),
            "score": score,
            "domain": domain,
        })

    # Filtrer par threshold et trier par score
    filtered = [c for c in contexts if c["score"] > threshold]
    filtered.sort(key=lambda x: x["score"], reverse=True)

    return filtered[:top_k]


def format_context(contexts):
    """Formate les résultats RAG en texte injectable dans le prompt."""
    if not contexts:
        return ""
    parts = []
    for i, ctx in enumerate(contexts, 1):
        source = ctx.get("source", "inconnu")
        title = ctx.get("title", "")
        header = f"[Source {i}: {source}"
        if title:
            header += f" — {title}"
        header += "]"
        
        # Troncature intelligente : coupe à la fin d'une phrase
        text = ctx['text']
        if len(text) > 400:
            last_period = text[:400].rfind('.')
            if last_period > 200:
                text = text[:last_period + 1]
            else:
                text = text[:380] + "..."
        
        parts.append(f"{header}\n{text}")
    return "\n\n---\n\n".join(parts)


def get_stats():
    """Stats rapides de toutes les collections."""
    stats = {}
    for domain in COLLECTIONS:
        try:
            coll = get_collection(domain)
            stats[domain] = {
                "chunks": coll.count(),
                "collection": COLLECTIONS[domain],
                "path": CHROMA_PATH,
            }
        except Exception as e:
            stats[domain] = {"error": str(e)}
    stats["embedding_model"] = EMBEDDING_MODEL
    return stats


# ── TEST ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    stats = get_stats()
    print(f"[RAG] Stats: {stats}")

    print("\n[RAG] Test recherche politique...")
    results = search_context("Qu'est-ce que le confédéralisme démocratique ?", 
                             domain="politique", top_k=3)
    for i, r in enumerate(results, 1):
        print(f"\n--- Résultat {i} (score: {r['score']:.3f}, domaine: {r['domain']}) ---")
        print(f"Source: {r['source']}")
        txt = r['text']
        print(f"Texte: {txt[:200]}...")

    print("\n[RAG] Test recherche code (collection vide attendue)...")
    results_code = search_context("Comment créer une classe Python SQLAlchemy ?", 
                                  domain="code", top_k=3)
    if results_code:
        for i, r in enumerate(results_code, 1):
            print(f"--- Résultat {i} (score: {r['score']:.3f}) ---")
            print(f"Source: {r['source']}")
    else:
        print("(Collection code vide - normal, pas encore de docs ingérées)")

    print("\n[RAG] Test auto-détection...")
    tests = [
        "Comment installer Python sur Arch Linux ?",
        "Quelle est la position de Luxemburg sur la grève ?",
        "Écris un script bash qui backup mes fichiers",
    ]
    for t in tests:
        domain = detect_domain(t, mode="auto")
        print(f"  '{t[:50]}...' → {domain}")
