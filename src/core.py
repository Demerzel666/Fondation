# src/core.py
# =============================================================================
# ENGINE PARTAGÉ — Logique de chat indépendante de l'interface
# Utilisé par cli.py (terminal) et web/app.py (navigateur)
# =============================================================================
# v2 — MIGRATION MESSAGES ROLÉS :
# - build_prompt() retourne "messages" (liste rolée) — voie principale
# - send_to_model() accepte une liste de messages OU une string (fallback)
# - manage_server() ne tue les serveurs QUE si le bon modèle n'est pas actif
# - Le message user est sauvegardé APRÈS build_prompt (sinon doublon dans
#   l'historique envoyé au modèle)
# - Plus de "full_prompt" : tout part en messages rolés, llama-server
#   applique lui-même le chat template Qwen.

import os
import re
import requests
import subprocess
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── CONFIGURATION SERVEURS ──────────────────────────────────────
LLAMA_CODER_URL = "http://localhost:8081/v1/chat/completions"
LLAMA_DEMERZEL_URL = "http://localhost:8080/v1/chat/completions"
SCRIPT_CODER = os.path.join(PROJECT_ROOT, "scripts", "start_coder_v2.sh")
SCRIPT_DEMERZEL = os.path.join(PROJECT_ROOT, "scripts", "start_demerzel.sh")


# ── GESTION DES SERVEURS ────────────────────────────────────────

def check_server(url):
    """Vérifie si un serveur est prêt."""
    try:
        r = requests.get(url, timeout=2)
        return r.status_code == 200
    except:
        return False


def kill_all_servers():
    """Tue tous les serveurs llama-server."""
    subprocess.run(["pkill", "-9", "llama-server"], capture_output=True)
    time.sleep(2)


def manage_server(target_mode):
    """Démarre le serveur du mode cible SEULEMENT s'il n'est pas déjà actif."""
    if target_mode == "code":
        health_url = "http://localhost:8081/health"
        script_start = SCRIPT_CODER
        target_name = "CODER"
        expected_port = 8081
    else:
        health_url = "http://localhost:8080/health"
        script_start = SCRIPT_DEMERZEL
        target_name = "DEMERZEL"
        expected_port = 8080

    # Déjà actif ? Rien à faire (sinon chaque message = reload complet)
    if check_server(health_url):
        return True

    print(f"\n[ORCHESTRATEUR] Arrêt des serveurs en cours...")
    kill_all_servers()

    print(f"[ORCHESTRATEUR] Démarrage de {target_name} sur le port {expected_port}...")
    subprocess.Popen(
        [script_start],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    print(f"[ORCHESTRATEUR] Chargement du modèle...", end="", flush=True)
    for i in range(60):
        time.sleep(3)
        print(".", end="", flush=True)
        if check_server(health_url):
            print(f"\n[READY] {target_name} actif sur port {expected_port}.\n")
            return True

    print(f"\n[ERROR] Échec démarrage après 3 minutes (port {expected_port})")
    return False


def send_to_model(payload, mode):
    """Envoie au bon serveur (avec lock inter-processus).

    payload : liste de messages rolés [{"role": ..., "content": ...}]
              OU string legacy (enveloppée en message user).
    """
    from src.queue_manager import acquire_model_lock, release_model_lock

    # Attendre le lock (max 5 min)
    for i in range(300):
        if acquire_model_lock():
            break
        time.sleep(1)
    else:
        return "[ERROR] Modèle occupé trop longtemps (>5 min)"

    try:
        url = LLAMA_CODER_URL if mode == "code" else LLAMA_DEMERZEL_URL
        manage_server(mode)

        payload_messages = (
            payload
            if isinstance(payload, list)
            else [{"role": "user", "content": payload}]
        )

        response = requests.post(url, json={
            "model": "default",
            "messages": payload_messages,
            "temperature": 0.7,
            "max_tokens": 16384
        }, timeout=600)

        if response.status_code != 200:
            return f"[ERROR] Serveur retourné {response.status_code}: {response.text[:200]}"

        return response.json()['choices'][0]['message']['content']
    except requests.exceptions.ConnectionError:
        return f"[ERROR] Impossible de contacter le serveur ({url}). Est-il lancé ?"
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}"
    finally:
        release_model_lock()


# ── UTILITAIRES ──────────────────────────────────────────────────

def generate_file_map(filepath):
    """Génère un plan structural du fichier (déf/class/if __name__)."""
    structure_patterns = [
        r'^\s*def\s+\w+',
        r'^\s*class\s+\w+',
        r'^\s*if\s+__name__',
        r'^\s*async\s+def\s+\w+',
    ]
    map_lines = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f, 1):
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue
                for pattern in structure_patterns:
                    if re.match(pattern, line):
                        code_part = line.split('#')[0].rstrip()
                        map_lines.append(f"Ligne {i}: {code_part}")
                        break
    except Exception as e:
        return f"[ERREUR génération file_map: {e}]"
    return '\n'.join(map_lines)


# ── PIPELINE PRINCIPAL ───────────────────────────────────────────

def process_message(user_input, conversation_id, mode_state, callbacks=None):
    """Pipeline complet : contexte → RAG → messages rolés → modèle.

    Returns: (response_text, rag_sources_list)
    """
    from src.db import add_message
    from src.context import build_prompt, save_response

    if callbacks is None:
        callbacks = {}

    def cb(name, *args):
        fn = callbacks.get(name)
        if fn:
            fn(*args)

    # 1. Construire les messages (system + historique + question courante)
    context_result = build_prompt(
        conversation_id,
        user_input,
        mode=mode_state['mode'],
        loaded_files=mode_state.get('loaded_files')
    )

    if context_result['rag_sources']:
        cb('rag', len(context_result['rag_sources']))

    if context_result.get('loaded_files'):
        cb('files', context_result['loaded_files'])

    api_messages = context_result['messages']

    # 2. Sauvegarder le message utilisateur APRÈS build_prompt
    #    (sinon il serait dupliqué : historique + question courante)
    add_message(conversation_id, "user", user_input)

    # 3. Fichier actif → annexé au system prompt
    if mode_state.get('active_file'):
        active_name = os.path.basename(mode_state['active_file'])
        active_path = mode_state['active_file']
        file_map = mode_state.get('file_map', '')

        api_messages[0]["content"] += (
            f"\n\n[FICHIER ACTIF] {active_name}\n"
            f"Chemin : {active_path}\n"
            f"Structure du fichier :\n{file_map}\n\n"
            f"Pour modifier ce fichier, utilise le format SEARCH/REPLACE :\n"
            f"<<<<<<< SEARCH\n"
            f"(code exact à trouver dans le fichier, espaces inclus)\n"
            f"=======\n"
            f"(nouveau code qui remplace le SEARCH)\n"
            f">>>>>>> REPLACE\n\n"
            f"Règles :\n"
            f"1. LIS le code avec [FUNC] ou [SED] AVANT de proposer un patch\n"
            f"2. Copie EXACTEMENT le code original dans SEARCH\n"
            f"3. Ne mets PAS de backticks markdown\n"
            f"4. Un bloc par modification\n"
        )

    # 4. Workspace → annexé au system prompt
    if mode_state.get('workspace_files') and mode_state.get('workspace_path'):
        ws_path = mode_state['workspace_path']
        ws_files = mode_state['workspace_files']

        file_maps = []
        for rel_path in ws_files:
            full_path = os.path.join(ws_path, rel_path)
            if os.path.isfile(full_path):
                fmap = generate_file_map(full_path)
                if fmap:
                    file_maps.append(f"--- {rel_path} ---\n{fmap}")

        if file_maps:
            api_messages[0]["content"] += (
                f"\n\n[WORKSPACE] {ws_path}\n"
                f"Fichiers actifs ({len(ws_files)}) :\n"
                f"{chr(10).join(file_maps)}\n\n"
                f"Pour modifier un fichier, utilise le format SEARCH/REPLACE.\n"
                f"Utilise [FUNC:chemin|nom_fonction] pour lire une fonction avant de proposer un patch.\n"
            )

    # 5. Envoyer au modèle (messages rolés)
    if os.environ.get("DEMERZEL_DEBUG"):
        cb('progress', '...')
        print("\n===== DEBUG : SYSTEM PROMPT RÉEL ENVOYÉ =====")
        print(api_messages[0]["content"][:3000])
        print(f"... (total : {len(api_messages[0]['content'])} chars)")
        print("===== FIN DEBUG =====\n")


    ai_content = send_to_model(
        api_messages,
        context_result.get('mode_used', mode_state['mode'])
    )

    # 6. Route interception (Demerzel → Coder)
    route_intercepted = False
    if '[ROUTE:' in ai_content:
        from src.tools import tool_grep, tool_sed, tool_read

        route_match = re.search(r'\[ROUTE:(\w+)(?::(.+?))?(?:\|file:(.+?))?\]', ai_content)
        if route_match:
            route_type = route_match.group(1)
            route_target = route_match.group(2) or ""
            route_file = route_match.group(3) or ""

            cb('route', {
                'type': route_type,
                'target': route_target,
                'file': route_file
            })

            code_content = ""
            code_range = ""

            if route_type == 'function' and route_file:
                grep_result = tool_grep(f"def {route_target}", route_file)
                first_line_match = re.match(r'(\d+):', grep_result.strip())
                if first_line_match:
                    first_line = int(first_line_match.group(1))
                    end_line = first_line + 200
                    code_content = tool_sed(route_file, first_line, end_line)
                    code_range = f"lignes {first_line}-{end_line}"

            elif route_type == 'file' and route_file:
                code_content = tool_read(route_file)
                code_range = "complet"

            mode_state['mode'] = 'code'

            coder_content = f"L'utilisateur a demandé : \"{user_input}\"\n\n"
            if code_content:
                coder_content += (
                    f"Voici le code réel extrait depuis le disque :\n\n"
                    f"--- {route_file} ({code_range}) ---\n"
                    f"{code_content}\n\n---\n\n"
                )
                if mode_state.get('active_file'):
                    coder_content += (
                        f"\n[FICHIER ACTIF] {os.path.basename(mode_state['active_file'])}\n"
                        f"Si tu proposes des modifications, utilise ce format EXACT :\n"
                        f"<<< OLD\n(ancien code exact)\n"
                        f">>> NEW\n(nouveau code)\n"
                    )
                coder_content += "Réponds à la demande de l'utilisateur en utilisant ce code réel."
            else:
                coder_content += f"Tâche : {route_target}\n\nRéponds à la demande de l'utilisateur."

            coder_messages = [{"role": "user", "content": coder_content}]

            cb('progress', '...')
            ai_content = send_to_model(coder_messages, 'code')
            route_intercepted = True

    # 7. Boucle agent (si mode code)
    if mode_state['mode'] == "code" and not ai_content.startswith("[ERROR]") and not route_intercepted:
        from src.tools import extract_tools, execute_tools

        if mode_state.get('active_file'):
            ai_content = re.sub(r'\[(?:EDIT|WRITE):[^\]]*\]', '', ai_content).strip()

        agent_max_iter = 10
        agent_system = api_messages[0]["content"]  # system prompt + contexte code
        read_files = set()

        for agent_iter in range(agent_max_iter):
            tools_found = extract_tools(ai_content)

            if not tools_found:
                break

            t_type, t_target, t_content = tools_found[0]

            if t_type == 'READ' and t_target in read_files:
                tool_results = "(fichier déjà lu précédemment)"
                agent_instruction = (
                    "Voici le contenu du fichier demandé.\n\n"
                    f"{tool_results}\n\n"
                    "Réponds UNIQUEMENT avec ce contenu, sans aucun tag. "
                    "Copie-colle le contenu du fichier puis termine avec [DONE]"
                )
            else:
                if t_type == 'READ':
                    read_files.add(t_target)

                if t_type == 'FUNC':
                    fake_resp = f"[FUNC:{t_target}|{t_content}]"
                else:
                    fake_resp = f"[{t_type}:{t_target}]"
                    if t_content:
                        fake_resp += f"\n{t_content}"

                tool_log, tool_results = execute_tools(fake_resp)

                if tool_log:
                    cb('tool', f"{tool_log} ({agent_iter+1}/{agent_max_iter})")

                if t_type == 'GREP':
                    agent_instruction = (
                        f"[REQUÊTE UTILISATEUR]\n{user_input}\n\n"
                        f"[RÉSULTAT GREP]\n{tool_results}\n\n"
                        f"Tu as les numéros de ligne des fonctions trouvées.\n"
                        f"Utilise [FUNC:chemin|nom_fonction] pour extraire la fonction complète.\n"
                        f"Ou [SED:chemin|start|end] si tu veux lire un range précis.\n\n"
                    )
                elif t_type == 'FUNC':
                    agent_instruction = (
                        f"[REQUÊTE UTILISATEUR]\n{user_input}\n\n"
                        f"[RÉSULTAT FUNC]\n{tool_results}\n\n"
                        f"Affiche le contenu de la fonction à l'utilisateur.\n"
                        f"Termine avec [DONE].\n\n"
                    )
                else:
                    agent_instruction = (
                        f"[REQUÊTE UTILISATEUR]\n{user_input}\n\n"
                        f"[RÉSULTAT DE L'OUTIL]\n{tool_results}\n\n"
                    )

            if mode_state.get('active_file'):
                agent_instruction += (
                    f"Tu as maintenant le contenu demandé.\n"
                    f"Consulte la file_map du fichier actif pour identifier les bonnes lignes.\n"
                    f"PROPOSE une modification avec ce format EXACT :\n"
                    f"<<<<<<< SEARCH\n(ancien code exact)\n"
                    f"=======\n(nouveau code)\n"
                    f">>>>>>> REPLACE\n"
                )
            else:
                agent_instruction += (
                    f"Tu as maintenant le contenu demandé. "
                    f"AFFICHE le contenu à l'utilisateur dans ta réponse. "
                    f"Ne mets PLUS de tags [READ] ou [LS]. "
                    f"Écris ta réponse normale puis termine avec [DONE]."
                )

            agent_messages = [
                {"role": "system", "content": agent_system},
                {"role": "user", "content": agent_instruction}
            ]

            cb('progress', '...')
            ai_content = send_to_model(
                agent_messages,
                context_result.get('mode_used', mode_state['mode'])
            )

            if ai_content.startswith("[ERROR]"):
                break

            if not extract_tools(ai_content):
                break
        else:
            cb('tool', f"⚠️ Limite atteinte ({agent_max_iter} itérations)")

        ai_content = re.sub(r'\[(?:READ|LS|WRITE|EDIT|DONE|PAGE):?[^\]]*\]', '', ai_content).strip()

    # 8. Sauvegarder la réponse
    if not ai_content.startswith("[ERROR]"):
        save_response(
            conversation_id,
            ai_content,
            rag_sources=context_result['rag_sources']
        )

    return ai_content, context_result['rag_sources']
