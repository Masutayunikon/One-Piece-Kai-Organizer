# 📺 Script One Piece Kaï → Plex

Ce script permet d’automatiser l’organisation du pack **One Piece Kaï** pour qu’il soit directement lisible par **Plex / Jellyfin / Emby** :

- **Dézippe** l’archive `One Piece Kaï (Pack Plex).zip` si elle est présente.  
- **Rassemble** tous les épisodes (`.mkv` / `.mp4`) depuis les dossiers `Saga*` dans un seul dossier central.  
- **Renomme** les épisodes au format `SxxEyyy` avec titre et bloc technique.  
- **Range** les fichiers dans les bons dossiers `Saison X` sous `One Piece Kaï/`.  
- **Normalise** aussi les fichiers annexes (`.nfo`, `-thumb.png`, sous-titres, etc.) pour qu’ils correspondent à Plex.  

---

## 📂 Pré-requis

1. Avoir Python 3 installé sur ton serveur.  
2. Le pack **One Piece Kaï (Pack Plex).zip** téléchargé et placé a coté du script
3. Créer un fichier `seasons_config.json` dans le même dossier que le script, par ex. :

```json
   {
     "show_name": "One Piece Yabai",
     "seasons": [
       { "season": 1,  "folder": "Saison 1",  "range": [1, 7] },
       { "season": 2,  "folder": "Saison 2",  "range": [8, 16] },
       { "season": 3,  "folder": "Saison 3",  "range": [17, 22] },
       { "season": 4,  "folder": "Saison 4",  "range": [23, 37] },
       { "season": 5,  "folder": "Saison 5",  "range": [38, 42] },
       { "season": 6,  "folder": "Saison 6",  "range": [43, 55] },
       { "season": 7,  "folder": "Saison 7",  "range": [56, 64] },
       { "season": 8,  "folder": "Saison 8",  "range": [65, 91] },
       { "season": 9,  "folder": "Saison 9",  "range": [92, 108] },
       { "season": 10, "folder": "Saison 10", "range": [109, 131] }
     ]
   }
```

---

## ⚙️ Utilisation

Lance le script depuis le dossier qui contient l’archive :  

```bash
    cd One Piece Kaï/
    python3 onepiece_kai_plex.py [options]
```


### Principales options :

- `--dry-run` → Mode simulation, affiche tout ce qui serait fait sans rien déplacer.  
- `--mode move` *(par défaut)* → Déplace les fichiers.  
- `--mode copy` → Copie les fichiers.  
- `--mode link` → Crée des **hardlinks** (rapide, mais seulement si les fichiers sont sur le même disque).  
- `--mode reflink` → Copie en **copy-on-write** (si ton FS supporte btrfs ou xfs).  

### Autres options :

- `--zip-name` → Nom de l’archive à dézipper (par défaut : `"One Piece Kaï (Pack Plex).zip"`).  
- `--episodes-dir` → Dossier central où regrouper les épisodes (par défaut : `"One Piece Kaï - Episodes"`).  
- `--show-root` → Dossier final contenant les saisons + assets (par défaut : `"One Piece Kaï"`).  
- `--config` → Chemin du fichier JSON de configuration (par défaut : `seasons_config.json` dans le dossier courant).  
- `--ext` → Extensions vidéo à prendre en compte (par défaut : `.mkv,.mp4`).  

---

## 🚀 Exemples

Simulation (recommandé la 1ère fois) :  

```bash
   python3 onepiece_kai_plex.py --dry-run
```

Déplacement réel :  

```bash
   python3 onepiece_kai_plex.py
```

Hardlinks (rapide, même disque) :  

```bash
   python3 onepiece_kai_plex.py --mode link
```

Reflinks (si btrfs/xfs) :  

```bash
   python3 onepiece_kai_plex.py --mode reflink
```

Copie classique :  

```bash
   python3 onepiece_kai_plex.py --mode copy
```

---

## 📑 Résultat attendu

Tous les épisodes seront renommés et classés ainsi :

```bash
One Piece Kaï/
├── Saison 1/
│   ├── One Piece Yabai - S01E001 - Chapeau de Paille - 1080p.MULTI.x264 [Mixouille].mkv
│   ├── One Piece Yabai - S01E001 - Chapeau de Paille - 1080p.MULTI.x264 [Mixouille].nfo
│   ├── One Piece Yabai - S01E001 - Chapeau de Paille - 1080p.MULTI.x264 [Mixouille]-thumb.png
│   └── ...
├── Saison 2/
│   └── ...
└── Saison 10/
    └── ...

```

👉 Avec ce format, Plex ou Jellyfin détectera correctement toutes les saisons et utilisera les `.nfo` et images comme métadonnées locales.
