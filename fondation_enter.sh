#!/bin/bash
echo "=========================================="
echo "PROJET FONDATION - ENVIRONNEMENT ACTIF"
echo "=========================================="

source /home/data/ml_env/bin/activate
cd /home/data/fondation-ia

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

python3 -c "
from src.db import init_db
init_db()

try:
    from src.rag import get_stats
    r = get_stats()
    print(f'RAG: {r[\"chunks\"]} chunks | {r[\"embedding_model\"]}')
except Exception as e:
    print(f'RAG: non disponible ({e})')
"

echo ""
echo "=========================================="
echo "COMMANDES :"
echo "  ./scripts/start_coder.sh    → Qwen3-Coder (port 8081)"
echo "  ./scripts/start_demerzel.sh  → Demerzel (port 8080)"
echo "  ./scripts/stop_all.sh        → Arrêter tout"
echo "  python3 src/cli.py           → Chat interactif"
echo "  python3 src/db.py             → Test SQLite"
echo "  python3 src/rag.py            → Test RAG"
echo "  python3 src/context.py        → Test Contexte"
echo "=========================================="

exec bash
