#!/bin/bash
# Détection automatique de l'environnement
if [[ "${PWD##*/}" == "fondation-ia-dev" ]]; then
    PROJET_NOM="FONDATION-IA DEV"
    ACCENT="🔧"
else
    PROJET_NOM="FONDATION-IA STABLE"
    ACCENT="🌍"
fi

echo "=========================================="
echo "${ACCENT} ${PROJET_NOM} - ENVIRONNEMENT ACTIF ${ACCENT}"
echo "=========================================="

# Warning si on est sur le stable
if [[ "${PWD##*/}" != "fondation-ia-dev" ]]; then
    echo ""
    echo -e "\e[1;31m  ╔══════════════════════════════════════════╗"
    echo -e "  ║  \e[5m⚠️  WARNING WARNING WARNING WARNING  ⚠️\e[25m ║"
    echo -e "  ║                                          ║"
    echo -e "  ║   TU ES SUR L'ENVIRONNEMENT STABLE       ║"
    echo -e "  ║   NE MODIFIE PAS LE CODE ICI             ║"
    echo -e "  ║   UTILISE fondation-ia-dev POUR ÇA       ║"
    echo -e "  ╚══════════════════════════════════════════╝\e[0m"
    echo ""
    sleep 1
fi

source /home/data/ml_env/bin/activate
cd "${FONDATION_PROJECT_DIR:-$(pwd)}"

export PATH="$PATH:/home/data/llama.cpp/build/bin"
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
echo "  /home/data/ml_env/bin/python3 src/cli.py           → Chat interactif"
echo "=========================================="
exec bash
