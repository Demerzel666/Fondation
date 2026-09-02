#!/usr/bin/env python3
"""
MIA TO RAG v3 - Ingestion depuis Marxists Internet Archive, Anarchist Library ou fichiers locaux
Supporte les index multi-chapitres, les pages seules, et les fichiers .txt locaux.
Usage: python3 mia_to_rag.py <URL_ou_FICHIER> [--title "Titre Optionnel"]
"""

import sys
import os
import re
import warnings
import requests
from pathlib import Path
from urllib.parse import urljoin

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import chromadb
from sentence_transformers import SentenceTransformer

# ============================================================================
# CONFIGURATION
# ============================================================================
SOURCE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw_texts")
CHROMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rag", "chroma_db")
COLLECTION_NAME = "fondation_knowledge"
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
MAX_TOKENS_PER_CHUNK = 750

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})


class E5EmbeddingFunction:
    """Wrapper ChromaDB pour multilingual-e5-large."""
    def __init__(self):
        print(f"[RAG] Chargement embeddings: {EMBEDDING_MODEL}")
        self.model = SentenceTransformer(EMBEDDING_MODEL, device='cpu')

    def __call__(self, input):
        if isinstance(input, str):
            input = [input]
        prefixed = ["query: " + t for t in input]
        embeddings = self.model.encode(prefixed)
        return embeddings.tolist()


def clean_html(html):
    """Nettoyage HTML robuste sans dépendance externe."""
    text = html

    for tag in ['script', 'style', 'nav', 'header', 'footer', 'aside']:
        text = re.sub(rf'<{tag}[^>]*>.*?</{tag}>', '', text, flags=re.DOTALL | re.IGNORECASE)

    text = re.sub(r'<br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)

    for entity, char in [('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'),
                         ('&quot;', '"'), ('&#39;', "'"), ('&nbsp;', ' '), ('&mdash;', '—')]:
        text = text.replace(entity, char)

    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'^[ \t]+', '', text, flags=re.MULTILINE)
    text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)

    text = re.sub(r'\[\s*(Next|Previous|Top|Contents|Back)\s*\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Marxists Internet Archive', '', text, flags=re.IGNORECASE)
    text = re.sub(r'The Anarchist Library', '', text, flags=re.IGNORECASE)

    return text.strip()


def extract_chapter_links(html, base_url):
    """Détecte les liens de chapitres dans une page d'index MIA ou AL."""
    parent_dir = base_url.rsplit('/', 1)[0] + '/'

    links = re.findall(r'href=["\']([^"\']+\.htm[l]?)["\']', html, re.IGNORECASE)
    chapter_urls = []
    seen = set()

    for link in links:
        if 'index.htm' in link.lower():
            continue
        full_url = urljoin(base_url, link)
        if full_url.startswith(parent_dir) and full_url not in seen:
            chapter_urls.append(full_url)
            seen.add(full_url)

    return chapter_urls


def fetch_page(url):
    """Télécharge une page web ou lit un fichier local."""
    # Fichier local
    if os.path.exists(url) and os.path.isfile(url):
        try:
            with open(url, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            print(f"   📄 Fichier local lu: {len(content)} chars")
            return content
        except Exception as e:
            print(f"   ⚠️ Erreur lecture fichier: {e}")
            return None

    # URL distante
    try:
        resp = SESSION.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"   ⚠️ Erreur fetch {url}: {e}")
        return None


def chunk_text(text, max_tokens=750):
    """Découpage intelligent par paragraphes avec fallback character-based."""
    CHUNK_CHARS = max_tokens * 4  # Estimation: 1 token ≈ 4 chars

    chunks = []
    paragraphs = re.split(r'\n{2,}', text)

    # Si on a assez de paragraphes (>10), découpage normal
    if len(paragraphs) > 10:
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

    else:
        # Fallback: pas assez de paragraphes → découpage forcé par caractères
        print(f"   ⚠️ Peu de paragraphes ({len(paragraphs)}), découpage forcé...")
        pos = 0
        chunk_num = 1
        while pos < len(text):
            end_pos = min(pos + CHUNK_CHARS, len(text))

            # Couper entre mots
            if end_pos < len(text):
                space_pos = text.rfind(' ', pos, end_pos)
                if space_pos > pos + CHUNK_CHARS * 0.5:
                    end_pos = space_pos

            chunk = text[pos:end_pos].strip()
            if chunk:
                chunks.append(chunk)

            pos = end_pos

    print(f"   → {len(chunks)} chunks générés.")
    return chunks


def infer_title_from_url(url):
    path = url.split('/')[-2] if '/' in url else url.split('/')[-1]
    return re.sub(r'[^\w\s-]', '', path.replace('-', ' ').replace('_', ' ').title())


def main():
    if len(sys.argv) < 2:
        print("❌ Erreur: URL ou fichier requis.")
        print(f"Usage: python3 {sys.argv[0]} <URL_ou_FICHIER> [--title \"Titre\"]")
        sys.exit(1)

    url = sys.argv[1]
    title = None

    for i, arg in enumerate(sys.argv):
        if arg == '--title' and i + 1 < len(sys.argv):
            title = sys.argv[i + 1]

    print("\n" + "=" * 70)
    print("🔄 MIA TO RAG v3 - INGESTION AUTOMATIQUE")
    print("=" * 70)
    print(f"📡 Source: {url}")
    print("-" * 70)

    # 1. Télécharger ou lire
    print("⬇️  Téléchargement / lecture...")
    html = fetch_page(url)
    if not html:
        print("❌ Impossible de récupérer le contenu. Abandon.")
        sys.exit(1)

    # 2. Vérifier index multi-chapitres (seulement pour URLs)
    is_local_file = os.path.exists(url) and os.path.isfile(url)
    chapter_links = [] if is_local_file else extract_chapter_links(html, url)

    all_texts = []

    if chapter_links and len(chapter_links) >= 2:
        print(f"📖 Index détecté: {len(chapter_links)} chapitres trouvés.")
        print(f"🕷️  Crawling des chapitres...\n")

        for i, chap_url in enumerate(chapter_links, 1):
            print(f"   [{i}/{len(chapter_links)}] {chap_url.split('/')[-1]}...", end="", flush=True)
            chap_html = fetch_page(chap_url)
            if chap_html:
                chap_text = clean_html(chap_html)
                if len(chap_text) > 200:
                    all_texts.append(chap_text)
                    print(f" ✅ ({len(chap_text)} chars)")
                else:
                    print(f" ⚠️ Trop court, ignoré")
            else:
                print(f" ❌ Échec")
    else:
        print("📄 Document unique détecté.")
        text = html if is_local_file else clean_html(html)
        if len(text) > 200:
            all_texts.append(text)
            print(f"   ✅ Texte extrait: {len(text)} caractères.")
        else:
            print(f"   ❌ Texte trop court ({len(text)} chars). Abandon.")
            sys.exit(1)

    if not all_texts:
        print("\n❌ Aucun texte exploitable trouvé. Abandon.")
        sys.exit(1)

    # 3. Combiner
    full_text = "\n\n---\n\n".join(all_texts)
    print(f"\n📝 Texte total combiné: {len(full_text)} caractères ({len(all_texts)} page(s))")

    # 4. Titre
    if not title:
        if not is_local_file and ("/archive/" in url or "/library/" in url):
            author_match = re.search(r'/archive/([^/]+)/', url) or re.search(r'/library/([^/-]+)', url)
            path_parts = url.split('/')
            work_name = [p for p in path_parts if p and p not in ('archive', 'francais', 'works', 'library')]
            if author_match:
                author = author_match.group(1).title()
                work = work_name[-1].replace('-', ' ').replace('.htm', '').replace('.html', '').title() if work_name else "Unknown"
                title = f"{author} - {work}"
            else:
                title = infer_title_from_url(url)
        else:
            title = infer_title_from_url(url)

    # 5. Sauvegarde locale
    os.makedirs(SOURCE_DIR, exist_ok=True)
    safe_name = re.sub(r'[^\w\-\.]', '_', title.replace(' ', '_'))[:50]
    filepath = os.path.join(SOURCE_DIR, f"{safe_name}.txt")
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_text)
        print(f"💾 Sauvegardé: {filepath}")
    except Exception as e:
        print(f"⚠️ Warning: impossible de sauvegarder localement: {e}")

    # 6. Ingestion ChromaDB
    print("🧠 Ingestion dans ChromaDB...")
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)

        # Récupérer ou créer la collection
        try:
            collection = client.get_collection(COLLECTION_NAME)
        except Exception:
            print(f"   ℹ️  Création nouvelle collection: {COLLECTION_NAME}")
            collection = client.create_collection(
                COLLECTION_NAME,
                embedding_function=E5EmbeddingFunction()
            )

        chunks = chunk_text(full_text, max_tokens=MAX_TOKENS_PER_CHUNK)

        print("   → Génération des embeddings...")
        model = SentenceTransformer(EMBEDDING_MODEL)
        embeddings = model.encode([c[:2000] for c in chunks], show_progress_bar=True).tolist()
        print("   → Embeddings terminés.")

        ids = [f"mia_{safe_name}_{i}" for i in range(len(chunks))]
        metadatas = [{"source": title, "type": "mia_auto", "chunk_idx": i} for i in range(len(chunks))]

        batch_size = 50
        total_batches = (len(chunks) // batch_size) + 1
        for i in range(0, len(chunks), batch_size):
            batch_num = i // batch_size + 1
            print(f"   → Batch {batch_num}/{total_batches}...", end="", flush=True)
            batch_ids = ids[i:i + batch_size]
            batch_embs = embeddings[i:i + batch_size]
            batch_docs = chunks[i:i + batch_size]
            batch_metas = metadatas[i:i + batch_size]
            collection.add(ids=batch_ids, embeddings=batch_embs, metadatas=batch_metas, documents=batch_docs)
            print(" ✅")

        del model
        del embeddings
        import gc
        gc.collect()

        print(f"   ✅ Ingestion réussie ! {len(chunks)} nouveaux chunks.")
        print(f"   📊 Total base: {collection.count()} chunks.")

    except Exception as e:
        print(f"   ❌ Échec ingestion: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 70)
    print("✅ TERMINÉ !")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
