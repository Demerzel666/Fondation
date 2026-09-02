#!/usr/bin/env python3
"""
TOOLS - Outils de navigation et modification de fichiers pour l'agent.
Le modèle output des tags spéciaux, le CLI les intercepte et exécute.
Tags supportés :
  [READ:chemin]          - Lit un fichier
  [LS:chemin]            - Liste un dossier
  [WRITE:chemin]         - Écrit un fichier (contenu suit le tag)
  [EDIT:chemin]          - Modifie une portion de fichier
  [DONE]                 - Termine la boucle agent
"""

import os
import re
import math

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TAG_PATTERNS = {
    'READ': re.compile(r'\[READ:(.+?)\]'),
    'LS': re.compile(r'\[LS:(.+?)\]'),
    'WRITE': re.compile(r'\[WRITE:(.+?)\](.*)', re.DOTALL),
    'EDIT': re.compile(r'\[EDIT:(.+?)\](.*)', re.DOTALL),
    'GREP': re.compile(r'\[GREP:(.+?)\]'),
    'SED': re.compile(r'\[SED:(.+?)\]'),
    'FUNC': re.compile(r'\[FUNC:(.+?)\|(.+?)\]'),
}

MAX_FILE_READ = 15000  # Réduit pour éviter d'écraser le contexte du modèle
MAX_WRITE_RESULT = 2000  # Ne renvoyer que 2Ko max vers le modèle
MAX_DIR_ITEMS = 50
MAX_CHARS_PER_PAGE = 12000
PAGINATION_THRESHOLD = 15000


def resolve_path(path):
    """Résout un chemin relatif vs absolu."""
    if os.path.isabs(path):
        return path
    # Nettoyage de chemins bizarres (../../ etc)
    clean_path = os.path.normpath(path.strip().strip('[]'))
    return os.path.join(PROJECT_ROOT, clean_path)

def tool_grep(pattern, filepath):
    """Recherche pattern dans un fichier avec numéros de ligne (équivalent grep -n)."""
    fullpath = resolve_path(filepath)

    if not os.path.isfile(fullpath):
        return f"[ERROR] Fichier inexistant: {filepath}"

    try:
        with open(fullpath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        results = []
        for i, line in enumerate(lines, 1):
            if pattern.lower() in line.lower():
                results.append(f"{i}: {line.rstrip()}")

        if not results:
            return f"[GREP] Aucun match trouvé pour '{pattern}' dans {filepath}"

        return "\n".join(results[:50])  # Max 50 résultats
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}"


def tool_sed(filepath, start, end):
    """Lit les lignes start à end (équivalent sed -n 'start,endp')."""
    try:
        start = int(start)
        end = int(end)
    except ValueError:
        return "[ERROR] Numéros de ligne invalides"

    fullpath = resolve_path(filepath)

    if not os.path.isfile(fullpath):
        return f"[ERROR] Fichier inexistant: {filepath}"

    try:
        with open(fullpath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        total_lines = len(lines)

        if start > total_lines or end < start:
            return f"[ERROR] Plage invalide: {start}-{end} (fichier a {total_lines} lignes)"

        # Slice Python: start-1 car humans comptent à 1, Python à 0
        chunk = lines[start-1:end]

        # Retourne avec numéros de ligne
        numbered = []
        for i, line in enumerate(chunk, start=start):
            numbered.append(f"{i}: {line.rstrip()}")

        return "\n".join(numbered)
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}"

def tool_read(filepath):
    """Lit un fichier et retourne son contenu (paginé si trop gros)."""
    fullpath = resolve_path(filepath)
    if not os.path.exists(fullpath):
        return f"[ERROR] Fichier introuvable: {filepath}"
    if os.path.isdir(fullpath):
        return f"[ERROR] C'est un dossier, utilise LS: {filepath}"
    try:
        with open(fullpath, 'r', encoding='utf-8', errors='ignore') as f:
            full_content = f.read()
        
        size = len(full_content)
        
        # ⚠️ CONTRAINTE PHYSIQUE : fichiers > 15000 chars → refus
        if size > MAX_FILE_READ:
            human_size = f"{size//1024}ko" if size >= 1024 else f"{size} chars"
            return (
                f"[READ REFUSÉ] Fichier {filepath} = {size} chars ({human_size}).\n"
                f"Limite autorisée: {MAX_FILE_READ} chars. Fonctionnement physique imposé.\n\n"
                f"🔧 Solution :\n"
                f"1. Utilise [GREP:def nom_fonction|{filepath}] pour trouver la ligne exacte\n"
                f"2. Puis [SED:{filepath}|start|end] pour lire seulement ce qui compte\n\n"
                f"Exemple : [GREP:auto_git|{filepath}] puis [SED:{filepath}|77|230]"
            )
        
        return full_content

    except Exception as e:
        return f"[ERROR] Lecture impossible: {type(e).__name__}: {str(e)[:100]}"

def tool_ls(dirpath):
    """Liste le contenu d'un dossier."""
    fullpath = resolve_path(dirpath)
    if not os.path.exists(fullpath):
        return f"[ERROR] Dossier introuvable: {dirpath}"
    if not os.path.isdir(fullpath):
        return f"[ERROR] C'est un fichier, utilise READ: {dirpath}"
    try:
        items = sorted(os.listdir(fullpath))
        truncated = False
        if len(items) > MAX_DIR_ITEMS:
            items = items[:MAX_DIR_ITEMS]
            truncated = True

        result = []
        for item in items:
            full_item = os.path.join(fullpath, item)
            if os.path.isdir(full_item):
                # Pas de recursion illimitée
                try:
                    subdir_count = len(os.listdir(full_item))
                    result.append(f"  📁 {item}/ ({subdir_count})")
                except PermissionError:
                    result.append(f"  📁 {item}/ (acc denied)")
            else:
                size = os.path.getsize(full_item)
                if size < 1024:
                    size_str = f"{size}o"
                elif size < 1024 * 1024:
                    size_str = f"{size//1024}Ko"
                else:
                    size_str = f"{size//(1024*1024)}Mo"
                result.append(f"  📄 {item} ({size_str})")

        if truncated:
            result.append(f"  ... (+ autres éléments tronqués)")

        return '\n'.join(result)
    except Exception as e:
        return f"[ERROR] Listing impossible: {type(e).__name__}: {str(e)[:100]}"

def tool_func(filepath, func_name):
    """Extrait une fonction COMPLETE par nom (utilise AST Python)."""
    fullpath = resolve_path(filepath)

    if not os.path.isfile(fullpath):
        return f"[ERROR] Fichier introuvable : {filepath}"

    try:
        with open(fullpath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        import ast
        
        tree = ast.parse(''.join(lines))
        
        # Trouver la fonction demandée
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == func_name:
                    start_line = node.lineno - 1  # AST = 0-indexé
                    end_line = node.end_lineno    # AST = 1-indexé (inclusif)
                    
                    # Extraire avec numéros de ligne humains (1-indexé)
                    result_lines = []
                    for i in range(start_line, end_line):
                        result_lines.append(f"{i+1}: {lines[i].rstrip()}")
                    
                    return '\n'.join(result_lines)
        
        return f"[INFO] Fonction '{func_name}' non trouvée dans {filepath}"
    
    except SyntaxError as e:
        return f"[ERROR] Syntaxe invalide dans {filepath}: {str(e)}"
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {str(e)[:100]}"

def _clean_markdown_blocks(content):
    """Retire les balises markdown superflues dans les tags WRITE/EDIT."""
    lines = content.splitlines()
    # Ignore première ligne si c'est un langue marker (cpp, py, etc)
    if lines and re.match(r'^[a-zA-Z]*$', lines[0].strip()):
        lines = lines[1:]
    
    # Retirer le dernier backtick s'il existe
    if lines and lines[-1].strip() == '```':
        lines.pop()
    
    return '\n'.join(lines)


def tool_write(filepath, content):
    """Écrit/crée un fichier."""
    fullpath = resolve_path(filepath)
    try:
        os.makedirs(os.path.dirname(fullpath), exist_ok=True)
        cleaned = _clean_markdown_blocks(content)
        with open(fullpath, 'w', encoding='utf-8') as f:
            f.write(cleaned)
        lines = cleaned.count('\n') + 1
        return f"[OK] Fichier écrit: {filepath} ({lines} lignes)"
    except Exception as e:
        return f"[ERROR] Écriture impossible: {type(e).__name__}: {str(e)[:100]}"


def tool_edit(filepath, content):
    """Remplace le contenu d'un fichier existant."""
    fullpath = resolve_path(filepath)
    if not os.path.exists(fullpath):
        return f"[ERROR] Fichier introuvable pour édition: {filepath}"
    try:
        cleaned = _clean_markdown_blocks(content)
        with open(fullpath, 'w', encoding='utf-8') as f:
            f.write(cleaned)
        lines = cleaned.count('\n') + 1
        return f"[OK] Fichier modifié: {filepath} ({lines} lignes)"
    except Exception as e:
        return f"[ERROR] Édition impossible: {type(e).__name__}: {str(e)[:100]}"


def extract_tools(response):
    tools = []
    
    # WRITE + EDIT (peuvent avoir du contenu sur plusieurs lignes)
    for match in TAG_PATTERNS['WRITE'].finditer(response):
        filepath = match.group(1).strip()
        content = match.group(2)
        if content.strip():
            tools.append(('WRITE', filepath, content))
    
    for match in TAG_PATTERNS['EDIT'].finditer(response):
        filepath = match.group(1).strip()
        content = match.group(2)
        if content.strip():
            tools.append(('EDIT', filepath, content))
    
    # READ + LS (tags seuls, sans contenu)
    for match in TAG_PATTERNS['READ'].finditer(response):
        filepath = match.group(1).strip()
        tools.append(('READ', filepath, None))
    
    for match in TAG_PATTERNS['LS'].finditer(response):
        dirpath = match.group(1).strip()
        tools.append(('LS', dirpath, None))

    # GREP et SED
    for match in TAG_PATTERNS['GREP'].finditer(response):
        target = match.group(1).strip()
        tools.append(('GREP', target, None))
    
    for match in TAG_PATTERNS['SED'].finditer(response):
        target = match.group(1).strip()
        tools.append(('SED', target, None))

    for match in TAG_PATTERNS['FUNC'].finditer(response):
        filepath = match.group(1).strip()
        func_name = match.group(2).strip()
        tools.append(('FUNC', filepath, func_name))

    return tools

def has_done_tag(response):
    """Vérifie si le modèle a signalé la fin."""
    return '[DONE]' in response


def execute_tools(response):
    """
    Exécute tous les outils trouvés dans la réponse.
    Retourne (tool_log, results_text) :
      - tool_log : résumé court pour affichage écran
      - results_text : résultats détaillés à renvoyer au modèle
    """
    tools = extract_tools(response)
    if not tools:
        return "", ""

    log_lines = []
    result_lines = []

    for tool_type, target, content in tools:
        if tool_type == 'READ':
            result = tool_read(target)
            log_lines.append(f"  📖 READ {target}")
            # Si pagination → garder le contenu + métadonnées
            if '[TRONCATURE AUTOMATIQUE]' in result:
                result_lines.append(f"=== CONTENU DE {target} (PAGE 1) ===\n{result}\n")
            elif len(result) > MAX_CHARS_PER_PAGE:
                # Pas paginé mais gros → tronquer pour le contexte modèle
                short_res = result[:MAX_CHARS_PER_PAGE] + "\n\n[... tranché pour économiser le contexte]"
                result_lines.append(f"=== CONTENU DE {target} ===\n{short_res}\n")
            else:
                result_lines.append(f"=== CONTENU DE {target} ===\n{result}\n")

        elif tool_type == 'LS':
            result = tool_ls(target)
            log_lines.append(f"  📂 LS {target}")
            result_lines.append(f"=== LISTING DE {target} ===\n{result}\n")

        elif tool_type == 'WRITE':
            result = tool_write(target, content)
            log_lines.append(f"  ✏️ WRITE {target}")
            result_lines.append(f"=== RÉSULTAT WRITE {target} ===\n{result}\n")

        elif tool_type == 'EDIT':
            result = tool_edit(target, content)
            log_lines.append(f"  🔧 EDIT {target}")
            result_lines.append(f"=== RÉSULTAT EDIT {target} ===\n{result}\n")

        elif tool_type == 'GREP':
            parts = re.split(r'\|', target, maxsplit=1)
            if len(parts) == 2:
                pattern, path = parts
                result = tool_grep(pattern, path)
            else:
                result = "[ERROR] Format GREP: [GREP:pattern|chemin]"
            log_lines.append(f"  🔍 GREP {pattern} in {path}")
            result_lines.append(f"=== RÉSULTAT GREP '{pattern}' dans {path} ===\n{result}\n")

        elif tool_type == 'SED':
            parts = re.split(r'\|', target)
            if len(parts) == 3:
                path, start, end = parts
                result = tool_sed(path, start, end)
            else:
                result = "[ERROR] Format SED: [SED:chemin|start|end]"
            log_lines.append(f"  📄 SED {path} lines {start}-{end}")
            result_lines.append(f"=== RÉSULTAT SED {path} lignes {start}-{end} ===\n{result}\n")

        elif tool_type == 'SED':
            parts = re.split(r'\|', target)
            if len(parts) == 3:
                path, start, end = parts
                result = tool_sed(path, start, end)
            else:
                result = "[ERROR] Format SED: [SED:chemin|start|end]"
            log_lines.append(f"  📄 SED {path} lines {start}-{end}")
            result_lines.append(f"=== RÉSULTAT SED {path} lignes {start}-{end} ===\n{result}\n")

        # ← NOUVEAU : FUNC
        elif tool_type == 'FUNC':
            result = tool_func(target, content)
            log_lines.append(f"  ⭐ FUNC {target}:{content}")
            result_lines.append(f"=== RÉSULTAT FUNC {target}:{content} ===\n{result}\n")

    return '\n'.join(log_lines), '\n'.join(result_lines)

    return '\n'.join(log_lines), '\n'.join(result_lines)

def load_project_index():
    """Charge l'index de projet pour injection dans le contexte."""
    index_path = os.path.join(PROJECT_ROOT, "data", "project_index.txt")
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""
