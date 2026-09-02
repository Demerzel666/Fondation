#!/usr/bin/env python3
"""
GEN_INDEX - Génère un index compact du projet pour le contexte du modèle.
Output: data/project_index.txt
Usage: python3 gen_index.py [dossier_racine]
"""

import sys
import os
import ast
import re

# ============================================================================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_OUTPUT = os.path.join(PROJECT_ROOT, "data", "project_index.txt")
SKIP_DIRS = {'__pycache__', '.git', 'node_modules', '.venv', 'venv',
             'backups_archive', 'audits', 'rag', 'data'}
CODE_EXTS = {'.py', '.sh', '.bash', '.cpp', '.h', '.hpp', '.yaml', '.yml',
             '.json', '.toml', '.md', '.txt', '.rst'}
MAX_FILE_SIZE = 500000  # 500Ko max par fichier analysé


def index_python(filepath, lines):
    """Extraction AST pour Python : imports, classes, fonctions."""
    try:
        tree = ast.parse('\n'.join(lines))
    except SyntaxError:
        return f"  (parse error)"

    result = []

    for node in ast.iter_child_nodes(tree):
        # Imports
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                names = ', '.join(a.name for a in node.names)
            else:
                names = ', '.join(a.name for a in node.names)
                if node.module:
                    names = f"{node.module}.{names}"
            result.append(f"  import {names}")

        # Classes
        elif isinstance(node, ast.ClassDef):
            bases = ''
            if node.bases:
                bases = '(' + ', '.join(
                    ast.dump(b) if hasattr(ast, 'dump') else str(getattr(b, 'id', '?'))
                    for b in node.bases
                ) + ')'
            result.append(f"  class {node.name}{bases} (line {node.lineno})")
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = ', '.join(a.arg for a in item.args.args)
                    result.append(f"    └─ {item.name}({args}) (line {item.lineno})")

        # Fonctions
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = ', '.join(a.arg for a in node.args.args)
            prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            result.append(f"  {prefix}def {node.name}({args}) (line {node.lineno})")

    return '\n'.join(result) if result else "  (vide)"


def index_cpp(filepath, lines):
    """Extraction regex pour C/C++ : includes, fonctions, classes."""
    result = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('#include'):
            result.append(f"  {stripped} (line {i})")
        # Fonctions simples : type_retour nom_fonction(args) {
        elif re.match(r'^(?!//|/\*|\*|#)', stripped):
            match = re.match(
                r'^(?:inline\s+|static\s+|virtual\s+)?'
                r'(?:[\w:*&]+\s+)+(\w+)\s*\([^)]*\)\s*(?:const)?\s*(?:\{|$)',
                stripped
            )
            if match and not stripped.endswith(';') and not stripped.startswith('//'):
                name = match.group(1)
                if name not in ('if', 'while', 'for', 'switch', 'return', 'sizeof'):
                    result.append(f"  func {stripped} (line {i})")

    return '\n'.join(result) if result else "  (vide)"


def index_shell(filepath, lines):
    """Extraction pour Bash/Shell : fonctions, variables globales."""
    result = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        match = re.match(r'^(\w+)\s*\(\)\s*\{', stripped)
        if match:
            result.append(f"  func {match.group(1)}() (line {i})")
        elif stripped.startswith(('export ', 'declare ', 'readonly ')):
            result.append(f"  var {stripped} (line {i})")

    return '\n'.join(result) if result else "  (vide)"


def index_generic(filepath, lines):
    """Fallback : premières lignes non-vides comme aperçu."""
    preview = []
    for line in lines[:5]:
        if line.strip():
            preview.append(f"  {line.strip()[:80]}")
    return '\n'.join(preview) if preview else "  (vide)"


def index_file(filepath):
    """Indexe un fichier selon son extension."""
    ext = os.path.splitext(filepath)[1].lower()
    rel_path = os.path.relpath(filepath, PROJECT_ROOT)

    try:
        size = os.path.getsize(filepath)
        if size > MAX_FILE_SIZE:
            return f"\n{rel_path} ({size//1024}Ko — trop gros, skippé)"

        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        line_count = len(lines)
        header = f"\n{rel_path} ({line_count} lignes)"

        if ext == '.py':
            body = index_python(filepath, lines)
        elif ext in ('.cpp', '.h', '.hpp', '.cc'):
            body = index_cpp(filepath, lines)
        elif ext in ('.sh', '.bash'):
            body = index_shell(filepath, lines)
        else:
            body = index_generic(filepath, lines)

        return f"{header}\n{body}"

    except Exception as e:
        return f"\n{filepath} (erreur: {e})"


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PROJECT_ROOT, "src")
    root = os.path.abspath(root)

    print("\n" + "=" * 60)
    print("🔍 GÉNÉRATEUR D'INDEX PROJET")
    print("=" * 60)
    print(f"Racine : {root}")
    print(f"Output : {INDEX_OUTPUT}")
    print("-" * 60)

    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in sorted(dirnames)
                       if d not in SKIP_DIRS and not d.startswith('.')]
        for fname in sorted(filenames):
            ext = os.path.splitext(fname)[1].lower()
            if ext in CODE_EXTS:
                files.append(os.path.join(dirpath, fname))

    if not files:
        print("❌ Aucun fichier trouvé.")
        sys.exit(1)

    print(f"📄 {len(files)} fichier(s) à indexer.\n")

    index_parts = [
        "# INDEX PROJET FONDATION-IA",
        f"# Généré automatiquement — {len(files)} fichiers",
        "# Format: chemin (lignes) puis signatures",
        "#" * 40,
    ]

    for i, fpath in enumerate(files, 1):
        fname = os.path.basename(fpath)
        print(f"  [{i}/{len(files)}] {fname}...", end="", flush=True)
        index_parts.append(index_file(fpath))
        print(" ✅")

    os.makedirs(os.path.dirname(INDEX_OUTPUT), exist_ok=True)
    with open(INDEX_OUTPUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(index_parts))

    size_kb = os.path.getsize(INDEX_OUTPUT) // 1024
    print(f"\n{'=' * 60}")
    print(f"✅ Index généré : {INDEX_OUTPUT}")
    print(f"📊 Taille : {size_kb} Ko")
    print(f"📊 Fichiers : {len(files)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
