# 🌿 Rayman Adventures Offline — Kit de Développement & Préservation

*Rayman Adventures* (Ubisoft, 2015) ne fonctionne plus depuis la fermeture de ses serveurs le 26 juin 2023 : plus de nouvelles aventures, plus d'éclosion d'œufs. Ce projet rend la version Android 4.0.0.2086 **jouable entièrement hors ligne** : la bibliothèque native du jeu est patchée et un serveur de jeu est embarqué dans l'APK (il répond à la place des serveurs Ubisoft, sur l'appareil).

## 📥 Télécharger et installer

Dans la page **Releases** du dépôt, télécharger les deux fichiers :
- `RaymanAdventures_Offline.apk` : le jeu patché ;
- `main.2086.com.ubisoft.raymanadventures.obb` : les données du jeu (≈ 420 Mo).

Puis :
1. Désinstaller la version Ubisoft si elle est installée (signature différente).
2. Installer `RaymanAdventures_Offline.apk`.
3. Copier le fichier `.obb` dans `Android/obb/com.ubisoft.raymanadventures/` (créer le dossier).
4. Lancer le jeu. Aucune connexion, aucun compte, aucun root nécessaire.

Testé sur Windows Subsystem for Android (ARM64 émulé). Une manette (Xbox, etc.) est reconnue si elle est connectée **avant** de lancer le jeu.

**Fonctionne** : aventures, œufs et incubateur, élixirs, tickets (probabilités d'Ubisoft), Charlie, loupe, cadeau quotidien, mini-événements, défi quotidien (seul), 3 emplacements de sauvegarde, pubs récompensées (si les régies répondent encore).
**Ne fonctionne plus** : achats en argent réel, Facebook et amis, classements mondiaux, synchronisation cloud, Everyplay, événements saisonniers (pour l'instant). Détails : `docs/AUDIT_2026-11-16.md` et `docs/DOSSIER_TECHNIQUE.md`.

## 🔧 Recompiler

Les fichiers d'Ubisoft ne sont pas dans le dépôt. Pour recompiler, placer :
- l'APK d'origine 4.0.0.2086 dans `apk/base_original.apk` ;
- sa bibliothèque `lib/arm64-v8a/libuaf.so` dans `binaries/libuaf_original.so`.

Outils : Python 3 (`keystone-engine`, `capstone`), Android SDK (build-tools 34, platform 34), JDK (celui d'Android Studio). Ensuite les trois étapes ci-dessous (`build_libuaf_offline.py`, `build_offline_server.py`, `repackage_apk.py`). La clé de signature (`apk/offline_testkey.jks`) est créée au premier build ; garder la même clé pour pouvoir mettre à jour le jeu sans perdre la partie.

---

## 📁 Structure du Dossier Isolé

```
Rayman_Adventures_Offline/
├── README.md                      # Le présent guide
├── RaymanAdventures_Offline.apk   # APK finale compilée, alignée et signée (40.8 Mo)
├── mock_server.py                 # (Dev) ancien serveur d'émulation sur PC — plus nécessaire
├── patch_purchase.py              # Script d'injection des gemmes (50k) et tryBuy
├── patch_ssl.py                   # Script de bypass TLS / certificats
├── store_v2_fixed.json            # Base JSON de la boutique Store V2 avec tous les articles
│
├── apk/                           # Fichiers de base Android & package
│   ├── base_original.apk          # APK d'origine Ubisoft (non modifiée)
│   ├── main.2086...obb            # Fichier de données OBB d'origine (404 Mo)
│   └── offline_testkey.jks        # Clé de signature keystore (alias: offline_key, pass: android)
│
├── binaries/                      # Fichiers binaires natifs ARM64
│   ├── libuaf_original.so         # Bibliothèque native d'origine Ubisoft (36.8 Mo)
│   └── libuaf_emulated.so         # Bibliothèque native patchée opérationnelle (36.8 Mo)
│
├── docs/                          # Documentation technique complète
│   └── DOSSIER_TECHNIQUE.md       # Analyse approfondie, adresses VAddr, rétro-ingénierie
│
├── offline_server/                # Serveur mock EMBARQUÉ dans l'APK (Java)
│   ├── src/com/rayman/offline/    # OfflineServerProvider (auto-start) + OfflineServer (HTTP/TLS)
│   └── assets/offline/            # store_v2.json + server.p12 (certificat auto-signé *.ubi.com)
│
├── mock_data/                     # Fichiers de réponses JSON émulées
│   ├── store_v1.json              # Schéma boutique v1
│   ├── store_v2.json              # Schéma boutique v2 brut
│   └── store_v2_fixed.json        # Schéma boutique v2 corrigé avec métadonnées
│
├── screenshots/                   # Preuves visuelles de validation en jeu
│   ├── screen_tickets.png         # Rayons de la boutique avec tickets surprise dorés
│   ├── screen_ticket_scratch.png  # Mini-jeu de grattage ("Gratte-moi bébé !")
│   ├── screen_scratched.png       # Découverte des récompenses (élixirs de vitesse)
│   ├── screen_map_clean.png       # Déblocage complet du tutoriel & carte Aventure 17
│   └── screen_tree_families.png   # Arbre Sacré (150m, familles de créatures)
│
└── scripts/                       # Outils d'automatisation
    ├── build_libuaf_offline.py    # Reconstruit libuaf_emulated.so (patchs + hooks réseau, incubateur, tickets, œufs ; --debug = instrumentation)
    ├── debug_hooks.py             # Instrumentation de débogage (logs RaymanDbg / RaymanITF)
    ├── net_hooks.py               # Hooks ARM64 getaddrinfo/connect (source asm + octets pré-assemblés)
    ├── build_offline_server.py    # Compile le serveur embarqué (javac + d8) -> classes.dex
    ├── patch_manifest.py          # Patch du AndroidManifest.xml binaire (déclare le provider)
    └── repackage_apk.py           # Injecte .so + dex + assets + manifest, zipalign, apksigner

tools/re/                          # Outils de rétro-ingénierie (capstone) : rdis.py (désassembleur annoté),
                                   # xref.py, endpoints.py (API du serveur de jeu), fields.py (champs ITF),
                                   # binding.py (tables UbiServices), annot.py (logs RaymanDbg -> classes)
backups/                           # (hors git) sauvegarde de test du jeu, cf. « Restaurer la sauvegarde »
```

---

## 🛠️ Instructions d'Utilisation

L'APK est désormais **100 % autonome** : aucun serveur PC, aucun fichier `hosts`, aucun root.

### 1. Recompiler la bibliothèque native (`libuaf_emulated.so`)
```powershell
python scripts/build_libuaf_offline.py
```
Applique les zones de patches historiques (Safe `atoi`/`atol`, bypass TLS…), les correctifs « en ligne » (serveur de jeu, incubateur synchronisé avec le serveur) **et** les hooks de `scripts/net_hooks.py` et `scripts/incubator_hooks.py`. L'ancienne « Code Cave `isItemOfType` » n'est plus branchée : le catalogue de la boutique porte les vrais attributs `ITEM_TYPE`.

### 2. Compiler le serveur embarqué
```powershell
python scripts/build_offline_server.py
```
Produit `offline_server/build/classes.dex` (javac + d8 du SDK Android) et génère au besoin le keystore TLS `offline_server/assets/offline/server.p12`.

### 3. Reconstruire et signer l'APK
```powershell
python scripts/repackage_apk.py
```
Injecte `libuaf.so`, `classes5.dex`, `assets/offline/*`, déclare le provider dans le manifeste binaire, puis zipalign + signature v1/v2/v3 avec `offline_testkey.jks`.

### (Optionnel) Serveur mock sur PC
`python mock_server.py` reste utilisable pour le débogage, mais n'est plus requis.

---

## 🔌 Fonctionnement de l'autonomie réseau

```
libuaf.so (curl + OpenSSL embarqués)
  getaddrinfo("xxx.ubi.com")  --hook-->  getaddrinfo("127.0.0.1")
  connect(127.0.0.1:443)      --hook-->  connect(127.0.0.1:18443)   (:80 -> :18080)
                                             |
OfflineServerProvider (démarré par Android avant toute Activity)
  OfflineServer : HTTP 127.0.0.1:18080 + HTTPS 127.0.0.1:18443 (certificat auto-signé,
                  accepté grâce au bypass TLS déjà présent dans libuaf.so)
```
Les requêtes servies sont visibles avec `adb logcat -s RaymanOffline`.

---

## 📱 Installation sur un Appareil Android

1. Si la version Ubisoft d'origine est installée, la désinstaller d'abord (signature différente → `INSTALL_FAILED_UPDATE_INCOMPATIBLE`).
2. Installer l'APK : `RaymanAdventures_Offline.apk`
3. Placer le fichier OBB `main.2086.com.ubisoft.raymanadventures.obb` dans :
   `Android/obb/com.ubisoft.raymanadventures/`
4. Lancer le jeu et **accepter l'accès au stockage** (requis pour la sauvegarde).

---

## 🔍 Ce qu'il reste à analyser et développer
1. ~~**Autonomie 100% sans serveur externe**~~ ✅ fait (hooks `getaddrinfo`/`connect` + serveur embarqué), validé sur WSA : écran titre, carte Aventure 17, 50 000 gemmes, boutique.
   - Reste : la couche Java `NetworkCoreAndroid` appelle `https://rc.ubi.com/v1/deviceconfig/...` via `HttpsURLConnection` (hors `libuaf.so`) ; l'appel échoue proprement et le jeu continue avec sa configuration par défaut.
2. **Gameplay étendu** :
   - Validation de l'éclosion complète dans l'incubateur via élixir.
   - Test du nourrissage des créatures dans l'Arbre Sacré.
   - Parcours complet des niveaux de l'Aventure 17.
3. **Test sur un vrai téléphone ARM64** (WSA est la seule plateforme validée à ce jour).
4. **Serveur de jeu RLC** (`offline_server/src/com/rayman/offline/`) : session, sauvegarde serveur, créatures, **tickets à gratter** (tirage avec les tables de probabilités d'Ubisoft retrouvées dans les données du jeu, œufs compris), **incubateur et éclosion** fonctionnent hors-ligne (validé sur WSA : « NOUVEAU ! Flore », famille complète, arbre 190 m). L'incubateur est synchronisé avec le serveur (l'œuf ne disparaît plus au toucher ; les œufs incubés par les anciennes versions sont conservés ; les élixirs or / argent / nouvelle créature changent bien la créature obtenue) et la **boutique d'élixirs** crédite les achats ; les **gemmes** sont réelles (plus de solde figé à 50 000) (élixirs déjà possédés de nouveau visibles). **Cadeau quotidien** et **Défi quotidien** (runner « Mini-marathon » : graine du jour, jetons, score, classement local, fantôme = ton propre dernier run, récompense à encaisser le lendemain) fonctionnent aussi. L'œuf caché « Charlie » et la loupe (œufs des prochaines aventures) sont gérés, le jeu choisissant lui-même la créature. Sans équivalent hors ligne (réponses vides) : économiseur de temps, perks, amis Facebook (détails : `docs/DOSSIER_TECHNIQUE.md`, Phase 1b).

### Restaurer la sauvegarde de test (WSA rooté)
Script : `sh scripts/restore_test_save.sh` (ou à la main :)
`backups/data.tgz` et `backups/extdata.tgz` (hors git) contiennent l'état du 15/11/2026 (Aventure 17, un œuf incubé localement prêt à éclore) ; `backups/user_20261116_*.tgz` la partie du joueur du 16/11/2026 (Aventure 19) :
```bash
adb push backups/data.tgz /sdcard/rayman_backup/data.tgz
```
```bash
adb shell "su -c 'P=com.ubisoft.raymanadventures; U=\$(stat -c %u /data/data/\$P); am force-stop \$P; rm -rf /data/data/\$P/*; tar xzf /sdcard/rayman_backup/data.tgz -C /data/data; chown -R \$U:\$U /data/data/\$P; restorecon -R /data/data/\$P'"
```
