#!/bin/bash
# =============================================================================
# LANCEMENT QWEN3-CODER-30B SUR PORT 8081
# =============================================================================

# Racine du projet = dossier parent du dossier scripts/
PROJECT_ROOT="$(cd "$(dirname "$(dirname "$0")")" && pwd)"

# binaire llama-server (configurable via env)
export PATH="${LLAMA_CPP_BIN:-/home/data/llama.cpp/build/bin}:$PATH"

MODEL="$PROJECT_ROOT/models/Qwen3-Coder-30B-A3B-Q4_K_M/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf"
PORT=8081

echo "=== FONDATION-IA : LANCEMENT MODELE CODE ==="

pkill -f "llama-server.*${PORT}" 2>/dev/null
sleep 1

if [ ! -f "$MODEL" ]; then
    echo "❌ Modèle introuvable : $MODEL"
    exit 1
fi

# Lancer avec context window 32K
llama-server \
    -m "$MODEL" \
    --host 0.0.0.0 \
    --port $PORT \
    -ngl 99 \
    -t 16 \
    -c 32768 \
    -np 1 \
    --flash-attn on \
    &

SERVER_PID=$!
echo "PID serveur : $SERVER_PID"
echo "Port : $PORT"
echo "Context window : 32768 tokens"

echo "Attente du serveur..."
for i in $(seq 1 30); do
    if curl -s "http://localhost:${PORT}/health" > /dev/null 2>&1; then
        echo "✅ Serveur prêt sur http://localhost:${PORT}"
        exit 0
    fi
    sleep 2
    echo "  Tentative $i/30..."
done

echo "❌ Le serveur n'a pas démarré dans les 60 secondes"
exit 1
