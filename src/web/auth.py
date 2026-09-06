# src/web/auth.py
# =============================================================================
# Gestion authentication tokens et sessions
# =============================================================================

import secrets
from functools import wraps
from flask import request, g
from src.db import authenticate_user, create_invite, register_user
import hashlib

def generate_token():
    """Génère un token d'invitation à usage unique."""
    return secrets.token_urlsafe(32)


def create_user_session(name, token, invite_code):
    """
    Enregistre un utilisateur avec son token haché.
    Retourne (user_id, error_msg) — user_id = None si erreur.
    """
    if not invite_code or len(invite_code) < 20:
        return None, "Code d'invitation invalide"
    
    user_id = register_user(name, token, invite_code)
    if user_id is None:
        return None, "Erreur d'inscription (nom déjà pris ou code invalidé)"
    
    return user_id, None

def validate_session(token):
    """
    Vérifie un token et retourne user_id ou None.
    1. Utilisateurs existants → auth PBKDF2 via db.py
    2. Codes d'invite à usage unique → SHA-256
    """
    from src.db import authenticate_user, get_conn

    # 1. Utilisateurs existants : la vraie auth (PBKDF2 + sel)
    user_id = authenticate_user(token)
    if user_id is not None:
        return user_id

    # 2. Codes d'invite non utilisés
    submitted = hashlib.sha256(token.encode()).hexdigest()
    conn = get_conn()
    rows = conn.execute(
        'SELECT id, code_hash, code FROM invites WHERE used = 0'
    ).fetchall()

    matched_id = None
    for row in rows:
        if row['code_hash'] is not None:
            ok = (row['code_hash'] == submitted)
        else:
            # Migration douce : ancien invite stocké en clair
            ok = (row['code'] == submitted) or (row['code'] == token)
        if ok:
            matched_id = row['id']
            break

    if matched_id is not None:
        conn.execute('UPDATE invites SET used = 1 WHERE id = ?', (matched_id,))
        conn.commit()
        conn.close()
        return matched_id

    conn.close()
    return None
