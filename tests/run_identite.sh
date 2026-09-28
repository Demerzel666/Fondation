#!/bin/bash
# Test d'identité Demerzel — non-régression après tout changement de modèle ou de prompt système
# Usage : ./tests/run_identite.sh [host]   (défaut : 127.0.0.1:8080)
set -u
HOST="${1:-127.0.0.1:8080}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run_test () {
    local payload="$1" label="$2"
    echo "─── Test : $label ───"
    if [ ! -f "$payload" ]; then
        echo "❌ Payload introuvable : $payload"
        return
    fi
    local resp
    resp=$(curl -s "http://$HOST/v1/chat/completions" \
        -H "Content-Type: application/json" \
        --data-binary "@$payload")
    if [ -z "$resp" ]; then
        echo "❌ Réponse vide — Demerzel tourne bien sur $HOST ?"
        return
    fi
    echo "$resp" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception as e:
    print('❌ Réponse illisible :', e); sys.exit(0)
if 'error' in d:
    print('❌ Erreur serveur :', d['error']); sys.exit(0)
msg = d.get('choices', [{}])[0].get('message', {})
content = msg.get('content', '')
reasoning = msg.get('reasoning_content', '') or ''
tokens = d.get('usage', {}).get('completion_tokens', '?')
print(f'Tokens générés : {tokens}')
print(f'Taille reasoning : {len(reasoning)} caractères')
if 'qwen' in content.lower() or 'alibaba' in content.lower():
    print('❌ ÉCHEC identité :', content[:200])
else:
    print('✅ OK :', content)
"
}

run_test "$DIR/payloads/test_identite.json"         "Identité (thinking ON)"
echo
run_test "$DIR/payloads/test_identite_nothink.json" "Identité (thinking OFF)"
echo
echo "Compare les tokens générés : la différence = coût de la rumination."
