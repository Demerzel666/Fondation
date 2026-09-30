#!/usr/bin/env python3
import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sentence_transformers import SentenceTransformer
import chromadb
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LICENCES = {
    "Kropotkine_-_La_Conquete_du_Pain": "public-domain",
    "Luxemburg_-_Reforme_ou_Revolution": "public-domain",
    "ia-et-zizanie": "cc-by-sa",
    "amour-et-revolution": "cc-by-sa",
}

def clean_text(text):
    text = text.replace('-\n', '')
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    return text

def chunk_text(text, size=2000, stride=1800):
    chunks = []
    for i in range(0, len(text), stride):
        chunk = text[i:i+size].strip()
        if chunk and len(chunk) > 100:
            chunks.append(chunk)
    return chunks

def main():
    print("=== INGESTION MULTILINGUAL-E5-SMALL (PRÉFIXES ACTIVÉS) ===")
    print("[1] Chargement modèle local...")
    model = SentenceTransformer(
        os.path.join(BASE_DIR, "models", "embeddings", "multilingual-e5-small"),
        device='cpu'
    )

    print("[2] Initialisation Chroma...")
    client = chromadb.PersistentClient(path=os.path.join(BASE_DIR, "rag", "chroma_db"))
    collection = client.get_or_create_collection('fondation_knowledge')

    filepaths = sys.argv[1:]
    if not filepaths:
        filepaths = sorted(glob.glob(os.path.join(BASE_DIR, "data", "raw_texts", "*.txt")))
        print(f"[3] Aucun argument — ingestion par défaut : {len(filepaths)} fichiers")

    total = 0
    for filepath in filepaths:
        print(f"\n=== INGESTION : {os.path.basename(filepath)} ===")
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()

        text = clean_text(text)
        chunks = chunk_text(text)
        if not chunks:
            print("   ⚠️ Aucun chunk — ignoré")
            continue

        texts_prefixed = [f"passage: {t}" for t in chunks]
        embeddings = model.encode(texts_prefixed).tolist()

        src_name = os.path.splitext(os.path.basename(filepath))[0]
        lic = LICENCES.get(src_name, "copyrighted")
        ids = [f"{src_name}_{i}" for i in range(len(chunks))]
        collection.upsert(
            documents=chunks,
            embeddings=embeddings,
            metadatas=[{"source": src_name, "license": lic} for _ in chunks],
            ids=ids
        )
        print(f"   ✅ {len(chunks)} chunks ingérés")
        total += len(chunks)

    print(f"\n✅ Ingestion terminée : {total} chunks traités, {collection.count()} en base.")

if __name__ == '__main__':
    main()
