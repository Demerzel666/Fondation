#!/usr/bin/env python3
# src/cli.py
# =============================================================================
# INTERFACE CHAT INTERACTIVE POUR FONDATION-IA
# Orchestrateur dynamique de serveurs IA + Gestion projets/conversations
# =============================================================================

import sys
import os
import requests
import subprocess
import json
import re
import time
from datetime import datetime
from pygments import highlight
from pygments.lexers import guess_lexer, get_lexer_by_name
from pygments.formatters import Terminal256Formatter

# ── CHEMINS RELATIFS ────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.db import init_db, create_project, list_projects, get_project, delete_project
from src.db import create_conversation, list_conversations, delete_conversation, get_messages
from src.db import add_message
from src.db import list_users, deactivate_user, activate_user, create_invite_code, create_invite, register_new_user, get_conn
from src.db import create_workspace, add_workspace_file, get_workspace
from src.context import build_prompt, save_response
from src.core import send_to_model, generate_file_map, manage_server
from src.queue_manager import acquire_model_lock, release_model_lock

def send_with_queue(message, mode):
    """Envoie un message avec gestion de lock inter-processus."""
    for i in range(30):
        if acquire_model_lock():
            try:
                return send_to_model(message, mode)
            finally:
                release_model_lock()
        time.sleep(1)
    raise RuntimeError("Modèle occupé trop longtemps (>30s)")

# ── READLINE : support flèches + historique des commandes ─────
try:
    import readline
    HISTORY_FILE = os.path.expanduser("~/.fondation_cli_history")
    if os.path.exists(HISTORY_FILE):
        readline.read_history_file(HISTORY_FILE)
    readline.set_history_length(1000)
except ImportError:
    pass

# ── CONFIGURATION ───────────────────────────────────────────────
PYTHON_INTERPRETER = os.environ.get("FONDATION_PYTHON", "/home/data/ml_env/bin/python3")

LLAMA_CODER_URL = "http://localhost:8081/v1/chat/completions"
LLAMA_DEMERZEL_URL = "http://localhost:8080/v1/chat/completions"
SCRIPT_CODER = os.path.join(PROJECT_ROOT, "scripts", "start_coder_v2.sh")
SCRIPT_DEMERZEL = os.path.join(PROJECT_ROOT, "scripts", "start_demerzel.sh")
MAX_LOADED_FILES = 50



def save_cli_history():
    """Sauvegarde l'historique des commandes entre sessions."""
    try:
        import readline
        readline.write_history_file(os.path.expanduser("~/.fondation_cli_history"))
    except Exception:
        pass


def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')

def colorize_code(code,lang=None):
    """Coloration syntaxique pour affichage terminal."""
    try:
        if lang:
            lexer = get_lexer_by_name(lang, stripall=True)
        else:
            lexer = guess_lexer(code)
        return highlight(code, lexer, Terminal256Formatter()).rstrip('\n')
    except Exception:
        return code

def auto_git_commit_secure(chemin_fichier, description=""):
    """
    Commit Git avec tri-couche sécurité:
    1. Stage du fichier ciblé
    2. Audit Python conditionnel (.py seulement)
    3. Commit avec --no-verify (évite double audit hook pre-commit)
    
    Détecte auto le repo parent via git rev-parse (--workdir safe)
    """
    import subprocess

    abs_path = os.path.abspath(chemin_fichier)
    file_dir = os.path.dirname(abs_path)

    # Détecter le repo parent du fichier
    repo_result = subprocess.run(
        ["git", "-C", file_dir, "rev-parse", "--show-toplevel"],
        capture_output=True, text=True
    )

    if repo_result.returncode != 0:
        # Pas dans un repo → fallback sur PROJECT_ROOT
        repo_root = PROJECT_ROOT
    else:
        repo_root = repo_result.stdout.strip()

    # Étape 1: Stage le fichier ciblé
    print(f"\n📦 Fichier à committer: {chemin_fichier}")

    stage_result = subprocess.run(
        ["git", "add", abs_path],
        cwd=repo_root, capture_output=True, text=True
    )
    if stage_result.returncode != 0:
        return False, f"[GIT] Erreur staging: {stage_result.stderr}"

    print(f"✅ Fichier staged: {chemin_fichier}")

    # Étape 2: Security audit pré-commit (Python seulement)
    ext = os.path.splitext(chemin_fichier)[1].lower()
    audit_blocked = False
    audit_error_msg = ""

    if ext == '.py':
        print("[SÉCURITÉ] Lancement audit pré-commit...")
        audit_script = os.path.join(PROJECT_ROOT, "scripts", "security_audit.py")
        
        audit_proc = subprocess.run(
            [PYTHON_INTERPRETER, audit_script, "./src/", "--offline"],
            cwd=repo_root, capture_output=True, text=True
        )
        
        if audit_proc.stdout.strip():
            print(audit_proc.stdout)
        
        if audit_proc.returncode != 0:
            print("\n❌ COMMIT BLOQUÉ — Vulnérabilités critiques détectées.")
            subprocess.run(["git", "reset", abs_path], cwd=repo_root)
            audit_blocked = True
            audit_error_msg = "Audit sécurité échoué — fix requis avant commit."
    else:
        print(f"[INFO] Audit skippé pour {ext} (Python seulement)")

# Si audit bloqué, annuler et retourner
    if audit_blocked:
        return False, audit_error_msg

    # Étape 3: Générer message de commit
    if description:
        msg = description
    else:
        ext = os.path.splitext(chemin_fichier)[1].lower()
        basename = os.path.basename(chemin_fichier)

        git_log = subprocess.run(
            ["git", "log", "--oneline", "--", abs_path],
            cwd=repo_root, capture_output=True, text=True
        )
        is_new = git_log.stdout.strip() == ""
        action = "ajouter" if is_new else "modifier"

        if ext == '.py':
            msg = f"feat: {action} {basename}"
        elif ext == '.sh':
            msg = f"chore: {action} script {basename}"
        elif ext == '.md':
            msg = f"docs: {action} {basename}"
        elif ext in ('.cpp', '.h', '.c'):
            msg = f"feat: {action} {basename}"
        else:
            msg = f"feat: {action} {basename}"

    # Étape 4: Commit final (--no-verify pour éviter double audit)
    commit_proc = subprocess.run(
        ["git", "commit", "-m", msg, "--no-verify"],
        cwd=repo_root, capture_output=True, text=True
    )

    if commit_proc.returncode == 0:
        print(f"\n✅ Commit réussi:\n   {msg}\n")
        hash_match = re.search(r'\[([a-f0-9]+)\]', commit_proc.stdout)
        if hash_match:
            return True, f"Commit {hash_match.group(1)[:7]} réalisé."
        return True, "Commit réalisé."
    else:
        print(f"❌ Échec commit: {commit_proc.stderr}")
        subprocess.run(["git", "reset", abs_path], cwd=repo_root)
        return False, f"Erreur Git: {commit_proc.stderr}"

def print_response(response: str) -> None:
    """Affiche la réponse du modèle avec coloration syntaxique des blocs de code."""
    if "```" in response:
        parts = response.split("```")
        for i, part in enumerate(parts):
            if i % 2 == 1:  # Bloc de code
                lines = part.strip().split("\n")
                lang = lines[0].strip() if lines else None
                code = "\n".join(lines[1:]) if lang else part.strip()
                print(colorize_code(code, lang if lang else None))
            else:
                print(part, end="")
        print()
    else:
        print(response)

def print_banner():
    print("=" * 60)
    print("🌍 FONDATION-IA — ENVIRONNEMENT 🌍")
    print("=" * 60)
    print()


def show_main_menu():
    print("\nMENU PRINCIPAL")
    print("-" * 30)
    print("[1] Lister les projets")
    print("[2] Créer un nouveau projet")
    print("[3] Choisir un projet existant")
    print("[4] Quitter")
    print()


def show_project_menu(mode_state):
    print(f"\nPROJET ACTUEL : {mode_state['project']['name']} (ID #{mode_state['project']['id']})")
    print(f"Mode actuel : {mode_state['mode'].upper()}")
    print("-" * 40)
    print("[1] Changer de mode (code/politique)")
    print("[2] Lister les conversations")
    print("[3] Nouvelle conversation")
    print("[4] Reprendre une conversation existante")
    print("[5] Retour menu principal")
    print("[6] Supprimer le projet actuel")
    print()

def get_vram_info():
    """Retourne VRAM info structurée: {'total': X, 'used': Y, 'free': Z} en Go."""
    import subprocess
    try:
        result = subprocess.run(['rocm-smi', '--showmeminfo', 'vram'],
                                capture_output=True, text=True, timeout=5)
        total = None
        used = None
        for line in result.stdout.splitlines():
            if 'GPU[0]' in line:
                val = int(line.split(':')[-1].strip().replace(',', ''))
                if 'Total Memory' in line:
                    total = val
                elif 'Used Memory' in line:
                    used = val
        if total and used:
            return {
                'total': total / (1024**3),  # Convertir en Go
                'used': used / (1024**3),
                'free': (total - used) / (1024**3)
            }
    except:
        pass
    return {'total': 24.0, 'used': 0, 'free': 24.0}  # Fallback RX 7900 XTX

def get_dynamic_limits():
    """Calcule les limites dynamiques selon VRAM disponible."""
    vram = get_vram_info()
    free_gb = vram['free']

    # Seuils adaptatifs
    if free_gb < 3.0:
        max_file_size = 50000   # 50 Ko
        max_files = 30
        reason = "VRAM limitée"
    elif free_gb < 8.0:
        max_file_size = 75000   # 75 Ko
        max_files = 40
        reason = "VRAM modérée"
    else:
        max_file_size = 100000  # 100 Ko
        max_files = 50
        reason = "VRAM abondante"

    return {
        'max_file_size': max_file_size,
        'max_files': max_files,
        'reason': reason,
        'vram_info': vram
    }

def run_chat_loop(mode_state):
    """Boucle de chat dans une conversation sélectionnée."""

    print(f"\n{'='*60}")
    print(f"CHAT ACTIF")
    print(f"Projet : {mode_state['project']['name']}")
    print(f"Conversation : #{mode_state['conversation_id']}")
    print(f"Mode : {mode_state['mode'].upper()} (/mode pour changer)")
    print(f"Commandes : /mode, /multi, /load, /files, /audit, /history, /sources, /menu, /quit")
    print(f"{'='*60}\n")

    # ── RESTAURATION WORKSPACE ─────────────────────────────
    if mode_state.get('project_id'):
        ws = get_workspace(mode_state['project_id'])
        if ws:
            mode_state['workspace_path'] = ws['path']
            mode_state['workspace_id'] = ws['id']
            mode_state['workspace_files'] = ws['files']
            print(f"[WORKSPACE] {ws['path']} ({len(ws['files'])} fichier(s) actif(s))")

    last_model_response = None

    while True:
        # Informations VRAM en temps réel
        vram_info = get_vram_info()
        limits = get_dynamic_limits()
        
        if mode_state['mode'] == "code":
            if mode_state.get('active_file'):
                basename = os.path.basename(mode_state['active_file'])
                prompt_prefix = f"[CODE:{basename} | {vram_info['used']:.1f}/{vram_info['total']:.1f}Go | Lib:{vram_info['free']:.1f}Go]"
            else:
                prompt_prefix = f"[CODE | {vram_info['used']:.1f}/{vram_info['total']:.1f}Go | Lib:{vram_info['free']:.1f}Go]"
        else:
            prompt_prefix = f"[DEMERZEL | {vram_info['used']:.1f}/{vram_info['total']:.1f}Go | Lib:{vram_info['free']:.1f}Go]"

        try:
            user_input = input(f"{prompt_prefix}> ").strip()

            if not user_input:
                continue

            # ── MULTI-LIGNES (/multi ou /paste) ─────────────────
            if user_input.lower() in ('/multi', '/paste'):
                print("[MULTI] Colle ton texte. Tape END seul sur une ligne pour terminer (ou Ctrl+D).")
                lines = []
                while True:
                    try:
                        line = input()
                        if line.strip() == 'END':
                            break
                        lines.append(line)
                    except EOFError:
                        break
                user_input = '\n'.join(lines).strip()
                if not user_input:
                    print("(vide, abandon)")
                    continue
                # Tombe directement vers l'envoi de message ci-dessous

            # ── COMMANDES ──────────────────────────────────────
            elif user_input.startswith('/'):
                cmd_parts = user_input.split(maxsplit=1)
                cmd = cmd_parts[0].lower()
                args = cmd_parts[1] if len(cmd_parts) > 1 else ""

                if cmd == '/quit' or cmd == '/exit':
                    print("Sortie du chat.")
                    save_cli_history()
                    return 'quit'

                elif cmd == '/user':
                    sub = args.split() if args else []
                    if not sub:
                        print("\nCommandes utilisateur:")
                        print("  /user list                  - Liste tous les users")
                        print("  /user create <nom>          - Crée un user (invite auto)")
                        print("  /user create <nom> <token>  - Crée un user avec token précis")
                        print("  /user deactivate <id/nom>   - Désactive un user")
                        print("  /user activate <id/nom>     - Réactive un user")
                        print("  /user generate-invite       - Génère un code d'invite")
                        continue
                    
                    action = sub[0]
                    
                    # /user list
                    if action == 'list':
                        users = list_users()
                        if not users:
                            print("(Aucun utilisateur)")
                        else:
                            print("\nUtilisateurs:")
                            for u in users:
                                status = "✓" if u['active'] else "✗"
                                print(f"  {status} #{u['id']:3} {u['name']:20} ({u['created_at']})")
                        continue
                    
                    # /user create
                    elif action == 'create':
                        if len(sub) < 2:
                            print("Usage: /user create <nom> [<token>]")
                            continue
                        
                        new_name = sub[1]
                        if len(sub) >= 3:
                            new_token = sub[2]
                            invite = create_invite_code()
                        else:
                            import secrets
                            new_token = secrets.token_urlsafe(32)
                            invite = create_invite_code()
                        
                        uid, used_invite, err = register_new_user(new_name, new_token, invite)
                        
                        if uid is None:
                            print(f"❌ Erreur: {err}")
                        else:
                            print(f"\n✅ Utilisateur créé:")
                            print(f"   ID    : #{uid}")
                            print(f"   Nom   : {new_name}")
                            print(f"   Token : {new_token}")
                            print(f"   Code  : {invite[:20]}...")
                            print(f"\n⚠️  Sauvegarde ces informations ! Le code expire après usage.")
                        continue
                    
                    # /user deactivate
                    elif action == 'deactivate':
                        if len(sub) < 2:
                            print("Usage: /user deactivate <id|nom>")
                            continue
                        
                        target = sub[1]
                        conn = get_conn()
                        # Essayer d'abord par ID
                        user = conn.execute(
                            "SELECT id, name FROM users WHERE id = ? OR name = ?", (target, target)
                        ).fetchone()
                        conn.close()
                        
                        if not user:
                            print(f"❌ Utilisateur introuvable: {target}")
                        else:
                            deactivate_user(user['id'])
                            status = "inactive" if user['active'] else "active"
                            print(f"✅ User #{user['id']} ({user['name']}) désactivé")
                        continue
                    
                    # /user activate
                    elif action == 'activate':
                        if len(sub) < 2:
                            print("Usage: /user activate <id|nom>")
                            continue
                        
                        target = sub[1]
                        conn = get_conn()
                        user = conn.execute(
                            "SELECT id, name FROM users WHERE id = ? OR name = ?", (target, target)
                        ).fetchone()
                        conn.close()
                        
                        if not user:
                            print(f"❌ Utilisateur introuvable: {target}")
                        else:
                            activate_user(user['id'])
                            print(f"✅ User #{user['id']} ({user['name']}) réactivé")
                        continue
                    
                    # /user generate-invite
                    elif action == 'generate-invite':
                        invite = create_invite()
                        print(f"\n💌 Code d'invitation généré: {invite}")
                        print(f"   ⏱️  Usage unique — donne-le immédiatement à la personne concernée.")
                        continue
                    
                    else:
                        print(f"Action inconnue: {action}")
                        continue

                elif cmd == '/menu':
                    return 'menu'

                elif cmd == '/mode':
                    parts = user_input.split(maxsplit=1)
                    if len(parts) < 2 or parts[1] not in ['code', 'politique']:
                        print("Usage: /mode code  |  /mode politique  |  /mode auto")
                        print(f"Mode actuel : {mode_state['mode'].upper()}")
                        continue
                    
                    new_mode = parts[1]
                    
                    # 🔥 SWITCH IMMÉDIAT — ne pas attendre le prochain message
                    print(f"[SWITCH] Changement vers {new_mode.upper()} en cours...")
                    if manage_server(new_mode):  # ← Déclenchement synchronisé
                        mode_state['mode'] = new_mode
                        vram_info = get_vram_info()
                        print(f"✅ Mode {new_mode.upper()} prêt et occupé {vram_info['used']:.1f}/{vram_info['total']:.1f}Go de VRAM.")
                    else:
                        print(f"❌ Échec démarrage {new_mode}. Mode inchangé.")
                    continue

                elif cmd == '/load':
                    limits = get_dynamic_limits()  # ← LIMITES DYNAMIQUES
                    
                    if not args:
                        print("Usage: /load <fichier1> [fichier2] [...]")
                        print(f"Limite dynamique: {limits['max_file_size']/1000:.0f}Ko | Max {limits['max_files']} fichiers")
                        print(f"VRAM: {limits['vram_info']['free']:.1f}Go libre ({limits['reason']})")
                        continue
                    
                    paths = args.split()
                    
                    valid_exts = {'.py', '.sh', '.bash', '.yaml', '.yml', '.json',
                                 '.toml', '.cfg', '.ini', '.conf', '.md', '.txt',
                                 '.rs', '.go', '.js', '.ts', '.c', '.cpp', '.h',
                                 '.sql', '.html', '.css', '.lua', '.rb', '.php',
                                 'Makefile', '.service', '.desktop'}
                    
                    for path in paths:
                        # Vérifie limite de fichiers
                        if len(mode_state['loaded_files']) >= limits['max_files']:
                            print(f"⛔ Limite de {limits['max_files']} fichiers atteinte (adapté à {limits['vram_info']['free']:.1f}Go VRAM)")
                            break
                        
                        # Cas : dossier (se termine par / ou est . ou ..)
                        if path.endswith('/') or path == '.' or path == '..' or os.path.isdir(path):
                            target_dir = os.path.abspath(path) if path in ('.', '..') else os.path.abspath(path.rstrip('/'))
                            print(f"[LOAD] Scan du dossier : {target_dir}")

                            loaded_count = 0
                            for root, dirs, files in os.walk(target_dir):
                                # Skip dossiers inutiles
                                dirs[:] = [d for d in dirs if d not in
                                          {'__pycache__', '.git', 'node_modules', '.venv',
                                           'venv', '.cache', '__pypackages__', '.idea', '.vscode'}]

                                for fname in sorted(files):
                                    fpath = os.path.join(root, fname)
                                    ext = os.path.splitext(fname)[1].lower()
                                    if ext in valid_exts or fname == 'Makefile':
                                        rel_path = os.path.relpath(fpath, target_dir)
                                        try:
                                            size = os.path.getsize(fpath)
                                            if size > limits['max_file_size']:  # ← LIMITES DYNAMIQUES
                                                print(f"  ⏭️  {rel_path} (trop gros: {size//1024}Ko > {limits['max_file_size']/1000:.0f}Ko)")
                                                continue
                                            if len(mode_state['loaded_files']) >= limits['max_files']:  # ← MAX FILES DYNAMIQUE
                                                print(f"  ⛔ Limite de {limits['max_files']} fichiers atteinte")
                                                break
                                            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                                                content = f.read()
                                            mode_state['loaded_files'][rel_path] = content
                                            loaded_count += 1
                                            print(f"  ✅ {rel_path} ({len(content)} chars)")
                                        except Exception as e:
                                            print(f"  ❌ {rel_path}: {e}")

                            print(f"\n[LOAD] {loaded_count} fichier(s) chargé(s). Total : {len(mode_state['loaded_files'])}")

                        # Cas : fichier unique
                        elif os.path.isfile(path):
                            try:
                                size = os.path.getsize(path)
                                if size > limits['max_file_size']:  # ← LIMITES DYNAMIQUES
                                    print(f"⛔ Fichier trop volumineux ({size//1024}Ko > {limits['max_file_size']/1000:.0f}Ko)")
                                    continue
                                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                                    content = f.read()
                                display_name = os.path.basename(path)
                                mode_state['loaded_files'][display_name] = content
                                print(f"✅ Chargé : {display_name} ({len(content)} chars)")
                            except Exception as e:
                                print(f"❌ Erreur lecture : {e}")

                        else:
                            print(f"❌ Chemin introuvable : {path}")

                    print(f"   Total fichiers en mémoire : {len(mode_state['loaded_files'])}")
                    continue

                elif cmd == '/unload':
                    if not mode_state['loaded_files']:
                        print("(Aucun fichier chargé)")
                    else:
                        count = len(mode_state['loaded_files'])
                        mode_state['loaded_files'] = {}
                        print(f"🗑️ {count} fichier(s) déchargé(s).")
                    continue

                elif cmd == '/files':
                    if not mode_state['loaded_files']:
                       print("(Aucun fichier chargé. Utilise /load <chemin>)")
                    else:
                        print(f"\n📁 Fichiers chargés ({len(mode_state['loaded_files'])}) :")
                        for fname, content in mode_state['loaded_files'].items():
                            print(f"  • {fname} ({len(content)} chars)")
                        print()
                    continue

                elif cmd == '/cat':
                    if not args:
                        print("Usage: /cat <chemin/vers/fichier>")
                        continue

                    filepath = args.strip()
                    fullpath = os.path.join(PROJECT_ROOT, filepath) if not os.path.isabs(filepath) else filepath

                    if not os.path.exists(fullpath):
                        print(f"❌ Fichier introuvable : {filepath}")
                        continue

                    if os.path.isdir(fullpath):
                        print(f"❌ C'est un dossier, utilise /ls")
                        continue

                    try:
                        with open(fullpath, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()

                        ext = os.path.splitext(filepath)[1].lstrip('.')
                        lang_map = {
                            'py': 'python', 'sh': 'bash', 'cpp': 'cpp', 'c': 'c',
                            'js': 'javascript', 'md': 'markdown', 'json': 'json',
                            'yaml': 'yaml', 'yml': 'yaml', 'sql': 'sql'
                        }
                        lang = lang_map.get(ext, None)

                        print(f"\n📄 {filepath} ({len(content)} chars)\n")
                        print(colorize_code(content, lang))
                        print(f"\n{'─'*60}\n")
                    except Exception as e:
                        print(f"❌ Erreur : {e}")
                    continue

                elif cmd == '/open':
                    if not args:
                        print("Usage: /open <fichier>")
                        continue

                    filepath = args.strip()
                    fullpath = os.path.join(PROJECT_ROOT, filepath) if not os.path.isabs(filepath) else filepath

                    if not os.path.exists(fullpath):
                        print(f"❌ Fichier introuvable : {filepath}")
                        continue

                    if os.path.isdir(fullpath):
                        print(f"❌ C'est un dossier, utilise /load")
                        continue

                    size = os.path.getsize(fullpath)
                    mode_state['active_file'] = fullpath
                    mode_state['file_map'] = generate_file_map(fullpath)
                    basename = os.path.basename(filepath)

                    print(f"📁 Fichier actif : {filepath} ({size} bytes)")
                    if size > limits['max_file_size']:
                        print(f"   ⚠️ Gros fichier — le modèle utilisera GREP/SED pour explorer")
                    print(f"   Format des modifications : SEARCH/REPLACE")
                    continue

                elif cmd == '/close':
                    if not mode_state.get('active_file'):
                        print("(Aucun fichier actif)")
                    else:
                        mode_state['active_file'] = None
                        print("📁 Fichier actif fermé.")
                    continue

                elif cmd == '/mkdir':
                    if not args:
                        print("Usage: /mkdir <chemin/dossier>")
                        continue

                    filepath = os.path.expanduser(args.strip())
                    fullpath = filepath if os.path.isabs(filepath) else os.path.join(PROJECT_ROOT, filepath)

                    try:
                        os.makedirs(fullpath, exist_ok=True)
                        print(f"✅ Dossier créé : {filepath}")
                    except Exception as e:
                        print(f"❌ Erreur : {e}")
                    continue

                elif cmd == '/touch':
                    if not args:
                        print("Usage: /touch <chemin/fichier>")
                        continue

                    filepath = os.path.expanduser(args.strip())
                    fullpath = filepath if os.path.isabs(filepath) else os.path.join(PROJECT_ROOT, filepath)

                    # Créer les dossiers parents si nécessaire
                    parent_dir = os.path.dirname(fullpath)
                    if parent_dir and not os.path.exists(parent_dir):
                        os.makedirs(parent_dir, exist_ok=True)

                    try:
                        if os.path.exists(fullpath):
                            # Fichier existe → met à jour le timestamp (comme touch réel)
                            os.utime(fullpath, None)
                            print(f"ℹ️ Fichier existant, timestamp mis à jour : {filepath}")
                        else:
                            open(fullpath, 'w').close()
                            print(f"✅ Fichier créé : {filepath}")
                    except Exception as e:
                        print(f"❌ Erreur : {e}")
                    continue

                elif cmd == '/tree':
                    target = os.path.expanduser(args.strip()) if args else "."

                    if target == "." or target == "":
                        fullpath = PROJECT_ROOT
                    elif os.path.isabs(target):
                        fullpath = target
                    else:
                        fullpath = os.path.expanduser(PROJECT_ROOT, target)

                    if not os.path.exists(fullpath):
                        print(f"❌ Chemin introuvable : {target}")
                        continue

                elif cmd == '/workspace':
                    if not mode_state.get('project_id'):
                        print("❌ Sélectionne d'abord un projet.")
                        continue

                    sub = args.split() if args else []

                    # /workspace (sans args) → afficher l'état
                    if not sub:
                        if not mode_state.get('workspace_path'):
                            print("Aucun workspace défini.")
                            print("Usage: /workspace <chemin>")
                            print("       /workspace add <fichier>")
                            print("       /workspace remove <fichier>")
                        else:
                            print(f"\n📂 WORKSPACE")
                            print(f"   Chemin : {mode_state['workspace_path']}")
                            print(f"   Fichiers actifs ({len(mode_state['workspace_files'])}) :")
                            for f in mode_state['workspace_files']:
                                print(f"     • {f}")
                        continue

                    action = sub[0]

                    # /workspace <chemin> → définir le workspace
                    if action not in ('add', 'remove'):
                        ws_path = os.path.expanduser(args.strip())
                        if not os.path.isabs(ws_path):
                            ws_path = os.path.join(PROJECT_ROOT, ws_path)

                        if not os.path.exists(ws_path):
                            print(f"❌ Chemin introuvable : {ws_path}")
                            continue

                        ws_id = create_workspace(mode_state['project_id'], ws_path)
                        mode_state['workspace_path'] = ws_path
                        mode_state['workspace_id'] = ws_id
                        mode_state['workspace_files'] = []

                        print(f"✅ Workspace défini : {ws_path}")
                        print(f"   ID : {ws_id}")
                        print(f"   Utilise /workspace add <fichier> pour ajouter des fichiers actifs")
                        continue

                    # /workspace add <fichier|dossier>
                    elif action == 'add':
                        if len(sub) < 2:
                            print("Usage: /workspace add <fichier|dossier>")
                            continue

                        target_path = os.path.expanduser(sub[1])

                        if not os.path.exists(target_path):
                            print(f"❌ Introuvable : {sub[1]}")
                            continue

                        if not mode_state.get('workspace_path'):
                            if os.path.isdir(target_path):
                                ws_path = target_path
                            else:
                                ws_path = os.path.dirname(target_path)
                            
                            ws_id = create_workspace(mode_state['project_id'], ws_path)
                            mode_state['workspace_path'] = ws_path
                            mode_state['workspace_id'] = ws_id
                            mode_state['workspace_files'] = []
                            print(f"[WORKSPACE] Auto-défini : {ws_path}")

                        valid_exts = {'.py', '.sh', '.bash', '.yaml', '.yml', '.json',
                                     '.toml', '.cfg', '.ini', '.conf', '.md', '.txt',
                                     '.rs', '.go', '.js', '.ts', '.c', '.cpp', '.h',
                                     '.sql', '.html', '.css', '.lua', '.rb', '.php',
                                     'Makefile', '.service', '.desktop'}

                        skip_dirs = {'__pycache__', '.git', 'node_modules', '.venv',
                                    'venv', '.cache', '__pypackages__', '.idea', '.vscode'}

                        added_count = 0

                        # Cas : dossier → scan récursif
                        if os.path.isdir(target_path):
                            print(f"[SCAN] {target_path}")
                            for root, dirs, files in os.walk(target_path):
                                dirs[:] = [d for d in dirs if d not in skip_dirs]
                                dirs.sort()
                                files.sort()

                                for fname in files:
                                    fpath = os.path.join(root, fname)
                                    ext = os.path.splitext(fname)[1].lower()
                                    if ext not in valid_exts and fname != 'Makefile':
                                        continue
                                    if os.path.getsize(fpath) > limits['max_file_size']:
                                        continue

                                    rel_path = os.path.relpath(fpath, mode_state['workspace_path'])
                                    if rel_path not in mode_state['workspace_files']:
                                        add_workspace_file(mode_state['workspace_id'], rel_path)
                                        mode_state['workspace_files'].append(rel_path)
                                        added_count += 1

                            print(f"✅ {added_count} nouveau(s) fichier(s) ajouté(s)")
                            print(f"   Total fichiers actifs : {len(mode_state['workspace_files'])}")

                        # Cas : fichier unique
                        else:
                            rel_path = os.path.relpath(target_path, mode_state['workspace_path'])
                            if rel_path in mode_state['workspace_files']:
                                print(f"ℹ️ Déjà dans les fichiers actifs : {rel_path}")
                            else:
                                add_workspace_file(mode_state['workspace_id'], rel_path)
                                mode_state['workspace_files'].append(rel_path)
                                print(f"✅ Ajouté : {rel_path}")
                        continue

                        valid_exts = {'.py', '.sh', '.bash', '.yaml', '.yml', '.json',
                                     '.toml', '.cfg', '.ini', '.conf', '.md', '.txt',
                                     '.rs', '.go', '.js', '.ts', '.c', '.cpp', '.h',
                                     '.sql', '.html', '.css', '.lua', '.rb', '.php',
                                     'Makefile', '.service', '.desktop'}

                        skip_dirs = {'__pycache__', '.git', 'node_modules', '.venv',
                                    'venv', '.cache', '__pypackages__', '.idea', '.vscode'}

                        added_count = 0
                        print(f"[DEBUG] workspace_files actuels: {mode_state['workspace_files']}")
                        print(f"[DEBUG] workspace_path: {mode_state['workspace_path']}")

                        # Cas : dossier → scan récursif
                        if os.path.isdir(target_path):
                            print(f"[SCAN] {target_path}")
                            for root, dirs, files in os.walk(target_path):
                                dirs[:] = [d for d in dirs if d not in skip_dirs]
                                dirs.sort()
                                files.sort()

                                for fname in files:
                                    fpath = os.path.join(root, fname)
                                    ext = os.path.splitext(fname)[1].lower()
                                    if ext not in valid_exts and fname != 'Makefile':
                                        continue
                                    if os.path.getsize(fpath) > limits['max_file_size']:
                                        continue

                                    rel_path = os.path.relpath(fpath, mode_state['workspace_path'])
                                    if rel_path not in mode_state['workspace_files']:
                                        add_workspace_file(mode_state['workspace_id'], rel_path)
                                        mode_state['workspace_files'].append(rel_path)
                                        added_count += 1

                            print(f"✅ {added_count} fichier(s) ajouté(s)")

                        # Cas : fichier unique
                        else:
                            rel_path = os.path.relpath(target_path, mode_state['workspace_path'])
                            if rel_path in mode_state['workspace_files']:
                                print(f"ℹ️ Déjà dans les fichiers actifs : {rel_path}")
                            else:
                                add_workspace_file(mode_state['workspace_id'], rel_path)
                                mode_state['workspace_files'].append(rel_path)
                                print(f"✅ Ajouté : {rel_path}")
                        continue

                    # /workspace remove <fichier>
                    elif action == 'remove':
                        if len(sub) < 2:
                            print("Usage: /workspace remove <fichier>")
                            continue

                        rel_path = sub[1]
                        if rel_path in mode_state['workspace_files']:
                            mode_state['workspace_files'].remove(rel_path)
                            print(f"🗑️ Retiré : {rel_path}")
                            # Note: pas de delete en DB, on recharge au prochain démarrage
                        else:
                            print(f"❌ Pas dans les fichiers actifs : {rel_path}")
                        continue

                    print(f"\n🌳 {target or '.'}\n")

                    # Skip ces dossiers
                    skip_dirs = {'__pycache__', '.git', 'node_modules', '.venv', 'venv', '.cache', '__pypackages__', '.idea', '.vscode'}

                    for root, dirs, files in os.walk(fullpath):
                        dirs[:] = [d for d in dirs if d not in skip_dirs]
                        dirs.sort()
                        files.sort()

                        # Calculer la profondeur pour l'indentation
                        depth = root.replace(fullpath, '').count(os.sep)
                        indent = '  ' * depth
                        dirname = os.path.basename(root) if depth > 0 else os.path.basename(fullpath)

                        if depth == 0:
                            print(f"{dirname}/")
                        else:
                            print(f"{indent}{dirname}/")

                        for f in files:
                            print(f"{indent}  {f}")
                    print()
                    continue

                elif cmd == '/edit':
                    if not args:
                        print("Usage: /edit <fichier>")
                        print("Exemple: /edit src/cli.py")
                        continue

                    filepath = args.strip()
                    fullpath = os.path.join(PROJECT_ROOT, filepath) if not os.path.isabs(filepath) else filepath

                    if not os.path.exists(fullpath):
                        print(f"❌ Fichier introuvable : {filepath}")
                        continue

                    if os.path.isdir(fullpath):
                        print(f"❌ C'est un dossier")
                        continue

                    import shutil

                    # Backup pour comparaison
                    backup_path = fullpath + ".fondation_backup"
                    shutil.copy2(fullpath, backup_path)

                    # Détecter l'éditeur
                    editor = shutil.which('nvim') or shutil.which('vim')
                    if not editor:
                        print("❌ Ni neovim ni vim détecté !")
                        print("Installe : sudo pacman -S neovim")
                        os.remove(backup_path)
                        continue

                    print(f"\n📝 [/edit] ÉDITION DE : {filepath}")
                    print(f"{'─'*60}")
                    print(f"  • NeoVim va se lancer sur ce fichier")
                    print(f"  • Édite normalement, sauvegarde avec :wq")
                    print(f"  • Au retour → diff + audit + commit\n")
                    input("Appuie sur [ENTER] pour ouvrir NeoVim...")

                    # Lancer l'éditeur
                    subprocess.call([editor, fullpath])
                    # Reset terminal après Vim
                    os.system('stty sane')

                    # ── RETOUR DE VIM ──
                    print(f"\n{'═'*60}")
                    print("RETOUR DE NEOVIM — ANALYSE")
                    print(f"{'═'*60}\n")

                    try:
                        with open(fullpath, 'r', encoding='utf-8') as f:
                            modified_content = f.read()

                        with open(backup_path, 'r', encoding='utf-8') as f:
                            original_content = f.read()

                        if modified_content == original_content:
                            print("ℹ️  Aucun changement détecté.")
                            os.remove(backup_path)
                            continue

                        # Diff
                        import difflib
                        diff_lines = list(difflib.unified_diff(
                            original_content.splitlines(keepends=True),
                            modified_content.splitlines(keepends=True),
                            fromfile=os.path.basename(filepath) + " (original)",
                            tofile=os.path.basename(filepath) + " (modifié)",
                            n=3
                        ))

                        print(f"{'━'*60}")
                        print("DIFF DES CHANGEMENTS")
                        print(f"{'━'*60}\n")
                        print(''.join(diff_lines))
                        print(f"\n{'─'*60}\n")

                        # Audit sécurité
                        response = input("Audit sécurité ? (y/n) > ").strip().lower()
                        if response in ['y', 'oui', 'yes']:
                            audit_script = os.path.join(PROJECT_ROOT, "scripts", "security_audit.py")
                            audit_proc = subprocess.run(
                                [PYTHON_INTERPRETER, audit_script, fullpath, "--offline"],
                                capture_output=True, text=True
                            )
                            print(audit_proc.stdout)

                            if audit_proc.returncode != 0:
                                warn = input("\n⚠️ Warnings détectés. Continuer ? (y/n) > ").strip().lower()
                                if warn not in ['y', 'oui', 'yes']:
                                    # Restaurer l'original
                                    shutil.move(backup_path, fullpath)
                                    print("↩️  Fichier restauré.")
                                    continue

                        # Commit
                        commit_response = input("Committer ? (y/n) > ").strip().lower()
                        if commit_response in ['y', 'oui', 'yes']:
                            description = input("Message de commit > ").strip() or "feat: mods via /edit"
                            success, message = auto_git_commit_secure(filepath, description)
                            if not success:
                                print(f"⚠️  {message}")

                        os.remove(backup_path)

                    except Exception as e:
                        print(f"❌ Erreur : {e}")
                        if os.path.exists(backup_path):
                            shutil.move(backup_path, fullpath)
                            print("↩️  Fichier restauré.")
                    continue


                elif cmd == '/audit':
                    print("\n[SECURITY AUDIT STARTED]")

                    target_path = args.strip() if args else os.path.join(PROJECT_ROOT, "src")

                    if not os.path.exists(target_path):
                        print(f"[ERROR] Chemin invalide : {target_path}")
                        continue

                    audit_script = os.path.join(PROJECT_ROOT, "scripts", "security_audit.py")

                    result = subprocess.run(
                        [PYTHON_INTERPRETER, audit_script, target_path, "--offline"],
                        capture_output=True, text=True
                    )

                    print(result.stdout)

                    if result.returncode != 0:
                        print(f"[WARN] Audit terminé avec warnings (code: {result.returncode})")

                    response = input("\n[AUDIT] Exporter rapport JSON ? (y/n) > ").strip().lower()
                    if response in ['y', 'oui']:
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        audit_dir = os.path.join(PROJECT_ROOT, "audits")
                        json_path = os.path.join(audit_dir, f"audit_{timestamp}.json")

                        os.makedirs(audit_dir, exist_ok=True)

                        result_json = subprocess.run(
                            [PYTHON_INTERPRETER, audit_script, target_path, "--json"],
                            capture_output=True, text=True
                        )

                        match = re.search(r'Rapport JSON exporté:\s*(\S+)', result_json.stdout)
                        if match:
                            source_json = match.group(1)
                            try:
                                with open(source_json, 'r') as src, open(json_path, 'w') as dst:
                                    dst.write(src.read())
                                os.remove(source_json)
                                print(f"✅ Exporté vers : {json_path}")
                            except FileNotFoundError:
                                print(f"⚠️ Fichier source introuvable : {source_json}")
                        else:
                            print("⚠️ Impossible de localiser le fichier JSON généré")
                            print(f"   Vérifie le dossier {audit_dir}")

                    continue

                elif cmd == '/history':
                    msgs = get_messages(mode_state['conversation_id'], limit=10)
                    if not msgs:
                        print("(Aucun message dans cette conversation)")
                    else:
                        print(f"\n--- Historique ({len(msgs)} messages) ---")
                        for m in msgs:
                            role = "toi" if m['role'] == 'user' else "IA"
                            content = m['content'][:100]
                            if len(m['content']) > 100:
                                content += "..."
                            print(f"  [{role}] {content}")
                        print()
                    continue


                elif cmd == '/sources':
                    msgs = get_messages(mode_state['conversation_id'], limit=5)
                    found = False
                    for m in msgs:
                        raw = m.get('rag_sources')
                        if raw:
                            if isinstance(raw, str):
                                try:
                                    parsed = json.loads(raw)
                                    # Double encodage : si c'est encore une string, on parse encore
                                    if isinstance(parsed, str):
                                        parsed = json.loads(parsed)
                                    sources = parsed
                                except json.JSONDecodeError:
                                    continue
                            elif isinstance(raw, list):
                                sources = raw
                            elif isinstance(raw, dict):
                                sources = [raw]
                            else:
                                continue
                            if sources and isinstance(sources, list):
                                print(f"  Message #{m['id']} :")
                                for s in sources:
                                    if isinstance(s, dict):
                                        print(f"    - {s.get('source', 'inconnu')}")
                                    else:
                                        print(f"    - {s}")
                                found = True
                    if not found:
                        print("(Aucune source RAG récente)")
                    continue

                elif cmd == '/help':
                    print(f"\nMode actuel : {mode_state['mode'].upper()}")
                    if mode_state.get('active_file'):
                        print(f"Fichier actif : {os.path.basename(mode_state['active_file'])}")
                    print("Commandes disponibles :")
                    print("  /mode [code|politique]       Changer de mode")
                    print("  /open <fichier>              Ouvrir un fichier en édition IA")
                    print("  /close                       Fermer le fichier actif")
                    print("  /apply [num]                 Appliquer une modification proposée")
                    print("  /multi                       Mode multi-lignes (terminer avec END)")
                    print("  /load <fichier|dossier>     Charger un fichier ou dossier projet")
                    print("  /files                       Lister les fichiers chargés")
                    print("  /unload                      Décharger tous les fichiers")
                    print("  /write [num] [chemin]       Extraire et sauvegarder un bloc de code")
                    print("  /fix <fichier> <commande>   Auto-correction compilation (boucle agentique)")
                    print("  /edit <fichier>             Éditer dans NeoVim + diff + audit + commit")
                    print("  /cat <fichier>             Afficher un fichier avec coloration")
                    print("  /audit <chemin>            Auditer sécurité dépendances")
                    print("  /history                     Historique récent")
                    print("  /sources                     Sources RAG utilisées")
                    print("  /menu                        Retour au menu projet")
                    print("  /quit                        Quitter Fondation")
                    print("  /clear                       Effacer l'écran")
                    print("  /workspace [chemin]          Définir/afficher le workspace du projet")
                    print("  /workspace add <fichier>     Ajouter un fichier actif au workspace")
                    print("  /workspace remove <fichier>  Retirer un fichier actif du workspace")
                    print("  /user                      - Gestion des utilisateurs (create/list/deactivate)")
                    print()
                    continue

                elif cmd == '/clear':
                    clear_screen()
                    print_banner()
                    continue


                elif cmd == '/write':
                    parts = args.split()
                    num_str = parts[0] if parts else None
                    chemin = parts[1] if len(parts) > 1 else None
                    
                    def get_blocks(text):
                        """Extrait les blocs de code markdown ``` ... ```."""
                        pattern = r'```(?:\w*)\s*\n(.*?)```'
                        return re.findall(pattern, text, re.DOTALL)
                    
                    # Cas 1: /write seul → liste les blocs disponibles
                    if not args or (not num_str and not chemin):
                        if not last_model_response:
                            print("(Pas de réponse modèle récente)")
                            continue
                        
                        blocs = get_blocks(last_model_response)
                        if not blocs:
                            print("(Aucun bloc de code trouvé dans la réponse)")
                            continue
                        
                        print(f"📝 Blocs détectés ({len(blocs)}):")
                        for i, bloc in enumerate(blocs[:10], 1):
                            preview = bloc[:60].replace('\n', '\\n')
                            print(f"  [{i}] {preview}...")
                        
                        if len(blocs) > 10:
                            print(f"... et {len(blocs)-10} autres")
                        continue
                    
                    # Cas 2: /write N → erreur, il faut un chemin aussi
                    if num_str and not chemin:
                        print("Usage: /write [num] [chemin]")
                        print("Exemple: /write 1 src/test.py")
                        continue
                    
                    # Cas 3: /write N chemin → écriture du bloc N au fichier
                    try:
                        num = int(num_str)
                        blocs = get_blocks(last_model_response)
                        
                        if not blocs or num > len(blocs):
                            print(f"(Bloc #{num} introuvable — disponible: 1-{len(blocs) if blocs else 0})")
                            continue
                        
                        contenu = blocs[num-1]
                        os.makedirs(os.path.dirname(chemin) or '.', exist_ok=True)
                        
                        with open(chemin, 'w', encoding='utf-8') as f:
                            f.write(contenu)
                        
                        print(f"✅ Écriture réussie: {chemin} ({len(contenu)} chars)")
                        continue
                    
                    except ValueError:
                        print("Numéro invalide")
                        continue
                    except Exception as e:
                        print(f"Erreur écriture: {e}")
                        continue

                elif cmd == '/apply':
                    if not mode_state.get('active_file'):
                        print("❌ Aucun fichier actif. Utilise /open <fichier> d'abord.")
                        continue

                    if not last_model_response:
                        print("(Aucune réponse récente. Pose d'abord une question.)")
                        continue


                    # Parser les blocs SEARCH/REPLACE
                    pattern = r'<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE'
                    patches_raw = re.findall(pattern, last_model_response, re.DOTALL)
                    patches = [(old.strip('\n'), new.strip('\n')) for old, new in patches_raw]

                    if not patches:
                        print("(Aucun bloc SEARCH/REPLACE trouvé dans la réponse)")
                        continue

                    # Sans args → lister
                    if not args:
                        print(f"\n✏️  Modifications détectées ({len(patches)}) :\n")
                        for i, (old, new) in enumerate(patches, 1):
                            old_preview = old[:60].replace('\n', '\\n')
                            new_preview = new[:60].replace('\n', '\\n')
                            print(f"  [{i}] OLD : {old_preview}...")
                            print(f"      NEW : {new_preview}...")
                        print(f"\nUtilise /apply <numéro> pour appliquer.")
                        continue

                    # Avec args → appliquer
                    try:
                        num = int(args.strip())
                    except ValueError:
                        print("Numéro invalide.")
                        continue

                    if num < 1 or num > len(patches):
                        print(f"Bloc #{num} introuvable. Disponible : 1-{len(patches)}")
                        continue

                    old_block, new_block = patches[num - 1]

                    # FIX BUG 1: Strip numéros de ligne venant du output SED (ex: "107: def foo:")
                    old_block = re.sub(r'^\d+:\s?', '', old_block, flags=re.MULTILINE)
                    new_block = re.sub(r'^\d+:\s?', '', new_block, flags=re.MULTILINE)

                    # FIX: Strip backticks markdown parasites
                    old_block = re.sub(r'^```[a-zA-Z]*\s*\n?', '', old_block).strip()
                    old_block = re.sub(r'\n?```\s*$', '', old_block).strip()
                    new_block = re.sub(r'^```[a-zA-Z]*\s*\n?', '', new_block).strip()
                    new_block = re.sub(r'\n?```\s*$', '', new_block).strip()


                    active_path = mode_state['active_file']

                    # Lire le VRAI fichier depuis le disque
                    try:
                        with open(active_path, 'r', encoding='utf-8', errors='ignore') as f:
                            file_content = f.read()
                    except Exception as e:
                        print(f"❌ Impossible de lire le fichier : {e}")
                        continue

                    if old_block not in file_content:
                        print(f"❌ Le bloc OLD n'a pas été trouvé dans le fichier.")
                        print(f"   - Le fichier a été modifié depuis /open")
                        print(f"   - Le modèle n'a pas copié le code exact")
                        continue

                    import shutil
                    backup_path = active_path + ".fondation_backup"
                    shutil.copy2(active_path, backup_path)

                    new_content = file_content.replace(old_block, new_block, 1)

                    # Diff
                    import difflib
                    diff_lines = list(difflib.unified_diff(
                        file_content.splitlines(keepends=True),
                        new_content.splitlines(keepends=True),
                        fromfile=os.path.basename(active_path),
                        tofile=os.path.basename(active_path),
                        n=3
                    ))

                    print(f"\n{'━'*60}\n{ ''.join(diff_lines)}\n{'━'*60}\n")

                    response = input("Appliquer ? (y/n) > ").strip().lower()
                    if response not in ['y', 'oui', 'yes']:
                        os.remove(backup_path)
                        continue

                    try:
                        with open(active_path, 'w', encoding='utf-8') as f:
                            f.write(new_content)
                        print(f"✅ Fichier modifié : {active_path}")
                    except Exception as e:
                        print(f"❌ Erreur écriture : {e}")
                        shutil.move(backup_path, active_path)
                        continue

                    audit_response = input("Audit sécurité ? (y/n) > ").strip().lower()
                    if audit_response in ['y', 'oui', 'yes']:
                        audit_script = os.path.join(PROJECT_ROOT, "scripts", "security_audit.py")
                        audit_proc = subprocess.run([PYTHON_INTERPRETER, audit_script, active_path, "--offline"], capture_output=True, text=True)
                        print(audit_proc.stdout)

                    commit_response = input("Committer ? (y/n) > ").strip().lower()
                    if commit_response in ['y', 'oui', 'yes']:
                        success, message = auto_git_commit_secure(active_path, "feat: modif via /apply")
                        if not success:
                            print(f"⚠️  {message}")

                    os.remove(backup_path)
                    continue


                elif cmd == '/fix':
                    """
                        /fix <fichier> <commande>: Boucle agentique auto-correction
                        Cycle: compile → capture erreurs → modèle corrige → écriture → recompile
                        - Max 5 itérations avant abandon
                        - Stop condition: compilation réussie (returncode 0)
                        - Extraction fallback: regex robuste si pas de backticks markdown
                    """
                    if not args:
                        print("Usage: /fix <fichier> <commande>")
                        print("Exemple: /fix /home/data/flotsam/src/server.cpp make")
                        continue

                    parts = args.split(maxsplit=1)
                    if len(parts) < 2:
                        print("Usage: /fix <fichier> <commande>")
                        print("Exemple: /fix /home/data/flotsam/src/server.cpp make")
                        continue

                    fix_filepath = parts[0]
                    fix_command = parts[1]

                    if not os.path.isfile(fix_filepath):
                        print(f"❌ Fichier introuvable : {fix_filepath}")
                        continue

                    MAX_ITERATIONS = 5
                    fix_mode = "code"

                    # Déterminer le répertoire de travail
                    work_dir = os.path.dirname(os.path.abspath(fix_filepath))

                    # Si "make", remonter pour trouver le Makefile
                    if fix_command.split()[0] == 'make':
                        test_dir = work_dir
                        for _ in range(5):
                            if os.path.isfile(os.path.join(test_dir, 'Makefile')):
                                work_dir = test_dir
                                break
                            parent = os.path.dirname(test_dir)
                            if parent == test_dir:
                                break
                            test_dir = parent

                    print(f"\n🔧 [/fix] Boucle de correction automatique")
                    print(f"   Fichier  : {fix_filepath}")
                    print(f"   Commande : {fix_command}")
                    print(f"   Work dir : {work_dir}")
                    print(f"   Max iter : {MAX_ITERATIONS}\n")

                    for iteration in range(1, MAX_ITERATIONS + 1):
                        print(f"{'─'*40}")
                        print(f"🔄 Itération {iteration}/{MAX_ITERATIONS}")
                        print(f"{'─'*40}")

                        # Étape 1: Compiler
                        print(f"[COMPILE] {fix_command} ...")
                        cmd_tokens = fix_command.split()

                        try:
                            compile_proc = subprocess.run(
                                cmd_tokens,
                                cwd=work_dir,
                                capture_output=True,
                                text=True,
                                timeout=30
                            )
                        except subprocess.TimeoutExpired:
                            print("❌ Timeout de compilation (30s)")
                            break
                        except Exception as e:
                            print(f"❌ Erreur lors de la compilation : {e}")
                            break

                        # Étape 2: Succès ?
                        if compile_proc.returncode == 0:
                            print(f"✅ Compilation réussie à l'itération {iteration} !")

                            response = input("\n[GIT] Committer la correction ? (y/n) > ").strip().lower()
                            if response in ['y', 'oui']:
                                success, message = auto_git_commit_secure(
                                    fix_filepath, f"fix: correction auto /fix iter {iteration}"
                                )
                                if not success:
                                    print(f"⚠️ {message}")
                            else:
                                print("Annulé. Tu peux commiter manuellement.")

                            break

                        # Étape 3: Capturer les erreurs
                        print(f"❌ Compilation échouée (code {compile_proc.returncode})")

                        stderr_output = compile_proc.stderr.strip()
                        stdout_output = compile_proc.stdout.strip()
                        error_output = stderr_output if stderr_output else stdout_output

                        if not error_output:
                            print("[WARN] Aucune sortie d'erreur capturée")
                            break

                        if len(error_output) > 3000:
                            error_output = "...(tronqué)...\n" + error_output[-3000:]

                        # Étape 4: Lire le fichier source
                        try:
                            with open(fix_filepath, 'r', encoding='utf-8') as f:
                                source_code = f.read()
                        except Exception as e:
                            print(f"❌ Impossible de lire le fichier : {e}")
                            break

                        # Étape 5: Construire le prompt
                        _, ext = os.path.splitext(fix_filepath)
                        lang_map = {
                            '.py': 'Python', '.cpp': 'C++', '.c': 'C', '.h': 'C/C++ header',
                            '.sh': 'Bash', '.rs': 'Rust', '.go': 'Go', '.js': 'JavaScript'
                        }
                        lang_name = lang_map.get(ext, 'code')
                        ext_clean = ext.lstrip('.')
                        tb = chr(96) * 3

                        fix_prompt = f"Tu es un expert en {lang_name}. Voici un fichier source qui ne compile pas.\n\n"
                        fix_prompt += f"## Fichier : {fix_filepath}\n\n"
                        fix_prompt += f"## Code source :\n{tb}{ext_clean}\n{source_code}\n{tb}\n\n"
                        fix_prompt += f"## Erreurs de compilation :\n{tb}\n{error_output}\n{tb}\n\n"
                        fix_prompt += "## Instruction :\n"
                        fix_prompt += "Analyse attentivement les erreurs de compilation. Identifie la cause précise de chaque erreur.\n"
                        fix_prompt += "Ensuite, fournis le code complet corrigé dans un seul bloc markdown. Ne donne pas d'explications avant le code.\n\n"
                        fix_prompt += "### ✅ Code corrigé"

                        # Étape 6: Envoyer au modèle
                        print(f"[MODEL] Envoi au modèle pour correction...")
                        print("[...] ", end="", flush=True)

                        model_response = send_to_model(fix_prompt, fix_mode)

                        if model_response.startswith("[ERROR]"):
                            print(f"\n❌ Erreur modèle : {model_response}")
                            break

                        print(f"\n{'─'*60}")
                        print_response(model_response)
                        print(f"{'─'*60}\n")

                        # ═══════════════════════════════════════════════════════
                        # ÉTAPE 7: EXTRAIRE LE CODE CORRIGÉ (ZONE À MODIFIER)
                        # ═══════════════════════════════════════════════════════

                        pattern_md = r'```\w*\s*\n(.*?)```'
                        blocs_code = re.findall(pattern_md, model_response, re.DOTALL)

                        # ✅ NOUVEAU CODE — COLLE CELA A LA PLACE :
                        if not blocs_code:
                            # Pattern robustisé avec limites de sécurité
                            pattern_fallback = r'### ✅.*?[Cc]ode.*?\n\n((?:.|\n)*?)(?:\n\n---|\n### |\[DONE\]|.{2500}\Z)'
                            raw_matches = re.findall(pattern_fallback, model_response, re.DOTALL)
                            
                            if raw_matches:
                                blocs_code = []
                                for m in raw_matches:
                                    m = m.strip()
                                    # Stop at [DONE] marker
                                    done_pos = m.find('[DONE]')
                                    if done_pos > 0:
                                        m = m[:done_pos].strip()
                                    # Length limit with smart truncation
                                    if len(m) > 2500:
                                        m = m[:2500]
                                        last_nl = m.rfind('\n')
                                        if last_nl > 2000:
                                            m = m[:last_nl]
                                        m += '\n... [tronqué]'
                                    # Minimum viable length
                                    if m and len(m) > 50:
                                        blocs_code.append(m)
                                if not blocs_code:
                                    blocs_code = None

                        # Fin de la zone à modifier
                        # ═══════════════════════════════════════════════════════

                        if not blocs_code:
                            print("❌ Aucun bloc de code trouvé dans la réponse du modèle")
                            break

                        # Prendre le bloc le plus long (le code complet corrigé)
                        corrected_code = max(blocs_code, key=len)

                        # Étape 8: Écrire le code corrigé
                        try:
                            with open(fix_filepath, 'w', encoding='utf-8') as f:
                                f.write(corrected_code)
                            print(f"✅ Fichier corrigé écrit : {fix_filepath} ({len(corrected_code)} chars)")
                        except Exception as e:
                            print(f"❌ Impossible d'écrire le fichier : {e}")
                            break

                        # La boucle continue -> recompile à l'itération suivante

                    else:
                        # for...else : la boucle a épuisé ses 5 itérations sans succès
                        print(f"\n❌ Échec après {MAX_ITERATIONS} itérations. La compilation échoue toujours.")
                        print("Tu devras corriger manuellement ou affiner le prompt.")

                    continue

                else:
                    print(f"Commande inconnue : {cmd}. Tape /help")
                    continue

            from src.core import process_message

            ai_content, rag_sources = process_message(
                user_input,
                mode_state['conversation_id'],
                mode_state,
                callbacks={
                    'progress': lambda msg='': print("[...] ", end="", flush=True),
                    'rag': lambda n: print(f"[RAG] {n} source(s)"),
                    'files': lambda n: print(f"[FILES] {n} fichier(s) en contexte"),
                    'tool': lambda log: print(f"\n🔧 OUTILS : {log}"),
                    'route': lambda info: print(f"\n🔀 [ROUTE] Demerzel → Coder : {info['type']} {info.get('target','')} {info.get('file','')}"),
                }
            )

            print(f"\n{'─'*60}")
            print_response(ai_content)
            print(f"{'─'*60}\n")

            if not ai_content.startswith("[ERROR]"):
                last_model_response = ai_content

        except KeyboardInterrupt:
            print("\n[CTRL+C] Tape /quit pour sortir, /menu pour revenir")
            continue

        except EOFError:
            print("\n[CTRL+D] Retour au menu projet.")
            return 'menu'

        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}")
            continue


def main():
    init_db()
    # User admin local pour le CLI
    from src.db import authenticate_user, create_invite, register_user
    admin_uid = authenticate_user("local_cli_admin_token", name="admin")
    if not admin_uid:
        invite = create_invite()
        admin_uid = register_user("admin", "local_cli_admin_token", invite)
    mode_state = {
        'project_id': None,
        'project': None,
        'conversation_id': None,
        'mode': 'politique',
        'loaded_files': {},
        'active_file': None,
        'workspace_path': None,
        'workspace_id': None,
        'workspace_files': [],
        'user_id': admin_uid,
    }

    print_banner()

    while True:
        if not mode_state['project_id']:
            show_main_menu()
            choice = input("> ").strip()

            if choice == '1':
                projects = list_projects(mode_state['user_id'])
                if not projects:
                    print("Aucun projet. Crée-en un !")
                else:
                    for p in projects:
                        print(f"  #{p['id']} - {p['name']} ({p.get('description', '')})")

            elif choice == '2':
                name = input("Nom du projet > ").strip()
                if not name:
                    print("Nom requis.")
                    continue
                desc = input("Description (optionnelle) > ").strip()
                pid = create_project(mode_state['user_id'], name, desc, 'politique')
                print(f"✅ Projet créé ! ID : {pid}")

            elif choice == '3':
                projects = list_projects(mode_state['user_id'])
                if not projects:
                    print("Aucun projet disponible.")
                    continue

                for p in projects:
                    print(f"  #{p['id']} - {p['name']} ({p.get('description', '')})")

                try:
                    proj_num = int(input("Numéro du projet > "))
                    project = get_project(proj_num, mode_state['user_id'])
                    if not project:
                        print("Projet introuvable.")
                        continue

                    mode_state['project_id'] = project['id']
                    mode_state['project'] = project

                    while True:
                        show_project_menu(mode_state)
                        sub_choice = input("> ").strip()

                        if sub_choice == '1':
                            print("[1] code  [2] politique")
                            mode_choice = input("Mode > ").strip()
                            modes = {'1': 'code', '2': 'politique'}
                            if mode_choice in modes:
                                mode_state['mode'] = modes[mode_choice]
                                print(f"✅ Mode : {mode_state['mode'].upper()}")
                            else:
                                print("Choix invalide.")

                        elif sub_choice == '2':
                            conversations = list_conversations(project['id'])
                            if not conversations:
                                print("Aucune conversation.")
                            else:
                                for c in conversations:
                                    msg_count = len(get_messages(c['id']))
                                    print(f"  #{c['id']} - {c['title']} ({msg_count} msgs)")

                        elif sub_choice == '3':
                            title = input("Titre de la conversation > ").strip()
                            if not title:
                                title = f"Conv du {datetime.now().strftime('%d/%m %H:%M')}"
                            cid = create_conversation(project['id'], title)
                            mode_state['conversation_id'] = cid
                            print(f"✅ Conversation créée : #{cid}")
                            result = run_chat_loop(mode_state)
                            if result == 'quit':
                                save_cli_history()
                                print("Au revoir camarade !")
                                sys.exit(0)

                        elif sub_choice == '4':
                            conversations = list_conversations(project['id'])
                            if not conversations:
                                print("Aucune conversation à reprendre.")
                                continue

                            for c in conversations:
                                msg_count = len(get_messages(c['id']))
                                print(f"  #{c['id']} - {c['title']} ({msg_count} msgs)")

                            try:
                                conv_num = int(input("Numéro de conversation > "))
                                conv_exists = any(c['id'] == conv_num for c in conversations)
                                if conv_exists:
                                    mode_state['conversation_id'] = conv_num
                                    print(f"✅ Reprise de la conversation #{conv_num}")
                                    result = run_chat_loop(mode_state)
                                    if result == 'quit':
                                        save_cli_history()
                                        print("Au revoir camarade !")
                                        sys.exit(0)
                                else:
                                    print("Conversation introuvable.")
                            except ValueError:
                                print("Numéro invalide.")

                        elif sub_choice == '5':
                            mode_state['project_id'] = None
                            mode_state['project'] = None
                            mode_state['conversation_id'] = None
                            break

                        elif sub_choice == '6':
                            confirm = input("Sûr ? (oui/non) > ").strip().lower()
                            if confirm in ['oui', 'o', 'yes', 'y']:
                                delete_project(project['id'], mode_state['user_id'])
                                mode_state['project_id'] = None
                                mode_state['project'] = None
                                mode_state['conversation_id'] = None
                                break
                            else:
                                print("Annulé.")

                        else:
                            print("Choix invalide.")

                except ValueError:
                    print("Numéro invalide.")

            elif choice == '4':
                save_cli_history()
                print("Au revoir camarade !")
                sys.exit(0)

            else:
                print("Choix invalide.")


if __name__ == "__main__":
    try:
        main()
    except EOFError:
        print("\n[CTRL+D] Fermeture propre.")
        save_cli_history()
        sys.exit(0)
