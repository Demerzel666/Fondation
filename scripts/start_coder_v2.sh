#!/bin/bash
# Ceci est un commentaire bidon
LLAMA_CPP_BIN="${LLAMA_CPP_BIN:-/home/data/llama.cpp/build/bin}"
MODEL="/home/data/models/Qwen2.5-Coder-14B-Instruct-abliterated-Q5_K_M.gguf"
PORT=8081
export LD_LIBRARY_PATH="/opt/rocm/lib:${LD_LIBRARY_PATH:-}"

exec $LLAMA_CPP_BIN/llama-server \
  -m "$MODEL" \
  --host 127.0.0.1 --port $PORT \
  -ngl 99 \
  -t 16 \
  -c 24576 \
  --flash-attn on
