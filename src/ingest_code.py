#!/usr/bin/env python3
"""
INGEST CODE - Ingestion de code source dans ChromaDB (collection fondation_code)
Usage: python3 ingest_code.py <fichier|dossier> [--title "Titre"] [--ext .py,.sh,.md]
Ingestion incrémentale : ne ré-ingère que les fichiers modifiés.
"""

import sys
import os
import re
import chromadb
from sentence_transformers import SentenceTransformer

# ============================================================================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_PATH = os.path.join(PROJECT_ROOT, "rag", "chroma_db")
COLLECTION_NAME = "fondation_code"
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
MAX_TOKENS_PER_CHUNK = 500
DEFAULT_EXTS = {'.md', '.txt', '.rst', '.org'}
CODE_EXTS = {'.py', '.sh', '.bash', '.yaml', '.yml', '.json', '.toml'}


def chunk_text(text, max_tokens=500):
    """Découpe par paragraphes."""
    chunks = []
    paragraphs = re.split(r'\n{2,}', text)
    current_chunk = []
    current_length = 0

    for para in paragraphs:
        if not para.strip():
            continue
        para_len = len(para) // 4

        if current_length + para_len > max_tokens and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [para]
            current_length = para_len
        else:
            current_chunk.append(para)
            current_length += para_len

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
    return chunks


def collect_files(path, extensions=None):
    """Collecte récursive de fichiers."""
    if extensions is None:
        extensions = DEFAULT_EXTS

    files = []
    if os.path.isfile(path):
        files.append(path)
    elif os.path.isdir(path):
        for root, dirs, filenames in os.walk(path):
            dirs[:] = [d for d in dirs if d not in
                      {'__pycache__', '.git', 'node_modules', '.venv', 'venv'}]
            for fname in sorted(filenames):
                ext = os.path.splitext(fname)[1].lower()
                if ext in extensions:
                    files.append(os.path.join(root, fname))
    return files


def get_stored_mtime(collection, filepath):
    """Récupère le mtime stocké en base pour un fichier, ou None."""
    try:
        results = collection.get(where={"filepath": filepath}, limit=1)
        if results['metadatas']:
            return results['metadatas'][0].get('mtime')
    except Exception:
        pass
    return None


def delete_file_chunks(collection, filepath):
    """Supprime tous les chunks d'un fichier donné."""
    try:
        collection.delete(where={"filepath": filepath})
    except Exception:
        pass


def ingest_file(filepath, collection, model, title=None):
    """Ingère un fichier dans ChromaDB (chunk par chunk pour éviter OOM)."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        if len(content) < 50:
            return 0

        if not title:
            title = os.path.basename(filepath)

        chunks = chunk_text(content)
        if not chunks:
            return 0

        mtime = os.path.getmtime(filepath)
        safe_name = re.sub(r'[^\w\-\.]', '_', title)[:50]
        ids = []
        metadatas = []
        documents = []
        embeddings = []

        for i, chunk_content in enumerate(chunks):
            if len(chunk_content) > 2000:
                chunk_content = chunk_content[:2000]

            ids.append(f"code_{safe_name}_{i}")
            metadatas.append({
                "source": title,
                "type": "tech_doc",
                "chunk_idx": i,
                "filepath": filepath,
                "mtime": mtime
            })
            documents.append(chunk_content)

            # Encodage chunk par chunk pour éviter OOM GPU
            embedding = model.encode([chunk_content])[0].tolist()
            embeddings.append(embedding)

        collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents
        )
        return len(chunks)

    except Exception as e:
        print(f"  ❌ {filepath}: {e}")
        return 0


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python3 {sys.argv[0]} <fichier|dossier> [--title \"Titre\"] [--ext .py,.txt,.md]")
        sys.exit(1)

    path = sys.argv[1]
    title = None
    ext_arg = None

    for i, arg in enumerate(sys.argv):
        if arg == '--title' and i + 1 < len(sys.argv):
            title = sys.argv[i + 1]
        elif arg == '--ext' and i + 1 < len(sys.argv):
            ext_arg = set('.' + e.strip().lstrip('.') for e in sys.argv[i + 1].split(','))

    extensions = ext_arg if ext_arg else DEFAULT_EXTS

    print("\n" + "=" * 60)
    print("📦 INGESTION CODE → ChromaDB (fondation_code)")
    print("=" * 60)
    print(f"Source : {path}")
    print(f"Extensions : {extensions}")
    print(f"ChromaDB : {CHROMA_PATH}")
    print("-" * 60)

    files = collect_files(path, extensions)
    if not files:
        print("❌ Aucun fichier trouvé.")
        sys.exit(1)

    print(f"📄 {len(files)} fichier(s) détecté(s).\n")

    print("[RAG] Connexion ChromaDB...")
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    try:
        collection = client.get_collection(COLLECTION_NAME)
    except Exception:
        print("[RAG] Collection inexistante, création...")
        print("[RAG] Chargement modèle embeddings...")
        emb_model = SentenceTransformer(EMBEDDING_MODEL)

        class E5EmbeddingFn:
            def __init__(self, model):
                self.model = model
            def __call__(self, input):
                if isinstance(input, str):
                    input = [input]
                prefixed = ["query: " + t for t in input]
                return self.model.encode(prefixed).tolist()

        collection = client.create_collection(
            COLLECTION_NAME,
            embedding_function=E5EmbeddingFn(emb_model)
        )
        print("[RAG] Collection créée.")

    print("[RAG] Chargement modèle embeddings...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    total_chunks = 0
    skipped = 0
    updated = 0

    for i, fpath in enumerate(files, 1):
        fname = os.path.basename(fpath)
        current_mtime = os.path.getmtime(fpath)
        stored_mtime = get_stored_mtime(collection, fpath)

        if stored_mtime is not None and abs(stored_mtime - current_mtime) < 1:
            print(f"  [{i}/{len(files)}] {fname} ⏭️ déjà à jour")
            skipped += 1
            continue

        if stored_mtime is not None:
            print(f"  [{i}/{len(files)}] {fname} 🔄 modifié, mise à jour...", end="", flush=True)
            delete_file_chunks(collection, fpath)
        else:
            print(f"  [{i}/{len(files)}] {fname}...", end="", flush=True)

        count = ingest_file(fpath, collection, model, title)
        if count > 0:
            print(f" ✅ {count} chunks")
            total_chunks += count
            if stored_mtime is not None:
                updated += 1
        else:
            print(" ⏭️ ignoré")

    print(f"\n{'=' * 60}")
    print(f"✅ Terminé ! {total_chunks} chunks ingérés.")
    print(f"🔄 {updated} fichier(s) mis à jour")
    print(f"⏭️ {skipped} fichier(s) déjà à jour (ignorés)")
    print(f"📊 Total collection '{COLLECTION_NAME}' : {collection.count()} chunks")
    print(f"{'=' * 60}\n")

    del model
    import gc
    gc.collect()


if __name__ == "__main__":
    main()
