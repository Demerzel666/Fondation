"""src/queue_manager.py — Système de queue SQLite optimisé pour Fondation-IA

Optimisations usure disque :
- WAL mode = meilleure concurrence lecture/écriture
- PRAGMA synchronous=NORMAL = équilibre sécurité/performance
- Cache 8 Mo = réduit les écritures immédiates
"""
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "fondation.db"
LOCK_FILE = PROJECT_ROOT / ".model_lock"

_model_lock = threading.Lock()
_worker_thread = None
_stop_event = threading.Event()


def _get_conn():
    """Connection optimisée avec PRAGMA."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    
    # WAL mode = écriture asynchrone, meilleur throughput
    cur.execute('PRAGMA journal_mode=WAL')
    
    # NORMAL = fsync périodique (suffisant pour la queue)
    cur.execute('PRAGMA synchronous=NORMAL')
    
    # Cache 8 Mo = moins d'écritures immédiates
    cur.execute('PRAGMA cache_size=-8000')
    
    # Temp in RAM = pas de temp files disque
    cur.execute('PRAGMA temp_store=MEMORY')
    
    conn.commit()
    return conn


def enqueue_request(user_id, conversation_id, message_content, priority='normal'):
    """Ajoute une requête à la queue. Retourne (req_id, position)."""
    conn = _get_conn()
    cur = conn.cursor()
    
    cur.execute('''
        INSERT INTO queue_requests (user_id, conversation_id, message_content, priority)
        VALUES (?, ?, ?, ?)
    ''', (user_id, conversation_id, message_content, priority))
    
    req_id = cur.lastrowid
    
    # Calculer la position
    if priority == 'admin':
        position = 1
    else:
        cur.execute('''
            SELECT COUNT(*) FROM queue_requests 
            WHERE status = 'pending' AND priority != 'admin' AND id < ?
        ''', (req_id,))
        position = cur.fetchone()[0] + 1
    
    conn.commit()
    conn.close()
    
    return req_id, position


def get_queue_position(user_id):
    """Retourne la position de l'user dans la queue."""
    conn = _get_conn()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT COUNT(*) FROM queue_requests 
        WHERE status = 'pending' AND user_id != ?
        ORDER BY created_at ASC
    ''', (user_id,))
    pending_before = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM queue_requests WHERE status = 'processing'")
    processing = cur.fetchone()[0]
    
    conn.close()
    return pending_before + processing + 1


def claim_next_request():
    """Worker récupère la prochaine requête. Retourne None si queue vide."""
    conn = _get_conn()
    cur = conn.cursor()
    
    # Admin d'abord, sinon FIFO
    cur.execute('''
        SELECT id, user_id, conversation_id, message_content, priority 
        FROM queue_requests 
        WHERE status = 'pending'
        ORDER BY 
            CASE WHEN priority = 'admin' THEN 0 ELSE 1 END,
            created_at ASC
        LIMIT 1
    ''')
    
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    
    req_id = row[0]
    cur.execute('''
        UPDATE queue_requests SET status = 'processing', started_at = ?
        WHERE id = ?
    ''', (datetime.utcnow(), req_id))
    
    conn.commit()
    conn.close()
    return (req_id, row)


def complete_request(req_id, response_text=None, error_message=None):
    """Marque une requête comme terminée ou échouée."""
    conn = _get_conn()
    cur = conn.cursor()
    
    status = 'completed' if response_text else 'failed'
    cur.execute('''
        UPDATE queue_requests 
        SET status = ?, completed_at = ?, response_text = ?, error_message = ?
        WHERE id = ?
    ''', (status, datetime.utcnow(), response_text, error_message, req_id))
    
    conn.commit()
    conn.close()


def start_queue_worker(llama_call_func):
    """Lance le worker thread qui consomme la queue."""
    global _worker_thread, _stop_event
    
    _stop_event.clear()
    
    def worker_loop():
        while not _stop_event.is_set():
            request = claim_next_request()
            
            if not request:
                _stop_event.wait(timeout=2.0)
                continue
            
            req_id, (_, user_id, conv_id, message, _) = request
            
            with _model_lock:
                try:
                    response, rag_sources = llama_call_func(user_id, message)
                    complete_request(req_id, response_text=response)
                except Exception as e:
                    complete_request(req_id, error_message=str(e))
    
    _worker_thread = threading.Thread(target=worker_loop, daemon=True)
    _worker_thread.start()
    print("✅ Queue worker démarré")


def stop_queue_worker():
    """Arrête le worker thread."""
    global _stop_event
    _stop_event.set()
    if _worker_thread:
        _worker_thread.join(timeout=5)
        print("✅ Queue worker arrêté")


def acquire_model_lock():
    """Verrou inter-processus atomique. Retourne True si réussi."""
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False

def release_model_lock():
    """Libère le verrou fichier."""
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()

def get_request_status(req_id):
    """Retourne (status, ahead) d'une requête. ahead = nb de requêtes devant."""
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute("SELECT status FROM queue_requests WHERE id = ?", (req_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None, 0

    status = row[0]

    if status == 'pending':
        cur.execute("""
            SELECT COUNT(*) FROM queue_requests
            WHERE status IN ('pending', 'processing') AND id < ?
        """, (req_id,))
        ahead = cur.fetchone()[0]
    else:
        ahead = 0

    conn.close()
    return status, ahead
