#!/usr/bin/env python3
"""
watch_downloads.py — Surveille le dossier Téléchargements et automatise l'import
des JSON de manga.

Fonctionnement :
  1. Surveille le répertoire Téléchargements (polling, aucune dépendance externe).
  2. Dès qu'un fichier .json apparaît ET respecte la structure attendue par le
     script hyperspeed v2 ({projectName, chapters}), il est déplacé dans le
     dossier data/ du projet.
  3. Le téléchargement est ensuite lancé automatiquement DANS UNE NOUVELLE FENÊTRE
     de terminal via le script hyperspeed v2, en lui passant le JSON en argument.
  4. Chaque fichier traité est consigné dans un journal persistant
     (watch_downloads_processed.json) pour ne jamais être repris, même après
     un redémarrage du watcher.

Usage :
    python scripts/utils/watch_downloads.py                # surveillance continue
    python scripts/utils/watch_downloads.py --once         # traite l'existant puis quitte
    python scripts/utils/watch_downloads.py --no-launch    # déplace sans lancer le DL
    python scripts/utils/watch_downloads.py --interval 3   # intervalle de polling (s)
    python scripts/utils/watch_downloads.py --downloads "D:/Downloads"
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------- #
# Chemins du projet
# --------------------------------------------------------------------------- #

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / 'data'
HYPERSPEED_V2 = (PROJECT_ROOT / 'scripts' / 'downloaders'
                 / 'hyperspeed_manga_script_downloader_hyperspeed_v2.py')

# Journal persistant des fichiers déjà traités (pour ne pas les reprendre au redémarrage)
LOG_FILE = PROJECT_ROOT / 'scripts' / 'utils' / 'watch_downloads_processed.json'

# On ne cible QUE les fichiers .json
CANDIDATE_SUFFIXES = ('.json',)

# Extensions de fichiers "en cours d'écriture" par le navigateur -> à ignorer
PARTIAL_SUFFIXES = ('.crdownload', '.part', '.tmp', '.download')


# --------------------------------------------------------------------------- #
# Journal persistant des fichiers traités
# --------------------------------------------------------------------------- #

def load_processed_log() -> dict:
    """
    Charge le journal des fichiers déjà traités.

    Structure : { "<nom_de_fichier>": {"processed_at": "...", "project": "...",
                                       "size": <octets>} }
    Un journal absent ou corrompu est traité comme vide (jamais bloquant).
    """
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return {}


def save_processed_log(log: dict) -> None:
    """Écrit le journal de façon atomique (fichier temporaire + remplacement)."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = LOG_FILE.with_suffix('.json.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
        os.replace(tmp, LOG_FILE)
    except OSError as e:
        print(f"⚠️  Impossible d'écrire le journal : {e}")


def log_key(path: Path) -> str:
    """Clé d'identité d'un fichier dans le journal : son nom, insensible à la casse."""
    return path.name.lower()


# --------------------------------------------------------------------------- #
# Détection du dossier Téléchargements
# --------------------------------------------------------------------------- #

def find_downloads_dir() -> Path:
    """Localise le dossier Téléchargements de l'utilisateur (Windows/macOS/Linux)."""
    candidates = []
    home = Path.home()
    candidates.append(home / 'Downloads')
    candidates.append(home / 'Téléchargements')

    userprofile = os.environ.get('USERPROFILE')
    if userprofile:
        candidates.append(Path(userprofile) / 'Downloads')

    for c in candidates:
        if c.is_dir():
            return c
    # Repli : on renvoie ~/Downloads même s'il n'existe pas encore
    return home / 'Downloads'


# --------------------------------------------------------------------------- #
# Validation de la structure
# --------------------------------------------------------------------------- #

def is_valid_manga_json(path: Path):
    """
    Vérifie qu'un fichier respecte la structure attendue par hyperspeed v2.

    Retourne un dict résumé si valide (projectName, chapter_count, image_count),
    sinon None. Un fichier partiel ou illisible renvoie None sans lever d'erreur.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    chapters = data.get('chapters')
    if not isinstance(chapters, dict) or not chapters:
        return None

    # Au moins un chapitre doit avoir une liste d'images non vide.
    total_images = 0
    has_images = False
    for chapter in chapters.values():
        if isinstance(chapter, dict):
            images = chapter.get('images')
            if isinstance(images, list):
                total_images += len(images)
                if images:
                    has_images = True
    if not has_images:
        return None

    return {
        'project_name': data.get('projectName') or path.stem,
        'chapter_count': len(chapters),
        'image_count': total_images,
    }


def is_stable(path: Path, wait: float = 1.5) -> bool:
    """
    Vérifie que le fichier n'est plus en cours d'écriture : sa taille ne doit
    pas changer sur un court intervalle. Évite de traiter un téléchargement
    encore partiel.
    """
    try:
        size1 = path.stat().st_size
        time.sleep(wait)
        size2 = path.stat().st_size
    except OSError:
        return False
    return size1 == size2 and size1 > 0


# --------------------------------------------------------------------------- #
# Déplacement + lancement
# --------------------------------------------------------------------------- #

def unique_destination(dest_dir: Path, filename: str) -> Path:
    """Retourne un chemin de destination non existant (ajoute _1, _2… si besoin)."""
    dest = dest_dir / filename
    if not dest.exists():
        return dest
    stem, suffix = Path(filename).stem, Path(filename).suffix
    i = 1
    while True:
        candidate = dest_dir / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def move_to_data(src: Path) -> Path:
    """Déplace le fichier vers data/ et retourne le nouveau chemin."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = unique_destination(DATA_DIR, src.name)
    # os.replace échoue entre volumes différents ; on retombe sur un move manuel.
    try:
        os.replace(src, dest)
    except OSError:
        import shutil
        shutil.move(str(src), str(dest))
    return dest


def launch_download_in_new_terminal(json_path: Path) -> None:
    """
    Lance hyperspeed v2 dans une NOUVELLE fenêtre de terminal, en lui passant
    le JSON en argument. Le téléchargement tourne indépendamment du watcher.
    """
    python_exe = sys.executable or 'python'
    cmd_args = [python_exe, str(HYPERSPEED_V2), str(json_path)]

    if os.name == 'nt':
        # 'start' ouvre une nouvelle console ; le premier "" est le titre de la fenêtre.
        # /k garde la fenêtre ouverte après la fin du script (pour lire le résumé).
        title = f"Hyperspeed - {json_path.stem}"
        quoted = ' '.join(f'"{a}"' for a in cmd_args)
        subprocess.Popen(
            f'start "{title}" cmd /k {quoted}',
            shell=True,
            cwd=str(PROJECT_ROOT),
        )
    elif sys.platform == 'darwin':
        script = ' '.join(f"'{a}'" for a in cmd_args)
        osa = (f'tell application "Terminal" to do script '
               f'"cd {PROJECT_ROOT!s}; {script}"')
        subprocess.Popen(['osascript', '-e', osa])
    else:
        # Linux : on tente quelques émulateurs courants, sinon exécution en arrière-plan.
        for term in ('x-terminal-emulator', 'gnome-terminal', 'konsole', 'xterm'):
            if _which(term):
                subprocess.Popen([term, '-e'] + cmd_args, cwd=str(PROJECT_ROOT))
                return
        subprocess.Popen(cmd_args, cwd=str(PROJECT_ROOT))


def _which(name: str) -> bool:
    from shutil import which
    return which(name) is not None


# --------------------------------------------------------------------------- #
# Boucle de surveillance
# --------------------------------------------------------------------------- #

def process_file(path: Path, launch: bool, log: dict):
    """
    Valide, déplace et (optionnellement) lance le téléchargement.

    Retourne :
      'done'    → fichier traité (déplacé + journalisé),
      'skip'    → fichier non pertinent (à marquer vu, ne plus réévaluer),
      'retry'   → fichier valide mais encore instable (à réessayer au tour suivant).
    """
    info = is_valid_manga_json(path)
    if info is None:
        return 'skip'

    if not is_stable(path):
        # Fichier encore en cours d'écriture : on le retraitera au prochain tour.
        return 'retry'

    print(f"\n📥 JSON manga détecté : {path.name}")
    print(f"   projet: {info['project_name']}  |  "
          f"{info['chapter_count']} chapitres  |  {info['image_count']} images")

    try:
        dest = move_to_data(path)
    except OSError as e:
        print(f"   ❌ Échec du déplacement : {e}")
        return 'skip'
    try:
        shown = dest.relative_to(PROJECT_ROOT)
    except ValueError:
        shown = dest
    print(f"   ➡️  Déplacé vers : {shown}")

    if launch:
        launch_download_in_new_terminal(dest)
        print(f"   🚀 Téléchargement lancé dans une nouvelle fenêtre de terminal.")
    else:
        print(f"   ⏸️  Lancement désactivé (--no-launch).")

    # Journalise le fichier traité pour ne jamais le reprendre, même après redémarrage.
    log[log_key(path)] = {
        'processed_at': datetime.now().isoformat(timespec='seconds'),
        'project': info['project_name'],
        'moved_to': str(dest.name),
    }
    save_processed_log(log)

    return 'done'


def scan_once(downloads_dir: Path, seen: set, launch: bool, log: dict) -> int:
    """Un passage de surveillance. Retourne le nombre de fichiers traités."""
    processed = 0
    try:
        entries = list(downloads_dir.iterdir())
    except OSError:
        return 0

    for entry in entries:
        if not entry.is_file():
            continue
        if entry.suffix.lower() in PARTIAL_SUFFIXES:
            continue
        if entry.suffix.lower() not in CANDIDATE_SUFFIXES:
            continue
        if entry in seen:
            continue
        # Déjà traité lors d'une session précédente (journal persistant).
        if log_key(entry) in log:
            seen.add(entry)
            continue

        result = process_file(entry, launch, log)
        if result == 'done':
            processed += 1
            seen.add(entry)
        elif result == 'skip':
            # Non pertinent : marqué vu pour ne pas le réévaluer indéfiniment.
            seen.add(entry)
        # 'retry' : on ne le marque PAS vu → réessai au prochain passage.

    return processed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Surveille le dossier Téléchargements et importe les JSON de manga."
    )
    parser.add_argument('--downloads', default=None,
                        help="Dossier à surveiller (défaut: dossier Téléchargements détecté)")
    parser.add_argument('--interval', type=float, default=2.0,
                        help="Intervalle de polling en secondes (défaut: 2)")
    parser.add_argument('--once', action='store_true',
                        help="Traite les fichiers déjà présents puis quitte")
    parser.add_argument('--no-launch', action='store_true',
                        help="Déplace les JSON sans lancer le téléchargement")
    args = parser.parse_args()

    downloads_dir = Path(args.downloads) if args.downloads else find_downloads_dir()
    launch = not args.no_launch

    if not HYPERSPEED_V2.exists():
        print(f"❌ Script hyperspeed introuvable : {HYPERSPEED_V2}")
        return 1

    log = load_processed_log()

    print("=" * 64)
    print("👁️  WATCH DOWNLOADS — import automatique des JSON de manga")
    print("=" * 64)
    print(f"📂 Surveillance : {downloads_dir}")
    print(f"📁 Destination  : {DATA_DIR}")
    print(f"🚀 Lancement    : {'activé (hyperspeed v2)' if launch else 'désactivé'}")
    print(f"⏱️  Intervalle   : {args.interval}s")
    print(f"📓 Journal      : {len(log)} fichier(s) déjà traité(s) enregistré(s)")
    print("=" * 64)

    if not downloads_dir.is_dir():
        print(f"❌ Dossier de surveillance introuvable : {downloads_dir}")
        return 1

    # On mémorise l'existant pour ne traiter, en mode continu, que les NOUVEAUX
    # fichiers — sauf en mode --once où l'on veut justement traiter l'existant.
    # Le journal persistant (LOG_FILE) empêche de retraiter un fichier déjà
    # importé lors d'une session précédente, même s'il est encore dans Downloads.
    seen: set = set()
    if not args.once:
        for entry in downloads_dir.iterdir():
            if entry.is_file():
                seen.add(entry)
        print(f"ℹ️  {len(seen)} fichier(s) déjà présent(s) ignoré(s). "
              f"En attente de nouveaux JSON…\n")

    if args.once:
        count = scan_once(downloads_dir, seen, launch, log)
        print(f"\n✅ Terminé. {count} fichier(s) importé(s).")
        return 0

    try:
        while True:
            scan_once(downloads_dir, seen, launch, log)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n⏹️  Surveillance arrêtée.")
        return 0


if __name__ == '__main__':
    sys.exit(main())
