#!/usr/bin/env python3
"""Assemble le dataset JSONL de fine-tuning depuis dataset/questions-types/*.md
Usage: python scripts/build_dataset.py
Source de vérité : les fichiers .md. Ce script ne fait que les lire."""
import json, pathlib, sys

BASE = pathlib.Path(__file__).resolve().parent.parent
QT_DIR = BASE / "dataset" / "questions-types"
SYSTEM_PROMPT_FILE = BASE / "prompts" / "politique.txt"
OUT = BASE / "dataset" / "fondation_v0.jsonl"

# Variants de formulation par fichier md (noms de fichiers exacts)
VARIANTS = {
    "q01-etat.md": [
        "que penses-tu de l'État ?",
        "l'État est-il réformable ?",
        "pourquoi es-tu contre l'État ?",
        "peut-on changer l'État de l'intérieur ?",
        "que reproches-tu au gouvernement ?",
        "l'État est-il nécessaire ?",
    ],
    "q03-amour.md": [
        "comment concevoir l'amour comme pratique politique ?",
        "l'amour est-il politique ?",
        "que penser de la famille nucléaire ?",
        "l'amour peut-il être une méthode révolutionnaire ?",
        "pourquoi parler d'amour dans un contexte militant ?",
        "quel lien entre l'amour et la révolution ?",
    ],
    "q09-religion-appareils.md": [
        "la religion est-elle compatible avec l'émancipation ?",
        "la religion est-elle un obstacle à la révolution ?",
        "que penses-tu des religions abrahamiques ?",
        "foi et émancipation sont-elles compatibles ?",
        "pourquoi critiquer la religion et pas la spiritualité ?",
    ],
}

# Contexte RAG simulé : injecté dans le message user.
# v0 = placeholder. Étape suivante : script qui requête Chroma pour de vrais chunks.
RAG_PLACEHOLDER = (
    "[CONTEXTE SOURCES]\n"
    "(chunks RAG à injecter par script — voir TODO injection Chroma)\n\n"
)

def main():
    system = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    examples = []
    for fname, variants in VARIANTS.items():
        path = QT_DIR / fname
        if not path.exists():
            sys.exit(f"[ERREUR] fichier manquant : {path}")
        raw = path.read_text(encoding="utf-8")
        try:
            answer = raw.split("## Réponse idéale", 1)[1].split("## Variantes", 1)[0].strip()
        except IndexError:
            sys.exit(f"[ERREUR] structure inattendue dans {fname} "
                     "(attend: '## Réponse idéale' puis '## Variantes')")
        for q in variants:
            examples.append({
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": RAG_PLACEHOLDER + q},
                    {"role": "assistant", "content": answer},
                ]
            })
    with OUT.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"OK : {len(examples)} exemples écrits dans {OUT}")
    print(f"    Réponses distinctes : {len(VARIANTS)} | "
          f"variantes : {[len(v) for v in VARIANTS.values()]}")

if __name__ == "__main__":
    main()
