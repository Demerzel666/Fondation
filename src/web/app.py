# src/web/app.py
# =============================================================================
# Serveur Flask pour Fondation-IA — HTML pur, zero JS
# =============================================================================

import os
import sys
from flask import (
    Flask, render_template, render_template_string, request, session,
    redirect, url_for, flash, g, jsonify
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'foundation-secret-key-change-in-production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

from src.web.auth import validate_session

from functools import wraps

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('login'))
        g.user_id = user_id
        return f(*args, **kwargs)
    return decorated

# ── MANIFESTE ────────────────────────────────────────────────────────────────

@app.route('/manifeste')
def manifeste():
    return render_template('manifeste.html')

# ── AUTH ───────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        token = request.form.get('token', '').strip()
        name = request.form.get('name', '').strip()

        if not token:
            return render_template('login.html', error='Token requis')

        user_id = validate_session(token)
        if user_id is None:
            return render_template('login.html', error='Token invalide')

        session['user_id'] = user_id
        session['username'] = name or 'anonyme'
        session['token'] = token
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Inscription avec code d'invite."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        token = request.form.get('token', '').strip()
        invite_code = request.form.get('invite_code', '').strip()
        
        if not name or not token or not invite_code:
            return "Nom, token et code d'invite requis", 400
        
        from src.db import register_user, is_invite_valid
        
        # Vérifier le code d'invite
        if not is_invite_valid(invite_code):
            return "Code d'invitation invalide ou déjà utilisé", 400
        
        # Créer l'utilisateur
        user_id = register_user(name, token, invite_code)
        if user_id is None:
            return "Erreur : nom déjà pris", 400
        
        # Login automatique
        session['user_id'] = user_id
        session['username'] = name
        return redirect(url_for('index'))
    
    # Page de formulaire GET
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Inscription - Fondation-IA</title>
    <link rel="stylesheet" href="/static/style.css">
    <style>
        body {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            font-family: monospace;
            background: linear-gradient(135deg, #0d0d1a 0%, #1a1a2e 100%);
        }
        form {
            background: #161625;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.5);
            max-width: 400px;
            width: 100%;
        }
        input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            background: #0d0d1a;
            border: 1px solid #6d4aff;
            border-radius: 6px;
            color: #fff;
            font-family: monospace;
            box-sizing: border-box;
        }
        button {
            width: 100%;
            padding: 14px;
            margin-top: 20px;
            background: #6d4aff;
            color: #fff;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 16px;
        }
        button:hover {
            background: #8a5eff;
        }
        h1 {
            color: #6d4aff;
            text-align: center;
            margin-bottom: 30px;
        }
    </style>
</head>
<body>
    <form method="POST">
        <h1>🚀 Inscription Fondation-IA</h1>
        <label>Nom d'utilisateur *</label>
        <input type="text" name="name" placeholder="Choisis un nom" required>
        
        <label>Token (mot de passe) *</label>
        <input type="password" name="token" placeholder="Crée ton token" required>
        
        <label>Code d'invitation *</label>
        <input type="text" name="invite_code" placeholder="Code donné par l'admin" required>
        
        <button type="submit">S'inscrire</button>
    </form>
</body>
</html>
''')

# ── MAIN ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    from src.db import list_projects, list_conversations, get_messages

    projects = list_projects(user_id)
    project_id = request.args.get('project', type=int)
    conv_id = request.args.get('conv', type=int)

    conversations = []
    messages = []

    if project_id:
        conversations = list_conversations(project_id)
    if conv_id:
        all_messages = get_messages(conv_id)
        messages = all_messages[-6:] if len(all_messages) > 6 else all_messages
    else:
        all_messages = []

    # Affichage normal du chat
    return render_template('chat.html',
        username=session.get('username', ''),
        projects=projects,
        conversations=conversations,
        messages=messages,
        current_project=int(project_id) if project_id else None,
        current_conv=conv_id,
    )

# ── ACTIONS ──────────────────────────────────────────────────────────────────

from flask import Response

@app.route('/send', methods=['POST'])
@require_auth
def send_message():
    from src.db import get_conn, add_message
    from src.queue_manager import enqueue_request
    
    user_id = session.get('user_id')
    conv_id = request.form.get('conversation_id')
    project_id = request.form.get('project_id')
    message = request.form.get('text', '').strip()
    
    if not message or not conv_id:
        return "Message vide ou conversation invalide", 400
   
   # Sauvegarder le message utilisateur immédiatement
    add_message(conv_id, 'user', message)

    # Priorité admin
    conn = get_conn()
    row = conn.execute('SELECT role FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    priority = 'admin' if row and row[0] == 'admin' else 'normal'
    
    # Enregistrer dans la queue et rediriger vers le polling
    req_id, position = enqueue_request(user_id, conv_id, message, priority)
    return redirect(url_for('queue_wait', req_id=req_id, project=project_id))

@app.route('/queue/<int:req_id>')
@require_auth
def queue_wait(req_id):
    from src.queue_manager import get_request_status, complete_request
    from src.db import get_conn, add_message
    from src.core import send_to_model
    
    user_id = session.get('user_id')
    project_id = request.args.get('project', '')
    
    conn = get_conn()
    req = conn.execute(
        'SELECT user_id, conversation_id, message_content FROM queue_requests WHERE id = ?',
        (req_id,)
    ).fetchone()
    conn.close()
    
    if not req:
        return "Requête introuvable", 404
    
    if req['user_id'] != user_id:
        return "Accès refusé", 403
    
    conv_id = req['conversation_id']
    message = req['message_content']
    
    status, ahead = get_request_status(req_id)
    
    # Déjà terminé
    if status == 'completed':
        return redirect(url_for('index', project=project_id, conv=conv_id) + '#last-msg')
    
    # Échoué
    if status == 'failed':
        return "❌ Erreur lors du traitement précédent", 500
    
    # Quelqu'un devant → bulle "Position X"
    if ahead > 0:
        return render_template('chat.html',
            username=session.get('username', ''),
            projects=[],
            conversations=[],
            messages=[],
            current_project=int(project_id) if project_id else None,
            current_conv=conv_id,
            thinking=True,
            queue_position=ahead + 1,
            thinking_refresh=True,
            thinking_refresh_seconds=3,
            thinking_refresh_url=f'/queue/{req_id}?project={project_id}',
        )
    
    # Deuxième passe (process=1) → afficher "Demerzel réfléchit"
    if request.args.get('process') == '1':
        return render_template('chat.html',
            username=session.get('username', ''),
            projects=[],
            conversations=[],
            messages=[],
            current_project=int(project_id) if project_id else None,
            current_conv=conv_id,
            thinking=True,
            thinking_refresh=True,
            thinking_refresh_seconds=1,
            thinking_refresh_url=f'/queue/{req_id}?project={project_id}&process=2',
        )
    
    # Troisième passe (process=2) → traiter
    if request.args.get('process') == '2':
        try:
            response = send_to_model(
                message,
                mode=session.get('mode', 'politique')
            )
            
            if not response.startswith("[ERROR]"):
                add_message(conv_id, 'assistant', response)
            
            complete_request(req_id, response_text=response)
            return redirect(url_for('index', project=project_id, conv=conv_id) + '#last-msg')
        except Exception as e:
            complete_request(req_id, error_message=str(e))
            return f"❌ Erreur: {e}", 500
    
    # Première passe → "Position 1"
    return render_template('chat.html',
        username=session.get('username', ''),
        projects=[],
        conversations=[],
        messages=[],
        current_project=int(project_id) if project_id else None,
        current_conv=conv_id,
        thinking=True,
        queue_position=1,
        thinking_refresh=True,
        thinking_refresh_seconds=1,
        thinking_refresh_url=f'/queue/{req_id}?project={project_id}&process=1',
    )

@app.route('/project/new', methods=['POST'])
def new_project():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    name = request.form.get('name', '').strip()
    if not name:
        return redirect(url_for('index'))

    from src.db import create_project
    pid = create_project(user_id, name)
    return redirect(url_for('index', project=pid))


@app.route('/conversation/new', methods=['POST'])
def new_conversation():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    project_id = request.form.get('project_id', type=int)
    title = request.form.get('title', '').strip()

    if not project_id:
        return redirect(url_for('index'))

    from src.db import create_conversation
    cid = create_conversation(project_id, title)
    return redirect(url_for('index', project=project_id, conv=cid))

# ── API ROUTES COMPLÉMENTAIRES ─────────────────────────────────────────────

@app.route('/api/project/<int:project_id>', methods=['DELETE'])
@require_auth
def delete_project_api(project_id):
    from src.db import delete_project, get_project

    project = get_project(project_id, g.user_id)
    if not project:
        return jsonify({'error': 'Projet introuvable'}), 404

    delete_project(project_id, g.user_id)
    return jsonify({'success': True})


@app.route('/api/conversation/<int:conv_id>', methods=['DELETE'])
@require_auth
def delete_conversation_api(conv_id):
    from src.db import delete_conversation, list_conversations

    # Vérifier que la conv appartient à un projet du user
    convs = list_conversations(g.user_id)  # faut filtrer
    conv = None
    for c in convs:
        if c['id'] == conv_id:
            conv = c
            break
    if not conv:
        return jsonify({'error': 'Conversation introuvable'}), 404

    delete_conversation(conv_id)
    return jsonify({'success': True})


@app.route('/api/users', methods=['GET'])
@require_auth
def list_users():
    # Admin-only : liste tous les utilisateurs (pour gestion)
    from src.db import get_conn
    conn = get_conn()
    users = conn.execute('SELECT id, name, active FROM users').fetchall()
    conn.close()
    return jsonify({'users': [{'id': u['id'], 'name': u['name'], 'active': u['active']} for u in users]})


@app.route('/api/user/create', methods=['POST'])
@require_auth
def api_create_user():
    # Créer un nouvel utilisateur (admin)
    from src.db import create_invite, register_user

    name = request.json.get('name', '').strip()
    token = request.json.get('token', '').strip()

    if not name or not token:
        return jsonify({'error': 'Nom et token requis'}), 400

    invite = create_invite()
    uid = register_user(name, token, invite)

    if uid is None:
        return jsonify({'error': 'Erreur création (nom existant?)'}), 400

    return jsonify({'success': True, 'user_id': uid, 'invite_code': invite})

@app.route('/project/delete/<int:project_id>', methods=['POST'])
def delete_project(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    from src.db import delete_project
    delete_project(project_id, user_id)
    return redirect(url_for('index'))


@app.route('/conversation/delete/<int:conv_id>', methods=['POST'])
def delete_conversation(conv_id):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    project_id = request.form.get('project_id', type=int)

    from src.db import delete_conversation
    delete_conversation(conv_id)

    if project_id:
        return redirect(url_for('index', project=project_id))
    return redirect(url_for('index'))

@app.route('/project/context/<int:project_id>', methods=['GET', 'POST'])
def edit_project_context(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    from src.db import get_project_context, update_project_context, get_project, list_projects

    projects = list_projects(user_id)
    project = get_project(project_id, user_id)
    if not project:
        return redirect(url_for('index'))

    if request.method == 'POST':
        context_text = request.form.get('context', '').strip()
        update_project_context(project_id, context_text)
        return redirect(url_for('index', project=project_id))

    context = get_project_context(project_id)
    return render_template('chat.html',
        username=session.get('username', ''),
        projects=projects,
        conversations=[],
        messages=[],
        current_project=project_id,
        current_conv=None,
        editing_context=True,
        context_text=context,
        context_type='project',
    )

@app.route('/global-context', methods=['GET', 'POST'])
def edit_global_context():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    from src.db import get_global_context, set_global_context, list_projects

    projects = list_projects(user_id)

    if request.method == 'POST':
        context_text = request.form.get('context', '').strip()
        set_global_context(context_text)
        return redirect(url_for('index'))

    context = get_global_context()
    return render_template('chat.html',
        username=session.get('username', ''),
        projects=projects,
        conversations=[],
        messages=[],
        current_project=None,
        current_conv=None,
        editing_context=True,
        context_text=context,
        context_type='global',
    )

@app.route('/history/<int:conv_id>')
def full_history(conv_id):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    from src.db import get_messages, list_projects
    messages = get_messages(conv_id)
    projects = list_projects(user_id)

    return render_template('chat.html',
        username=session.get('username', ''),
        projects=projects,
        conversations=[],
        messages=messages,
        current_project=None,
        current_conv=conv_id,
        full_history=True,
    )

if __name__ == '__main__':
    print("[FLASK] Démarrage sur 127.0.0.1:5000")
    #start_queue_worker(worker_llama_call)
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
