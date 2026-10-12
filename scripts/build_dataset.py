#!/usr/bin/env python3
"""Assemble le dataset JSONL de fine-tuning depuis dataset/questions-types/q*.md
Usage: python scripts/build_dataset.py
Source de vérité : les fichiers .md (réponse signée + variantes).
Le script lit TOUS les fichiers q*.md — _provenance.md est exclu par le glob."""
import json, pathlib, sys

BASE = pathlib.Path(__file__).resolve().parent.parent
QT_DIR = BASE / "dataset" / "questions-types"
SYSTEM_PROMPT_FILE = BASE / "prompts" / "politique.txt"
OUT = BASE / "dataset" / "fondation_v0.jsonl"

# Contexte RAG simulé : injecté dans le message user.
# v0 = placeholder. Étape suivante : inject_rag_chunks.py remplace par de vrais chunks.
RAG_PLACEHOLDER = (
    "[CONTEXTE SOURCES]\n"
    "(chunks RAG à injecter par script — voir TODO injection Chroma)\n\n"
)


def parse_variants(raw, fname):
    """Lit la section '## Variantes' d'un fichier md signé.
    Ignore les lignes d'instruction entre parenthèses (*à générer*...)."""
    try:
        block = raw.split("## Variantes", 1)[1]
    except IndexError:
        sys.exit(f"[ERREUR] section '## Variantes' manquante dans {fname}")
    out = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("- ") or line.startswith("- *("):
            continue
        v = line[2:].strip().strip('"«» ')
        if v:
            out.append(v)
    if not out:
        sys.exit(f"[ERREUR] aucune variante lue dans {fname} — section vide ?")
    return out


def main():
    system = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")

    files = sorted(QT_DIR.glob("q*.md"))
    if not files:
        sys.exit(f"[ERREUR] aucun fichier q*.md dans {QT_DIR}")

    examples = []
    for path in files:
        fname = path.name
        raw = path.read_text(encoding="utf-8")

        # Réponse idéale : entre '## Réponse idéale' et '## Variantes'
        try:
            answer = (
                raw.split("## Réponse idéale", 1)[1]
                .split("## Variantes", 1)[0]
                .strip()
            )
        except IndexError:
            sys.exit(
                f"[ERREUR] structure inattendue dans {fname} "
                "(attend: '## Réponse idéale' puis '## Variantes')"
            )

        variants = parse_variants(raw, fname)

        # La question cœur : ligne '**Question cœur :**' si présente,
        # sinon première variante de la liste.
        core = None
        for line in raw.splitlines():
            if "Question cœur" in line and ":" in line:
                core = line.split(":", 1)[1].strip().strip('"«» ')
                break

        questions = ([core] if core else []) + [v for v in variants if v != core]

        for q in questions:
            examples.append({
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": RAG_PLACEHOLDER + q},
                    {"role": "assistant", "content": answer},
                ]
            })
        print(f"[OK] {fname}: {len(questions)} questions (dont cœur: {core is not None})")

    # Garde-fou : on n'envoie pas un run 1 bis au fine-tuning
    MIN_EXAMPLES = 100
    if len(examples) < MIN_EXAMPLES:
        sys.exit(
            f"[ERREUR] seulement {len(examples)} exemples (< {MIN_EXAMPLES}) — "
            "compléter les variantes avant de lancer le run 2"
        )

    with open(OUT, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\n[DONE] {len(examples)} exemples → {OUT}")
    print(f"      {len(files)} fichiers, seuil minimum {MIN_EXAMPLES} respecté")


if __name__ == "__main__":
    main()
