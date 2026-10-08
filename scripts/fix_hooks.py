#!/usr/bin/env python3
"""Patch des residus dans bell-hooks-feminism-clean.txt (headers, césures, OCR)."""

import re

SRC = 'data/raw_texts/bell-hooks-feminism-clean.txt'
OUT = 'data/raw_texts/bell-hooks-feminism-clean-fixed.txt'

t = open(SRC, encoding='utf-8').read()

# 1) Headers survivants (lignes CAPS + nombre, isolées)
lines = t.split('\n')
kept = []
for ln in lines:
    s = ln.strip()
    # Skip headers survivants (majuscules dominantes avec numerotation)
    if len(s) > 4 and s.upper() == s and re.search(r'[0-9IVXL]', s):
        continue
    kept.append(ln)
t = '\n'.join(kept)

# 2) Fix espaces après césure mal jointes (natureand -> nature and)
t = re.sub(r'([a-z])([A-Z])', r'\1 \2', t)

# 3) Chiffres collés en fin de mot (ex: everybody.0)
t = re.sub(r'([a-z]\.)\s*(\d+)(?=\s|$)', r'\1', t)
t = re.sub(r'(\w+)(\d{1,2})\s*$', r'\1', t, flags=re.MULTILINE)

# 4) Fixes OCR ponctuels
for a, b in [('Oots', 'Lots'), ('Se!f-', 'Self-'), ('wrongminded', 'wrong-minded'), ('constandy', 'constantly'), ('natureand', 'nature and')]:
    t = t.replace(a, b)

# Normalisation finale
t = re.sub(r'\n{3,}', '\n\n', t)
t = re.sub(r' +', ' ', t)
open(OUT, 'w', encoding='utf-8').write(t)

print('Verification:')
print(f'  ratio espaces: {round(t.count(" ")/len(t),3)}')
print(f'  residus CAPS+numero: {sum(1 for l in t.split("\\n") if l.strip().isupper() and re.search(r"[0-9]", l))}')
print('  debut:', t[:80])
print('  fin:', t[-120:])
