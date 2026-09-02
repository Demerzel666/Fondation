# src/web/auth.py
# =============================================================================
# Gestion authentication tokens et sessions
# =============================================================================

import secrets
from functools import wraps
from flask import request, g
from src.db import authenticate_user, create_invite, register_user


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
    Supporte aussi les codes d'invite à usage unique.
    """
    from src.db import get_conn

    # 1. Chercher dans les utilisateurs existants
    conn = get_conn()
    row = conn.execute('SELECT id FROM users WHERE token_hash = ?', (token,)).fetchone()
    if row:
        conn.close()
        return row[0]

    # 2. Chercher dans les codes d'invite (non utilisés)
    row = conn.execute('SELECT id FROM invites WHERE code = ? AND used = 0', (token,)).fetchone()
    if row:
        # Marquer comme utilisé (usage unique)
        conn.execute('UPDATE invites SET used = 1 WHERE id = ?', (row[0],))
        conn.commit()
        conn.close()
        # Le code a été validé, retourne True pour autoriser l'inscription
        return row[0]

    conn.close()
    return None
