#!/bin/bash
# Injection de la commande /write dans cli.py - VERSION GARANTIE PROPRE

echo "🔧 Injection de /write... Verbose activé"

# Backup immédiat
cp src/cli.py src/cli_before_write.backup

# Lire le fichier original
python3 << 'PYCODE'
import os, shutil, subprocess

with open('src/cli.py', 'r') as f:
    content = f.read()

# Trouver l'endroit exact où insérer (/unload)
insert_marker = "                elif cmd == '/unload':"
if insert_marker not in content:
    print("❌ Erreur: '/unload' introuvable")
    exit(1)

idx_insert = content.index(insert_marker)

# Bloc complet à insérer
write_code = '''                elif cmd == '/write':
                    if not mode_state.get('last_model_response'):
                        print("❌ Aucune réponse récente.")
                        continue
                    
                    import re, os, shutil
                    args_list = args.strip().split()
                    
                    def extract_blocks(txt):
                        pattern = r'```(?:python|bash|sh|json|yaml|txt|php|js)?\\n?(.*?)```'
                        return [b.strip() for b in re.findall(pattern, txt, re.DOTALL | re.IGNORECASE) if b.strip()]
                    
                    blocks = extract_blocks(mode_state['last_model_response'])

                    # Si aucun argument → liste les blocs
                    if not args_list:
                        if not blocks:
                            print("❌ Aucun bloc détecté.")
                            continue
                        print(f"📦 Blocs trouvés ({len(blocks)}) :")
                        for i, blk in enumerate(blocks, 0):
                            preview = blk[:75].replace('\\n', ' ').strip()
                            print(f"  [{i}] {len(blk)} chars : {preview}...")
                        print("\\nUsage: /write <fichier>              → Écrit bloc 0")
                        print("       /write <index> <fichier>        → Écrit bloc index")
                        continue

                    # Déterminer indice et chemin
                    outpath = None
                    target_idx = 0
                    
                    if len(args_list) == 1:
                        outpath = args_list[0]
                        target_idx = 0
                    elif len(args_list) >= 2:
                        try:
                            target_idx = int(args_list[0]) - 1
                            outpath = args_list[-1]
                        except ValueError:
                            outpath = args_list[0]
                            target_idx = 0
                    else:
                        print("Usage: /write <chemin>")
                        continue

                    if target_idx < 0 or target_idx >= len(blocks):
                        print(f"❌ Index invalide (0-{len(blocks)-1})")
                        continue

                    code = blocks[target_idx].strip()
                    abspath = os.path.abspath(outpath)
                    basedir = "/home/data/fondation-ia-dev"

                    if not abspath.startswith(basedir):
                        print(f"❌ Chemin hors projet interdit")
                        continue

                    if os.path.exists(abspath):
                        bak = abspath + ".bak"
                        if not os.path.exists(bak):
                            shutil.copy2(abspath, bak)
                            print(f"💾 Backup créé : {os.path.basename(bak)}")

                    prev = '\\n'.join(code.split('\\n')[:6])
                    nlcount = code.count('\\n') + 1
                    
                    print(f"\\n📝 Aperçu ({len(code)} chars, {nlcount} lignes) :")
                    for ln in prev.split('\\n'):
                        print(f"  {ln}")
                    if nlcount > 6:
                        print(f"  ... ({nlcount-6} lignes suppl.)")

                    confirm = input(f"\\n✏️  Écrire ? (y/N) ").strip().lower()
                    if confirm not in ('y','yes','oui','o'):
                        print("Annulé.")
                        continue

                    outdir = os.path.dirname(abspath)
                    if outdir and not os.path.exists(outdir):
                        os.makedirs(outdir, exist_ok=True)
                    
                    with open(abspath, 'w', encoding='utf-8') as fw:
                        fw.write(code)

                    print(f"✅ {abspath} écrit !")
                    continue

'''

# Insertion
new_content = content[:idx_insert] + write_code + '\n\n' + content[idx_insert:]

with open('src/cli_new.py', 'w') as f:
    f.write(new_content)

# Vérification syntaxe
result = subprocess.run(['python3', '-m', 'py_compile', 'src/cli_new.py'], capture_output=True)
if result.returncode == 0:
    shutil.move('src/cli.py', 'src/cli_backup_manual.bak')
    shutil.move('src/cli_new.py', 'src/cli.py')
    print("✨ Injecté avec succès !")
else:
    print(f"❌ Erreur syntaxe : {result.stderr.decode()}")

PYCODE

