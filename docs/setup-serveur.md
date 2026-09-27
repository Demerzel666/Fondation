a# Setup notes — Fondation (27 sept. 2026)

## Matériel

| Composant | Rôle |
|---|---|
| nvme0n1 (1.8T) | Windows (jeu) — jamais touché par Arch |
| nvme2n1 (1.8T) | **Arch Linux** (système) |
| nvme1n1 (1.8T) | Futur RAID1 données |
| Ryzen 9 + 7900 XTX + 64 Go RAM | Serveur d'inférence IA |

## Système installé

- **LUKS2** argon2id (mémoire de dérivation 2 Go) → **LVM**
- **Volumes** : root 200G / swap 64G / home 1.6T (ext4)
- **Kernels** : `linux` + `linux-hardened`
- **GRUB** : timeout 3s, recovery désactivé, pas d'os-prober
- **Clavier** : be-latin1 ; **Locales** : en_US.UTF-8
- **Réseau** : IPv4 DHCP (eno1), **IPv6 coupée**, systemd-networkd
- **SSH** : ed25519 uniquement, root interdit, mot de passe serveur mort

## Accès distant

- **SSH via onion service Tor** (adresse dans le gestionnaire de mots de passe)

## Checklist sécurité

| Verrou | État |
|---|---|
| SSH clés-only | ✅ |
| Root interdit | ✅ |
| IPv6 coupée | ✅ |
| nftables | ✅ |
| /boot chiffré (clé USB) | ⏳ |

## Roadmap

1. **nftables** (deny all in, sauf SSH LAN)
2. **llama.cpp + Vulkan** sur la 7900 XTX
3. **RAID1 nvme1n1** (mdadm)
4. **/boot sur clé USB duplicable**
5. **Service d'IA partagé** (onion dédié + jetons d'invitation)
6. **Flint 2** : VLANs, box en bridge, migration du réseau
