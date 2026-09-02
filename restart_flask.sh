#!/bin/bash
# Script pour redémarrer proprement le service Flask de Fondation-IA Web

echo "🔄 Redémarrage du service Flask..."

# Tuer tous les process Flask en cours
pkill -9 -f "python.*app.py"
sleep 2

# Démarrer Flask en arrière-plan
cd "$(dirname "$0")"
nohup /home/data/ml_env/bin/python3 src/web/app.py > /tmp/flask.log 2>&1 &

# Attendre que Flask démarre
sleep 2

# Vérifier que c'est actif
if pgrep -f "python.*app.py" > /dev/null; then
    echo "✅ Flask est en ligne !"
    echo "📊 PID: $(pgrep -f 'python.*app.py')"
    echo "📄 Logs: /tmp/flask.log"
    echo ""
    echo "🌐 Adresse: http://127.0.0.1:5000"
    echo "🧅 Onion: nrwtshrkpg5k4ywjgijnyhc4elqcrvpj4qb4kfobf7ukgzbwwflkpvad.onion"
else
    echo "❌ Échec du démarrage"
    echo "📄 Vérifie les logs: /tmp/flask.log"
fi
