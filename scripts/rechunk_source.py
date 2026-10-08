#!/usr/bin/env python3
"""
Re-chunkage : frontières de phrases, overlap en phrases, strip des
en-têtes de page, tagging these|narratif.

Usage :
  python scripts/rechunk_source.py <fichier.txt> <nom_source> [ligne_début] [ligne_fin]

Exemple Fanon :
  python scripts/rechunk_source.py data/raw_texts/Rags_clean/Fanon_Damnes_de_la_Terre.txt \
      Fanon_Damnes_de_la_Terre 1240 10710

[ligne_début]/[ligne_fin] = portion du fichier à traiter (1-indexée, inclusive)
— sert à exclure l'appareil éditorial (préfaces, notices, postfaces).
"""
import sys, re, json
from collections import Counter

# ── Arguments ─────────────────────────────────────────────────
INPUT_FILE = sys.argv[1]
SOURCE_NAME = sys.argv[2]
START_LINE = int(sys.argv[3]) if len(sys.argv) > 3 else 1
END_LINE   = int(sys.argv[4]) if len(sys.argv) > 4 else 10**9

# ── Chargement de la portion ───────────────────────────────────
with open(INPUT_FILE, 'r', encoding='utf-8') as f:
    lignes = f.readlines()
portion = lignes[START_LINE - 1:END_LINE]
print(f"[1] Portion : lignes {START_LINE} à {min(END_LINE, len(lignes))} ({len(portion)} lignes)")

# ── Strip des en-têtes de page (running headers) ──────────────
pat_header = re.compile(r'^\s*(.{3,60}?)\s{3,}\d{1,3}\s*$')
compteur = Counter()
for l in portion:
    m = pat_header.match(l)
    if m:
        compteur[m.group(1).strip()] += 1
titres_headers = {t for t, n in compteur.items() if n >= 4}
portion = [l for l in portion
           if not (pat_header.match(l)
                   and pat_header.match(l).group(1).strip() in titres_headers)]
print(f"[2] {len(titres_headers)} en-têtes de page strippés : "
      f"{sorted(titres_headers)[:5]}{'...' if len(titres_headers) > 5 else ''}")

# ── Nettoyage typographique ────────────────────────────────────
texte = ''.join(portion)
texte = texte.replace("\u00ad\n", "")            # soft-hyphen + fin de ligne = mot coupé
texte = texte.replace('\u00ad', '')              # soft-hyphens (« natio­nale »)
texte = texte.replace('-\n', '')                 # césures en fin de ligne
texte = texte.replace('\u00a0', ' ')             # espaces insécables
texte = re.sub(r'[ \t]+\n', '\n', texte)         # espaces traînants
texte = re.sub(r'\n{3,}', '\n\n', texte)          # vides multiples

# ── Segmentation par phrases ───────────────────────────────────
phrases = re.split(r'(?<=[.!?…])\s+(?=[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜŒÇ«"])', texte)
phrases = [p.strip() for p in phrases if len(p.strip()) > 20]
print(f"[3] {len(phrases)} phrases extraites")

# ── Tagging thèse vs récit (heuristique relative) ──────────────
def et_type(t):
    tl = t.lower().replace('\u2019', "'")         # apostrophe typographique
    marqueurs_these = [
        "il faut", "il ne faut", "nous devons", "la vérité",
        "n'est pas", "ne peut", "doit être", "au contraire",
        "en réalité", "c'est pourquoi", "la colonisation",
        "le colonialisme", "le nationalisme", "la violence",
        "we must", "is not", "cannot", "must be", "rather",
        "in reality", "in fact", "requires", "means that",
    ]
    marqueurs_recit = [
        "il est né", "il meurt", "il a été", "en 19", "cette année",
        "selon", "son livre", "la publication", "revue", "journal",
        "la préface", "l'édition", "l'auteur", "écrit en", "paraît",
        "was published", "according to", "was born", "the author",
        "in 19", "written in", "his book",
    ]
    st = sum(1 for m in marqueurs_these if m in tl)
    sn = sum(1 for m in marqueurs_recit if m in tl)
    return "these" if st > sn else "narratif"

# ── Chunking : phrases entières, ~1400 chars, overlap 2 phrases ─
MAX_CHARS, OVERLAP_PHRASES = 1400, 2
chunks, buf, buf_len = [], [], 0

def flush(buf):
    txt = ' '.join(buf).replace('\n', ' ').strip()
    txt = re.sub(r'\s{2,}', ' ', txt)
    if len(txt) > 100:
        return {"text": txt, "type": et_type(txt), "source": SOURCE_NAME}
    return None

for p in phrases:
    if buf_len + len(p) > MAX_CHARS and buf:
        c = flush(buf)
        if c:
            chunks.append(c)
        buf = buf[-OVERLAP_PHRASES:]
        buf_len = sum(len(x) for x in buf)
    buf.append(p)
    buf_len += len(p)

if buf:
    c = flush(buf)
    if c:
        chunks.append(c)

for i, c in enumerate(chunks):
    c["id"] = f"{SOURCE_NAME}_rc{i}"             # suffixe _rc : pas de collision avec l'ancien

# ── Statistiques et previews ──────────────────────────────────
types = Counter(c['type'] for c in chunks)
tailles = sorted(len(c['text']) for c in chunks)
print(f"[4] {len(chunks)} chunks | these: {types['these']} | narratif: {types['narratif']}")
print(f"    Taille médiane : {tailles[len(tailles)//2]} chars")

for t in ("these", "narratif"):
    print(f"\n--- SAMPLE '{t}' ---")
    echant = [x for x in chunks if x['type'] == t][:4]
    for c in echant:
        print(f"[{c['id']}] {c['text'][:180]}...\n")

# ── Export JSON (validation manuelle AVANT ingestion) ─────────
out_path = f"data/rechunk_{SOURCE_NAME}.json"
with open(out_path, "w", encoding='utf-8') as f:
    json.dump(chunks, f, indent=2, ensure_ascii=False)
print(f"✅ {out_path} — à RELIRE avant ingestion (jamais d'ingestion aveugle)")
