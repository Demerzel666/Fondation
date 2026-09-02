#!/usr/bin/env python3
"""Script pour injecter la commande /write améliorée dans cli.py"""

print("🔧 Injection de la commande /write améliorée...")

with open('src/cli.py', 'r') as f:
    content = f.read()

# Bloc de code /write à insérer
write_block = '''                elif cmd == '/write':
                    # ---------------------------------------------------------------------
                    # FONCTION /WRITE : Extraction et écriture de blocs de code détectés
                    # Syntaxes supportées :
                    #   /write <fichier>                 → Écrit le 1er bloc automatiquement
                    #   /write <index> <fichier>         → Écrit le bloc index spécifié
                    #   /write list                      → Liste les blocs disponibles
                    # ---------------------------------------------------------------------
                    
                    if not mode_state.get('last_model_response'):
                        print("❌ Aucune réponse récente enregistrée.")
                        continue
                    
                    import re
                    import os
                    import shutil

                    def extract_code_blocks(response_text):
                        pattern = r'```(?:python|bash|sh|json|yaml|txt|php|js)?\\n?(.*?)```'
                        blocks = re.findall(pattern, response_text, re.DOTALL | re.IGNORECASE)
                        return [b.strip() for b in blocks if b.strip()]
                    
                    blocks = extract_code_blocks(mode_state['last_model_response'])
                    args_list = args.strip().split()

                    # ── CAS A : Aucun argument → liste les blocs
                    if not args_list:
                        if not blocks:
                            print("❌ Aucun bloc de code détecté dans la dernière réponse.")
                            continue
                        
                        print(f"📦 Blocs de code détectés ({len(blocks)}) :")
                        for idx, block in enumerate(blocks, 0):
                            preview = block[:90].replace('\\n', ' ').strip()
                            print(f"  [{idx}] {len(block)} chars : {preview}...")
                        
                        print(f"\\nUsage: /write <fichier>           Écris le 1er bloc (shortcut)")
                        print("       /write <index> <fichier>    Écris le bloc index spécifique")
                        print("       Ex: /write src/new_feature.py")
                        continue

                    # ── CAS B : Un seul argument → c'est le chemin de fichier
                    if len(args_list) == 1:
                        output_path = args_list[0]
                        target_idx = 0
                        if target_idx >= len(blocks):
                            print(f"❌ Indisponible : seulement {len(blocks)} bloc(s) trouvé(s)")
                            continue

                    # ── CAS C : Deux arguments → index explicite
                    elif len(args_list) == 2:
                        try:
                            target_idx = int(args_list[0]) - 1
                        except ValueError:
                            target_idx = 0
                            output_path = args_list[0]
                        
                        output_path = args_list[-1]
                        if target_idx < 0 or target_idx >= len(blocks):
                            print(f"❌ Indice invalide (valable : 0-{len(blocks)-1})")
                            continue

                    else:
                        print("Usage: /write <fichier>")
                        continue

                    code_content = blocks[target_idx]
                    abs_path = os.path.abspath(output_path)
                    base_dir = "/home/data/fondation-ia-dev"

                    if not abs_path.startswith(base_dir):
                        print(f"❌ Chemin hors projet interdit : {output_path}")
                        continue

                    backup_created = False
                    if os.path.exists(abs_path):
                        backup = f"{abs_path}.bak"
                        if not os.path.exists(backup):
                            shutil.copy2(abs_path, backup)
                            backup_created = True
                            print(f"💾 Backup créé : {os.path.basename(backup)}")
                        else:
                            print(f"⚠️ Backup existant : {os.path.basename(backup)}")

                    num_chars = len(code_content)
                    num_lines = code_content.count('\\n') + 1
                    first_lines = '\\n'.join(code_content.split('\\n')[:5])
                    
                    print(f"\\n📝 Aperçu ({num_chars} chars, {num_lines} lignes) :")
                    for line in first_lines.split('\\n'):
                        print(f"  {line}")
                    if num_lines > 5:
                        print(f"  ... ({num_lines - 5} lignes supplémentaires)")

                    confirm = input(f"\\n✏️  Écrire {num_chars} chars dans {os.path.basename(abs_path)} ? (y/N) ")
                    if confirm.lower() not in ('y', 'yes', 'oui', 'o'):
                        print("Annulé.")
                        continue

                    output_dir = os.path.dirname(abs_path)
                    if output_dir and not os.path.exists(output_dir):
                        os.makedirs(output_dir, exist_ok=True)
                    
                    with open(abs_path, 'w', encoding='utf-8') as fw:
                        fw.write(code_content)

                    print(f"✅ Fichier écrit : {abs_path}")
                    continue'''

# Trouver l'endroit pour insérer (avant /unload)
if "elif cmd == '/unload':" in content:
    insert_point = content.index("                elif cmd == '/unload':")
    
    new_content = content[:insert_point] + write_block + "\n\n                " + content[insert_point + 32:]
    
    with open('src/cli.py.new', 'w') as f:
        f.write(new_content)
    
    # Vérifier syntaxe Python avant remplacement
    import subprocess
    result = subprocess.run(['python3', '-m', 'py_compile', 'src/cli.py.new'], capture_output=True)
    
    if result.returncode == 0:
        print("✅ Syntaxe valide ! Remplacement en cours...")
        
        # Backup de l'original
        subprocess.run(['mv', 'src/cli.py', 'src/cli.py.backup_before_write'])
        
        # Nouveau fichier actif
        subprocess.run(['mv', 'src/cli.py.new', 'src/cli.py'])
        
        print("✨ Patch appliqué avec succès !")
        print("Nouvelles commandes disponibles :")
        print("  /write fichier.py          → Écrit le 1er bloc détecté")
        print("  /write 2 fichier.py        → Écrit le bloc 2 spécifiquement")
        print("  /write                     → Liste les blocs")
    else:
        print(f"❌ Erreur de syntaxe détectée :")
        print(result.stderr.decode())
        print("Fichier .new conservé pour debug")
else:
    print("❌ Impossible de trouver le point d'injection (/unload)")
    print("Vérifie que cli.py n'a pas déjà été modifié")

