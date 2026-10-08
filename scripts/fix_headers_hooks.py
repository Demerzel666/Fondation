#!/usr/bin/env python3
"""Patch hooks : retire headers incrustes et recoud les mots fendus."""
import re

SRC = 'data/raw_texts/bell-hooks-feminism-clean-fixed.txt'
OUT = SRC

t = open(SRC, encoding='utf-8').read()

# Pattern: sequence CAPS longue avec numero
hdr_pattern = r'[A-Z][A-Z ]{12,}\d+(?: \\ \\d+\\)?'

# Liste toutes les occurrences uniques
headers = sorted(set(re.findall(hdr_pattern, t)))
print('headers trouves:', len(headers))
for h in headers: print(' ', repr(h))

# Pour chaque header, retirer et voir ce que ça produit
n_residus = len(re.findall(hdr_pattern, t))
for hdr in headers:
    # Enlever le header et les espaces superflus autour
    t = re.sub(r'\s*' + re.escape(hdr) + r'\s*', ' ', t)
    
# Normaliser les doubles espaces
t = re.sub(r' +', ' ', t)
t = re.sub(r'\n{3,}', '\n\n', t)

open(OUT, 'w', encoding='utf-8').write(t)
print('apres retrait:', len(re.findall(hdr_pattern, t)), 'residus')
print('taille:', len(t))
