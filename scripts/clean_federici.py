#!/usr/bin/env python3
"""Nettoyage v2 : Caliban and the Witch.
Coupe TOC/Acknowledgments/colophon (démarre à la préface de Federici),
converte les wraps de ligne en espaces (sans coller les mots !),
préserve les paragraphes, corrige DaUa -> Dalla."""

import re

SRC = 'data/raw_texts/federici-caliban-extracted.txt'
OUT = 'data/raw_texts/federici-caliban-clean.txt'

t = open(SRC, encoding='utf-8').read()

# 1) Départ : la vraie préface de Federici
anchor = 'Caliban and the Witch presents the main themes'
idx = t.find(anchor)
assert idx > 0, 'ancre de préface introuvable'
t = t[idx - len('Preface'):]

# 2) Paragraphes préservés : les blocs séparés par lignes vides restent,
#    les wraps internes deviennent des espaces (JAMAIS de collage)
paras = []
for p in t.split('\n\n'):
    p = re.sub(r'\s*\n\s*', ' ', p.strip())   # newline -> espace
    p = re.sub(r' +', ' ', p)
    if p:
        paras.append(p)

t = '\n\n'.join(paras)

# 3) Corrections ciblées
t = t.replace('DaUa', 'Dalla')

open(OUT, 'w', encoding='utf-8').write(t)
print(f'{len(paras)} paragraphes, {len(t)} chars -> {OUT}')
