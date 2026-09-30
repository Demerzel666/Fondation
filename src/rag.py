# src/rag.py
# =============================================================================
# RAG - Retrieval Augmented Generation pour Fondation-IA
# Collections multiples : politique + code
# =============================================================================

import re
import chromadb
from sentence_transformers import SentenceTransformer
import numpy as np
import re

# ═══════ SOURDISSEMENT LOGS EMBEDDINGS ═══════
import os
import logging

os.environ['TOKENIZERS_PARALLELISM'] = 'false'
logging.getLogger('sentence_transformers').setLevel(logging.ERROR)
logging.getLogger('chromadb').setLevel(logging.ERROR)
logging.getLogger('transformers').setLevel(logging.ERROR)
# ──────────────────────────────────────────────

CHROMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rag", "chroma_db")
EMBEDDING_MODEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "embeddings", "multilingual-e5-small")

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
    code_hits = sum(1 for kw in keywords_code if re.search(r'\b' + re.escape(kw) + r'\b', input_lower))
    pol_hits = sum(1 for kw in keywords_politique if re.search(r'\b' + re.escape(kw) + r'\b', input_lower))

    if code_hits > pol_hits:
        return "code"
    return "politique"

def reformulate_query(question):
    '''Reformule en requêtes RAG neutres (FR + EN), sans le biais du mot-ancre.
    Fallback garanti : [question] en cas d'échec — jamais bloquer la recherche.'''
    try:
        from src.core import send_to_model
        messages = [
            {"role": "system", "content": (
                "Tu es un module de reformulation pour moteur de recherche. "
                "Réponds UNIQUEMENT avec deux lignes, sans commentaire :\n"
                "Ligne 1 : la requête française (mots-clés neutres, pas une question)\n"
                "Ligne 2 : la traduction anglaise des mêmes concepts.\n"
                "CONSERVE TOUJOURS les noms propres d'auteurs et d'oeuvres cités "
                "(Federici, Bookchin, hooks...).\n"
                "Exemple pour 'que dit Federici sur le travail domestique ?' :\n"
                "Federici travail domestique reproduction sociale salariat\n"
                "Federici domestic work social reproduction wages housework"
            )},
            {"role": "user", "content": question}
        ]
        resp = send_to_model(messages, 'chat')
        if not resp or resp.startswith("[ERROR]"):
            return [question]
        lignes = [l.strip() for l in resp.strip().split('\n') if l.strip()]
        return lignes[:2] if lignes else [question]
    except Exception:
        return [question]

def search_context(query, top_k=5, domain="auto", mode="auto", threshold=0.5, reformulate=True):
    '''Recherche multi-requêtes (question + reformulation FR/EN en politique),
    fusion dédoublonnée, seuil, diversification stricte (max 2 par source).

    Returns:
        Liste de dicts avec: id, text, source, title, score, domain'''
    if domain == "auto":
        domain = detect_domain(query, mode=mode)

    collection = get_collection(domain)
    model = get_embedding_model()

    # Requêtes : question brute + (FR reformulée + EN) en mode politique
    queries = [query]
    if domain == "politique" and reformulate:
        queries += reformulate_query(query)

    fetch_k = min(top_k * 4, 20)

    # Fusion des candidats de toutes les requêtes, dédoublonnés par id
    # (un chunk retrouvé en FR ET en EN garde son meilleur score)
    merged = {}
    for q in queries:
        emb_raw = model.encode(["query: " + q])
        if isinstance(emb_raw, np.ndarray):
            emb_list = emb_raw.tolist()
        else:
            emb_list = list(emb_raw)
        query_emb = [float(x) for x in emb_list[0]]

        results = collection.query(
            query_embeddings=[query_emb],
            n_results=fetch_k,
            include=['documents', 'metadatas', 'distances']
        )
        ids = results.get("ids", [[]])
        if not ids or not ids[0]:
            continue
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        for i in range(len(ids[0])):
            cid = ids[0][i]
            score = 1.0 - float(dists[i]) if i < len(dists) else 0.0
            if cid not in merged or score > merged[cid]["score"]:
                merged[cid] = {
                    "id": cid,
                    "text": docs[i] if i < len(docs) else "",
                    "source": (metas[i] or {}).get("source", "inconnu"),
                    "title": (metas[i] or {}).get("title", ""),
                    "score": score,
                    "domain": domain,
                }

    # Seuil puis tri par score
    filtered = [c for c in merged.values() if c["score"] > threshold]
    filtered.sort(key=lambda x: x["score"], reverse=True)

    # Diversification STRICTE : max 2 chunks par source, pas de fill-back
    # qui contourne le cap. Mieux vaut 4 chunks variés que 5 monolithiques.
    per_source = {}
    diversified = []
    for c in filtered:
        n = per_source.get(c["source"], 0)
        if n < 2:
            diversified.append(c)
            per_source[c["source"]] = n + 1
        if len(diversified) >= top_k:
            break

    return diversified[:top_k]
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
