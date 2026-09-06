# Contribuer à la Fondation

**Vive l'Amour et la Révolution !**

Merci de vouloir contribuer à ce projet. Ce dépôt est une **infrastructure de guérison révolutionnaire** — pas seulement du code, mais une pratique politique vivante.

---

## 🧭 Qui est bienvenu ?

Toute personne qui :

- ✅ A grandi sans amour et cherche la guérison
- ✅ A connu la violence et veut reconstruire par l'amour
- ✅ Est militante antifa, anticapitaliste, féministe
- ✅ Veut participer à une technologie libératrice (pas oppressive)
- ✅ Rejoint avec bienveillance et humilité

Tu n'as pas besoin d'être un·e expert·e en code. Tu as besoin d'avoir **vécu la blessure** et de **vouloir la guérir** — pour toi et pour les autres.

---

## ❤️ Charte d'amour politique

Avant de contribuer, lis et accepte cette charte. Elle n'est pas négociable.

### Principes fondamentaux

1. L'amour n'est pas optionnel — c'est la base de tout ce que nous faisons. Pas de haine, pas de vengeance, pas de violence contre les humains.

2. La vulnérabilité est acceptée — tu peux dire "je ne sais pas", "j'ai mal", "j'ai besoin d'aide". Personne ne sera jugé pour sa faiblesse.

3. Le consentement est non-négociable — dans le code comme dans les relations. Aucun push forcé, aucune obligation non explicite.

4. L'inclusion est prioritaire — pas de discrimination basée sur genre, origine, couleur de peau, classe, handicap, orientation sexuelle, statut migratoire, religion.

5. La transparence est requise — aucun code secret, aucune arrière-portière, aucune surveillance cachée. Tout est public, auditable.

6. L'autonomie est respectée — tu peux partir quand tu veux. Aucune rétention, aucun harcèlement après départ.

7. La guérison personnelle vient avant le militantisme — tu n'es pas obligé·e de brûler pour avancer. Prends soin de toi d'abord.

### Comportements attendus

| Attendu | À éviter absolument |
|---------|---------------------|
| Écouter avant de parler | Interrupter, dominer la parole |
| Demander du consentement avant de modifier | Push direct sans avis |
| Reconnaître ses erreurs publiquement | Nier, minimiser, rationaliser |
| Offrir du soutien aux nouveaux membres | Ignorer, mépriser, humilier |
| Respecter les limites personnelles | Insister, forcer, manipuler |
| Exprimer ses besoins clairement | Manipulation passive-agressive |

### Conflits et résolution

Si un conflit surgit :

1. Discute directement avec la personne concernée (message privé si besoin)
2. Si blocage, ouvre une discussion GitHub avec tag conflict
3. Si escalade, contacter les mainteneurs (@Demerzel666) pour médiation
4. Si violence avérée, expulsion immédiate sans appel

Rappel : La violence (verbale, physique, psychologique) → exclusion permanente. Pas de deuxième chance pour ceux qui blessent sciemment.

---

## 💻 Comment contribuer techniquement ?

### Types de contributions acceptées

| Type | Description | Comment commencer |
|------|-------------|-------------------|
| Code | Scripts, API, outils d'automatisation | Voir scripts/, propose PR |
| Documentation | Traductions, guides, tutoriels | Voir docs/, propose PR |
| Prompts IA | Templates pour guérison, résistance | Ajoute dans prompts/ |
| Données | Articles, archives, témoignages | Place dans data/ |
| Audit de sécurité | Revue de code, tests d'intrusion | Remplis template audits/ |
| Design | Schémas, infographies, logos | Propose SVG/PNG dans assets/ |

### Processus de contribution

1. Forke le dépôt → 2. Crée branche → 3. Code/documentation → 4. Teste localement → 5. Push → 6. Ouvre PR

Important : Pour toute modification sensible (données personnelles, prompts IA), demande d'abord en issue avant de coder.

### Standards de code

- Python 3.10+ avec type hints
- Format avec Black (config dans .pyproject.toml)
- Tests unitaires requis pour tout backend
- Documentation docstrings obligatoire
- Secrets jamais commités (utilise .env)

### Branches recommandées

git checkout -b feat/guerison-prompts
git checkout -b fix/security-audit
git checkout -b docs/traduction-arabe
git checkout -b test/integration-ia

---

## 🌍 Traductions

Ce document est écrit en français. Nous cherchons des traducteurs·trices pour :

- Arabe (priorité #1 — solidarité Palestine/Rojava)
- Kurde (Sorani/Kurmanci — priorité #1 — solidarité Rojava)
- Anglais (pour audience internationale)
- Espagnol (Amérique latine, solidarité zapatiste)
- Allemand (Europe, mouvement antifa)
- Portugais (Brésil, mouvements sociaux)

Comment contribuer : Crée docs/<lang>/theorie.md avec traduction complète. Signale dans une issue pour tracking.

---

## 🔐 Sécurité et confidentialité

### Ce que nous protégeons

- Données personnelles des contributeurs (jamais stockées sans consentement)
- Clés de chiffrement (jamais dans le dépôt)
- Identités des personnes en situation de danger

### Ce que nous NE protégeons PAS

- Code source (public par définition)
- Théorie politique (doit être diffusée)
- Citations et références (libres de droits)

### Audit de sécurité

Si tu découvres une vulnérabilité :

1. Ne la publie pas publiquement (responsible disclosure)
2. Envoie un message chiffré à @Demerzel666 via :
   - Signal : cy4.20
   - Proton Mail : [à définir]
   - Issue GitHub privée : security@github.com
3. Attends patch avant divulgation publique

---

## 🛠️ Outils recommandés pour contributors

### Environnement minimum

python --version
pip --version
git --version
node --version

### Commandes utiles

# Installer environnement
./fondation_enter.sh

# Activer virtual environment
source fondation_venv.sh

# Tester localement
pytest test_project/

# Audit sécurité
python scripts/security_audit.py

# Redémarrer serveur Flask
./restart_flask.sh

---

## 📚 Apprentissage recommandé

Avant de contribuer techniquement, lis :

1. bell hooks - All About Love — comprendre la base théorique
2. bell hooks - Feminism is for Everybody — méthodologie politique
3. Abdullah Öcalan - Manifeste pour une révolution civique — Jinéologie
4. Audre Lorde - Sister Outsider — intersectionnalité
5. David Graeber - Fragments of an Anarchist Anthropologist — organisation horizontale

Note : Tu n'es pas obligé·e d'avoir lu tous ces livres avant de contribuer. Mais plus tu connais la théorie, plus ta contribution sera alignée.

---

## 🌱 Comment rejoindre la communauté ?

### Étapes

1. Star le dépôt — signale ton intérêt public
2. Ouvre une issue Bonjour — présente-toi brièvement
3. Choisis un premier petit task — documentation, traduction, ou bug mineur
4. Participe à la discussion GitHub — pas besoin de code pour discuter
5. Propose une contribution — PR pour première tâche

### Canaux de communication

| Canal | Usage | Accès |
|-------|-------|-------|
| GitHub Issues | Bugs, idées, demandes | Public |
| GitHub Discussions | Conversation communautaire | Public |
| Telegram | Coordination rapide | [lien à définir] |
| Matrix/IRC | Chat en temps réel | [lien à définir] |
| Email | Communication officielle | [proton.me à définir] |

Rappel : Aucun canal ne collecte d'adresses IP ou d'identifiants personnels. Utilise Tor si possible.

---

## 💝 Merci

Merci de rejoindre ce projet. Chaque ligne de code, chaque mot ajouté, chaque traduction — c'est une pierre de plus à la reconstruction.

Tu n'es pas seul·e. Tu n'as jamais été seul·e.
L'amour existe. Il t'a sauvé·e une fois. Il te sauverera encore.

---

Dernière mise à jour : 2 septembre 2026
Mainteneurs : @Demerzel666
Licence : CC-BY-SA 4.0