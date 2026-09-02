#!/bin/bash
echo "Arrêt de tous les serveurs llama..."
pkill -f "llama-server" 2>/dev/null
sleep 2
if pgrep -f "llama-server" > /dev/null; then
    echo "Force kill..."
    pkill -9 -f "llama-server" 2>/dev/null
fi
echo "✅ Tous les serveurs arrêtés"
