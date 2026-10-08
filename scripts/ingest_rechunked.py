#!/usr/bin/env python3
"""
Ingestion contrôlée d'une source re-chunkée :
  1. Supprime les ANCIENS chunks de la source (id sans suffixe _rc)
  2. Upserte les nouveaux (_rc) avec métadonnée type: these|narratif

Usage : python scripts/ingest_rechunked.py data/rechunk_<SOURCE>.json
"""
import sys, json, chromadb
from sentence_transformers import SentenceTransformer

JSON_PATH = sys.argv[1]
MODEL_PATH = "models/embeddings/multilingual-e5-small"
DB_PATH = "rag/chroma_db"

# --- 1. Charger les nouveaux chunks ---
with open(JSON_PATH, encoding="utf-8") as f:
    chunks = json.load(f)
source = chunks[0]["source"]
assert all(c["source"] == source for c in chunks), "sources mixtes dans le JSON ?!"
print(f"[1] {len(chunks)} chunks à ingérer pour '{source}'")

# --- 2. Connecter et identifier les anciens ---
col = chromadb.PersistentClient(path=DB_PATH).get_collection("fondation_knowledge")
avant = col.count()
tous_ids = col.get(include=[])["ids"]
anciens = [i for i in tous_ids if i.startswith(source) and "_rc" not in i]
print(f"[2] Corpus actuel : {avant} chunks | anciens '{source}*' à supprimer : {len(anciens)}")

confirmation = input(f"   Supprimer les {len(anciens)} anciens et ingérer les {len(chunks)} nouveaux ? [oui/NON] ")
if confirmation.strip().lower() != "oui":
    print("Abandon — rien n'a été touché.")
    sys.exit(0)

# --- 3. Suppression ancienne ---
if anciens:
    col.delete(ids=anciens)
apres_del = col.count()
print(f"[3] Supprimés. Corpus : {avant} → {apres_del} (delta {avant - apres_del})")

# --- 4. Embedding + upsert des nouveaux ---
print("[4] Chargement du modèle d'embeddings (CPU)...")
model = SentenceTransformer(MODEL_PATH)
# Convention e5 : "passage: " pour les documents
embeddings = model.encode([f"passage: {c['text']}" for c in chunks]).tolist()
col.upsert(
    ids=[c["id"] for c in chunks],
    documents=[c["text"] for c in chunks],
    embeddings=embeddings,
    metadatas=[{"source": c["source"], "type": c["type"]} for c in chunks],
)
apres = col.count()
print(f"[5] Ingestion faite. Corpus final : {apres} chunks")
print(f"    Vérification : {apres} = {apres_del} + {len(chunks)} → {'✅ COHÉRENT' if apres == apres_del + len(chunks) else '⚠️ INCOHÉRENT'}")
