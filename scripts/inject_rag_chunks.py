#!/usr/bin/env python3
import json, pathlib, sys, os
import chromadb
from sentence_transformers import SentenceTransformer

BASE = pathlib.Path(__file__).resolve().parent.parent
MODEL = os.path.join(str(BASE), "models", "embeddings", "multilingual-e5-small")
CHROMA_DIR = BASE / "rag" / "chroma_db"
INPUT_JSONL = BASE / "dataset" / "fondation_v0.jsonl"
OUTPUT_JSONL = BASE / "dataset" / "fondation_v1_with_rag.jsonl"
COLLECTION_NAME = "fondation_knowledge"
TOP_K = 15

print(f"[1] Modèle : {MODEL}")
model = SentenceTransformer(MODEL)
db = chromadb.PersistentClient(path=str(CHROMA_DIR))
col = db.get_collection(COLLECTION_NAME)

def load_chunks(question):
    emb = model.encode(["query: " + question]).tolist()
    res = col.query(query_embeddings=emb, n_results=TOP_K,
                    include=["documents", "metadatas", "distances"])
    docs, metas, dists = (res["documents"][0], res["metadatas"][0], res["distances"][0])
    seen, out = {}, []
    for doc, meta, dist in zip(docs, metas, dists):
        src = meta.get("source", "unknown")
        if seen.get(src, 0) >= 2:
            continue
        seen[src] = seen.get(src, 0) + 1
        out.append(f"[{src}] score={1 - dist:.3f}\n{doc[:200]}...")
    return "\n\n".join(out) if out else "[AUCUNE SOURCE TROUVÉE]"

lines = INPUT_JSONL.read_text(encoding="utf-8").strip().split("\n")
out_lines = []
for line in lines:
    ex = json.loads(line)
    user = ex["messages"][1]["content"]
    
    # RECHERCHE EXACTE DU PLACEHOLDER ET REMPLACEMENT TOTAL
    if "[CONTEXTE SOURCES]" in user:
        # Extraire LA QUESTION (elle est après le placeholder)
        parts = user.split("[CONTEXTE SOURCES]")
        if len(parts) >= 2:
            after = parts[1].strip()
            # Enlever "(chunks RAG à injecter...)" s'il existe
            after = after.replace("(chunks RAG à injecter par script — voir TODO injection Chroma)", "").strip()
            question = after
            rag = load_chunks(question)
            # NOUVEAU MESSAGE : placeholder + chunks + question
            new_user = f"[CONTEXTE SOURCES]\n{rag}\n\n{question}"
            ex["messages"][1]["content"] = new_user
    
    out_lines.append(json.dumps(ex, ensure_ascii=False))

OUTPUT_JSONL.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
print(f"OK : {len(out_lines)} exemples")
print(f"Vérification : {sum(1 for l in out_lines if 'score=' in l)} ont des chunks")
print(f"Reste de placeholders ? {sum(1 for l in out_lines if 'TODO injection' in l)}")
