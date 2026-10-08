#!/usr/bin/env python3
"""Nettoyage one-shot : bell hooks, Feminism Is for Everybody.
Bornes: corps = lignes 96..3846 (INTRODUCTION -> avant INDEX).
Retire: en-tetes de page (lignes CAPS + numero), numeros de page orphelins,
\x0c, pub/imprimeur. Recolle les cesures de fin de ligne. Fix OCR ponctuels."""

import re

SRC = 'data/raw_texts/bell-hooks-feminism-is-for-everybody.txt'
OUT = 'data/raw_texts/bell-hooks-feminism-clean.txt'

lines = open(SRC, encoding='utf-8').read().split('\n')
corps = lines[96:3847]          # bornes validees par reconnaissance

kept, dropped = [], 0
for ln in corps:
    l = ln.replace('\x0c', '').rstrip()
    s = l.strip()
    if not s:
        kept.append('')
        continue
    # en-tete de page: ligne courte quasi-tout-caps avec numero romain/arabe colle
    if len(s) < 50 and re.fullmatch(
            r'[IVXLC\d\.]*\s*[A-Z][A-Z\-\' :!?,]+\s*[\dIVXLC\-]*', s) \
       and s.upper() == s:
        dropped += 1
        continue
    # numero de page orphelin
    if re.fullmatch(r'\d{1,3}', s):
        dropped += 1
        continue
    kept.append(l)

t = '\n'.join(kept)

# cesures: mot coupe en fin de ligne -> recoller (compter + lister pour relecture)
joins = []
def recolle(m):
    left, right = m.group(1), m.group(2)
    joins.append(left + '-' + right)
    return left + right
t = re.sub(r'(\w+)-\s*\n\s*(\w+)', recolle, t)

# fixes OCR ponctuels valides
for a, b in [('Oots of folks', 'Lots of folks'),
             ('Se!f-', 'Self-'), ('wrongminded', 'wrong-minded')]:
    t = t.replace(a, b)

t = re.sub(r'\n{3,}', '\n\n', t)
open(OUT, 'w', encoding='utf-8').write(t)

print(f'lignes gardees: {len(kept)} | en-tetes/pages droppes: {dropped}')
print(f'cesures recollees: {len(joins)} | caracteres: {len(t)}')
print('ratio espaces:', round(t.count(' ')/max(len(t),1), 3))
print('echantillon des 15 premiers recollages:')
for j in joins[:15]: print('  ', repr(j))
