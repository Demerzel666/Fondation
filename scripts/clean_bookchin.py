#!/usr/bin/env python3
"""Nettoyage one-shot : Bookchin Philosophy of Social Ecology (TAL / AK Press 2022, 3e éd. 1996).
Règles : coupe avant START (préface éditeur) et après END (afterword McGowan),
vire les numéros de page orphelins, vire les paragraphes-footnote bibliographiques,
recolle les mots coupés aux frontières de page.
Log complet des jointures et suppressions pour relecture humaine."""

import re

SRC   = 'data/raw_texts/bookchin-philosophy-of-social-ecology.txt'
OUT   = 'data/raw_texts/bookchin-philosophy-clean.txt'
START = 138   # première ligne du texte Bookchin (« Introduction: A Philosophical Naturalism »)
END   = 3762  # dernière ligne de Bookchin (« —February 15, 1994 » inclus, avant l'afterword)

pagenum = re.compile(r'^\d{1,3}$')
biblio  = re.compile(r'(University Press|Humanities Press|Free Press|AK Press|'
                     r'trans\.|vol\. \d|\bpp?\.? ?\d|[,(] ?(19|20)\d\d\)?|\(New$)')
word_end   = re.compile(r'[a-z](\d{1,2})?$')   # tolère un numéro de note collé
word_start = re.compile(r'^(\d{1,2})?[a-z]')

raw = open(SRC, encoding='utf-8').read().split('\n')
raw = raw[START-1:END]

# 1) numéros de page seuls sur leur ligne
dropped_pages = sum(1 for l in raw if pagenum.match(l.strip()))
kept = [l for l in raw if not pagenum.match(l.strip())]

# 2) paragraphes séparés par lignes vides
paras = [p.strip() for p in '\n'.join(kept).split('\n\n') if p.strip()]

# 3) paragraphes-footnote (signature bibliographique + paragraphe court)
def is_footnote(p):
    return bool(biblio.search(p)) and len(p) < 400
notes, body = [], []
for p in paras:
    (notes if is_footnote(p) else body).append(p)

# 4) recollement des mots coupés aux frontières de page
joined = []
joins = []
for p in body:
    if joined and word_end.search(joined[-1]) and word_start.match(p):
        a = re.sub(r'(?<=[a-z])\d{1,2}$', '', joined[-1])   # marqueur de note collé
        b = re.sub(r'^\d{1,2}(?=[a-z])', '', p)
        joins.append(f'  « ...{a[-30:]}» + «{b[:30]}... »')
        joined[-1] = a + ' ' + b
    else:
        joined.append(p)

open(OUT, 'w', encoding='utf-8').write('\n\n'.join(joined) + '\n')
print(f'numéros de page supprimés : {dropped_pages}')
print(f'footnotes supprimées      : {len(notes)}')
for n in notes: print(f'  [NOTE] {n[:70]}...')
print(f'jointures effectuées      : {len(joins)}')
for j in joins: print(j)
print(f'{len(joined)} paragraphes écrits dans {OUT}')
