import json
import os
import requests
from pathlib import Path
from urllib.parse import urlparse
import time
import re
import zipfile
import shutil
from colorama import Fore, Back, Style, init
import random

# Initialisation de colorama pour Windows
init(autoreset=True)

# Définition des couleurs style terminal rétro
class HackerColors:
    GREEN = Fore.GREEN
    BRIGHT_GREEN = Fore.LIGHTGREEN_EX
    DARK_GREEN = Fore.GREEN + Style.DIM
    RED = Fore.RED
    YELLOW = Fore.YELLOW
    CYAN = Fore.CYAN
    WHITE = Fore.WHITE
    BLACK = Fore.BLACK
    MATRIX = Fore.LIGHTGREEN_EX + Style.BRIGHT
    ERROR = Fore.RED + Style.BRIGHT
    WARNING = Fore.YELLOW + Style.BRIGHT
    RESET = Style.RESET_ALL

def print_ascii_art():
    """Affiche l'art ASCII d'introduction"""
    art = f"""{HackerColors.MATRIX}
    ███╗   ███╗ █████╗ ███╗   ██╗ ██████╗  █████╗ 
    ████╗ ████║██╔══██╗████╗  ██║██╔════╝ ██╔══██╗
    ██╔████╔██║███████║██╔██╗ ██║██║  ███╗███████║
    ██║╚██╔╝██║██╔══██║██║╚██╗██║██║   ██║██╔══██║
    ██║ ╚═╝ ██║██║  ██║██║ ╚████║╚██████╔╝██║  ██║
    ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝
    
    ██████╗  ██████╗ ██╗    ██╗███╗   ██╗██╗      ██████╗  █████╗ ██████╗ ███████╗██████╗ 
    ██╔══██╗██╔═══██╗██║    ██║████╗  ██║██║     ██╔═══██╗██╔══██╗██╔══██╗██╔════╝██╔══██╗
    ██║  ██║██║   ██║██║ █╗ ██║██╔██╗ ██║██║     ██║   ██║███████║██║  ██║█████╗  ██████╔╝
    ██║  ██║██║   ██║██║███╗██║██║╚██╗██║██║     ██║   ██║██╔══██║██║  ██║██╔══╝  ██╔══██╗
    ██████╔╝╚██████╔╝╚███╔███╔╝██║ ╚████║███████╗╚██████╔╝██║  ██║██████╔╝███████╗██║  ██║
    ╚═════╝  ╚═════╝  ╚══╝╚══╝ ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚══════╝╚═╝  ╚═╝
    
    {HackerColors.DARK_GREEN}>>> INITIATING MANGA EXTRACTION PROTOCOL...
    >>> CYBERPUNK DATA MINING SYSTEM v3.1337
    >>> ACCESS GRANTED - WELCOME TO THE MATRIX
    {HackerColors.RESET}"""
    
    print(art)
    time.sleep(0.5)

def matrix_effect(text, delay=0.03):
    """Effet Matrix pour l'affichage du texte"""
    for char in text:
        print(f"{HackerColors.MATRIX}{char}{HackerColors.RESET}", end='', flush=True)
        time.sleep(delay)
    print()

def print_glitch_line():
    """Affiche une ligne de glitch"""
    glitch_chars = "█▓▒░▄▀▌▐"
    line = "".join(random.choice(glitch_chars) for _ in range(60))
    print(f"{HackerColors.MATRIX}{line}{HackerColors.RESET}")

def print_hacker_header(text):
    """Affiche un en-tête style hacker"""
    print(f"\n{HackerColors.GREEN}┌{'─' * 58}┐")
    print(f"│{HackerColors.MATRIX} {text.center(56)} {HackerColors.GREEN}│")
    print(f"└{'─' * 58}┘{HackerColors.RESET}")

def print_system_msg(prefix, text, color=HackerColors.GREEN):
    """Affiche un message système"""
    timestamp = time.strftime("%H:%M:%S")
    print(f"{HackerColors.DARK_GREEN}[{timestamp}]{color} {prefix} {text}{HackerColors.RESET}")

def print_success(text):
    """Message de succès style hacker"""
    print_system_msg("[SUCCESS]", text, HackerColors.BRIGHT_GREEN)

def print_error(text):
    """Message d'erreur style hacker"""
    print_system_msg("[ERROR]", text, HackerColors.ERROR)

def print_warning(text):
    """Message d'avertissement style hacker"""
    print_system_msg("[WARNING]", text, HackerColors.WARNING)

def print_info(text):
    """Message d'information style hacker"""
    print_system_msg("[INFO]", text, HackerColors.CYAN)

def print_progress(text):
    """Message de progression style hacker"""
    print_system_msg("[PROCESS]", text, HackerColors.YELLOW)

def loading_animation(text, duration=2):
    """Animation de chargement style hacker"""
    print(f"{HackerColors.YELLOW}[LOADING] {text}", end="", flush=True)
    for _ in range(duration * 10):
        print("█", end="", flush=True)
        time.sleep(0.1)
    print(f" {HackerColors.BRIGHT_GREEN}[COMPLETE]{HackerColors.RESET}")

def sanitize_filename(filename):
    """Nettoie le nom de fichier pour éviter les caractères problématiques"""
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = filename.replace(' ', '_')
    return filename

def download_image(url, filepath, max_retries=3):
    """Télécharge une image avec gestion des erreurs et retry"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; CyberMangaBot/1.0; +http://cybermanga.hax)'
    }
    
    for attempt in range(max_retries):
        try:
            print_progress(f"INFILTRATING SERVER... {filepath.name}")
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            print_success(f"DATA EXTRACTED: {filepath.name}")
            return True
            
        except requests.exceptions.RequestException as e:
            print_error(f"INTRUSION FAILED (RETRY {attempt + 1}/{max_retries}): {filepath.name}")
            print(f"    {HackerColors.ERROR}SYSTEM_ERROR: {e}{HackerColors.RESET}")
            if attempt < max_retries - 1:
                print_info("REROUTING THROUGH PROXY...")
                time.sleep(2)
            
    return False

def extract_chapter_number(chapter_name):
    """Extrait le numéro de chapitre pour le tri"""
    match = re.search(r'Chapitre (\d+)', chapter_name)
    return int(match.group(1)) if match else 0

def create_cbr_from_folder(folder_path, output_path):
    """Crée un fichier CBR (ZIP) à partir d'un dossier d'images"""
    try:
        print_progress("COMPRESSING DATA PACKAGE...")
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            image_files = sorted([f for f in folder_path.glob('*') 
                                if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']])
            
            if not image_files:
                print_warning(f"NO DATA FOUND IN SECTOR: {folder_path}")
                return False
            
            for image_file in image_files:
                zipf.write(image_file, image_file.name)
        
        print_success(f"CBR PACKAGE CREATED: {output_path.name}")
        return True
        
    except Exception as e:
        print_error(f"COMPRESSION FAILED: {e}")
        return False

def delete_folder_safely(folder_path):
    """Supprime un dossier de manière sécurisée"""
    try:
        if folder_path.exists() and folder_path.is_dir():
            print_progress("WIPING TEMPORARY FILES...")
            shutil.rmtree(folder_path)
            print_success(f"SECTOR CLEANED: {folder_path.name}")
            return True
    except Exception as e:
        print_error(f"WIPE FAILED: {folder_path} - {e}")
    return False

def hack_progress_bar(current, total, length=40):
    """Barre de progression style hacker"""
    filled_length = int(length * current // total)
    bar = '█' * filled_length + '░' * (length - filled_length)
    percent = f"{100 * current / total:.1f}%"
    print(f"\r{HackerColors.MATRIX}[HACKING] |{bar}| {percent} {HackerColors.RESET}", end='', flush=True)

def main():
    print_ascii_art()
    
    # Animation d'initialisation
    matrix_effect(">>> INITIALIZING NEURAL NETWORK...", 0.05)
    matrix_effect(">>> CONNECTING TO MANGA DATABASE...", 0.05)
    matrix_effect(">>> BYPASSING SECURITY PROTOCOLS...", 0.05)
    
    print_glitch_line()
    
    # Chemin vers le fichier JSON
    json_file = 'manga_script_json.txt'
    
    try:
        print_progress("SCANNING FOR DATA FILES...")
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        project_name = data.get('projectName', 'manga')
        chapters = data.get('chapters', {})
        
        print_success(f"TARGET ACQUIRED: {project_name}")
        
        # Création du dossier principal
        main_folder = Path(project_name)
        main_folder.mkdir(exist_ok=True)
        
        # Création du dossier CBR
        cbr_folder = main_folder / 'CBR'
        cbr_folder.mkdir(exist_ok=True)
        
        print_success(f"BASE DIRECTORY ESTABLISHED: {main_folder}")
        print_success(f"CBR VAULT CREATED: {cbr_folder}")
        print_info(f"CHAPTERS TO INFILTRATE: {len(chapters)}")
        
        # Tri des chapitres par numéro
        sorted_chapters = sorted(chapters.items(), key=lambda x: extract_chapter_number(x[0]))
        
        # Variables de statistiques
        total_images = 0
        downloaded_images = 0
        cbr_created = 0
        chapters_processed = 0
        
        print_glitch_line()
        
        for chapter_name, chapter_data in sorted_chapters:
            chapters_processed += 1
            
            print_hacker_header(f"INFILTRATING CHAPTER {chapters_processed}/{len(chapters)}")
            matrix_effect(f">>> TARGET: {chapter_name}")
            
            # Nettoyage du nom de chapitre
            clean_chapter_name = sanitize_filename(chapter_name)
            chapter_folder = main_folder / clean_chapter_name
            chapter_folder.mkdir(exist_ok=True)
            
            images = chapter_data.get('images', [])
            total_images += len(images)
            
            print_info(f"TEMP DIRECTORY: {chapter_folder}")
            print_info(f"IMAGES TO EXTRACT: {len(images)}")
            
            chapter_downloaded = 0
            
            # Téléchargement des images
            for i, image_url in enumerate(images, 1):
                # Barre de progression
                hack_progress_bar(i-1, len(images))
                
                # Extraction de l'extension
                parsed_url = urlparse(image_url)
                path_parts = parsed_url.path.split('/')
                filename = path_parts[-1] if path_parts else f"image_{i}"
                
                if '.' not in filename:
                    if image_url.lower().find('.jpg') != -1 or image_url.lower().find('.jpeg') != -1:
                        filename = f"page_{i:03d}.jpg"
                    elif image_url.lower().find('.png') != -1:
                        filename = f"page_{i:03d}.png"
                    else:
                        filename = f"page_{i:03d}.jpg"
                else:
                    name, ext = filename.rsplit('.', 1)
                    filename = f"page_{i:03d}.{ext}"
                
                filepath = chapter_folder / filename
                
                if filepath.exists():
                    print_warning(f"FILE ALREADY IN CACHE: {filepath.name}")
                    downloaded_images += 1
                    chapter_downloaded += 1
                    continue
                
                if download_image(image_url, filepath):
                    downloaded_images += 1
                    chapter_downloaded += 1
                
                time.sleep(0.3)  # Pause pour effet dramatique
            
            # Finalisation de la barre de progression
            hack_progress_bar(len(images), len(images))
            print()
            
            # Création du CBR
            if chapter_downloaded > 0:
                print_progress("INITIATING DATA COMPRESSION...")
                
                chapter_number = extract_chapter_number(chapter_name)
                cbr_filename = f"Chapter_{chapter_number:03d}_-_{sanitize_filename(chapter_name.split(' - ')[0])}.cbr"
                cbr_path = cbr_folder / cbr_filename
                
                if cbr_path.exists():
                    print_warning(f"CBR ALREADY EXISTS: {cbr_path.name}")
                    cbr_created += 1
                else:
                    if create_cbr_from_folder(chapter_folder, cbr_path):
                        cbr_created += 1
                
                # Suppression du dossier temporaire
                delete_folder_safely(chapter_folder)
                
            else:
                print_warning("NO DATA EXTRACTED - MISSION FAILED")
                delete_folder_safely(chapter_folder)
            
            print_glitch_line()
        
        # Statistiques finales
        print_hacker_header("MISSION REPORT")
        
        print(f"{HackerColors.MATRIX}╔═══════════════════════════════════════════════════════════╗")
        print(f"║ {HackerColors.CYAN}EXTRACTION STATISTICS{HackerColors.MATRIX}                                   ║")
        print(f"║                                                           ║")
        print(f"║ {HackerColors.WHITE}Total Images Scanned:{HackerColors.BRIGHT_GREEN} {total_images:>8}{HackerColors.MATRIX}                     ║")
        print(f"║ {HackerColors.WHITE}Images Successfully Extracted:{HackerColors.BRIGHT_GREEN} {downloaded_images:>8}{HackerColors.MATRIX}            ║")
        print(f"║ {HackerColors.WHITE}Extraction Failures:{HackerColors.ERROR} {total_images - downloaded_images:>8}{HackerColors.MATRIX}                     ║")
        print(f"║ {HackerColors.WHITE}CBR Packages Created:{HackerColors.BRIGHT_GREEN} {cbr_created:>8}{HackerColors.MATRIX}                    ║")
        print(f"║                                                           ║")
        print(f"║ {HackerColors.WHITE}Base Directory:{HackerColors.CYAN} {str(main_folder.absolute())[:35]:<35}{HackerColors.MATRIX} ║")
        print(f"║ {HackerColors.WHITE}CBR Vault:{HackerColors.CYAN} {str(cbr_folder.absolute())[:39]:<39}{HackerColors.MATRIX} ║")
        print(f"╚═══════════════════════════════════════════════════════════╝{HackerColors.RESET}")
        
        # Calcul du pourcentage de réussite
        if total_images > 0:
            success_rate = (downloaded_images / total_images) * 100
            if success_rate == 100:
                matrix_effect(">>> MISSION ACCOMPLISHED - 100% SUCCESS RATE")
                print(f"{HackerColors.BRIGHT_GREEN}>>> ALL TARGETS NEUTRALIZED{HackerColors.RESET}")
            elif success_rate >= 80:
                matrix_effect(f">>> MISSION SUCCESSFUL - {success_rate:.1f}% SUCCESS RATE")
            else:
                matrix_effect(f">>> PARTIAL SUCCESS - {success_rate:.1f}% SUCCESS RATE")
        
        print_glitch_line()
        matrix_effect(">>> DISCONNECTING FROM MATRIX...")
        matrix_effect(">>> WIPING TRACES...")
        matrix_effect(">>> HACKER OUT.")
        
    except FileNotFoundError:
        print_error(f"DATA FILE NOT FOUND: {json_file}")
    except json.JSONDecodeError:
        print_error(f"CORRUPTED DATA IN FILE: {json_file}")
    except Exception as e:
        print_error(f"SYSTEM BREACH DETECTED: {e}")
    
    print(f"\n{HackerColors.MATRIX}[PRESS ENTER TO TERMINATE SESSION]{HackerColors.RESET}")
    input()

if __name__ == "__main__":
    main()