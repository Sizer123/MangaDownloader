# Scripts « hyperspeed » — Récapitulatif

Documentation des trois scripts `hyperspeed_manga_script_downloader_*.py` : ce qu'ils font,
comment ils fonctionnent, et leurs limites connues.

---

## 1. Vue d'ensemble

Ces scripts sont des **téléchargeurs de masse hors-ligne**. Ils ne font aucun scraping :
ils consomment un fichier JSON déjà produit par les scripts d'extraction
(`phenix_scans_*.py`, `demonic_scans_*.py`, ou les scripts Tampermonkey
`tampermonkey_manga_console_json_export*.js`) et se contentent de :

1. lire le JSON (liste des chapitres → liste d'URLs d'images) ;
2. télécharger toutes les images **en parallèle** (10 threads) ;
3. empaqueter chaque dossier de chapitre en fichier `.cbr`.

Pipeline global du projet :

```text
Site web  →  script d'extraction (Selenium/BeautifulSoup/Tampermonkey)  →  fichier .json
                                                                              │
                                                              script hyperspeed (ce document)
                                                                              │
                                                          dossiers d'images  +  CBR/*.cbr
```

---

## 2. Les trois fichiers

| Fichier | JSON d'entrée (en dur, ligne ~207) |
| --- | --- |
| `hyperspeed_manga_script_downloader_hyperspeed.py` | `hyper_manga_data.json` |
| `hyperspeed_manga_script_downloader_hyperspeed_v2.py` | `hyper_manga_data.json` |
| `hyperspeed_manga_script_downloader_2_speed_v3.py` | `manga_script_json.txt` |

> **⚠️ À savoir : ces trois scripts sont le même code.**
> `hyperspeed.py` et `hyperspeed_v2.py` sont **strictement identiques** (même MD5).
> `2_speed_v3.py` en diffère par **une seule ligne** : le nom du fichier d'entrée.
> Les suffixes `v2` / `v3` ne correspondent donc à aucune évolution fonctionnelle —
> ce sont des copies faites pour changer le fichier source. Voir §7.

---

## 3. Format du JSON d'entrée

```json
{
  "projectName": "wistoria__wand_and_sword",
  "chapters": {
    "Chapitre 5 - Chapitre 5Il y a 1 mois": {
      "url": "https://phenix-scans.com/manga/.../chapitre/5",
      "images": [
        "https://api.phenix-scans.co/uploads/mangas/.../1.webp?width=720",
        "https://api.phenix-scans.co/uploads/mangas/.../2.webp?width=720"
      ]
    }
  }
}
```

- `projectName` → devient le **nom du dossier de sortie** (défaut : `manga`).
- `chapters` → dictionnaire `nom_du_chapitre → { url, images }`.
- Le champ `url` **n'est jamais utilisé** par le script (informatif seulement).
- L'extension `.txt` de `manga_script_json.txt` est trompeuse : c'est du JSON.

---

## 4. Arborescence de sortie

```text
<projectName>/
├── CBR/
│   ├── Chapter_005 - Chapitre_5.cbr
│   ├── Chapter_006 - Chapitre_6.cbr
│   └── ...
├── Chapitre_5_-_Chapitre_5Il_y_a_1_mois/
│   ├── page_001.webp
│   ├── page_002.webp
│   └── ...
└── Chapitre_6_-_Chapitre_6Il_y_a_1_mois/
    └── ...
```

Les dossiers d'images sont **conservés** après la création des CBR (le script suggère
seulement, en fin d'exécution, de les supprimer manuellement pour gagner de la place).

---

## 5. Fonctionnement détaillé

### 5.1 Préparation — `prepare_download_tasks()`

Aplatit le JSON en une liste plate de `DownloadTask(url, filepath, page_number, chapter_name)`.

- Les chapitres sont triés via `extract_chapter_number()` (regex `Chapitre (\d+)`).
- Le nom du dossier vient de `sanitize_filename()` : suppression de `<>:"/\|?*`, espaces → `_`.
- Le nom de fichier est **normalisé et renuméroté** : `page_001.webp`, `page_002.webp`…
  L'index vient de la **position dans le tableau `images`**, pas du nom d'origine.
  → l'ordre du JSON fait foi pour l'ordre de lecture.
- L'extension est déduite du chemin de l'URL (`urlparse` retire le `?width=720`) ;
  repli sur une détection par mots-clés dans l'URL, puis `jpg` par défaut.

### 5.2 Téléchargement — `download_image_optimized()`

- **`ThreadPoolExecutor(max_workers=10)`** : 10 images en vol simultanément.
- **10 sessions `requests` pré-créées**, distribuées en round-robin (`i % max_workers`).
  Chaque session monte un `HTTPAdapter` avec `pool_connections=20`, `pool_maxsize=20`
  et un **retry automatique** (3 tentatives, `backoff_factor=0.3`, sur 500/502/503/504).
  → keep-alive : on évite de refaire un handshake TLS par image.
- **Reprise gratuite** : si `filepath.exists()`, l'image est comptée « skipped » et ignorée.
  Relancer le script après une interruption ne retélécharge donc rien.
- Écriture en **streaming** par chunks de 8 Ko (`stream=True`) — l'image ne passe jamais
  entièrement en RAM. Timeout de 30 s par requête.
- Une exception sur une image est **attrapée et comptée en échec** : elle n'interrompt
  jamais le reste du téléchargement.

### 5.3 Suivi de progression

Un thread `daemon` dédié (`progress_monitor`) consomme une `queue.Queue` alimentée par
les workers, et affiche `[42.3%] ✅ Chapitre 5 - Page 007`. Les compteurs vivent dans
`DownloadStats`, protégés par un `threading.Lock`.

### 5.4 Empaquetage CBR — `create_cbr_from_folder()`

Un `.cbr` ici est en réalité un **ZIP** (`zipfile.ZIP_DEFLATED`, `compresslevel=1` —
compression minimale, car JPEG/WebP sont déjà compressés ; on privilégie la vitesse).
Les images y sont ajoutées **à plat**, triées par nom, sans dossier parent.

Nom généré : `Chapter_{num:03d} - {préfixe du nom de chapitre}.cbr`.

> Techniquement un vrai `.cbr` est une archive **RAR** ; un ZIP est un `.cbz`.
> Tous les lecteurs courants (CDisplayEx, YACReader, Komga, Tachiyomi…) ouvrent
> l'un comme l'autre sans se soucier de l'extension, donc c'est sans conséquence pratique.

---

## 6. Utilisation

```bash
pip install requests          # seule dépendance réellement utilisée ici
python hyperspeed_manga_script_downloader_hyperspeed.py
```

Le script **ne prend aucun argument**. Pour changer de manga, il faut éditer
la variable `json_file` dans `main()` (ligne ~207). `max_workers` (ligne ~208)
règle le parallélisme.

Exécuter depuis la racine du projet : les chemins sont relatifs au dossier courant.

---

## 7. Bugs corrigés (2026-07-20)

### CBR vides malgré des images téléchargées ✅ corrigé

`create_cbr_from_folder()` filtrait sur `['.jpg', '.jpeg', '.png', '.gif', '.bmp']` —
**`.webp` absent**. Or Phenix Scans sert tout en WebP. La liste d'images ressortait vide,
mais le ZIP était quand même créé puis refermé → **archive valide contenant 0 fichier**,
et le script affichait tout de même `📦 CBR créé`.

Corrections appliquées aux trois fichiers :

- ajout de `.webp`, `.avif`, `.jxl` à la liste des extensions ;
- le listing se fait **avant** l'ouverture du ZIP, et si aucune image n'est trouvée,
  la fonction **avertit et retourne `False` sans créer de fichier** (plus de CBR fantôme) ;
- `prepare_download_tasks()` : la détection d'extension de repli connaît désormais
  `webp` (testé en premier) et `avif`.

Vérifié sur `wistoria__wand_and_sword/Chapitre_10` : **42 entrées / 27,16 Mo**, contre 0 avant.

---

### CBR vides jamais régénérés ✅ corrigé

`main()` sautait la création dès que `cbr_path.exists()`, sans regarder le contenu :
les archives vides du bug précédent n'étaient donc **jamais reconstruites**, même en
relançant le script. Ajout d'un helper `cbr_is_valid()` qui ouvre l'archive et vérifie
qu'elle contient au moins une entrée ; un CBR vide ou illisible est supprimé puis
régénéré (message `♻️`).

---

## 8. Script fusionné : `manga_hyperspeed.py` ⭐ recommandé

Remplace les trois scripts par un seul, avec **sélection interactive du JSON**.

```bash
python manga_hyperspeed.py                    # liste les JSON du dossier et demande
python manga_hyperspeed.py mon_manga.json     # fichier imposé
python manga_hyperspeed.py -w 16              # 16 téléchargements simultanés
python manga_hyperspeed.py --cbr-only         # reconstruit les CBR, sans rien télécharger
python manga_hyperspeed.py --rebuild-cbr      # force la régénération de tous les CBR
python manga_hyperspeed.py --no-cbr           # télécharge sans empaqueter
```

Sans argument, il scanne le répertoire, ne garde que les fichiers contenant réellement
un objet `chapters` non vide (les `progress_backup_*.json` et `nexa_blueprint_schema.json`
sont donc écartés), et affiche un menu :

```text
📚 14 fichier(s) exploitable(s) trouvé(s):

  [ 3] hyper_manga_data.json 📂
       └─ projet: wistoria__wand_and_sword  |  64 chapitres  |  2483 images
```

Le 📂 signale qu'un dossier de sortie existe déjà (reprise). Les `.txt` du projet qui
contiennent du JSON (`manga_script_json*.txt`) sont inclus automatiquement.

### Apports par rapport aux scripts d'origine

| Point | Avant | Maintenant |
|---| --- | --- |
| Fichier d'entrée | en dur dans le code | menu interactif ou argument CLI |
| Chapitres décimaux | `21.5` → `21` (tri ambigu) | `021.5`, tri correct |
| Chapitres non numérotés | tous → `Chapter_000` (écrasement) | `Chapter_XXX`, rejetés en fin |
| CBR vide/incomplet | jamais régénéré | détecté et reconstruit |
| Écriture des fichiers | directe | temporaire `.part` + `os.replace` (atomique) |
| Fichier vide (0 octet) | compté comme réussi | traité comme échec |
| Échecs | comptés seulement | journalisés dans `echecs_telechargement.json` |
| Duplication | 3 copies | 1 seul fichier |

La validation va un cran plus loin que « non vide » : `cbr_is_valid()` compare le nombre
d'entrées de l'archive au nombre d'images du dossier, donc un CBR **partiel** (créé lors
d'une interruption) est aussi régénéré.

### Vérifications effectuées

- Reconstruction réelle : `Chapter_010 - Chapitre_10.cbr` → **42 pages, 25,9 Mo**.
- Idempotence : au 2ᵉ passage, `CBR déjà complet`, rien n'est réécrit.
- Régénération testée sur les 3 cas : archive **vide**, **incomplète** (20/42), **corrompue**.
- Téléchargement réel de 4 images `.webp` → CBR de 4 pages, 0 échec.

---

## 9. Limites restantes

- **Aucune validation du contenu téléchargé.** Une page d'erreur HTML renvoyée en HTTP 200
  est enregistrée telle quelle en `.webp`. Seule la taille nulle est détectée ; il n'y a pas
  de contrôle des magic bytes.
- **Extension déduite de l'URL, pas du `Content-Type`.** Un serveur qui sert du JPEG sous
  une URL en `.webp` produirait un fichier mal nommé (sans conséquence pour les lecteurs).
- **`.cbr` contenant un ZIP** : voir §5.4 — sans impact pratique, mais `.cbz` serait exact.
- **Les dossiers d'images sont conservés** après création des CBR (suppression manuelle).
- Les trois anciens scripts sont conservés et corrigés, mais **`manga_hyperspeed.py` est
  celui à utiliser** ; les autres ne servent plus que de référence.
