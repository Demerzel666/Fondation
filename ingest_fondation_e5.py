#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sentence_transformers import SentenceTransformer
import chromadb
import re

print("=== INGESTION E5-SMALL (PRÉFIXES ACTIVÉS) ===")

# 1. Charger le modèle LOCAL
print("[1] Chargement modèle local...")
model = SentenceTransformer('/home/dot/private/fondation-ia/models/embeddings/e5-small', device='cpu')
print("   ✅ Modèle chargé (384 dims)")

# 2. ChromaDB
print("[2] Initialisation Chroma...")
client = chromadb.PersistentClient(path="rag/chroma_db")
try:
    client.delete_collection('fondation_knowledge')
except:
    pass
collection = client.create_collection('fondation_knowledge')
print("   ✅ Collection prête")

# 3. Charger le texte
print("[3] Chargement corpus...")
filepath = 'data/raw_texts/abdullah-ocalan-democratic-confederalism.txt'
with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

# 4. Nettoyage (césures + mots collés)
print("[4] Nettoyage du texte...")
text = text.replace('-\n', '')
text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

chunks = []
for i in range(0, len(text), 2000 - 200):
    chunk = text[i:i+2000].strip()
    if chunk and len(chunk) > 100:
        chunks.append(chunk)
print(f"   {len(chunks)} chunks")

# 5. Embeddings avec préfixe "passage:"
print("[5] Génération embeddings (préfixe 'passage:')...")
texts_prefixed = [f"passage: {t}" for t in chunks]
embeddings = model.encode(texts_prefixed).tolist()

# 6. Injection
ids = [f"ocalan_{i}" for i in range(len(chunks))]
collection.add(
    documents=chunks,
    embeddings=embeddings,
    metadatas=[{"source": "ocalan"} for _ in chunks],
    ids=ids
)
print(f"   ✅ {len(chunks)} chunks ingérés")

# 7. Test avec préfixe "query:"
print("\n=== TEST RECHERCHE (PRÉFIXE 'query:') ===")
query = "Quel est le confédéralisme démocratique?"
query_emb = model.encode([f"query: {query}"]).tolist()
results = collection.query(query_embeddings=query_emb, n_results=3)

for i, (doc, dist) in enumerate(zip(results['documents'][0], results['distances'][0]), 1):
    print(f"{i}. Distance: {dist:.3f}")
    print(f"   {doc[:200]}...")
    print()

print("✅ Ingestion terminée !")
