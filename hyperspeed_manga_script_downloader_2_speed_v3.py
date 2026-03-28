import json
import os
import requests
from pathlib import Path
from urllib.parse import urlparse
import time
import re
import zipfile
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from dataclasses import dataclass
from typing import List, Tuple, Optional
import queue

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
    
    def add_success(self):
        with self.lock:
            self.downloaded_images += 1
    
    def add_failure(self):
        with self.lock:
            self.failed_images += 1
    
    def add_skip(self):
        with self.lock:
            self.skipped_images += 1
    
    def get_stats(self):
        with self.lock:
            return {
                'total': self.total_images,
                'downloaded': self.downloaded_images,
                'failed': self.failed_images,
                'skipped': self.skipped_images
            }

def sanitize_filename(filename):
    """Nettoie le nom de fichier pour éviter les caractères problématiques"""
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = filename.replace(' ', '_')
    return filename

def create_session():
    """Crée une session réutilisable avec des optimisations"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    
    # Configuration des adaptateurs pour la réutilisation des connexions
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=20,
        pool_maxsize=20,
        max_retries=requests.adapters.Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=[500, 502, 503, 504]
        )
    )
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    return session

def download_image_optimized(task: DownloadTask, session: requests.Session, stats: DownloadStats, progress_queue: queue.Queue) -> bool:
    """Télécharge une image de manière optimisée"""
    try:
        # Vérifie si le fichier existe déjà
        if task.filepath.exists():
            stats.add_skip()
            progress_queue.put(f"⏭️  Fichier déjà existant: {task.filepath.name}")
            return True
        
        # Téléchargement avec streaming pour économiser la mémoire
        response = session.get(task.url, timeout=30, stream=True)
        response.raise_for_status()
        
        # Crée le dossier parent si nécessaire
        task.filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Écrit le fichier par chunks
        with open(task.filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        stats.add_success()
        progress_queue.put(f"✅ {task.chapter_name} - Page {task.page_number:03d}")
        return True
        
    except Exception as e:
        stats.add_failure()
        progress_queue.put(f"❌ Erreur {task.chapter_name} - Page {task.page_number:03d}: {str(e)[:50]}...")
        return False

def progress_monitor(progress_queue: queue.Queue, stats: DownloadStats, total_tasks: int):
    """Monitore et affiche le progrès en temps réel"""
    while True:
        try:
            message = progress_queue.get(timeout=1)
            current_stats = stats.get_stats()
            completed = current_stats['downloaded'] + current_stats['failed'] + current_stats['skipped']
            progress = (completed / total_tasks) * 100 if total_tasks > 0 else 0
            
            print(f"[{progress:.1f}%] {message}")
            
            if completed >= total_tasks:
                break
                
        except queue.Empty:
            continue
        except KeyboardInterrupt:
            break

def extract_chapter_number(chapter_name):
    """Extrait le numéro de chapitre pour le tri"""
    match = re.search(r'Chapitre (\d+)', chapter_name)
    return int(match.group(1)) if match else 0

def create_cbr_from_folder(folder_path: Path, output_path: Path) -> bool:
    """Crée un fichier CBR (ZIP) à partir d'un dossier d'images"""
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as zipf:
            # Trie les fichiers par nom pour maintenir l'ordre
            image_files = sorted([f for f in folder_path.glob('*') if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']])
            
            for image_file in image_files:
                zipf.write(image_file, image_file.name)
        
        print(f"📦 CBR créé: {output_path.name}")
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors de la création du CBR {output_path.name}: {e}")
        return False

def prepare_download_tasks(chapters: dict, main_folder: Path) -> List[DownloadTask]:
    """Prépare toutes les tâches de téléchargement"""
    tasks = []
    
    # Tri des chapitres par numéro
    sorted_chapters = sorted(chapters.items(), key=lambda x: extract_chapter_number(x[0]))
    
    for chapter_name, chapter_data in sorted_chapters:
        clean_chapter_name = sanitize_filename(chapter_name)
        chapter_folder = main_folder / clean_chapter_name
        images = chapter_data.get('images', [])
        
        for i, image_url in enumerate(images, 1):
            # Génération du nom de fichier
            parsed_url = urlparse(image_url)
            path_parts = parsed_url.path.split('/')
            original_filename = path_parts[-1] if path_parts else f"image_{i}"
            
            # Détermine l'extension
            if '.' not in original_filename or len(original_filename.split('.')[-1]) > 4:
                if any(ext in image_url.lower() for ext in ['.jpg', '.jpeg']):
                    extension = 'jpg'
                elif '.png' in image_url.lower():
                    extension = 'png'
                elif '.gif' in image_url.lower():
                    extension = 'gif'
                else:
                    extension = 'jpg'  # Par défaut
            else:
                extension = original_filename.split('.')[-1]
            
            filename = f"page_{i:03d}.{extension}"
            filepath = chapter_folder / filename
            
            tasks.append(DownloadTask(
                url=image_url,
                filepath=filepath,
                page_number=i,
                chapter_name=chapter_name
            ))
    
    return tasks

def main():
    # Configuration
    json_file = 'manga_script_json.txt'
    max_workers = 10  # Nombre de téléchargements simultanés (ajustez selon votre connexion)
    
    try:
        # Lecture du fichier JSON
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        project_name = data.get('projectName', 'manga')
        chapters = data.get('chapters', {})
        
        # Création des dossiers
        main_folder = Path(project_name)
        main_folder.mkdir(exist_ok=True)
        cbr_folder = main_folder / 'CBR'
        cbr_folder.mkdir(exist_ok=True)
        
        print(f"📁 Dossier principal: {main_folder}")
        print(f"📁 Dossier CBR: {cbr_folder}")
        print(f"📊 Nombre de chapitres: {len(chapters)}")
        print(f"🚀 Téléchargements simultanés: {max_workers}")
        
        # Préparation des tâches
        print("\n🔄 Préparation des tâches de téléchargement...")
        tasks = prepare_download_tasks(chapters, main_folder)
        
        if not tasks:
            print("❌ Aucune tâche de téléchargement trouvée!")
            return
        
        stats = DownloadStats()
        stats.total_images = len(tasks)
        progress_queue = queue.Queue()
        
        print(f"📋 Total d'images à traiter: {len(tasks)}")
        print("\n🚀 Début des téléchargements parallèles...")
        
        # Thread pour le monitoring du progrès
        monitor_thread = threading.Thread(
            target=progress_monitor,
            args=(progress_queue, stats, len(tasks)),
            daemon=True
        )
        monitor_thread.start()
        
        # Téléchargement parallèle
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Crée une session par thread
            sessions = {i: create_session() for i in range(max_workers)}
            
            # Soumet toutes les tâches
            future_to_task = {}
            for i, task in enumerate(tasks):
                session = sessions[i % max_workers]
                future = executor.submit(download_image_optimized, task, session, stats, progress_queue)
                future_to_task[future] = task
            
            # Attend la completion de toutes les tâches
            for future in as_completed(future_to_task):
                pass  # Le monitoring se fait via la queue
        
        download_time = time.time() - start_time
        
        # Fermeture des sessions
        for session in sessions.values():
            session.close()
        
        # Attendre que le monitoring se termine
        monitor_thread.join(timeout=2)
        
        # Création des CBR
        print(f"\n📦 Création des fichiers CBR...")
        cbr_created = 0
        
        # Groupe les tâches par chapitre
        chapters_folders = {}
        for task in tasks:
            chapter_folder = task.filepath.parent
            if chapter_folder not in chapters_folders:
                chapters_folders[chapter_folder] = task.chapter_name
        
        for chapter_folder, chapter_name in chapters_folders.items():
            if any(chapter_folder.glob('*')):  # Si le dossier contient des fichiers
                chapter_number = extract_chapter_number(chapter_name)
                cbr_filename = f"Chapter_{chapter_number:03d} - {sanitize_filename(chapter_name.split(' - ')[0])}.cbr"
                cbr_path = cbr_folder / cbr_filename
                
                if not cbr_path.exists():
                    if create_cbr_from_folder(chapter_folder, cbr_path):
                        cbr_created += 1
                else:
                    print(f"📦 CBR déjà existant: {cbr_path.name}")
                    cbr_created += 1
        
        # Statistiques finales
        final_stats = stats.get_stats()
        print(f"\n📈 RÉSUMÉ FINAL:")
        print(f"📊 Total des images: {final_stats['total']}")
        print(f"✅ Images téléchargées: {final_stats['downloaded']}")
        print(f"⏭️ Images déjà existantes: {final_stats['skipped']}")
        print(f"❌ Images échouées: {final_stats['failed']}")
        print(f"📦 Fichiers CBR créés/vérifiés: {cbr_created}")
        print(f"⏱️ Temps de téléchargement: {download_time:.2f} secondes")
        print(f"🚀 Vitesse moyenne: {final_stats['downloaded']/download_time:.1f} images/sec")
        
        # Estimation du débit utilisé
        if final_stats['downloaded'] > 0:
            avg_size_kb = 200  # Estimation moyenne d'une page manga
            total_mb = (final_stats['downloaded'] * avg_size_kb) / 1024
            throughput_kbps = (total_mb * 1024) / download_time
            print(f"📡 Débit moyen estimé: {throughput_kbps:.0f} KB/s ({total_mb:.1f} MB total)")
        print(f"📁 Destination: {main_folder.absolute()}")
        
        # Option de nettoyage
        if final_stats['downloaded'] > 0:
            print(f"\n💡 Conseil: Vous pouvez supprimer les dossiers d'images individuels")
            print(f"   et garder seulement les fichiers CBR pour économiser l'espace.")
            print(f"🎯 Avec votre connexion haut débit, le téléchargement devrait être très rapide!")
        
    except FileNotFoundError:
        print(f"❌ Fichier JSON non trouvé: {json_file}")
    except json.JSONDecodeError:
        print(f"❌ Erreur de format JSON dans le fichier: {json_file}")
    except KeyboardInterrupt:
        print(f"\n⏹️ Téléchargement interrompu par l'utilisateur")
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")

if __name__ == "__main__":
    main()