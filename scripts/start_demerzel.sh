#!/bin/bash
# =============================================================================
# LANCEMENT DEMERZEL — AUTODÉTECTION CPU/RAM (port 8080)
# =============================================================================

PROJECT_ROOT="$(cd "$(dirname "$(dirname "$0")")" && pwd)"

# Binaires llama.cpp (chemin local ThinkPad par défaut, configurable)
export PATH="${LLAMA_CPP_BIN:-$HOME/tools/llama.cpp/build/bin}:$PATH"

PORT=8080
MODEL="${DEMERZEL_MODEL:-$PROJECT_ROOT/models/demerzel.gguf}"

# --- RAM totale (Mo) ---
TOTAL_RAM_MB=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo)

# --- Si le modèle par défaut est absent, choisir selon la RAM ---
if [ ! -f "$MODEL" ]; then
    echo "ℹ️ Modèle par défaut introuvable — sélection selon RAM (${TOTAL_RAM_MB} Mo)..."
    for candidate in demerzel-4b.gguf demerzel-officiel.gguf demerzel-abliterated.gguf demerzel-1.7b.gguf demerzel-0.6b.gguf; do
        if [ -f "$PROJECT_ROOT/models/$candidate" ]; then
            MODEL="$PROJECT_ROOT/models/$candidate"
            echo "→ Sélection : $candidate"
            break
        fi
    done
fi

[ -f "$MODEL" ] || { echo "❌ Aucun modèle dans $PROJECT_ROOT/models/ — voir README"; exit 1; }

# --- Threads et contexte selon la RAM ---
if   [ "$TOTAL_RAM_MB" -lt 6000 ];  then CTX=2048; THREADS=4
elif [ "$TOTAL_RAM_MB" -lt 10000 ]; then CTX=4096; THREADS=6
elif [ "$TOTAL_RAM_MB" -lt 20000 ]; then CTX=8192; THREADS=8
else                                      CTX=16384; THREADS=16
fi

# --- GPU : ROCm présent ? (serveur) sinon CPU pur (ThinkPad, téléphones amis) ---
GPU_ARGS=""
if command -v rocminfo >/dev/null 2>&1 && rocminfo 2>/dev/null | grep -q gfx; then
    export LD_LIBRARY_PATH="/opt/rocm/lib:${LD_LIBRARY_PATH:-}"
    GPU_ARGS="-ngl 99 --flash-attn on"
    echo "🎮 GPU AMD détecté → offload complet"
else
    echo "🖥️ CPU seul → threads=$THREADS"
fi

echo "=== FONDATION-IA : LANCEMENT DEMERZEL ==="
echo "Modèle : $MODEL"
echo "RAM : ${TOTAL_RAM_MB} Mo | Contexte : ${CTX} | Port : ${PORT}"

pkill -f "llama-server.*${PORT}" 2>/dev/null
sleep 1

llama-server \
    -m "$MODEL" \
    --host "${DEMERZEL_HOST:-127.0.0.1}" \
    --port $PORT \
    $GPU_ARGS \
    -t $THREADS \
    -c ${CTX} \
    -b 2048 \
    -ub 512 &
    -ub 512 &

SERVER_PID=$!
echo "PID serveur : $SERVER_PID"

echo "Attente du serveur..."
for i in $(seq 1 60); do
    if curl -s "http://localhost:${PORT}/health" > /dev/null 2>&1; then
        echo "✅ Serveur prêt sur http://localhost:${PORT}"
        exit 0
    fi
    sleep 2
    echo "  Tentative $i/60..."
done

echo "❌ Le serveur n'a pas démarré dans les 120 secondes"
exit 1
