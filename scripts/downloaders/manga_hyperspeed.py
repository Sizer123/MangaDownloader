#!/usr/bin/env python3
"""
Manga Hyperspeed — téléchargeur parallèle + compilateur CBR.

Fusion des trois scripts hyperspeed_manga_script_downloader_*.py.
Sans argument, le script liste les fichiers JSON du répertoire courant
et propose de choisir lequel traiter.

Usage:
    python manga_hyperspeed.py                      # sélection interactive
    python manga_hyperspeed.py mon_manga.json       # fichier imposé
    python manga_hyperspeed.py -j x.json -w 16      # 16 téléchargements simultanés
    python manga_hyperspeed.py --no-cbr             # téléchargement seul
    python manga_hyperspeed.py --rebuild-cbr        # reconstruit tous les CBR
"""

import argparse
import json
import os
import queue
import re
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.avif', '.jxl']

# Certains JSON du projet portent l'extension .txt alors que le contenu est du JSON.
JSON_GLOBS = ['*.json', 'manga_script_json*.txt']

# Racine du projet (deux niveaux au-dessus de scripts/downloaders/manga_hyperspeed.py)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / 'data'
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / 'manga_downloads'


# --------------------------------------------------------------------------- #
# Modèles
# --------------------------------------------------------------------------- #

@dataclass
class DownloadTask:
    url: str
    filepath: Path
    page_number: int
    chapter_name: str


class DownloadStats:
    def __init__(self):
        self.lock = threading.Lock()
        self.total_images = 0
        self.downloaded_images = 0
        self.failed_images = 0
        self.skipped_images = 0
        self.failures: List[Tuple[str, int, str, str]] = []

    def add_success(self):
        with self.lock:
            self.downloaded_images += 1

    def add_failure(self, chapter_name: str, page_number: int, url: str, error: str):
        with self.lock:
            self.failed_images += 1
            self.failures.append((chapter_name, page_number, url, error))

    def add_skip(self):
        with self.lock:
            self.skipped_images += 1

    def get_stats(self):
        with self.lock:
            return {
                'total': self.total_images,
                'downloaded': self.downloaded_images,
                'failed': self.failed_images,
                'skipped': self.skipped_images,
            }


# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #

def sanitize_filename(filename: str) -> str:
    """Nettoie le nom de fichier pour éviter les caractères problématiques"""
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = re.sub(r'\s+', '_', filename.strip())
    return filename.rstrip('. ')[:150]


def extract_chapter_number(chapter_name: str) -> float:
    """
    Extrait le numéro de chapitre pour le tri.

    Gère les décimaux ('Chapitre 21.5' -> 21.5) et accepte les libellés
    anglais ('Chapter 7'). Renvoie +inf si aucun numéro n'est trouvé, afin que
    les chapitres non numérotés soient rejetés en fin de liste plutôt que
    regroupés en tête sous le numéro 0.
    """
    match = re.search(r'(?:chapitre|chapter|ch\.?|ep\.?|episode)\s*(\d+(?:[.,]\d+)?)',
                      chapter_name, re.IGNORECASE)
    if not match:
        match = re.search(r'(\d+(?:[.,]\d+)?)', chapter_name)
    if not match:
        return float('inf')
    return float(match.group(1).replace(',', '.'))


def format_chapter_number(number: float) -> str:
    """Formate le numéro pour un nom de fichier triable: 21 -> '021', 21.5 -> '021.5'"""
    if number == float('inf'):
        return 'XXX'
    if number == int(number):
        return f"{int(number):03d}"
    integer_part = int(number)
    decimal_part = f"{number:.10g}".split('.')[1]
    return f"{integer_part:03d}.{decimal_part}"


def guess_extension(image_url: str, fallback_index: int) -> str:
    """Détermine l'extension de l'image à partir de l'URL"""
    parsed_url = urlparse(image_url)
    original_filename = parsed_url.path.split('/')[-1]

    if '.' in original_filename:
        candidate = original_filename.split('.')[-1].lower()
        if f'.{candidate}' in IMAGE_EXTENSIONS:
            return 'jpg' if candidate == 'jpeg' else candidate

    url_lower = image_url.lower()
    for ext in ['webp', 'avif', 'jpeg', 'jpg', 'png', 'gif', 'jxl']:
        if f'.{ext}' in url_lower:
            return 'jpg' if ext == 'jpeg' else ext
    return 'jpg'


def create_session() -> requests.Session:
    """Crée une session réutilisable avec des optimisations"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    })
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=20,
        pool_maxsize=20,
        max_retries=requests.adapters.Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=[500, 502, 503, 504],
        ),
    )
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


# --------------------------------------------------------------------------- #
# Sélection du fichier JSON
# --------------------------------------------------------------------------- #

def describe_json(path: Path) -> Optional[Dict]:
    """Lit un JSON candidat et en extrait un résumé, ou None s'il est inexploitable"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None
    chapters = data.get('chapters')
    if not isinstance(chapters, dict) or not chapters:
        return None

    total_images = sum(
        len(c.get('images', []))
        for c in chapters.values()
        if isinstance(c, dict)
    )
    return {
        'path': path,
        'project_name': data.get('projectName', path.stem),
        'chapter_count': len(chapters),
        'image_count': total_images,
    }


def find_json_candidates(directory: Path) -> List[Dict]:
    """Retourne les fichiers du répertoire exploitables par ce script"""
    seen = set()
    candidates = []
    for pattern in JSON_GLOBS:
        for path in sorted(directory.glob(pattern)):
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            info = describe_json(path)
            if info:
                candidates.append(info)
    return candidates


def select_json_file(directory: Path) -> Optional[Dict]:
    """Affiche les JSON disponibles et demande à l'utilisateur de choisir"""
    print(f"🔍 Recherche des fichiers JSON dans: {directory}\n")
    candidates = find_json_candidates(directory)

    if not candidates:
        print("❌ Aucun fichier JSON exploitable trouvé dans ce répertoire.")
        print("   Le fichier doit contenir un objet 'chapters' non vide.")
        return None

    print(f"📚 {len(candidates)} fichier(s) exploitable(s) trouvé(s):\n")
    width = len(str(len(candidates)))
    for i, info in enumerate(candidates, 1):
        already = (DEFAULT_OUTPUT_DIR / info['project_name']).is_dir()
        marker = ' 📂' if already else ''
        print(f"  [{i:>{width}}] {info['path'].name}{marker}")
        print(f"       {'└─'} projet: {info['project_name']}  |  "
              f"{info['chapter_count']} chapitres  |  {info['image_count']} images")
    print(f"\n  [{'0':>{width}}] Annuler\n")

    while True:
        try:
            answer = input(f"👉 Votre choix [1-{len(candidates)}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n⏹️  Annulé.")
            return None

        if answer in ('0', 'q', 'Q'):
            print("⏹️  Annulé.")
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(candidates):
            return candidates[int(answer) - 1]
        print(f"⚠️  Entrée invalide. Saisissez un nombre entre 1 et {len(candidates)}.")


# --------------------------------------------------------------------------- #
# Téléchargement
# --------------------------------------------------------------------------- #

def download_image(task: DownloadTask, session: requests.Session,
                   stats: DownloadStats, progress_queue: queue.Queue) -> bool:
    """Télécharge une image de manière optimisée"""
    try:
        # Un fichier déjà présent et non vide est considéré comme acquis
        if task.filepath.exists() and task.filepath.stat().st_size > 0:
            stats.add_skip()
            progress_queue.put(f"⏭️  Déjà présent: {task.filepath.name}")
            return True

        response = session.get(task.url, timeout=30, stream=True)
        response.raise_for_status()

        task.filepath.parent.mkdir(parents=True, exist_ok=True)

        # Écriture dans un fichier temporaire: une interruption ne laisse pas
        # un fichier partiel qui serait ensuite considéré comme complet.
        temp_path = task.filepath.with_suffix(task.filepath.suffix + '.part')
        bytes_written = 0
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    bytes_written += len(chunk)

        if bytes_written == 0:
            temp_path.unlink(missing_ok=True)
            raise ValueError("réponse vide (0 octet)")

        os.replace(temp_path, task.filepath)
        stats.add_success()
        progress_queue.put(f"✅ {task.chapter_name} - Page {task.page_number:03d}")
        return True

    except Exception as e:
        stats.add_failure(task.chapter_name, task.page_number, task.url, str(e))
        progress_queue.put(
            f"❌ Erreur {task.chapter_name} - Page {task.page_number:03d}: {str(e)[:50]}...")
        return False


def progress_monitor(progress_queue: queue.Queue, stats: DownloadStats, total_tasks: int):
    """Monitore et affiche le progrès en temps réel"""
    while True:
        try:
            message = progress_queue.get(timeout=1)
        except queue.Empty:
            current = stats.get_stats()
            if current['downloaded'] + current['failed'] + current['skipped'] >= total_tasks:
                break
            continue
        except KeyboardInterrupt:
            break

        current = stats.get_stats()
        completed = current['downloaded'] + current['failed'] + current['skipped']
        progress = (completed / total_tasks) * 100 if total_tasks > 0 else 0
        print(f"[{progress:5.1f}%] {message}")

        if completed >= total_tasks:
            break


def prepare_download_tasks(chapters: dict, main_folder: Path) -> List[DownloadTask]:
    """Prépare toutes les tâches de téléchargement"""
    tasks = []
    sorted_chapters = sorted(chapters.items(), key=lambda x: extract_chapter_number(x[0]))

    for chapter_name, chapter_data in sorted_chapters:
        if not isinstance(chapter_data, dict):
            continue
        chapter_folder = main_folder / sanitize_filename(chapter_name)

        for i, image_url in enumerate(chapter_data.get('images', []), 1):
            if not isinstance(image_url, str) or not image_url.strip():
                continue
            extension = guess_extension(image_url, i)
            tasks.append(DownloadTask(
                url=image_url,
                filepath=chapter_folder / f"page_{i:03d}.{extension}",
                page_number=i,
                chapter_name=chapter_name,
            ))

    return tasks


# --------------------------------------------------------------------------- #
# CBR
# --------------------------------------------------------------------------- #

def list_images(folder_path: Path) -> List[Path]:
    """Liste triée des images d'un dossier de chapitre"""
    return sorted(
        f for f in folder_path.glob('*')
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    )


def cbr_is_valid(cbr_path: Path, expected_count: Optional[int] = None) -> bool:
    """Vérifie qu'un CBR existant est une archive lisible et non vide"""
    try:
        with zipfile.ZipFile(cbr_path) as zipf:
            entries = zipf.namelist()
    except Exception:
        return False
    if not entries:
        return False
    if expected_count is not None and len(entries) < expected_count:
        return False
    return True


def create_cbr_from_folder(folder_path: Path, output_path: Path) -> bool:
    """Crée un fichier CBR (archive ZIP) à partir d'un dossier d'images"""
    try:
        image_files = list_images(folder_path)
        if not image_files:
            print(f"⚠️  Aucune image dans {folder_path.name}, CBR non créé")
            return False

        # Écriture sous nom temporaire: une interruption ne laisse jamais
        # une archive tronquée en place du CBR final.
        temp_path = output_path.with_suffix('.cbr.tmp')
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as zipf:
            for image_file in image_files:
                zipf.write(image_file, image_file.name)
        os.replace(temp_path, output_path)

        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"📦 CBR créé: {output_path.name} ({len(image_files)} pages, {size_mb:.1f} Mo)")
        return True

    except Exception as e:
        print(f"❌ Erreur lors de la création du CBR {output_path.name}: {e}")
        return False


def build_all_cbr(tasks: List[DownloadTask], cbr_folder: Path,
                  force_rebuild: bool = False) -> Tuple[int, int]:
    """Construit les CBR de tous les chapitres. Retourne (créés, ignorés)"""
    chapters_folders: Dict[Path, str] = {}
    for task in tasks:
        chapters_folders.setdefault(task.filepath.parent, task.chapter_name)

    created = skipped = 0
    for chapter_folder, chapter_name in sorted(chapters_folders.items()):
        images = list_images(chapter_folder)
        if not images:
            continue

        number = extract_chapter_number(chapter_name)
        label = sanitize_filename(chapter_name.split(' - ')[0])
        cbr_path = cbr_folder / f"Chapter_{format_chapter_number(number)} - {label}.cbr"

        if cbr_path.exists() and not force_rebuild:
            if cbr_is_valid(cbr_path, expected_count=len(images)):
                print(f"📦 CBR déjà complet: {cbr_path.name}")
                skipped += 1
                continue
            print(f"♻️  CBR vide/incomplet, régénération: {cbr_path.name}")

        if cbr_path.exists():
            cbr_path.unlink()
        if create_cbr_from_folder(chapter_folder, cbr_path):
            created += 1

    return created, skipped


# --------------------------------------------------------------------------- #
# Programme principal
# --------------------------------------------------------------------------- #

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Télécharge un manga depuis un JSON d'extraction et génère les CBR.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('json_file', nargs='?', default=None,
                        help="Fichier JSON à traiter (sélection interactive si omis)")
    parser.add_argument('-j', '--json', dest='json_flag', default=None,
                        help="Équivalent de l'argument positionnel")
    parser.add_argument('-w', '--workers', type=int, default=10,
                        help="Téléchargements simultanés (défaut: 10)")
    parser.add_argument('-o', '--output', default=None,
                        help=f"Dossier de sortie (défaut: {DEFAULT_OUTPUT_DIR}/<projectName>)")
    parser.add_argument('-d', '--directory', default=str(DEFAULT_DATA_DIR),
                        help=f"Répertoire où chercher les JSON (défaut: {DEFAULT_DATA_DIR})")
    parser.add_argument('--no-cbr', action='store_true',
                        help="Télécharge sans générer les CBR")
    parser.add_argument('--rebuild-cbr', action='store_true',
                        help="Régénère tous les CBR même s'ils semblent complets")
    parser.add_argument('--cbr-only', action='store_true',
                        help="Ne télécharge rien, reconstruit les CBR depuis les images locales")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    directory = Path(args.directory).resolve()

    # 1. Résolution du fichier JSON -----------------------------------------
    chosen = args.json_flag or args.json_file
    if chosen:
        json_path = Path(chosen)
        if not json_path.is_absolute():
            json_path = directory / json_path
        if not json_path.exists():
            print(f"❌ Fichier introuvable: {json_path}")
            return 1
        info = describe_json(json_path)
        if not info:
            print(f"❌ Fichier illisible ou sans objet 'chapters': {json_path}")
            return 1
    else:
        info = select_json_file(directory)
        if not info:
            return 1
        json_path = info['path']

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    chapters = data.get('chapters', {})
    project_name = data.get('projectName') or json_path.stem

    if args.output:
        main_folder = Path(args.output)
        if not main_folder.is_absolute():
            main_folder = Path.cwd() / main_folder
    else:
        main_folder = DEFAULT_OUTPUT_DIR / project_name
    main_folder.mkdir(parents=True, exist_ok=True)
    cbr_folder = main_folder / 'CBR'
    cbr_folder.mkdir(exist_ok=True)

    print(f"\n{'=' * 62}")
    print(f"📄 Source       : {json_path.name}")
    print(f"📁 Destination  : {main_folder}")
    print(f"📊 Chapitres    : {len(chapters)}")
    print(f"{'=' * 62}\n")

    tasks = prepare_download_tasks(chapters, main_folder)
    if not tasks:
        print("❌ Aucune image à traiter dans ce fichier!")
        return 1

    download_time = 0.0
    stats = DownloadStats()
    stats.total_images = len(tasks)

    # 2. Téléchargement -----------------------------------------------------
    if args.cbr_only:
        print("⏭️  Mode --cbr-only: téléchargement ignoré.\n")
    else:
        max_workers = max(1, args.workers)
        print(f"🚀 {len(tasks)} images à traiter — {max_workers} téléchargements simultanés\n")

        progress_queue: queue.Queue = queue.Queue()
        monitor_thread = threading.Thread(
            target=progress_monitor,
            args=(progress_queue, stats, len(tasks)),
            daemon=True,
        )
        monitor_thread.start()

        sessions = {i: create_session() for i in range(max_workers)}
        start_time = time.time()
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(download_image, task, sessions[i % max_workers],
                                    stats, progress_queue)
                    for i, task in enumerate(tasks)
                ]
                for _ in as_completed(futures):
                    pass
        except KeyboardInterrupt:
            print("\n⏹️  Interruption — les images déjà téléchargées sont conservées.")
        finally:
            download_time = time.time() - start_time
            for session in sessions.values():
                session.close()
            monitor_thread.join(timeout=3)

    # 3. Génération des CBR -------------------------------------------------
    cbr_created = cbr_skipped = 0
    if not args.no_cbr:
        print(f"\n📦 Génération des fichiers CBR...\n")
        cbr_created, cbr_skipped = build_all_cbr(tasks, cbr_folder, args.rebuild_cbr)

    # 4. Rapport final ------------------------------------------------------
    final = stats.get_stats()
    print(f"\n{'=' * 62}")
    print("📈 RÉSUMÉ FINAL")
    print(f"{'=' * 62}")
    if not args.cbr_only:
        print(f"📊 Total des images      : {final['total']}")
        print(f"✅ Téléchargées          : {final['downloaded']}")
        print(f"⏭️  Déjà présentes        : {final['skipped']}")
        print(f"❌ Échecs                : {final['failed']}")
        print(f"⏱️  Durée                 : {download_time:.1f} s")
        if download_time > 0 and final['downloaded'] > 0:
            print(f"🚀 Vitesse moyenne       : {final['downloaded'] / download_time:.1f} images/s")
    if not args.no_cbr:
        print(f"📦 CBR créés             : {cbr_created}")
        print(f"📦 CBR déjà complets     : {cbr_skipped}")
    print(f"📁 Destination           : {main_folder}")

    # Les échecs sont journalisés pour permettre un re-run ciblé.
    if stats.failures:
        log_path = main_folder / 'echecs_telechargement.json'
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(
                [{'chapitre': c, 'page': p, 'url': u, 'erreur': e}
                 for c, p, u, e in stats.failures],
                f, ensure_ascii=False, indent=2,
            )
        print(f"\n⚠️  {len(stats.failures)} échec(s) journalisé(s): {log_path.name}")
        print("   Relancez le script: seules les images manquantes seront retentées.")

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⏹️  Interrompu par l'utilisateur")
        sys.exit(130)
