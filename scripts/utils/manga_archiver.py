#!/usr/bin/env python3
"""
manga_archiver.py — Range tes mangas/manhwas sur ton disque dur via une interface web.

Fonctionnement :
  1. Lance un petit serveur local et ouvre une interface web dans le navigateur.
  2. Scanne le répertoire du projet (et d'autres dossiers au choix) ainsi que le
     disque externe choisi, à la recherche des fichiers .cbr / .cbz.
  3. Regroupe les fichiers par série, détecte le numéro de chapitre, élimine les
     doublons et propose un nom hyper lisible :
         <Disque>/Manga_Manhwa_Archives/Wistoria - Wand and Sword/
             Wistoria - Wand and Sword - Chapitre 021.5.cbr
     Les dossiers de chapitres contenant les images ne sont JAMAIS copiés.
  4. Tu valides dans l'interface ce qui sera copié (série par série, chapitre par
     chapitre, titre de série modifiable) puis la copie démarre.
  5. Chaque fichier copié est consigné dans un journal persistant. Si la copie
     s'arrête brutalement (disque débranché, PC éteint…), la reprise est proposée
     au prochain lancement / au prochain branchement du disque.

Lancement automatique au branchement du disque :
  Active « Lancement auto » dans l'interface (ou --install-autostart). Le script
  tourne alors discrètement au démarrage de Windows et ouvre l'interface dès que
  le disque d'une copie inachevée est rebranché.

Usage :
    python scripts/utils/manga_archiver.py                    # ouvre l'interface
    python scripts/utils/manga_archiver.py --background       # veille silencieuse
    python scripts/utils/manga_archiver.py --target "D:/Test"  # dossier utilisé comme disque
    python scripts/utils/manga_archiver.py --install-autostart
    python scripts/utils/manga_archiver.py --uninstall-autostart

Aucune dépendance externe (bibliothèque standard uniquement).
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import string
import sys
import threading
import time
import webbrowser
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

# --------------------------------------------------------------------------- #
# Constantes
# --------------------------------------------------------------------------- #

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_NAME = 'Manga_Manhwa_Archives'
TRASH_NAME = '.Corbeille_MangaArchiver'  # suppressions de l'onglet Archive (récupérables)
APP_ID = 'manga_archiver'
HOST = '127.0.0.1'
DEFAULT_PORT = 8765

STATE_DIR = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / '.local' / 'share')) / 'MangaArchiver'
JOBS_DIR = STATE_DIR / 'jobs'
SETTINGS_FILE = STATE_DIR / 'settings.json'
LOG_FILE = STATE_DIR / 'archiver.log'

COMIC_EXTS = {'.cbr', '.cbz'}
# Dossiers "conteneurs" : la série est le dossier parent (ex. <Série>/CBR/*.cbr)
CONTAINER_DIR_NAMES = {'cbr', 'cbz', 'cbrs', 'cbzs', 'archive', 'archives'}
SKIP_DIRS = {
    '$recycle.bin', 'system volume information', 'node_modules', '__pycache__',
    'windows', 'program files', 'program files (x86)', 'programdata', 'appdata',
    'recovery', 'msocache',
}
# Fichiers parasites du système : un dossier qui ne contient que ça est considéré comme vide
JUNK_FILES = {'.ds_store', 'thumbs.db', 'desktop.ini'}
CHUNK = 4 * 1024 * 1024
PARTIAL_SUFFIX = '.part'

# Statuts d'un fichier dans un journal de copie
ITEM_DONE = {'done', 'skipped', 'missing', 'exists'}

# Petits mots laissés en minuscules dans les titres
SMALL_WORDS = {
    'a', 'an', 'and', 'as', 'at', 'by', 'for', 'in', 'of', 'on', 'or', 'the', 'to',
    'with', 'from', 'into', 'vs', 'de', 'du', 'des', 'la', 'le', 'les', 'et', 'à',
    'au', 'aux', 'en', 'un', 'une',
}

KEYWORD_NUM = re.compile(
    r'(?<![a-z])(?:chap(?:ter|itre)?|ch|ep(?:isode)?)[\s._-]*0*(\d+(?:[.,]\d+)?)', re.I)


def log(msg: str) -> None:
    line = f'[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}'
    print(line)
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Persistance JSON (écriture atomique)
# --------------------------------------------------------------------------- #

def load_json(path: Path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_settings() -> dict:
    s = load_json(SETTINGS_FILE, {}) or {}
    s.setdefault('sources', [str(PROJECT_ROOT)])
    s.setdefault('scan_disk', True)
    s.setdefault('move_projects', True)
    s.setdefault('titles', {})
    s.setdefault('last_disk', None)
    return s


def job_path(disk_id: str) -> Path:
    return JOBS_DIR / f'job_{disk_id}.json'


# --------------------------------------------------------------------------- #
# Disques
# --------------------------------------------------------------------------- #

def _drive_info(root: str, drive_id: str, label: str, letter: str, kind: str) -> dict:
    usage = shutil.disk_usage(root)
    return {
        'id': drive_id, 'root': root, 'label': label or 'Disque sans nom',
        'letter': letter, 'kind': kind, 'total': usage.total, 'free': usage.free,
        'has_archive': os.path.isdir(os.path.join(root, ARCHIVE_NAME)),
    }


def list_drives(extra_targets=()) -> list:
    """Disques candidats (hors disque système), identifiés par numéro de série de volume."""
    drives = []
    if os.name == 'nt':
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.SetErrorMode(1)  # pas de popup "insérez un disque"
        mask = k32.GetLogicalDrives()
        system = (os.environ.get('SystemDrive') or 'C:').upper()
        for i, letter in enumerate(string.ascii_uppercase):
            if not mask & (1 << i) or f'{letter}:' == system:
                continue
            root = f'{letter}:\\'
            dtype = k32.GetDriveTypeW(root)
            if dtype not in (2, 3):  # amovible / fixe
                continue
            label = ctypes.create_unicode_buffer(261)
            fs = ctypes.create_unicode_buffer(261)
            serial = ctypes.c_uint32()
            if not k32.GetVolumeInformationW(root, label, 261, ctypes.byref(serial),
                                             None, None, fs, 261):
                continue  # lecteur sans média
            try:
                drives.append(_drive_info(root, f'{serial.value:08X}', label.value, letter,
                                          'amovible' if dtype == 2 else 'disque'))
            except OSError:
                pass
    else:
        bases = [Path('/Volumes'), Path('/media') / os.environ.get('USER', ''),
                 Path('/run/media') / os.environ.get('USER', '')]
        for base in bases:
            if not base.is_dir():
                continue
            for p in base.iterdir():
                if p.is_dir() and os.path.ismount(p) and str(p) != '/':
                    did = 'VOL-' + hashlib.md5(p.name.encode()).hexdigest()[:8].upper()
                    try:
                        drives.append(_drive_info(str(p), did, p.name, '', 'disque'))
                    except OSError:
                        pass
    for t in extra_targets:
        p = Path(t).resolve()
        if p.is_dir():
            did = 'DIR-' + hashlib.md5(str(p).lower().encode()).hexdigest()[:8].upper()
            drives.append(_drive_info(str(p), did, p.name, '', 'dossier'))
    return drives


# --------------------------------------------------------------------------- #
# Analyse des noms
# --------------------------------------------------------------------------- #

def is_junk_file(name: str) -> bool:
    return name.lower() in JUNK_FILES or name.startswith('._')


def series_key(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', name.lower())


def safe_name(s: str) -> str:
    s = s.replace(':', ' -')
    s = re.sub(r'[<>"/\\|?*\x00-\x1f]', '', s)
    s = re.sub(r'\s+', ' ', s).strip(' .')
    return s[:150] or 'Sans titre'


def prettify_title(raw: str) -> str:
    s = raw.replace('__', ' - ').replace('_', ' ')
    s = re.sub(r'\s+', ' ', s).strip(' -')
    words = s.split(' ')
    out = []
    for i, w in enumerate(words):
        after_dash = i > 0 and words[i - 1] == '-'
        if w.lower() in SMALL_WORDS and i > 0 and not after_dash:
            out.append(w.lower())
        elif w.islower():
            out.append(w[0].upper() + w[1:])
        else:
            out.append(w)
    return safe_name(' '.join(out))


def parse_chapter(stem: str):
    """Numéro de chapitre ('21.5', '5'…) ou None. Préfère un numéro décimal explicite
    (corrige les anciens noms du type 'Chapter_021 - Chapitre_21.5')."""
    nums = [m.group(1).replace(',', '.') for m in KEYWORD_NUM.finditer(stem)]
    if not nums:
        nums = re.findall(r'\d+(?:\.\d+)?', stem)[-1:]
    if not nums:
        return None
    for n in nums:
        if '.' in n:
            return n.lstrip('0') or '0' if not n.startswith('0.') else n
    return nums[0].lstrip('0') or '0'


def chapter_label(num: str, width: int) -> str:
    whole, _, frac = num.partition('.')
    frac = frac.rstrip('0')
    return f'Chapitre {whole.zfill(width)}' + (f'.{frac}' if frac else '')


def clean_stem(stem: str) -> str:
    return safe_name(stem.replace('_', ' '))


def series_dir_of(file: Path, root: Path) -> Path:
    d = file.parent
    if d.name.lower() in CONTAINER_DIR_NAMES and d != root:
        d = d.parent
    return d


def walk_comics(root: Path, exclude: set, on_dir=None):
    """Itère sur les .cbr/.cbz sous root, en ignorant dossiers cachés/système."""
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
        if on_dir:
            on_dir(dirpath)
        dirnames[:] = [d for d in dirnames
                       if not d.startswith('.') and d.lower() not in SKIP_DIRS
                       and os.path.normcase(os.path.join(dirpath, d)) not in exclude]
        for f in filenames:
            if os.path.splitext(f)[1].lower() in COMIC_EXTS and not f.startswith('.'):
                yield Path(dirpath) / f


# --------------------------------------------------------------------------- #
# Construction du plan de rangement
# --------------------------------------------------------------------------- #

def build_plan(sources: list, drive: dict, scan_disk: bool, title_overrides: dict, progress,
               move_projects: bool = True) -> dict:
    disk_root = Path(drive['root'])
    archive = disk_root / ARCHIVE_NAME
    entries = []

    def add(file: Path, origin: str, raw_series: str, project: bool = False):
        try:
            st = file.stat()
        except OSError:
            return
        if st.st_size == 0:
            return
        entries.append({
            'path': file, 'origin': origin, 'raw_series': raw_series,
            'key': series_key(raw_series), 'size': st.st_size, 'mtime': st.st_mtime,
            'chapter': parse_chapter(file.stem), 'ext': file.suffix.lower(), 'project': project,
        })
        progress['files'] += 1

    def on_dir(d):
        progress['dirs'] += 1
        progress['current'] = d

    # 1. Archive existante sur le disque
    archive_series = {}  # clé -> nom de dossier existant
    if archive.is_dir():
        progress['phase'] = 'Lecture de l\'archive existante'
        for f in walk_comics(archive, set(), on_dir):
            rel = f.relative_to(archive)
            if len(rel.parts) < 2:
                continue
            archive_series.setdefault(series_key(rel.parts[0]), rel.parts[0])
            add(f, 'archive', rel.parts[0])

    # 2. Sources sur le PC
    exclude = {os.path.normcase(str(archive))}
    for src in sources:
        root = Path(src)
        if not root.is_dir():
            continue
        progress['phase'] = f'Scan de {root}'
        for f in walk_comics(root, exclude, on_dir):
            d = series_dir_of(f, root)
            on_pc = not _is_under(f, disk_root)
            # Dossier de projet (<Série>/CBR/*.cbr) : le CBR est déplacé, pas seulement copié
            is_project = move_projects and on_pc and d != f.parent
            add(f, 'pc' if on_pc else 'disk', d.name or f.stem, is_project)

    # 3. Reste du disque (hors archive)
    if scan_disk:
        progress['phase'] = f'Scan du disque {drive["label"]}'
        for f in walk_comics(disk_root, exclude | {os.path.normcase(str(p)) for p in map(Path, sources)}, on_dir):
            d = series_dir_of(f, disk_root)
            add(f, 'disk', d.name or f.stem)

    progress['phase'] = 'Analyse'
    # Dédoublonnage des chemins (une source peut être incluse dans une autre)
    seen, uniq = set(), []
    for e in entries:
        k = os.path.normcase(str(e['path']))
        if k not in seen:
            seen.add(k)
            uniq.append(e)

    groups = {}
    for e in uniq:
        groups.setdefault(e['key'], []).append(e)

    series_out, items_out = [], []
    for key, ents in groups.items():
        if key in archive_series:
            title = archive_series[key]
        elif key in title_overrides:
            title = title_overrides[key]
        else:
            raw = next((e['raw_series'] for e in ents if e['origin'] != 'archive'), ents[0]['raw_series'])
            title = prettify_title(raw)
        nums = [int(float(e['chapter'])) for e in ents if e['chapter']]
        width = max(3, len(str(max(nums)))) if nums else 3

        by_chap = {}
        for e in ents:
            ck = f"n:{float(e['chapter'])}" if e['chapter'] else 'x:' + e['path'].stem.lower()
            by_chap.setdefault(ck, []).append(e)

        sitems = []
        for ck, ch_ents in by_chap.items():
            first = ch_ents[0]
            label = chapter_label(first['chapter'], width) if first['chapter'] else clean_stem(first['path'].stem)
            in_arch = [e for e in ch_ents if e['origin'] == 'archive']
            cands = [e for e in ch_ents if e['origin'] != 'archive']
            # Meilleure source : plus gros fichier, puis déjà sur le disque (déplacement), puis plus récent
            cands.sort(key=lambda e: (e['size'], e['origin'] == 'disk', e['mtime']), reverse=True)
            ext = (cands[0] if cands else in_arch[0])['ext']
            target_name = safe_name(f'{title} - {label}') + ext
            target_rel = f'{safe_name(title)}/{target_name}'

            def mk(e, status, op=None, checked=False, note='', move_src=False):
                it = {
                    'id': str(len(items_out)), 'series': key, 'label': label, 'ext': e['ext'],
                    'src': str(e['path']), 'origin': e['origin'], 'size': e['size'],
                    'status': status, 'op': op, 'checked': checked, 'note': note, 'move_src': move_src,
                    'chapter_sort': float(first['chapter']) if first['chapter'] else 1e9,
                }
                items_out.append(it)
                sitems.append(it['id'])
                return it

            arch_hit = None
            for a in in_arch:
                if a['path'].relative_to(archive).as_posix().lower() == target_rel.lower():
                    arch_hit = a
            arch_any = arch_hit or (in_arch[0] if in_arch else None)

            if cands:
                best = cands[0]
                op = 'move' if best['origin'] == 'disk' else 'copy'
                if arch_any and arch_any['size'] == best['size']:
                    mk(best, 'present', note='Déjà dans l\'archive')
                    if arch_hit is None:
                        mk(arch_any, 'rename', 'rename', True, 'Renommage dans l\'archive')
                elif arch_any:
                    mk(best, 'conflict', op, False,
                       f'Version différente déjà archivée ({fmt_size(arch_any["size"])})',
                       move_src=op == 'copy' and best['project'])
                else:
                    ms = op == 'copy' and best['project']
                    mk(best, 'new', op, True,
                       'Rangement par déplacement sur le disque' if op == 'move'
                       else 'Dossier projet : original supprimé après copie vérifiée' if ms else '',
                       move_src=ms)
                for d in cands[1:]:
                    mk(d, 'duplicate', note='Doublon ignoré')
            else:
                if arch_hit is None and in_arch:
                    mk(in_arch[0], 'rename', 'rename', True, 'Renommage dans l\'archive')
                elif arch_hit:
                    mk(arch_hit, 'present', note='Déjà dans l\'archive')

        sitems.sort(key=lambda i: (items_out[int(i)]['chapter_sort'], items_out[int(i)]['label']))
        origins = sorted({e['origin'] for e in ents})
        series_out.append({'key': key, 'title': title, 'locked': key in archive_series,
                           'items': sitems, 'origins': origins})

    series_out.sort(key=lambda s: s['title'].lower())
    return {
        'disk_id': drive['id'], 'disk_label': drive['label'], 'archive': str(archive),
        'created': datetime.now().isoformat(timespec='seconds'),
        'series': series_out, 'items': items_out,
    }


def _is_under(a: Path, root: Path) -> bool:
    a, root = os.path.normcase(str(a)), os.path.normcase(str(root)).rstrip('\\/')
    return a.startswith(root + os.sep)


def fmt_size(n: float) -> str:
    for unit in ('o', 'Ko', 'Mo', 'Go', 'To'):
        if n < 1024 or unit == 'To':
            return f'{n:.1f} {unit}' if unit != 'o' else f'{int(n)} o'
        n /= 1024


# --------------------------------------------------------------------------- #
# Gestion du disque : index, dossiers vides, archive
# --------------------------------------------------------------------------- #

def resolve_under(root: Path, rel: str) -> Path:
    """Chemin rel sous root, refusé s'il en sort (.., chemin absolu…)."""
    base = Path(root).resolve()
    p = (base / rel).resolve()
    if p != base and base not in p.parents:
        raise ValueError('Chemin refusé')
    return p


def index_disk(root: Path, progress: dict) -> dict:
    """Index de tous les dossiers du disque : taille, fichiers, CBR (cumulés sur les sous-dossiers)."""
    dirs = {}
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith('.') and d.lower() not in SKIP_DIRS)
        rel = Path(dirpath).relative_to(root).as_posix()
        rel = '' if rel == '.' else rel
        size = files = comics = 0
        for f in filenames:
            if is_junk_file(f):
                continue
            try:
                size += os.lstat(os.path.join(dirpath, f)).st_size
            except OSError:
                pass
            files += 1
            if os.path.splitext(f)[1].lower() in COMIC_EXTS:
                comics += 1
        dirs[rel] = {'size': size, 'files': files, 'comics': comics, 'own_files': files,
                     'children': list(dirnames)}
        progress['dirs'] += 1
    for rel in sorted(dirs, key=lambda r: r.count('/') if r else -1, reverse=True):
        if not rel:
            continue
        parent = dirs.get(rel.rpartition('/')[0])
        if parent:
            for k in ('size', 'files', 'comics'):
                parent[k] += dirs[rel][k]
    return {'dirs': dirs, 'created': datetime.now().isoformat(timespec='seconds')}


def dir_kind(rel: str, d: dict) -> str:
    if rel == ARCHIVE_NAME or rel.startswith(ARCHIVE_NAME + '/'):
        return 'archive'
    if not d['files']:
        return 'vide'
    if d['comics'] == d['files']:
        return 'manga'
    return 'mixte' if d['comics'] else 'autre'


def is_empty_tree(p: Path) -> bool:
    for _, _, filenames in os.walk(p):
        if any(not is_junk_file(f) for f in filenames):
            return False
    return True


def remove_empty_tree(p: Path) -> bool:
    """Supprime un dossier qui ne contient que des sous-dossiers vides / fichiers parasites."""
    if not p.is_dir() or not is_empty_tree(p):
        return False
    for dirpath, _, filenames in os.walk(p, topdown=False):
        for f in filenames:
            os.unlink(os.path.join(dirpath, f))
        os.rmdir(dirpath)
    return True


def rename_prefix(name: str, old: str, new: str) -> str:
    """'Old - Chapitre 001.cbr' -> 'New - Chapitre 001.cbr' (autres noms inchangés)."""
    if name.lower().startswith(old.lower() + ' - '):
        return new + name[len(old):]
    return name


def list_archive(archive: Path) -> list:
    out = []
    if not archive.is_dir():
        return out
    for sd in sorted(archive.iterdir(), key=lambda x: x.name.lower()):
        if not sd.is_dir() or sd.name.startswith('.'):
            continue
        chapters, others = [], 0
        for f in sd.iterdir():
            if not f.is_file() or is_junk_file(f.name):
                continue
            if f.suffix.lower() not in COMIC_EXTS:
                others += 1
                continue
            num = parse_chapter(f.stem)
            chapters.append({'name': f.name, 'size': f.stat().st_size,
                             'num': float(num) if num else None})
        seen = {}
        for c in chapters:
            if c['num'] is not None:
                seen[c['num']] = seen.get(c['num'], 0) + 1
        for c in chapters:
            c['dup'] = c['num'] is not None and seen[c['num']] > 1
        chapters.sort(key=lambda c: (c['num'] if c['num'] is not None else 1e9, c['name'].lower()))
        out.append({'name': sd.name, 'count': len(chapters), 'others': others,
                    'size': sum(c['size'] for c in chapters),
                    'dups': sum(1 for c in chapters if c['dup']), 'chapters': chapters})
    return out


# --------------------------------------------------------------------------- #
# Lancement automatique (Windows)
# --------------------------------------------------------------------------- #

def autostart_file() -> Path | None:
    if os.name != 'nt' or not os.environ.get('APPDATA'):
        return None
    return (Path(os.environ['APPDATA']) / 'Microsoft' / 'Windows' / 'Start Menu'
            / 'Programs' / 'Startup' / 'MangaArchiver.vbs')


def set_autostart(enabled: bool) -> bool:
    f = autostart_file()
    if f is None:
        return False
    if not enabled:
        f.unlink(missing_ok=True)
        return False
    pyw = Path(sys.executable).with_name('pythonw.exe')
    exe = pyw if pyw.exists() else Path(sys.executable)
    script = Path(__file__).resolve()
    f.write_text(
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'sh.Run """{exe}"" ""{script}"" --background", 0, False\r\n',
        encoding='utf-8')
    return True


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #

class Stop(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class App:
    def __init__(self, port: int, extra_targets: list, background: bool):
        self.lock = threading.RLock()
        self.settings = load_settings()
        self.extra_targets = extra_targets
        self.url = f'http://{HOST}:{port}/'
        self.scan = {'running': False, 'version': 0, 'phase': '', 'files': 0, 'dirs': 0,
                     'current': '', 'error': None}
        self.plan = None
        self.live = None
        self.worker = None
        self.pause_evt = threading.Event()
        self.cancel_evt = threading.Event()
        self.last_ui_ping = 0.0 if background else time.time()
        self.drives_cache = []
        self.disk_idx = {}
        self.disk_scan = {'running': False, 'disk_id': None, 'dirs': 0, 'version': 0, 'error': None}

    # ----- état ---------------------------------------------------------------

    def drives(self) -> list:
        self.drives_cache = list_drives(self.extra_targets)
        return self.drives_cache

    def find_drive(self, disk_id: str):
        return next((d for d in list_drives(self.extra_targets) if d['id'] == disk_id), None)

    def save_settings(self):
        save_json(SETTINGS_FILE, self.settings)

    def job_running(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def pending_jobs(self) -> list:
        out = []
        connected = {d['id']: d for d in self.drives_cache}
        if not JOBS_DIR.is_dir():
            return out
        for p in JOBS_DIR.glob('job_*.json'):
            job = load_json(p)
            if not job or job.get('status') in ('done', 'cancelled'):
                continue
            if self.job_running() and self.live and self.live['disk_id'] == job['disk_id']:
                continue
            left = [i for i in job['items'] if i['status'] not in ITEM_DONE]
            if not left:
                continue
            out.append({
                'disk_id': job['disk_id'], 'disk_label': job.get('disk_label', ''),
                'updated': job.get('updated'), 'status': job.get('status'),
                'total': len(job['items']), 'left': len(left),
                'left_bytes': sum(i['size'] for i in left if i['op'] != 'rename'),
                'errors': sum(1 for i in job['items'] if i['status'] == 'error'),
                'connected': job['disk_id'] in connected,
                'letter': connected.get(job['disk_id'], {}).get('letter', ''),
            })
        return out

    def state(self) -> dict:
        self.last_ui_ping = time.time()
        with self.lock:
            drives = self.drives()
            f = autostart_file()
            return {
                'project_root': str(PROJECT_ROOT), 'archive_name': ARCHIVE_NAME,
                'drives': drives, 'settings': self.settings, 'scan': dict(self.scan),
                'job': dict(self.live) if self.live else None,
                'job_running': self.job_running(),
                'pending_jobs': self.pending_jobs(),
                'disk_scan': dict(self.disk_scan),
                'autostart': {'supported': f is not None, 'enabled': bool(f and f.exists())},
            }

    # ----- scan ---------------------------------------------------------------

    def start_scan(self, disk_id: str):
        with self.lock:
            if self.scan['running']:
                raise ValueError('Analyse déjà en cours')
            drive = self.find_drive(disk_id)
            if not drive:
                raise ValueError('Disque introuvable — est-il branché ?')
            self.settings['last_disk'] = disk_id
            self.save_settings()
            self.scan.update(running=True, phase='Démarrage', files=0, dirs=0, current='', error=None)
        threading.Thread(target=self._scan, args=(drive,), daemon=True).start()

    def _scan(self, drive):
        try:
            plan = build_plan(self.settings['sources'], drive, self.settings['scan_disk'],
                              self.settings['titles'], self.scan,
                              self.settings.get('move_projects', True))
            with self.lock:
                self.plan = plan
        except Exception as e:  # noqa: BLE001 — remonté à l'interface
            log(f'Erreur de scan : {e!r}')
            self.scan['error'] = str(e)
        finally:
            with self.lock:
                self.scan['running'] = False
                self.scan['version'] += 1

    # ----- copie --------------------------------------------------------------

    def start_job(self, disk_id: str, titles: dict, selected: list):
        with self.lock:
            if self.job_running():
                raise ValueError('Une copie est déjà en cours')
            if not self.plan or self.plan['disk_id'] != disk_id:
                raise ValueError('Relance l\'analyse pour ce disque')
            drive = self.find_drive(disk_id)
            if not drive:
                raise ValueError('Disque introuvable')
            disk_root = Path(drive['root'])
            archive = disk_root / ARCHIVE_NAME
            titles = {k: safe_name(v) for k, v in titles.items() if v.strip()}
            self.settings['titles'].update(titles)
            self.save_settings()

            series_title = {s['key']: titles.get(s['key'], s['title']) for s in self.plan['series']}
            new_items = []
            for iid in selected:
                it = self.plan['items'][int(iid)]
                if not it['op']:
                    continue
                title = series_title[it['series']]
                dest_rel = f'{safe_name(title)}/{safe_name(title + " - " + it["label"])}{it["ext"]}'
                src = Path(it['src'])
                on_disk = it['op'] in ('move', 'rename')
                new_items.append({
                    'src': (src.relative_to(disk_root).as_posix() if on_disk else str(src)),
                    'src_on_disk': on_disk, 'dest_rel': dest_rel, 'size': it['size'],
                    'op': it['op'], 'overwrite': it['status'] == 'conflict', 'status': 'pending',
                    'delete_src': bool(it.get('move_src')),
                })
            if not new_items:
                raise ValueError('Rien à copier')

            need = sum(i['size'] for i in new_items if i['op'] == 'copy')
            if need > drive['free']:
                raise ValueError(f'Espace insuffisant : {fmt_size(need)} requis, '
                                 f'{fmt_size(drive["free"])} libres')

            # Fusion avec une copie inachevée sur le même disque
            path = job_path(disk_id)
            old = load_json(path)
            items = []
            if old and old.get('status') not in ('done', 'cancelled'):
                items = [i for i in old['items'] if i['status'] not in ITEM_DONE]
            known = {i['dest_rel'].lower() for i in items}
            items += [i for i in new_items if i['dest_rel'].lower() not in known]

            job = {'disk_id': disk_id, 'disk_label': drive['label'], 'archive': str(archive),
                   'created': datetime.now().isoformat(timespec='seconds'),
                   'updated': datetime.now().isoformat(timespec='seconds'),
                   'status': 'pending', 'items': items}
            save_json(path, job)
            self._launch(disk_id)

    def resume_job(self, disk_id: str):
        with self.lock:
            if self.job_running():
                raise ValueError('Une copie est déjà en cours')
            if not job_path(disk_id).exists():
                raise ValueError('Aucune copie à reprendre')
            if not self.find_drive(disk_id):
                raise ValueError('Branche le disque pour reprendre')
            self._launch(disk_id)

    def discard_job(self, disk_id: str):
        with self.lock:
            if self.job_running() and self.live and self.live['disk_id'] == disk_id:
                raise ValueError('Arrête d\'abord la copie en cours')
            p = job_path(disk_id)
            job = load_json(p)
            if job:
                job['status'] = 'cancelled'
                save_json(p, job)
            if self.live and self.live['disk_id'] == disk_id:
                self.live = None

    def _launch(self, disk_id):
        self.pause_evt.clear()
        self.cancel_evt.clear()
        self.live = {'disk_id': disk_id, 'status': 'running', 'done_files': 0, 'total_files': 0,
                     'done_bytes': 0, 'total_bytes': 0, 'current': '', 'speed': 0, 'eta': None,
                     'errors': [], 'message': '', 'archive': ''}
        self.worker = threading.Thread(target=self._run_job, args=(disk_id,), daemon=True)
        self.worker.start()

    def _run_job(self, disk_id):
        path = job_path(disk_id)
        job = load_json(path)
        live = self.live
        for it in job['items']:
            if it['status'] == 'error':
                it['status'] = 'pending'
                it.pop('error', None)
        items = job['items']
        live['total_files'] = len(items)
        live['total_bytes'] = sum(i['size'] for i in items if i['op'] == 'copy')
        live['done_files'] = sum(1 for i in items if i['status'] in ITEM_DONE)
        live['done_bytes'] = sum(i['size'] for i in items if i['op'] == 'copy' and i['status'] in ITEM_DONE)

        def finish(status, message=''):
            job['status'] = status
            job['updated'] = datetime.now().isoformat(timespec='seconds')
            try:
                save_json(path, job)
            except OSError as e:
                log(f'Journal non sauvegardé : {e!r}')
            live.update(status=status, message=message, current='', speed=0, eta=None)
            log(f'Copie {status} ({live["done_files"]}/{live["total_files"]}) {message}')

        drive = self.find_drive(disk_id)
        if not drive:
            return finish('interrupted', 'Disque introuvable')
        disk_root = self.disk_root = Path(drive['root'])
        archive = disk_root / ARCHIVE_NAME
        live['archive'] = str(archive)
        job['status'] = 'running'
        save_json(path, job)
        log(f'Copie démarrée vers {archive} ({len(items)} fichiers)')

        t0, b0 = time.time(), live['done_bytes']
        for it in items:
            if it['status'] in ITEM_DONE:
                continue
            if self.cancel_evt.is_set():
                return finish('cancelled', 'Copie annulée')
            if self.pause_evt.is_set():
                return finish('paused', 'Copie en pause')
            src = disk_root / it['src'] if it['src_on_disk'] else Path(it['src'])
            dest = archive / it['dest_rel']
            live['current'] = it['dest_rel']
            try:
                it['status'] = self._process(it, src, dest, live, t0, b0)
                it.pop('error', None)
            except Stop as s:
                return finish('paused' if s.reason == 'pause' else 'cancelled',
                              'Copie en pause' if s.reason == 'pause' else 'Copie annulée')
            except OSError as e:
                if not disk_root.exists() or self.find_drive(disk_id) is None:
                    return finish('interrupted', 'Disque débranché pendant la copie')
                it['status'] = 'error'
                it['error'] = str(e)
                live['errors'].append({'file': it['dest_rel'], 'error': str(e)})
                log(f'Erreur sur {it["dest_rel"]} : {e!r}')
            live['done_files'] += 1
            job['updated'] = datetime.now().isoformat(timespec='seconds')
            try:
                save_json(path, job)
            except OSError as e:
                log(f'Journal non sauvegardé : {e!r}')

        if any(i['op'] in ('move', 'rename') and i['status'] == 'done' for i in items):
            removed = self._sweep_empty(disk_root, archive)
            if removed:
                log(f'{removed} dossier(s) vide(s) supprimé(s) sur le disque')
        errors = sum(1 for i in items if i['status'] == 'error')
        finish('done_errors' if errors else 'done',
               f'{errors} erreur(s) — relance pour réessayer' if errors else 'Copie terminée')

    def _check_stop(self):
        if self.cancel_evt.is_set():
            raise Stop('cancel')
        if self.pause_evt.is_set():
            raise Stop('pause')

    def _process(self, it, src: Path, dest: Path, live, t0, b0) -> str:
        if not src.exists():
            return 'missing'
        size = src.stat().st_size
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists() and os.path.normcase(str(dest)) != os.path.normcase(str(src)):
            if dest.stat().st_size == size:
                live['done_bytes'] += size if it['op'] == 'copy' else 0
                if it.get('delete_src') and zipfile.is_zipfile(dest):
                    self._remove_source(src)
                return 'skipped'
            if not it.get('overwrite'):
                return 'exists'

        if it['op'] in ('move', 'rename'):
            if os.path.normcase(str(dest)) == os.path.normcase(str(src)):
                os.replace(src, dest)  # changement de casse uniquement
                return 'done'
            os.replace(src, dest)
            self._prune_empty(src.parent, self.disk_root if it['op'] == 'move' else dest.parent.parent)
            return 'done'

        # Copie par blocs vers un fichier .part, vérification, puis renommage atomique
        tmp = dest.with_name(dest.name + PARTIAL_SUFFIX)
        copied = 0
        try:
            with open(src, 'rb') as fi, open(tmp, 'wb') as fo:
                while True:
                    self._check_stop()
                    chunk = fi.read(CHUNK)
                    if not chunk:
                        break
                    fo.write(chunk)
                    copied += len(chunk)
                    live['done_bytes'] += len(chunk)
                    el = time.time() - t0
                    if el > 0.5:
                        live['speed'] = (live['done_bytes'] - b0) / el
                        rest = live['total_bytes'] - live['done_bytes']
                        live['eta'] = rest / live['speed'] if live['speed'] else None
                fo.flush()
                os.fsync(fo.fileno())
            if tmp.stat().st_size != size:
                raise OSError(f'Taille incohérente après copie ({tmp.stat().st_size} != {size})')
            if zipfile.is_zipfile(src) and not zipfile.is_zipfile(tmp):
                raise OSError('Archive corrompue après copie')
            os.replace(tmp, dest)
            st = src.stat()
            os.utime(dest, (st.st_atime, st.st_mtime))
            if it.get('delete_src'):
                self._remove_source(src)
            return 'done'
        except BaseException:
            live['done_bytes'] -= copied
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    @classmethod
    def _remove_source(cls, src: Path):
        """Supprime l'original après copie vérifiée, puis son dossier CBR s'il est vide."""
        try:
            src.unlink()
        except OSError as e:
            log(f'Original non supprimé {src} : {e!r}')
            return
        cls._rmdir_if_empty(src.parent)

    @staticmethod
    def _rmdir_if_empty(d: Path) -> bool:
        """Supprime d s'il ne contient plus rien, à part des fichiers parasites du système."""
        try:
            for e in os.scandir(d):
                if not (e.is_file(follow_symlinks=False) and is_junk_file(e.name)):
                    return False
            for e in os.scandir(d):
                os.unlink(e.path)
            d.rmdir()
            return True
        except OSError:
            return False

    @classmethod
    def _prune_empty(cls, d: Path, stop: Path):
        """Supprime les dossiers devenus vides après un déplacement (jamais de vrais fichiers)."""
        stop = os.path.normcase(str(stop))
        while os.path.normcase(str(d)) != stop and len(d.parts) > 1:
            if not cls._rmdir_if_empty(d):
                return
            d = d.parent

    @classmethod
    def _sweep_empty(cls, disk_root: Path, archive: Path) -> int:
        """Nettoie tout le disque (hors archive) : supprime les dossiers vides, de bas en haut."""
        skip = os.path.normcase(str(archive))
        removed = 0
        for dirpath, _, _ in os.walk(disk_root, topdown=False, onerror=lambda e: None):
            p = Path(dirpath)
            parts = [x.lower() for x in p.relative_to(disk_root).parts]
            if (not parts or os.path.normcase(str(p)).startswith(skip)
                    or any(x.startswith('.') or x in SKIP_DIRS for x in parts)):
                continue
            if cls._rmdir_if_empty(p):
                removed += 1
        return removed

    # ----- gestion du disque --------------------------------------------------

    def _disk(self, disk_id: str) -> dict:
        drive = self.find_drive(disk_id)
        if not drive:
            raise ValueError('Disque introuvable — est-il branché ?')
        return drive

    def _guard(self, disk_id: str):
        if self.job_running() and self.live and self.live['disk_id'] == disk_id:
            raise ValueError('Une copie est en cours sur ce disque — attends la fin')
        if self.scan['running']:
            raise ValueError('Analyse en cours — attends la fin')

    def _changed(self, disk_id: str):
        """Le contenu du disque a changé : index et plan de rangement deviennent obsolètes."""
        self.disk_idx.pop(disk_id, None)
        self.disk_scan['version'] += 1
        if self.plan and self.plan['disk_id'] == disk_id:
            self.plan = None
            self.scan['version'] += 1

    def start_disk_index(self, disk_id: str):
        with self.lock:
            if self.disk_scan['running']:
                raise ValueError('Exploration déjà en cours')
            drive = self._disk(disk_id)
            self.disk_scan.update(running=True, disk_id=disk_id, dirs=0, error=None)

        def run():
            try:
                idx = index_disk(Path(drive['root']), self.disk_scan)
                with self.lock:
                    self.disk_idx[disk_id] = idx
            except Exception as e:  # noqa: BLE001 — remonté à l'interface
                log(f'Erreur exploration : {e!r}')
                self.disk_scan['error'] = str(e)
            finally:
                with self.lock:
                    self.disk_scan['running'] = False
                    self.disk_scan['version'] += 1
        threading.Thread(target=run, daemon=True).start()

    def disk_ls(self, disk_id: str, rel: str) -> dict:
        idx = self.disk_idx.get(disk_id)
        if not idx:
            return {'indexed': False}
        rel = rel.strip('/')
        node = idx['dirs'].get(rel)
        if node is None:
            raise ValueError('Dossier introuvable — actualise l\'exploration')
        children = []
        for c in node['children']:
            k = f'{rel}/{c}' if rel else c
            d = idx['dirs'].get(k)
            if d:
                children.append({'name': c, 'path': k, 'size': d['size'], 'files': d['files'],
                                 'comics': d['comics'], 'subdirs': len(d['children']),
                                 'kind': dir_kind(k, d)})
        children.sort(key=lambda c: (-c['size'], c['name'].lower()))
        return {'indexed': True, 'created': idx['created'], 'path': rel,
                'size': node['size'], 'files': node['files'], 'comics': node['comics'],
                'own_files': node['own_files'], 'children': children}

    def disk_empty(self, disk_id: str) -> dict:
        idx = self.disk_idx.get(disk_id)
        if not idx:
            return {'indexed': False}
        dirs = idx['dirs']
        out = []
        for rel, d in dirs.items():
            if not rel or d['files']:
                continue
            parent = rel.rpartition('/')[0]
            if parent and not dirs[parent]['files']:
                continue  # le dossier parent, vide lui aussi, est déjà listé
            out.append({'path': rel, 'subdirs': len(d['children'])})
        out.sort(key=lambda e: e['path'].lower())
        return {'indexed': True, 'dirs': out}

    def delete_empty(self, disk_id: str, paths: list) -> dict:
        with self.lock:
            self._guard(disk_id)
            root = Path(self._disk(disk_id)['root'])
            removed, kept = 0, []
            for rel in paths:
                p = resolve_under(root, rel)
                if p == root.resolve():
                    continue
                try:
                    if remove_empty_tree(p):
                        removed += 1
                    else:
                        kept.append(rel)
                except OSError as e:
                    kept.append(f'{rel} ({e})')
            log(f'{removed} dossier(s) vide(s) supprimé(s) depuis l\'interface')
            self._changed(disk_id)
            msg = f'{removed} dossier(s) supprimé(s)'
            if kept:
                msg += f' — {len(kept)} ignoré(s) car plus vides : ' + ', '.join(kept[:5])
            return {'ok': True, 'message': msg}

    def archive_list(self, disk_id: str) -> dict:
        drive = self._disk(disk_id)
        return {'series': list_archive(Path(drive['root']) / ARCHIVE_NAME)}

    def archive_action(self, disk_id: str, body: dict) -> dict:
        with self.lock:
            self._guard(disk_id)
            root = Path(self._disk(disk_id)['root']).resolve()
            archive = root / ARCHIVE_NAME
            action = body.get('action')
            series = body.get('series') or ''
            src_dir = resolve_under(archive, series)
            if not series or src_dir.parent != archive or not src_dir.is_dir():
                raise ValueError('Série introuvable')
            file = body.get('file')
            src = None
            if file:
                src = resolve_under(src_dir, file)
                if src.parent != src_dir or not src.is_file():
                    raise ValueError('Chapitre introuvable')

            if action == 'delete':
                stamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
                target = src or src_dir
                dest = root / TRASH_NAME / stamp / target.relative_to(archive)
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, dest)
                if src:
                    self._rmdir_if_empty(src_dir)
                msg = f'« {target.name} » mis à la corbeille ({TRASH_NAME} à la racine du disque)'

            elif action in ('rename', 'move'):
                new = safe_name(body.get('to') or '')
                if not (body.get('to') or '').strip():
                    raise ValueError('Nom de série vide')
                dst_dir = archive / new
                if action == 'move':
                    if not src:
                        raise ValueError('Chapitre manquant')
                    dst_dir.mkdir(exist_ok=True)
                    dest = dst_dir / rename_prefix(src.name, series, new)
                    if dest.exists():
                        raise ValueError(f'« {dest.name} » existe déjà dans {new}')
                    os.replace(src, dest)
                    self._rmdir_if_empty(src_dir)
                    msg = f'Chapitre déplacé vers {new}'
                elif new == series:
                    raise ValueError('Même nom')
                else:
                    merge = dst_dir.exists() and not os.path.samefile(dst_dir, src_dir)
                    if not merge:
                        os.replace(src_dir, dst_dir)  # renommage simple (ou changement de casse)
                    conflicts = []
                    base = dst_dir if not merge else src_dir
                    for f in list(base.iterdir()):
                        if not f.is_file():
                            continue
                        target = dst_dir / rename_prefix(f.name, series, new)
                        if target == f:
                            continue
                        if target.exists() and not os.path.samefile(target, f):
                            conflicts.append(f.name)
                            continue
                        os.replace(f, target)
                    if merge:
                        self._rmdir_if_empty(src_dir)
                    msg = (f'Série fusionnée dans {new}' if merge else f'Série renommée en {new}')
                    if conflicts:
                        msg += f' — {len(conflicts)} fichier(s) laissé(s) dans {series} (nom déjà pris)'
            else:
                raise ValueError('Action inconnue')
            log(f'Archive : {msg}')
            self._changed(disk_id)
            return {'ok': True, 'message': msg}

    # ----- veille disque ------------------------------------------------------

    def watch_drives(self):
        """Détecte le (re)branchement d'un disque ayant une copie inachevée."""
        known = set()
        while True:
            try:
                with self.lock:
                    ids = {d['id'] for d in self.drives()}
                    new = ids - known
                    pending = {p['disk_id'] for p in self.pending_jobs()} if new else set()
                known = ids
                if new & pending and time.time() - self.last_ui_ping > 6:
                    log('Disque avec copie inachevée détecté → ouverture de l\'interface')
                    self.last_ui_ping = time.time()
                    webbrowser.open(self.url)
            except Exception as e:  # noqa: BLE001 — la veille ne doit jamais mourir
                log(f'Veille : {e!r}')
            time.sleep(3)


# --------------------------------------------------------------------------- #
# Serveur HTTP
# --------------------------------------------------------------------------- #

def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body, ctype='application/json; charset=utf-8'):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def _local_host(self):
            host = (self.headers.get('Host') or '').rsplit(':', 1)[0]
            return host in ('127.0.0.1', 'localhost')

        def do_GET(self):
            if not self._local_host():
                return self._send(403, {'error': 'hôte refusé'})
            p = urlparse(self.path).path
            if p == '/':
                return self._send(200, PAGE.encode('utf-8'), 'text/html; charset=utf-8')
            if p == '/api/ping':
                return self._send(200, {'app': APP_ID})
            if p == '/api/state':
                return self._send(200, app.state())
            if p == '/api/plan':
                return self._send(200, app.plan or {})
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            try:
                if p == '/api/disk/ls':
                    return self._send(200, app.disk_ls(q['disk_id'], q.get('path', '')))
                if p == '/api/disk/empty':
                    return self._send(200, app.disk_empty(q['disk_id']))
                if p == '/api/archive':
                    return self._send(200, app.archive_list(q['disk_id']))
            except (ValueError, KeyError) as e:
                return self._send(400, {'error': str(e)})
            except OSError as e:
                return self._send(500, {'error': str(e)})
            self._send(404, {'error': 'introuvable'})

        def do_POST(self):
            p = urlparse(self.path).path
            # Protection basique : seules les requêtes de la page locale sont acceptées
            origin = self.headers.get('Origin')
            if not self._local_host() or origin and urlparse(origin).hostname not in ('127.0.0.1', 'localhost'):
                return self._send(403, {'error': 'origine refusée'})
            try:
                n = int(self.headers.get('Content-Length') or 0)
                body = json.loads(self.rfile.read(n) or b'{}')
                if p == '/api/scan':
                    app.start_scan(body['disk_id'])
                elif p == '/api/settings':
                    with app.lock:
                        if 'sources' in body:
                            app.settings['sources'] = [s.strip().strip('"') for s in body['sources'] if s.strip()]
                        if 'move_projects' in body:
                            app.settings['move_projects'] = bool(body['move_projects'])
                        if 'scan_disk' in body:
                            app.settings['scan_disk'] = bool(body['scan_disk'])
                        app.save_settings()
                elif p == '/api/job/start':
                    app.start_job(body['disk_id'], body.get('titles', {}), body.get('selected', []))
                elif p == '/api/job/pause':
                    app.pause_evt.set()
                elif p == '/api/job/resume':
                    app.resume_job(body['disk_id'])
                elif p == '/api/job/cancel':
                    if app.job_running():
                        app.cancel_evt.set()
                        app.worker.join(10)
                    app.discard_job(body['disk_id'])
                elif p == '/api/disk/index':
                    app.start_disk_index(body['disk_id'])
                elif p == '/api/disk/delete_empty':
                    return self._send(200, app.delete_empty(body['disk_id'], body.get('paths', [])))
                elif p == '/api/archive/action':
                    return self._send(200, app.archive_action(body['disk_id'], body))
                elif p == '/api/autostart':
                    set_autostart(bool(body.get('enabled')))
                elif p == '/api/quit':
                    if app.job_running():
                        app.pause_evt.set()
                        app.worker.join(10)
                    self._send(200, {'ok': True})
                    threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start()
                    return
                else:
                    return self._send(404, {'error': 'introuvable'})
                self._send(200, {'ok': True})
            except (ValueError, KeyError) as e:
                self._send(400, {'error': str(e)})
            except OSError as e:
                self._send(500, {'error': str(e)})

    return Handler


def instance_running(port: int) -> bool:
    try:
        with urlopen(f'http://{HOST}:{port}/api/ping', timeout=1) as r:
            return json.load(r).get('app') == APP_ID
    except (OSError, ValueError):
        return False


def main():
    ap = argparse.ArgumentParser(description='Range tes CBR sur ton disque via une interface web.')
    ap.add_argument('--port', type=int, default=DEFAULT_PORT)
    ap.add_argument('--background', action='store_true',
                    help='veille silencieuse : ouvre l\'interface au rebranchement du disque')
    ap.add_argument('--no-browser', action='store_true')
    ap.add_argument('--target', action='append', default=[],
                    help='dossier à proposer comme destination (comme un disque)')
    ap.add_argument('--install-autostart', action='store_true')
    ap.add_argument('--uninstall-autostart', action='store_true')
    args = ap.parse_args()

    if args.install_autostart or args.uninstall_autostart:
        ok = set_autostart(args.install_autostart)
        print('Lancement auto activé.' if ok else 'Lancement auto désactivé.')
        return

    url = f'http://{HOST}:{args.port}/'
    if instance_running(args.port):
        if not args.background and not args.no_browser:
            webbrowser.open(url)
        print(f'Déjà lancé : {url}')
        return

    app = App(args.port, args.target, args.background)
    server = ThreadingHTTPServer((HOST, args.port), make_handler(app))
    threading.Thread(target=app.watch_drives, daemon=True).start()
    log(f'Manga Archiver prêt sur {url}')
    if not args.background and not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if app.job_running():
            app.pause_evt.set()
            app.worker.join(10)
        print('\nArrêt.')


# --------------------------------------------------------------------------- #
# Interface web
# --------------------------------------------------------------------------- #

PAGE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Manga Archiver</title>
<style>
:root{
  --bg:#0d0f14;--bg2:#141821;--card:#181d28;--card2:#1f2533;--line:#2a3142;
  --txt:#e8ebf2;--mut:#8b93a7;--acc:#ff5d8f;--acc2:#7c6cff;--ok:#3ddc97;--warn:#ffb547;--err:#ff6161;
  --r:14px;
}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 600px at 10% -10%,#2a1530 0,transparent 60%),
  radial-gradient(900px 500px at 110% 0,#16204a 0,transparent 55%),var(--bg);
  color:var(--txt);font:14px/1.45 "Segoe UI",system-ui,-apple-system,sans-serif;min-height:100vh}
header{display:flex;align-items:center;gap:16px;padding:18px 28px;border-bottom:1px solid var(--line);
  backdrop-filter:blur(8px);position:sticky;top:0;z-index:20;background:#0d0f14cc}
.logo{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;font-size:22px;font-weight:700;
  background:linear-gradient(135deg,var(--acc),var(--acc2));box-shadow:0 6px 24px #ff5d8f44}
h1{font-size:19px;margin:0}
.sub{color:var(--mut);font-size:12.5px}
.spacer{flex:1}
main{max-width:1180px;margin:0 auto;padding:24px 28px 140px}
.card{background:linear-gradient(180deg,var(--card),var(--bg2));border:1px solid var(--line);
  border-radius:var(--r);padding:20px 22px;margin-bottom:18px}
h2{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);margin:0 0 12px;font-weight:600}
h2 b{color:var(--acc);margin-right:6px}
.drives{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}
.drive{border:1.5px solid var(--line);border-radius:12px;padding:14px;cursor:pointer;background:var(--card2);
  transition:.15s;position:relative}
.drive:hover{border-color:#47506a}
.drive.sel{border-color:var(--acc);box-shadow:0 0 0 3px #ff5d8f22}
.drive .nm{font-weight:600;font-size:15px}
.drive .lt{color:var(--mut);font-size:12px}
.bar{height:6px;border-radius:9px;background:#0003;overflow:hidden;margin:10px 0 6px;border:1px solid var(--line)}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,var(--acc2),var(--acc));border-radius:9px;transition:width .4s}
.badge{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:600;
  background:#ffffff10;color:var(--mut);margin:2px 4px 0 0;white-space:nowrap}
.b-ok{background:#3ddc9722;color:var(--ok)}.b-warn{background:#ffb54722;color:var(--warn)}
.b-err{background:#ff616122;color:var(--err)}.b-acc{background:#ff5d8f22;color:var(--acc)}
.b-vio{background:#7c6cff26;color:#a79dff}
.empty{color:var(--mut);padding:14px;border:1px dashed var(--line);border-radius:12px;text-align:center}
.srcs{display:flex;flex-direction:column;gap:6px;margin-bottom:10px}
.src{display:flex;align-items:center;gap:10px;background:var(--card2);border:1px solid var(--line);
  border-radius:10px;padding:8px 12px;font-family:Consolas,monospace;font-size:12.5px}
.src span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
input[type=text]{background:var(--bg);border:1px solid var(--line);color:var(--txt);border-radius:10px;
  padding:9px 12px;font:inherit;outline:none;min-width:0}
input[type=text]:focus{border-color:var(--acc2)}
button{font:inherit;border:1px solid var(--line);background:var(--card2);color:var(--txt);border-radius:10px;
  padding:9px 16px;cursor:pointer;font-weight:600;transition:.15s}
button:hover:not(:disabled){border-color:#56607a;background:#262d3e}
button:disabled{opacity:.45;cursor:not-allowed}
.primary{background:linear-gradient(135deg,var(--acc),#e04bb0);border:0;box-shadow:0 6px 22px #ff5d8f33}
.primary:hover:not(:disabled){filter:brightness(1.08);background:linear-gradient(135deg,var(--acc),#e04bb0)}
.ghost{background:transparent}
.x{background:none;border:0;color:var(--mut);padding:2px 6px}
.x:hover{color:var(--err)!important;background:none!important}
label.chk{display:flex;gap:8px;align-items:center;cursor:pointer;color:var(--mut);user-select:none}
input[type=checkbox]{accent-color:var(--acc);width:16px;height:16px;cursor:pointer}
.scanst{color:var(--mut);font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0}
.spin{display:inline-block;width:12px;height:12px;border:2px solid var(--acc);border-right-color:transparent;
  border-radius:50%;animation:sp .8s linear infinite;vertical-align:-2px;margin-right:6px}
@keyframes sp{to{transform:rotate(360deg)}}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:16px}
.stat{background:var(--card2);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.stat .v{font-size:22px;font-weight:700}.stat .k{color:var(--mut);font-size:12px}
.tools{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
.chip{padding:6px 12px;border-radius:99px;font-size:12.5px}
.chip.on{border-color:var(--acc);color:var(--acc);background:#ff5d8f14}
.series{border:1px solid var(--line);border-radius:12px;margin-bottom:10px;background:var(--card2);overflow:hidden}
.shead{display:flex;align-items:center;gap:12px;padding:12px 14px}
.shead .ttl{flex:1;min-width:0;display:flex;flex-direction:column;gap:3px}
.shead input[type=text]{font-weight:600;font-size:15px;background:transparent;border-color:transparent;padding:4px 8px;margin-left:-8px}
.shead input[type=text]:hover{border-color:var(--line)}
.meta{color:var(--mut);font-size:12px}
.chev{background:none;border:0;color:var(--mut);font-size:18px;padding:4px 10px;transition:transform .2s}
.chev.open{transform:rotate(90deg)}
.sbody{border-top:1px solid var(--line);max-height:460px;overflow:auto}
table{width:100%;border-collapse:collapse;font-size:12.5px}
td,th{padding:7px 10px;border-bottom:1px solid #ffffff08;text-align:left;vertical-align:middle}
th{color:var(--mut);font-weight:600;position:sticky;top:0;background:var(--card2);z-index:1}
td.mono{font-family:Consolas,monospace;font-size:12px}
td.old{color:var(--mut);max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
td.new{color:#cfe3ff}
tr.dim td{opacity:.5}
.foot{position:fixed;left:0;right:0;bottom:0;background:#11141bf2;border-top:1px solid var(--line);
  backdrop-filter:blur(10px);padding:14px 28px;z-index:15}
.foot .in{max-width:1180px;margin:0 auto;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.foot .sum{flex:1;min-width:200px}
.foot .sum b{font-size:16px}
.job{border-color:#7c6cff66;background:linear-gradient(180deg,#1d1b33,var(--bg2))}
.job .big{height:12px}
.jobgrid{display:flex;gap:22px;flex-wrap:wrap;color:var(--mut);font-size:12.5px;margin:6px 0 10px}
.jobgrid b{color:var(--txt);font-size:14px;display:block}
.cur{font-family:Consolas,monospace;font-size:12px;color:#cfe3ff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.errs{margin-top:10px;max-height:150px;overflow:auto;font-size:12px;color:var(--err)}
.modal{position:fixed;inset:0;background:#000a;display:none;place-items:center;z-index:50;padding:16px}
.modal.on{display:grid}
.mbox{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:26px;max-width:480px;width:100%;
  box-shadow:0 30px 80px #000a}
.mbox h3{margin:0 0 8px;font-size:19px}
.mbox p{color:var(--mut);margin:0 0 18px}
.toast{position:fixed;top:84px;right:24px;background:var(--card2);border:1px solid var(--line);border-left:4px solid var(--err);
  padding:12px 16px;border-radius:10px;z-index:60;max-width:380px;display:none}
.toast.on{display:block}
.toast.ok{border-left-color:var(--ok)}
.switch{display:flex;align-items:center;gap:8px;color:var(--mut);font-size:12.5px;cursor:pointer}
.tabs{display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap}
.tabs button.on{border-color:var(--acc);color:var(--acc);background:#ff5d8f14}
.crumb{display:flex;flex-wrap:wrap;gap:4px;align-items:center;font-family:Consolas,monospace;font-size:12.5px;margin-bottom:10px}
.crumb a{color:#a79dff;cursor:pointer;text-decoration:none}.crumb a:hover{text-decoration:underline}
tr.nav{cursor:pointer}tr.nav:hover td{background:#ffffff06}
td.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.sz{display:flex;align-items:center;gap:8px;min-width:150px}
.sz .bar{flex:1;margin:0;height:5px}
.acts{display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap}
.acts button,.sm{padding:4px 10px;font-size:12px;font-weight:600}
.danger{color:var(--err)}.danger:hover:not(:disabled){border-color:var(--err)!important}
@media (max-width:700px){header,main{padding-left:16px;padding-right:16px}.foot{padding:12px 16px}
  td.old{display:none}.hide-sm{display:none}}
</style>
</head>
<body>
<header>
  <div class="logo">漫</div>
  <div><h1>Manga Archiver</h1><div class="sub">Rangement des CBR vers <span id="archName">Manga_Manhwa_Archives</span></div></div>
  <div class="spacer"></div>
  <label class="switch hide-sm" id="autoWrap" title="Lance le script au démarrage de Windows et ouvre cette page quand le disque d'une copie inachevée est rebranché">
    <input type="checkbox" id="auto"> Lancement auto
  </label>
  <button class="ghost" id="quit" title="Arrêter le serveur">Quitter</button>
</header>

<main>
  <section class="card job" id="jobSec" hidden>
    <div class="row"><h2 style="margin:0;flex:1"><b>●</b><span id="jobTitle">Copie en cours</span></h2>
      <button id="jPause">Pause</button><button id="jResume" class="primary">Reprendre</button>
      <button id="jCancel" class="ghost">Annuler</button><button id="jClose" class="ghost">Fermer</button></div>
    <div class="bar big"><i id="jBar" style="width:0"></i></div>
    <div class="jobgrid">
      <div><b id="jPct">0 %</b>progression</div>
      <div><b id="jFiles">0 / 0</b>fichiers</div>
      <div><b id="jBytes">—</b>copié</div>
      <div><b id="jSpeed">—</b>vitesse</div>
      <div><b id="jEta">—</b>restant</div>
    </div>
    <div class="cur" id="jCur"></div>
    <div class="meta" id="jMsg"></div>
    <div class="errs" id="jErrs"></div>
  </section>

  <section class="card">
    <h2><b>1</b>Disque de destination</h2>
    <div class="drives" id="drives"></div>
  </section>

  <section class="card">
    <h2><b>2</b>Sources sur ce PC</h2>
    <div class="srcs" id="srcs"></div>
    <div class="row">
      <input type="text" id="srcIn" placeholder="Ajouter un dossier, ex. D:\Mangas" style="flex:1">
      <button id="srcAdd">Ajouter</button>
    </div>
    <div class="row" style="margin-top:14px">
      <label class="chk"><input type="checkbox" id="scanDisk"> Analyser aussi le reste du disque (fichiers à ranger)</label>
      <label class="chk"><input type="checkbox" id="moveProjects"> Dossiers projet (<i>Série/CBR</i>) : déplacer les CBR vers l'archive (original supprimé après copie vérifiée)</label>
    </div>
    <div class="row" style="margin-top:16px">
      <button class="primary" id="scanBtn">Analyser</button>
      <div class="scanst" id="scanSt"></div>
    </div>
  </section>

  <section class="card" id="diskSec" hidden>
    <h2><b>4</b>Gestion du disque <span id="dkName" style="text-transform:none;letter-spacing:0;color:var(--txt)"></span></h2>
    <div class="tabs">
      <button data-tab="explore">Explorateur</button>
      <button data-tab="empty">Dossiers vides</button>
      <button data-tab="archive">Archive</button>
      <div class="spacer"></div>
      <button id="dkIndex" class="ghost">Actualiser l'exploration</button>
    </div>
    <div class="scanst" id="dkSt" style="margin-bottom:10px"></div>
    <div id="dkBody"></div>
  </section>

  <section class="card" id="planSec" hidden>
    <h2><b>3</b>Validation</h2>
    <div class="stats" id="stats"></div>
    <div class="tools">
      <button class="chip" data-f="todo">À traiter</button>
      <button class="chip" data-f="all">Tout</button>
      <button class="chip" data-f="present">Déjà archivé</button>
      <button class="chip" data-f="issues">Doublons / conflits</button>
      <button class="chip on" id="pfChip" hidden title="Seul ce dossier est affiché et coché — clique pour tout afficher"></button>
      <div class="spacer"></div>
      <input type="text" id="q" placeholder="Rechercher une série…" style="width:220px">
      <button id="selAll" class="ghost">Tout cocher</button>
      <button id="selNone" class="ghost">Tout décocher</button>
    </div>
    <div id="series"></div>
  </section>
</main>

<div class="foot" id="foot" hidden>
  <div class="in">
    <div class="sum"><b id="fSum">0 fichier</b><div class="meta" id="fDest"></div></div>
    <button class="primary" id="go">Lancer la copie</button>
  </div>
</div>

<div class="modal" id="modal"><div class="mbox">
  <h3>Reprendre la copie ?</h3>
  <p id="mTxt"></p>
  <div class="row" style="justify-content:flex-end">
    <button class="ghost" id="mDrop">Abandonner</button>
    <button class="ghost" id="mLater">Plus tard</button>
    <button class="primary" id="mGo">Reprendre</button>
  </div>
</div></div>
<div class="toast" id="toast"></div>

<script>
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtB = n => { if(n==null) return '—'; const u=['o','Ko','Mo','Go','To']; let i=0; while(n>=1024&&i<4){n/=1024;i++} return (i?n.toFixed(1):n)+' '+u[i]; };
const fmtT = s => { if(s==null||!isFinite(s)) return '—'; s=Math.round(s); const h=Math.floor(s/3600), m=Math.floor(s%3600/60); return h?`${h} h ${m} min`:m?`${m} min ${s%60} s`:`${s} s`; };
const STATUS = {new:['À copier','b-acc'],present:['Déjà archivé','b-ok'],conflict:['Conflit','b-warn'],
  duplicate:['Doublon','b-err'],rename:['À renommer','b-vio']};
const OP = {copy:'Copie', move:'Déplacement', rename:'Renommage'};
const ORIG = {pc:'PC', disk:'Disque', archive:'Archive'};

let S=null, plan=null, planVer=0, selDisk=null, sel=new Set(), titles={}, opened=new Set(),
    filter='todo', q='', dismissed=new Set(), hideJob=false, planFolder=null;
const normP = p => p.replace(/\\/g,'/').replace(/\/+$/,'').toLowerCase();
const inFolder = src => !planFolder || normP(src).startsWith(normP(planFolder)+'/');

async function api(path, body){
  const r = await fetch(path, body===undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const j = await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(j.error || ('HTTP '+r.status));
  return j;
}
function toast(msg, ok){ const t=$('#toast'); t.textContent=msg; t.className='toast on'+(ok?' ok':''); clearTimeout(t._h); t._h=setTimeout(()=>t.className='toast',4500); }
async function act(path, body, okMsg){ try{ await api(path, body); if(okMsg) toast(okMsg, true); await poll(true); }catch(e){ toast(e.message); } }

async function poll(once){
  try{
    S = await api('/api/state');
    if(!selDisk || !S.drives.some(d=>d.id===selDisk)){
      const last = S.settings.last_disk;
      selDisk = S.drives.some(d=>d.id===last) ? last : (S.drives[0]||{}).id || null;
    }
    render();
    if(!S.scan.running && S.scan.version !== planVer){
      planVer = S.scan.version;
      if(S.scan.error) toast('Analyse : '+S.scan.error);
      plan = await api('/api/plan');
      if(plan && plan.items){ sel = new Set(plan.items.filter(i=>i.checked && inFolder(i.src)).map(i=>i.id)); titles={}; renderPlan(); }
    }
  }catch(e){ $('#scanSt').textContent = 'Serveur injoignable — relance le script.'; }
  if(!once) setTimeout(poll, S && S.job_running ? 700 : 1500);
}

function render(){
  $('#archName').textContent = S.archive_name;
  // disques
  const pend = Object.fromEntries(S.pending_jobs.map(p=>[p.disk_id,p]));
  $('#drives').innerHTML = S.drives.length ? S.drives.map(d=>{
    const used = d.total ? (1 - d.free/d.total)*100 : 0, p = pend[d.id];
    return `<div class="drive ${d.id===selDisk?'sel':''}" data-id="${d.id}">
      <div class="nm">${esc(d.label)}</div>
      <div class="lt">${d.letter ? d.letter+':' : esc(d.root)} · ${esc(d.kind)} · ${d.id}</div>
      <div class="bar"><i style="width:${used.toFixed(1)}%"></i></div>
      <div class="lt">${fmtB(d.free)} libres sur ${fmtB(d.total)}</div>
      ${d.has_archive?'<span class="badge b-ok">Archive existante</span>':''}
      ${p?`<span class="badge b-warn">Copie inachevée · ${p.left} restants</span>`:''}
    </div>`}).join('') : '<div class="empty">Aucun disque externe détecté. Branche ton disque dur, il apparaîtra ici automatiquement.</div>';
  // sources
  const srcs = S.settings.sources;
  $('#srcs').innerHTML = srcs.length ? srcs.map((s,i)=>`<div class="src"><span title="${esc(s)}">${esc(s)}</span>
     ${s===S.project_root?'<span class="badge b-vio" style="flex:none">projet</span>':''}<button class="x" data-rm="${i}">✕</button></div>`).join('')
     : '<div class="empty">Aucune source.</div>';
  $('#scanDisk').checked = S.settings.scan_disk;
  $('#moveProjects').checked = S.settings.move_projects !== false;
  // scan
  const sc = S.scan;
  $('#scanBtn').disabled = sc.running || !selDisk || S.job_running;
  $('#scanSt').innerHTML = sc.running ? `<span class="spin"></span>${esc(sc.phase)} — ${sc.files} CBR · ${sc.dirs} dossiers · <span title="${esc(sc.current)}">${esc(sc.current)}</span>`
    : (plan && plan.items ? `Dernière analyse : ${esc(plan.created.replace('T',' '))} (${esc(plan.disk_label)})` : '');
  // autostart
  $('#autoWrap').style.display = S.autostart.supported ? '' : 'none';
  $('#auto').checked = S.autostart.enabled;
  renderJob(); renderModal(); renderFoot(); renderDisk();
}

function renderJob(){
  const j = S.job, sec = $('#jobSec');
  if(!j || (hideJob && !S.job_running)){ sec.hidden = true; return; }
  sec.hidden = false;
  const titles = {running:'Copie en cours', paused:'Copie en pause', interrupted:'Copie interrompue',
    cancelled:'Copie annulée', done:'Copie terminée ✓', done_errors:'Copie terminée avec erreurs'};
  $('#jobTitle').textContent = titles[j.status] || j.status;
  const pct = j.total_bytes ? j.done_bytes/j.total_bytes*100 : (j.total_files ? j.done_files/j.total_files*100 : 0);
  $('#jBar').style.width = Math.min(100,pct).toFixed(1)+'%';
  $('#jPct').textContent = pct.toFixed(1)+' %';
  $('#jFiles').textContent = `${j.done_files} / ${j.total_files}`;
  $('#jBytes').textContent = `${fmtB(j.done_bytes)} / ${fmtB(j.total_bytes)}`;
  $('#jSpeed').textContent = j.speed ? fmtB(j.speed)+'/s' : '—';
  $('#jEta').textContent = fmtT(j.eta);
  $('#jCur').textContent = j.current ? '→ '+j.current : (j.archive||'');
  $('#jMsg').textContent = j.message || '';
  $('#jErrs').innerHTML = j.errors.slice(-30).map(e=>`<div>✕ ${esc(e.file)} — ${esc(e.error)}</div>`).join('');
  const run = S.job_running;
  $('#jPause').hidden = !run; $('#jCancel').hidden = !run && !['paused','interrupted','done_errors'].includes(j.status);
  $('#jResume').hidden = run || !['paused','interrupted','done_errors'].includes(j.status);
  $('#jResume').textContent = j.status==='done_errors' ? 'Réessayer les erreurs' : 'Reprendre';
  $('#jClose').hidden = run;
}

function renderModal(){
  const p = S.pending_jobs.find(p=>p.connected && !dismissed.has(p.disk_id+p.updated));
  const m = $('#modal');
  if(!p || S.job_running || (S.job && S.job.disk_id===p.disk_id && !hideJob)){ m.classList.remove('on'); return; }
  m.dataset.id = p.disk_id; m.dataset.k = p.disk_id+p.updated;
  const when = p.updated ? new Date(p.updated).toLocaleString('fr-FR',{dateStyle:'full',timeStyle:'short'}) : '';
  const why = {interrupted:'s\'est arrêtée brutalement', running:'s\'est arrêtée brutalement', paused:'a été mise en pause', done_errors:'s\'est terminée avec des erreurs', pending:'n\'a pas démarré'}[p.status] || 'est inachevée';
  $('#mTxt').innerHTML = `La copie vers <b>${esc(p.disk_label)}</b>${p.letter?' ('+p.letter+':)':''} ${why}${when?' le '+esc(when):''}.<br><br>
    Il reste <b>${p.left}</b> fichier(s) sur ${p.total} (${fmtB(p.left_bytes)})${p.errors?`, dont ${p.errors} en erreur`:''}.`;
  m.classList.add('on');
}

function itemsOf(s){ return s.items.map(id=>plan.items[+id]); }
function titleOf(s){ return (titles[s.key] ?? s.title).trim() || s.title; }
function safe(t){ return t.replace(/:/g,' -').replace(/[<>"\/\\|?*\x00-\x1f]/g,'').replace(/\s+/g,' ').replace(/^[ .]+|[ .]+$/g,''); }
function newName(s,it){ return safe(titleOf(s)+' - '+it.label)+it.ext; }

function renderPlan(){
  if(!plan || !plan.items){ $('#planSec').hidden = true; return; }
  $('#planSec').hidden = false;
  const all = plan.items;
  const cnt = st => all.filter(i=>i.status===st).length;
  $('#stats').innerHTML = [
    [plan.series.length,'séries'], [cnt('new'),'nouveaux chapitres'], [cnt('present'),'déjà archivés'],
    [cnt('rename'),'à renommer'], [cnt('duplicate'),'doublons ignorés'], [cnt('conflict'),'conflits'],
  ].map(([v,k])=>`<div class="stat"><div class="v">${v}</div><div class="k">${k}</div></div>`).join('');
  document.querySelectorAll('.chip[data-f]').forEach(c=>c.classList.toggle('on', c.dataset.f===filter));
  const ql = q.toLowerCase();
  const list = plan.series.filter(s=>{
    const its = itemsOf(s);
    if(ql && !titleOf(s).toLowerCase().includes(ql)) return false;
    if(planFolder && !its.some(i=>inFolder(i.src))) return false;
    if(filter==='todo') return its.some(i=>i.op);
    if(filter==='present') return its.some(i=>i.status==='present');
    if(filter==='issues') return its.some(i=>i.status==='duplicate'||i.status==='conflict');
    return true;
  });
  $('#pfChip').hidden = !planFolder;
  $('#pfChip').textContent = planFolder ? '📁 '+planFolder.split(/[\\/]/).pop()+'  ✕' : '';
  $('#series').innerHTML = list.length ? list.map(seriesHtml).join('') : '<div class="empty">Rien à afficher pour ce filtre.</div>';
  list.forEach(s=>{ const cb=document.querySelector(`[data-sall="${s.key}"]`); if(cb) setTri(cb,s); });
  renderFoot();
}

function setTri(cb, s){
  const sel_ = itemsOf(s).filter(i=>i.op), n = sel_.filter(i=>sel.has(i.id)).length;
  cb.checked = n>0 && n===sel_.length; cb.indeterminate = n>0 && n<sel_.length; cb.disabled = !sel_.length;
}

function seriesHtml(s){
  const its = itemsOf(s), act = its.filter(i=>i.op), chosen = act.filter(i=>sel.has(i.id));
  const by = st => its.filter(i=>i.status===st).length;
  const isOpen = opened.has(s.key);
  const meta = [chosen.length+' / '+act.length+' sélectionné(s)', fmtB(chosen.reduce((a,i)=>a+(i.op==='copy'?i.size:0),0))+' à copier',
    by('present')?by('present')+' déjà archivé(s)':'', by('duplicate')?by('duplicate')+' doublon(s)':''].filter(Boolean).join(' · ');
  return `<div class="series" data-key="${s.key}">
    <div class="shead">
      <input type="checkbox" data-sall="${s.key}">
      <div class="ttl">
        <input type="text" value="${esc(titleOf(s))}" data-title="${s.key}" ${s.locked?'readonly title="Nom du dossier existant dans l\'archive"':'title="Clique pour renommer la série"'}>
        <div class="meta">${meta} ${s.origins.map(o=>`<span class="badge">${ORIG[o]}</span>`).join('')}${s.locked?'<span class="badge b-ok">dans l\'archive</span>':''}</div>
      </div>
      <button class="chev ${isOpen?'open':''}" data-open="${s.key}">›</button>
    </div>
    ${isOpen?`<div class="sbody">${bodyHtml(s)}</div>`:''}
  </div>`;
}

function bodyHtml(s){
  return `<table><tr><th></th><th>Chapitre</th><th class="hide-sm">Fichier d'origine</th><th>Nouveau nom</th><th>Taille</th><th>État</th></tr>
  ${itemsOf(s).map(i=>{
    const [lbl,cls] = STATUS[i.status];
    return `<tr class="${i.op?'':'dim'}">
      <td><input type="checkbox" data-it="${i.id}" ${sel.has(i.id)?'checked':''} ${i.op?'':'disabled'}></td>
      <td>${esc(i.label)}</td>
      <td class="old mono hide-sm" title="${esc(i.src)}">${esc(i.src.split(/[\\/]/).slice(-2).join('/'))}</td>
      <td class="new mono">${i.op?esc(newName(s,i)):'—'}</td>
      <td>${fmtB(i.size)}</td>
      <td><span class="badge ${cls}" title="${esc(i.note)}">${lbl}</span>${i.op?`<span class="badge">${OP[i.op]}</span>`:''}</td>
    </tr>`}).join('')}</table>`;
}

function refreshSeries(key){
  const s = plan.series.find(x=>x.key===key), el = document.querySelector(`.series[data-key="${CSS.escape(key)}"]`);
  if(!s||!el) return;
  const focus = document.activeElement && document.activeElement.dataset.title===key;
  const pos = focus ? document.activeElement.selectionStart : 0;
  el.outerHTML = seriesHtml(s);
  setTri(document.querySelector(`[data-sall="${CSS.escape(key)}"]`), s);
  if(focus){ const inp=document.querySelector(`[data-title="${CSS.escape(key)}"]`); inp.focus(); inp.setSelectionRange(pos,pos); }
  renderFoot();
}

function renderFoot(){
  const f = $('#foot');
  if(!plan || !plan.items || !S){ f.hidden = true; return; }
  f.hidden = false;
  const chosen = plan.items.filter(i=>sel.has(i.id)&&i.op);
  const bytes = chosen.reduce((a,i)=>a+(i.op==='copy'?i.size:0),0);
  const d = S.drives.find(d=>d.id===plan.disk_id);
  const ops = ['copy','move','rename'].map(o=>[o,chosen.filter(i=>i.op===o).length]).filter(x=>x[1]).map(([o,n])=>`${n} ${OP[o].toLowerCase()}${n>1?'s':''}`).join(' · ');
  $('#fSum').textContent = `${chosen.length} fichier${chosen.length>1?'s':''} · ${fmtB(bytes)} à copier`;
  let dest = d ? `→ ${d.root.replace(/[\\/]$/,'')}${d.root.includes('/')?'/':'\\'}${S.archive_name} · ${fmtB(d.free)} libres` : '⚠ Disque de l\'analyse débranché';
  if(selDisk!==plan.disk_id) dest = '⚠ Disque sélectionné différent de l\'analyse — relance l\'analyse';
  if(d && bytes > d.free) dest = '⚠ Espace insuffisant sur le disque';
  $('#fDest').textContent = (ops?ops+'  ':'')+dest;
  $('#go').disabled = !chosen.length || !d || S.job_running || selDisk!==plan.disk_id || bytes > d.free;
}

// ---------- événements ----------
$('#drives').onclick = e => { const d=e.target.closest('.drive'); if(d){ selDisk=d.dataset.id; render(); } };
$('#srcs').onclick = e => { const i=e.target.dataset.rm; if(i!==undefined){ const s=[...S.settings.sources]; s.splice(+i,1); act('/api/settings',{sources:s}); } };
$('#srcAdd').onclick = () => { const v=$('#srcIn').value.trim(); if(!v) return; $('#srcIn').value=''; act('/api/settings',{sources:[...S.settings.sources,v]}); };
$('#srcIn').onkeydown = e => { if(e.key==='Enter') $('#srcAdd').click(); };
$('#scanDisk').onchange = e => act('/api/settings',{scan_disk:e.target.checked});
$('#moveProjects').onchange = e => act('/api/settings',{move_projects:e.target.checked});
$('#scanBtn').onclick = () => { planFolder = null; act('/api/scan',{disk_id:selDisk}); };
$('#auto').onchange = e => act('/api/autostart',{enabled:e.target.checked}, e.target.checked?'Lancement auto activé':'Lancement auto désactivé');
$('#quit').onclick = async () => { if(!confirm('Arrêter Manga Archiver ? (une copie en cours sera mise en pause et reprise plus tard)')) return;
  await api('/api/quit',{}).catch(()=>{}); document.body.innerHTML='<main><div class="card">Manga Archiver arrêté. Tu peux fermer cet onglet.</div></main>'; };
document.querySelectorAll('.chip[data-f]').forEach(c=>c.onclick=()=>{ filter=c.dataset.f; renderPlan(); });
$('#q').oninput = e => { q=e.target.value; renderPlan(); };
$('#pfChip').onclick = () => { planFolder = null; renderPlan(); };
$('#selAll').onclick = () => { plan.items.forEach(i=>{ if(i.op) sel.add(i.id); }); renderPlan(); };
$('#selNone').onclick = () => { sel.clear(); renderPlan(); };
$('#series').addEventListener('click', e => {
  const o = e.target.closest('[data-open]');
  if(o){ const k=o.dataset.open; opened.has(k)?opened.delete(k):opened.add(k); refreshSeries(k); }
});
$('#series').addEventListener('change', e => {
  const t = e.target;
  if(t.dataset.sall){ const s=plan.series.find(x=>x.key===t.dataset.sall);
    itemsOf(s).filter(i=>i.op).forEach(i=>t.checked?sel.add(i.id):sel.delete(i.id)); refreshSeries(s.key); }
  if(t.dataset.it){ t.checked?sel.add(t.dataset.it):sel.delete(t.dataset.it); refreshSeries(plan.items[+t.dataset.it].series); }
});
$('#series').addEventListener('input', e => { const k=e.target.dataset.title; if(k){ titles[k]=e.target.value; refreshSeries(k); } });
$('#go').onclick = async () => {
  const selected = [...sel];
  const nt = Object.fromEntries(Object.entries(titles).filter(([k,v])=>v.trim()));
  hideJob = false;
  await act('/api/job/start',{disk_id:plan.disk_id, titles:nt, selected}, 'Copie lancée');
  window.scrollTo({top:0,behavior:'smooth'});
};
$('#jPause').onclick = () => act('/api/job/pause',{});
$('#jResume').onclick = () => { hideJob=false; act('/api/job/resume',{disk_id:S.job.disk_id}); };
$('#jCancel').onclick = () => { if(confirm('Annuler la copie ? Les fichiers déjà copiés restent sur le disque.')) act('/api/job/cancel',{disk_id:S.job.disk_id}); };
$('#jClose').onclick = () => { hideJob=true; renderJob(); if(['done','done_errors'].includes(S.job.status)) act('/api/scan',{disk_id:S.job.disk_id}); };
$('#mGo').onclick = () => { const id=$('#modal').dataset.id; hideJob=false; $('#modal').classList.remove('on'); act('/api/job/resume',{disk_id:id},'Reprise de la copie'); };
$('#mLater').onclick = () => { dismissed.add($('#modal').dataset.k); $('#modal').classList.remove('on'); };
$('#mDrop').onclick = () => { if(!confirm('Abandonner cette copie ? Les fichiers déjà copiés restent sur le disque.')) return;
  const id=$('#modal').dataset.id; $('#modal').classList.remove('on'); act('/api/job/cancel',{disk_id:id},'Copie abandonnée'); };
// ---------- gestion du disque ----------
const KIND = {archive:['Archive','b-ok'], manga:['Mangas à ranger','b-acc'], mixte:['Mangas + autres','b-warn'],
  vide:['Vide','b-err'], autre:['Autres fichiers','']};
const dk = {tab:'explore', disk:null, path:'', data:null, ver:-1, esel:new Set(), aq:'', aopen:new Set(), busy:false};

function renderDisk(){
  const sec = $('#diskSec');
  if(!selDisk){ sec.hidden = true; return; }
  sec.hidden = false;
  const d = S.drives.find(x=>x.id===selDisk), ds = S.disk_scan;
  $('#dkName').textContent = d ? '— '+d.label : '';
  document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('on', b.dataset.tab===dk.tab));
  const mine = ds.disk_id===selDisk;
  $('#dkIndex').disabled = ds.running;
  $('#dkSt').innerHTML = ds.running ? `<span class="spin"></span>Exploration de ${esc(d?d.label:'')} — ${ds.dirs} dossiers…`
    : (mine && ds.error ? 'Erreur : '+esc(ds.error) : '');
  if(dk.disk !== selDisk){ Object.assign(dk, {disk:selDisk, path:'', data:null, esel:new Set(), aopen:new Set()}); loadDisk(); }
  else if(ds.version !== dk.ver && !ds.running){ loadDisk(); }
}

async function loadDisk(){
  dk.ver = S.disk_scan.version;
  const id = encodeURIComponent(selDisk);
  try{
    if(dk.tab==='explore') dk.data = await api(`/api/disk/ls?disk_id=${id}&path=${encodeURIComponent(dk.path)}`);
    else if(dk.tab==='empty') dk.data = await api(`/api/disk/empty?disk_id=${id}`);
    else dk.data = await api(`/api/archive?disk_id=${id}`);
  }catch(e){
    if(dk.tab==='explore' && dk.path){ dk.path=''; return loadDisk(); }
    dk.data = {error:e.message};
  }
  renderDiskBody();
}

const notIndexed = () => `<div class="empty">Le disque n'a pas encore été exploré.<br><br>
  <button class="primary" data-do="index">Explorer le disque</button></div>`;

function renderDiskBody(){
  const b = $('#dkBody'), x = dk.data;
  if(!x){ b.innerHTML = '<div class="empty"><span class="spin"></span>Chargement…</div>'; return; }
  if(x.error){ b.innerHTML = `<div class="empty">${esc(x.error)}</div>`; return; }
  if(dk.tab==='explore') b.innerHTML = x.indexed ? exploreHtml(x) : notIndexed();
  else if(dk.tab==='empty') b.innerHTML = x.indexed ? emptyHtml(x) : notIndexed();
  else b.innerHTML = archiveHtml(x);
}

function exploreHtml(x){
  const parts = x.path ? x.path.split('/') : [];
  const crumb = [`<a data-go="">Racine</a>`].concat(parts.map((p,i)=>`<span>/</span><a data-go="${esc(parts.slice(0,i+1).join('/'))}">${esc(p)}</a>`)).join('');
  const max = Math.max(1, ...x.children.map(c=>c.size));
  const rows = x.children.map(c=>{ const [l,cls]=KIND[c.kind];
    return `<tr class="nav" data-go="${esc(c.path)}">
      <td>📁 ${esc(c.name)}</td><td><span class="badge ${cls}">${l}</span></td>
      <td><div class="sz"><div class="bar"><i style="width:${(c.size/max*100).toFixed(1)}%"></i></div><span>${fmtB(c.size)}</span></div></td>
      <td class="num">${c.comics}</td><td class="num hide-sm">${c.files}</td><td class="num hide-sm">${c.subdirs}</td>
      <td>${['manga','mixte'].includes(c.kind)?`<button class="primary sm" data-rg="${esc(c.path)}">Ranger</button>`:''}</td></tr>`; }).join('');
  const inArch = x.path===S.archive_name || x.path.startsWith(S.archive_name+'/');
  const isProj = x.children.some(c=>['cbr','cbz'].includes(c.name.toLowerCase()) && c.comics);
  const here = x.path && !inArch && x.comics ? `<div class="row" style="margin-bottom:12px;padding:12px 14px;border:1px solid #ff5d8f55;border-radius:12px;background:#ff5d8f0d">
      <div style="flex:1"><b>${isProj?'Dossier projet':'Dossier avec mangas'}</b>
        <div class="meta">${x.comics} CBR/CBZ${isProj?' · répertoire CBR + dossiers de chapitres (images non copiées)':''}</div></div>
      <button class="primary" data-rg="${esc(x.path)}">Ranger ce dossier</button></div>` : '';
  return `<div class="crumb">${crumb}</div>${here}
    <div class="stats">
      <div class="stat"><div class="v">${fmtB(x.size)}</div><div class="k">dans ce dossier</div></div>
      <div class="stat"><div class="v">${x.comics}</div><div class="k">CBR / CBZ</div></div>
      <div class="stat"><div class="v">${x.files}</div><div class="k">fichiers au total</div></div>
      <div class="stat"><div class="v">${x.own_files}</div><div class="k">fichiers directement ici</div></div>
    </div>
    ${x.children.length ? `<div class="sbody" style="max-height:520px;border:1px solid var(--line);border-radius:12px">
      <table><tr><th>Dossier</th><th>Contenu</th><th>Taille</th><th class="num">CBR</th><th class="num hide-sm">Fichiers</th><th class="num hide-sm">Sous-dossiers</th><th></th></tr>${rows}</table></div>`
      : '<div class="empty">Aucun sous-dossier.</div>'}
    <div class="meta" style="margin-top:8px">Exploré le ${esc(x.created.replace('T',' '))}. « Ranger » : analyse ce dossier et prépare son rangement dans l'archive (étape 3), à valider avant copie.</div>`;
}

function emptyHtml(x){
  if(!x.dirs.length) return '<div class="empty">Aucun dossier vide sur ce disque 🎉</div>';
  const n = x.dirs.filter(d=>dk.esel.has(d.path)).length;
  return `<div class="tools"><span class="meta" style="flex:1">${x.dirs.length} dossier(s) vide(s) — vides ou ne contenant que des fichiers parasites (.DS_Store, Thumbs.db…)</span>
      <button class="ghost sm" data-do="eall">Tout cocher</button><button class="ghost sm" data-do="enone">Tout décocher</button>
      <button class="primary sm" data-do="edel" ${n?'':'disabled'}>Supprimer (${n})</button></div>
    <div class="sbody" style="max-height:520px;border:1px solid var(--line);border-radius:12px"><table>
      <tr><th></th><th>Dossier</th><th class="num">Sous-dossiers vides</th></tr>
      ${x.dirs.map(d=>`<tr><td style="width:30px"><input type="checkbox" data-e="${esc(d.path)}" ${dk.esel.has(d.path)?'checked':''}></td>
        <td class="mono">${esc(d.path)}</td><td class="num">${d.subdirs}</td></tr>`).join('')}</table></div>`;
}

function archiveHtml(x){
  if(!x.series.length) return '<div class="empty">Archive vide ou absente sur ce disque.</div>';
  const ql = dk.aq.toLowerCase(), list = x.series.filter(s=>!ql || s.name.toLowerCase().includes(ql));
  const tot = x.series.reduce((a,s)=>a+s.size,0), dups = x.series.reduce((a,s)=>a+s.dups,0);
  const names = x.series.map(s=>`<option value="${esc(s.name)}">`).join('');
  return `<div class="stats">
      <div class="stat"><div class="v">${x.series.length}</div><div class="k">séries</div></div>
      <div class="stat"><div class="v">${x.series.reduce((a,s)=>a+s.count,0)}</div><div class="k">chapitres</div></div>
      <div class="stat"><div class="v">${fmtB(tot)}</div><div class="k">au total</div></div>
      <div class="stat"><div class="v">${dups}</div><div class="k">doublons (même n°)</div></div></div>
    <div class="tools"><input type="text" id="aq" placeholder="Rechercher une série…" value="${esc(dk.aq)}" style="flex:1">
      <span class="meta">Suppressions → corbeille <code>.Corbeille_MangaArchiver</code> à la racine du disque</span></div>
    <datalist id="snames">${names}</datalist>
    ${list.map(s=>{ const o = dk.aopen.has(s.name);
      return `<div class="series"><div class="shead">
        <div class="ttl"><input type="text" value="${esc(s.name)}" data-ren="${esc(s.name)}" list="snames" title="Renomme, ou tape le nom d'une autre série pour fusionner">
          <div class="meta">${s.count} chapitre(s) · ${fmtB(s.size)}${s.dups?` <span class="badge b-err">${s.dups} doublon(s)</span>`:''}${s.others?` <span class="badge">${s.others} autre(s) fichier(s)</span>`:''}</div></div>
        <div class="acts"><button data-do="ren" data-s="${esc(s.name)}">Renommer / fusionner</button>
          <button class="danger" data-do="sdel" data-s="${esc(s.name)}">Supprimer</button></div>
        <button class="chev ${o?'open':''}" data-aopen="${esc(s.name)}">›</button></div>
        ${o?`<div class="sbody"><table><tr><th>Chapitre</th><th>Taille</th><th class="hide-sm">Déplacer vers</th><th></th></tr>
          ${s.chapters.map(c=>`<tr><td class="mono">${esc(c.name)} ${c.dup?'<span class="badge b-err">doublon</span>':''}</td><td>${fmtB(c.size)}</td>
            <td class="hide-sm"><div class="row"><input type="text" list="snames" placeholder="Série…" data-mvto style="width:200px">
              <button class="sm" data-do="mv" data-s="${esc(s.name)}" data-f="${esc(c.name)}">Déplacer</button></div></td>
            <td><div class="acts"><button class="sm danger" data-do="fdel" data-s="${esc(s.name)}" data-f="${esc(c.name)}">Supprimer</button></div></td></tr>`).join('')}
        </table></div>`:''}</div>`; }).join('') || '<div class="empty">Aucune série ne correspond.</div>'}`;
}

async function archiveAct(body, confirmMsg){
  if(confirmMsg && !confirm(confirmMsg)) return;
  try{ const r = await api('/api/archive/action', {disk_id:selDisk, ...body}); toast(r.message, true); }
  catch(e){ toast(e.message); }
  await poll(true); loadDisk();
}

document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{ dk.tab=b.dataset.tab; dk.data=null; renderDisk(); renderDiskBody(); loadDisk(); });
$('#dkIndex').onclick = () => act('/api/disk/index',{disk_id:selDisk});
$('#dkBody').addEventListener('click', async e => {
  const rg = e.target.closest('[data-rg]');
  if(rg){
    const d = S.drives.find(x=>x.id===selDisk), sep = d.root.includes('\\') ? '\\' : '/';
    planFolder = d.root.replace(/[\\/]+$/,'') + sep + rg.dataset.rg.split('/').join(sep);
    filter = 'all';
    try{ if(!S.settings.scan_disk) await api('/api/settings',{scan_disk:true});
         await api('/api/scan',{disk_id:selDisk}); toast('Analyse lancée — le plan de « '+rg.dataset.rg+' » apparaîtra à l\'étape 3', true); }
    catch(err){ toast(err.message); return; }
    await poll(true); $('#scanBtn').scrollIntoView({behavior:'smooth', block:'center'}); return;
  }
  const go = e.target.closest('[data-go]');
  if(go){ dk.path = go.dataset.go; dk.data = null; renderDiskBody(); return loadDisk(); }
  const ao = e.target.closest('[data-aopen]');
  if(ao){ const n=ao.dataset.aopen; dk.aopen.has(n)?dk.aopen.delete(n):dk.aopen.add(n); return renderDiskBody(); }
  const b = e.target.closest('[data-do]'); if(!b) return;
  const d = b.dataset.do, sname = b.dataset.s, f = b.dataset.f;
  if(d==='index') return act('/api/disk/index',{disk_id:selDisk});
  if(d==='eall'){ dk.data.dirs.forEach(x=>dk.esel.add(x.path)); return renderDiskBody(); }
  if(d==='enone'){ dk.esel.clear(); return renderDiskBody(); }
  if(d==='edel'){
    const paths = dk.data.dirs.filter(x=>dk.esel.has(x.path)).map(x=>x.path);
    if(!confirm(`Supprimer ${paths.length} dossier(s) vide(s) ? Un dossier qui contient un vrai fichier est toujours ignoré.`)) return;
    try{ const r = await api('/api/disk/delete_empty',{disk_id:selDisk, paths}); toast(r.message, true); dk.esel.clear(); }
    catch(err){ toast(err.message); }
    await poll(true); return act('/api/disk/index',{disk_id:selDisk});
  }
  if(d==='ren'){ const to = b.closest('.shead').querySelector('[data-ren]').value.trim();
    if(!to || to===sname) return toast('Modifie le nom de la série d\'abord');
    const merge = dk.data.series.some(x=>x.name.toLowerCase()===to.toLowerCase() && x.name!==sname);
    return archiveAct({action:'rename', series:sname, to}, merge ? `Fusionner « ${sname} » dans la série existante « ${to} » ?` : `Renommer « ${sname} » en « ${to} » ? Les fichiers seront renommés aussi.`); }
  if(d==='mv'){ const to = b.closest('tr').querySelector('[data-mvto]').value.trim();
    if(!to) return toast('Choisis la série de destination');
    return archiveAct({action:'move', series:sname, file:f, to}); }
  if(d==='sdel') return archiveAct({action:'delete', series:sname}, `Mettre toute la série « ${sname} » à la corbeille du disque ?`);
  if(d==='fdel') return archiveAct({action:'delete', series:sname, file:f}, `Mettre « ${f} » à la corbeille du disque ?`);
});
$('#dkBody').addEventListener('change', e => { const p = e.target.dataset.e;
  if(p!==undefined){ e.target.checked ? dk.esel.add(p) : dk.esel.delete(p); renderDiskBody(); } });
$('#dkBody').addEventListener('input', e => { if(e.target.id==='aq'){ dk.aq = e.target.value; const pos=e.target.selectionStart;
  renderDiskBody(); const i=$('#aq'); i.focus(); i.setSelectionRange(pos,pos); } });

poll();
</script>
</body>
</html>
"""


if __name__ == '__main__':
    main()
