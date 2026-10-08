#!/usr/bin/env python3
"""Parse les pages GitBook de Caliban -> corps et notes separes.
Sources: data/raw_texts/gitbook_caliban/*.html (anarchivists, 2016)
Sorties: federici-caliban-corps.txt + federici-caliban-notes.txt
La bibliographie (bibliography.html) reste archivee, non assemblee."""

import re, html
from pathlib import Path

SRC = Path('data/raw_texts/gitbook_caliban')
PAGES = ['prefacemd', 'introduction', 'jolt', 'accumulation',
         'the_great_caliban', 'the_great_witch-hunt_in_europe',
         'colonization_and_christianization']

NOTE_RE     = re.compile(r'<blockquote id="fn_(\d+)">(.*?)</blockquote>', re.S)
REF_RE      = re.compile(r'<sup>\s*<a[^>]*href="#fn_\d+"[^>]*>\s*\d+\s*</a>\s*</sup>')
NOTENUM_RE  = re.compile(r'^\s*<sup>\s*(?:<a[^>]*>)?\s*\d+\s*(?:</a>)?\s*</sup>\s*\.?\s*')
BACKLINK_RE = re.compile(r'<a[^>]*href="#reffn_\d+"[^>]*>.*?</a>\s*$', re.S)
BLOCK_CLOSE = re.compile(r'</(?:p|h[1-6]|li|blockquote|div|tr)>', re.I)
TAG_RE      = re.compile(r'<[^>]+>')

def textify(t):
    t = BLOCK_CLOSE.sub('\n\n', t)
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.I)
    t = TAG_RE.sub('', t)
    t = html.unescape(t)
    lines = [re.sub(r' +', ' ', ln).strip() for ln in t.split('\n')]
    paras = [ln for ln in lines if ln]
    return '\n\n'.join(paras)

corps_parts, notes_parts = [], []
for page in PAGES:
    raw = (SRC / f'{page}.html').read_text(encoding='utf-8')
    assert raw.count('markdown-section') >= 1, f'{page}: pas de markdown-section'
    sec_start = raw.find('<section class="normal markdown-section">')
    assert sec_start >= 0, f'{page}: balise section introuvable'
    sec_end = raw.find('</section>', sec_start)
    sec = raw[sec_start:sec_end]

    notes, n_expected = [], len(re.findall(r'id="fn_\d+"', sec))
    for num, bloc in NOTE_RE.findall(sec):
        bloc = NOTENUM_RE.sub('', bloc.strip())
        bloc = BACKLINK_RE.sub('', bloc.strip())
        notes.append(f'[{page} fn {num}] {textify(bloc)}')
    assert len(notes) == n_expected, f'{page}: {len(notes)} notes / {n_expected} ancres'
    sec = NOTE_RE.sub(' ', sec)          # retire les notes du corps
    sec = REF_RE.sub('', sec)            # retire les appels numerotes
    corps_parts.append(textify(sec))
    notes_parts.extend(notes)
    print(f'{page}: {len(notes)} notes, corps {len(corps_parts[-1])} chars')

corps = '\n\n\n'.join(corps_parts)       # separation nette entre chapitres
notes = '\n\n'.join(notes_parts)
Path('data/raw_texts/federici-caliban-corps.txt').write_text(corps, encoding='utf-8')
Path('data/raw_texts/federici-caliban-notes.txt').write_text(notes, encoding='utf-8')

# --- verification ---
for nom, t in [('CORPS', corps), ('NOTES', notes)]:
    print(f'{nom}: {len(t)} chars | ratio espaces {round(t.count(" ")/len(t),3)}'
          f' | residus HTML: {len(re.findall(chr(60)+r"[a-zA-Z/!?]", t))}'
          f' | \u21a9: {t.count(chr(0x21A9))}')
print('--- tete du corps ---')
print(corps[:300])
print('--- premiere note ---')
print(notes[:300])
