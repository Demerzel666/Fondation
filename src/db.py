# src/db.py
# =============================================================================
# Gestionnaire SQLite pour Fondation-IA
# Projets → Conversations → Messages
# =============================================================================

import os
import sqlite3
import json
import secrets
import hashlib
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fondation.db")


def get_conn():
    """Connexion SQLite avec foreign keys activées."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row  # résultats comme dict
    return conn


def init_db():
    """Crée toutes les tables si elles n'existent pas."""
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            name        TEXT UNIQUE NOT NULL,
            description TEXT,
            model_mode  TEXT DEFAULT 'politique',
            context     TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL,
            title       TEXT,
            summary     TEXT,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role            TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
            content         TEXT NOT NULL,
            rag_sources     TEXT,
            token_count     INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );
                CREATE TABLE IF NOT EXISTS workspaces (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL,
            path        TEXT NOT NULL,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS workspace_files (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id    INTEGER NOT NULL,
            filepath        TEXT NOT NULL,
            created_at      TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT UNIQUE NOT NULL,
            token_hash  TEXT NOT NULL,
            salt        TEXT NOT NULL,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            active      INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS invites (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT UNIQUE NOT NULL,
            used        INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now', 'localtime'))
        );

            CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

    """)


    # Migration: ajouter colonne context si elle n'existe pas
    try:
        conn.execute("ALTER TABLE projects ADD COLUMN context TEXT DEFAULT ''")
    except:
        pass

    conn.commit()
    conn.close()
    print(f"[DB] Initialisée : {DB_PATH}")


# ── INVITES ───────────────────────────────────────────────────────────────

def create_invite():
    """Génère et enregistre un code d'invite à usage unique. Retourne le code."""
    import secrets
    from src.db import get_conn
    
    code = secrets.token_urlsafe(32)
    conn = get_conn()
    conn.execute('INSERT INTO invites (code, used) VALUES (?, 0)', (code,))
    conn.commit()
    conn.close()
    return code

def is_invite_valid(code):
    """Vérifie qu'un code d'invitation est valide et non utilisé."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM invites WHERE code = ? AND used = 0", (code,)
    ).fetchone()
    conn.close()
    return row is not None


def use_invite(code):
    """Marque un code d'invitation comme utilisé."""
    conn = get_conn()
    conn.execute("UPDATE invites SET used = 1 WHERE code = ?", (code,))
    conn.commit()
    conn.close()


# ── USERS ──────────────────────────────────────────────────────────────────

def _hash_token(token, salt=None):
    """Hache un token avec sel. Retourne (hash, salt)."""
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', token.encode(), salt.encode(), 100000)
    return hashed.hex(), salt


def register_user(name, token, invite_code):
    """Inscrit un utilisateur avec un code d'invitation. 
    Le camarade choisit son propre token.
    Retourne son ID ou None si l'invitation est invalide."""
    if not is_invite_valid(invite_code):
        return None
    token_hash, salt = _hash_token(token)
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO users (name, token_hash, salt) VALUES (?, ?, ?)",
            (name, token_hash, salt)
        )
        conn.commit()
        use_invite(invite_code)
        uid = c.lastrowid
        conn.close()
        return uid
    except sqlite3.IntegrityError:
        conn.close()
        return None  # nom déjà pris


def authenticate_user(token, name=None):
    """Vérifie un token. Si name est fourni, vérifie que ça correspond.
    Retourne user_id ou None."""
    conn = get_conn()
    if name:
        row = conn.execute(
            "SELECT id, token_hash, salt FROM users WHERE name = ? AND active = 1",
            (name,)
        ).fetchone()
    else:
        rows = conn.execute(
            "SELECT id, token_hash, salt, name FROM users WHERE active = 1"
        ).fetchall()
        for row in rows:
            token_hash, salt = _hash_token(token, row["salt"])
            if token_hash == row["token_hash"]:
                conn.close()
                return row["id"]
        conn.close()
        return None
    
    if row:
        token_hash, _ = _hash_token(token, row["salt"])
        if token_hash == row["token_hash"]:
            conn.close()
            return row["id"]
    conn.close()
    return None


def revoke_user(user_id):
    """Désactive un utilisateur sans supprimer ses données."""
    conn = get_conn()
    conn.execute("UPDATE users SET active = 0 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

# ── USERS & INVITES GESTION ──────────────────────────────────────────────────

def list_users():
    """Liste tous les utilisateurs."""
    conn = get_conn()
    rows = conn.execute("SELECT id, name, active, created_at FROM users ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def deactivate_user(user_id):
    """Désactive un utilisateur (sans supprimer ses données)."""
    conn = get_conn()
    conn.execute("UPDATE users SET active = 0 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def activate_user(user_id):
    """Réactive un utilisateur désactivé."""
    conn = get_conn()
    conn.execute("UPDATE users SET active = 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def create_invite_code():
    """Crée et retourne un code d'invitation à usage unique."""
    return create_invite()  # réutilise la fonction existante


def register_new_user(name, token, invite_code):
    """
    Enregistre un nouvel utilisateur.
    Retourne (user_id, invite_code, error_message).
    """
    user_id = register_user(name, token, invite_code)
    if user_id is None:
        # Essayer de déterminer l'erreur
        conn = get_conn()
        existing = conn.execute(
            "SELECT id FROM users WHERE name = ?", (name,)
        ).fetchone()
        conn.close()
        
        if existing:
            return None, None, f"Le nom '{name}' existe déjà"
        return None, None, f"Code d'invitation invalide ou expiré"
    
    # Recracher le code utilisé pour confirmation
    return user_id, invite_code, None


# ── PROJECTS ──────────────────────────────────────────────────────────────

def create_project(user_id, name, description="", model_mode="politique"):
    """Crée un projet pour un utilisateur. Retourne son ID."""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO projects (user_id, name, description, model_mode) VALUES (?, ?, ?, ?)",
        (user_id, name, description, model_mode)
    )
    conn.commit()
    pid = c.lastrowid
    conn.close()
    return pid


def list_projects(user_id):
    """Liste les projets d'un utilisateur."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM projects WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_project(project_id, user_id=None):
    """Récupère un projet. Si user_id fourni, vérifie l'appartenance."""
    conn = get_conn()
    if user_id is not None:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user_id)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_project(project_id, user_id=None):
    """Supprime un projet. Si user_id fourni, vérifie l'appartenance."""
    conn = get_conn()
    if user_id is not None:
        conn.execute(
            "DELETE FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user_id)
        )
    else:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()

# ── CONVERSATIONS ─────────────────────────────────────────────────────────

def create_conversation(project_id, title=None):
    """Crée une conversation dans un projet. Retourne son ID."""
    if title is None:
        title = f"Conversation du {datetime.now().strftime('%d/%m %H:%M')}"
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO conversations (project_id, title) VALUES (?, ?)",
        (project_id, title)
    )
    conn.commit()
    cid = c.lastrowid
    conn.close()
    print(f"[DB] Conversation créée : #{cid} '{title}'")
    return cid


def list_conversations(project_id):
    """Liste les conversations d'un projet."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM conversations WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_conversation(conversation_id):
    """Supprime une conversation et tous ses messages."""
    conn = get_conn()
    conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    conn.commit()
    conn.close()
    print(f"[DB] Conversation #{conversation_id} supprimée")


def update_summary(conversation_id, summary):
    """Met à jour le résumé d'une conversation."""
    conn = get_conn()
    conn.execute(
        "UPDATE conversations SET summary = ? WHERE id = ?",
        (summary, conversation_id)
    )
    conn.commit()
    conn.close()


# ── MESSAGES ──────────────────────────────────────────────────────────────

def add_message(conversation_id, role, content, rag_sources=None, token_count=0):
    """Ajoute un message. Retourne son ID."""
    sources_json = json.dumps(rag_sources) if rag_sources else None
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """INSERT INTO messages
           (conversation_id, role, content, rag_sources, token_count)
           VALUES (?, ?, ?, ?, ?)""",
        (conversation_id, role, content, sources_json, token_count)
    )
    conn.commit()
    mid = c.lastrowid
    conn.close()
    return mid


def get_messages(conversation_id, limit=None):
    """Récupère les messages d'une conversation, du plus récent au plus ancien.
    Si limit est donné, ne récupère que les N derniers."""
    conn = get_conn()
    if limit:
        rows = conn.execute(
            """SELECT * FROM messages
               WHERE conversation_id = ?
               ORDER BY id DESC LIMIT ?""",
            (conversation_id, limit)
        ).fetchall()
        rows = list(reversed(rows))  # remettre dans l'ordre chrono
    else:
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_conversation_summary(conversation_id):
    """Récupère le résumé stocké d'une conversation, s'il existe."""
    conn = get_conn()
    row = conn.execute(
        "SELECT summary FROM conversations WHERE id = ?",
        (conversation_id,)
    ).fetchone()
    conn.close()
    return row["summary"] if row else None

# ── WORKSPACE CRUD ─────────────────────────────────────────────

def create_workspace(project_id, path):
    """Crée ou met à jour le workspace d'un projet."""
    conn = get_conn()
    c = conn.cursor()

    # Vérifier si le projet a déjà un workspace
    existing = c.execute("SELECT id FROM workspaces WHERE project_id = ?", (project_id,)).fetchone()
    if existing:
        c.execute("UPDATE workspaces SET path = ? WHERE project_id = ?", (path, project_id))
        ws_id = existing[0]
    else:
        c.execute("INSERT INTO workspaces (project_id, path) VALUES (?, ?)", (project_id, path))
        ws_id = c.lastrowid

    # Vider les anciens fichiers actifs
    c.execute("DELETE FROM workspace_files WHERE workspace_id = ?", (ws_id,))

    conn.commit()
    return ws_id


def add_workspace_file(workspace_id, filepath):
    """Ajoute un fichier au workspace."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO workspace_files (workspace_id, filepath) VALUES (?, ?)", (workspace_id, filepath))
    conn.commit()
    return c.lastrowid


def get_workspace(project_id):
    """Récupère le workspace d'un projet (path + fichiers actifs)."""
    conn = get_conn()
    c = conn.cursor()

    ws = c.execute("SELECT id, path FROM workspaces WHERE project_id = ?", (project_id,)).fetchone()
    if not ws:
        return None

    files = c.execute("SELECT filepath FROM workspace_files WHERE workspace_id = ?", (ws[0],)).fetchall()
    file_list = [f[0] for f in files]

    return {"id": ws[0], "path": ws[1], "files": file_list}

# ── CONTEXTES ──────────────────────────────────────────────────────────────

def get_global_context():
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = 'global_context'").fetchone()
    conn.close()
    return row['value'] if row else ''


def set_global_context(text):
    conn = get_conn()
    conn.execute("""
        INSERT INTO settings (key, value) VALUES ('global_context', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (text,))
    conn.commit()
    conn.close()


def get_project_context(project_id):
    conn = get_conn()
    row = conn.execute("SELECT context FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    return row['context'] if row else ''


def update_project_context(project_id, context_text):
    conn = get_conn()
    conn.execute("UPDATE projects SET context = ? WHERE id = ?", (context_text, project_id))
    conn.commit()
    conn.close()

# ── TEST RAPIDE ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()

    # Créer une invitation
    invite = create_invite()
    print(f"[TEST] Invitation générée : {invite[:20]}...")

    # Inscrire un utilisateur de test
    uid = register_user("testuser", "mon_super_token", invite)
    print(f"[TEST] Utilisateur inscrit : #{uid}")

    # Authentifier
    auth_uid = authenticate_user("mon_super_token")
    print(f"[TEST] Authentifié : #{auth_uid}")
    assert auth_uid == uid, "L'auth a échoué"

    # Créer un projet pour cet user
    pid = create_project(uid, "fondation-dev", "Développement de Fondation-IA", "code")
    print(f"[TEST] Projet créé : #{pid}")

    # Créer une conversation
    cid = create_conversation(pid, "Test SQLite")

    # Ajouter quelques messages
    add_message(cid, "user", "Comment je crée une table SQLite ?")
    add_message(cid, "assistant", "CREATE TABLE machin...", rag_sources=["doc_sqlite.md"])

    # Vérifier l'isolation : lister les projets de cet user
    projects = list_projects(uid)
    print(f"[TEST] Projets de l'user : {len(projects)}")

    # Vérifier qu'un autre user ne voit rien
    invite2 = create_invite()
    uid2 = register_user("intrus", "autre_token", invite2)
    projects_intrus = list_projects(uid2)
    print(f"[TEST] Projets visibles par l'intrus : {len(projects_intrus)}")
    assert len(projects_intrus) == 0, "L'isolation a échoué !"

    # Nettoyage
    delete_project(pid)
    print("\n[TEST] OK tout marche, isolation validée.")
