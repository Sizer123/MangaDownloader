import os
import re
import zipfile
import shutil
from pathlib import Path
import time
import tkinter as tk
from tkinter import filedialog, messagebox

# --- ANSI Color Codes ---
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    MAGENTA = '\033[95m'
    LIGHTBLUE = '\033[94m'

# --- Helper Functions ---

def sanitize_filename(filename):
    """Cleans up the filename to avoid problematic characters."""
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = filename.replace(' ', '_')
    return filename

def extract_chapter_number(chapter_name):
    """Extracts the chapter number for sorting, handling various formats."""
    # Prioritize 'Chapitre N'
    match_fr = re.search(r'[Cc]hapitre\s*(\d+)', chapter_name)
    if match_fr:
        return int(match_fr.group(1))
    
    # Try 'Chapter N'
    match_en = re.search(r'[Cc]hapter\s*(\d+)', chapter_name)
    if match_en:
        return int(match_en.group(1))

    # Try numeric prefix (e.g., "001 - Title")
    match_prefix = re.search(r'^(\d+)', chapter_name)
    if match_prefix:
        return int(match_prefix.group(1))

    return 0 # Default if no number found

def create_cbr_from_folder(folder_path, output_path):
    """Creates a CBR (ZIP) file from a folder of images."""
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Sort image files numerically (e.g., page_001.jpg, page_002.jpg)
            image_files = sorted(
                [f for f in folder_path.iterdir() if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']],
                key=lambda x: int(re.search(r'(\d+)', x.stem).group(1)) if re.search(r'(\d+)', x.stem) else 0
            )
            
            for image_file in image_files:
                zipf.write(image_file, image_file.name)
        
        print(f"{Colors.OKGREEN}📦 CBR créé: {output_path}{Colors.ENDC}")
        return True
        
    except Exception as e:
        print(f"{Colors.FAIL}❌ Erreur lors de la création du CBR pour {folder_path.name}: {e}{Colors.ENDC}")
        return False

# --- Main Logic ---

def main():
    # Hide the main Tkinter window
    root = tk.Tk()
    root.withdraw() 

    print(f"{Colors.HEADER}{Colors.BOLD}\n--- Lancement du Générateur de CBR ---{Colors.ENDC}")
    print(f"{Colors.OKCYAN}Veuillez sélectionner le dossier principal de vos téléchargements de manga...{Colors.ENDC}")

    # Open a folder selection dialog
    root_download_folder_str = filedialog.askdirectory(
        title="Sélectionnez le dossier principal de vos téléchargements de manga"
    )

    if not root_download_folder_str:
        print(f"{Colors.WARNING}⚠️ Aucune sélection de dossier. Annulation.{Colors.ENDC}")
        return

    root_download_folder = Path(root_download_folder_str)

    if not root_download_folder.exists():
        print(f"{Colors.FAIL}❌ Le dossier sélectionné '{root_download_folder}' n'existe pas. Veuillez réessayer.{Colors.ENDC}")
        return

    print(f"{Colors.OKCYAN}Dossier sélectionné: {root_download_folder.absolute()}{Colors.ENDC}")

    processed_manga_count = 0
    created_cbr_count = 0

    for manga_series_folder in root_download_folder.iterdir():
        if not manga_series_folder.is_dir():
            continue

        print(f"\n{Colors.LIGHTBLUE}--- Traitement de la série: {manga_series_folder.name} ---{Colors.ENDC}")

        cbr_output_folder = manga_series_folder / 'CBR'
        if cbr_output_folder.exists():
            print(f"{Colors.OKBLUE}➡️ Dossier CBR existant pour '{manga_series_folder.name}'. Vérification des chapitres...{Colors.ENDC}")
        else:
            cbr_output_folder.mkdir(exist_ok=True)
            print(f"{Colors.OKBLUE}➕ Création du dossier CBR: {cbr_output_folder.name}{Colors.ENDC}")

        # Get existing CBRs to avoid re-creation
        existing_cbrs = {f.name for f in cbr_output_folder.glob('*.cbr')}

        chapter_folders = []
        for item in manga_series_folder.iterdir():
            if item.is_dir() and item.name.lower() != 'cbr': # Exclude the CBR folder itself
                chapter_folders.append(item)
        
        if not chapter_folders:
            print(f"{Colors.WARNING}⚠️ Aucun dossier de chapitre trouvé dans '{manga_series_folder.name}'.{Colors.ENDC}")
            continue

        # Sort chapter folders numerically
        sorted_chapter_folders = sorted(chapter_folders, key=lambda x: extract_chapter_number(x.name))

        manga_cbr_created_this_run = 0

        for chapter_folder in sorted_chapter_folders:
            clean_chapter_name = sanitize_filename(chapter_folder.name)
            
            # Formulate the expected CBR filename
            chapter_num = extract_chapter_number(chapter_folder.name)
            
            # Extract actual chapter title more robustly
            cbr_base_name = chapter_folder.name
            # Remove common chapter prefixes for a cleaner name
            cbr_base_name = re.sub(r'^[Cc]hapitre\s*\d+\s*[-_]?\s*', '', cbr_base_name, flags=re.IGNORECASE).strip()
            cbr_base_name = re.sub(r'^[Cc]hapter\s*\d+\s*[-_]?\s*', '', cbr_base_name, flags=re.IGNORECASE).strip()
            # If after removal it's empty, use the full name
            if not cbr_base_name:
                cbr_base_name = chapter_folder.name

            # Construct the CBR filename including series name
            cbr_filename = f"{manga_series_folder.name} - Chapter_{chapter_num:03d} - {sanitize_filename(cbr_base_name)}.cbr"
            cbr_path = cbr_output_folder / cbr_filename

            if cbr_path.name in existing_cbrs:
                print(f"{Colors.OKCYAN}⏭️ CBR déjà existant pour '{chapter_folder.name}'. Skippé.{Colors.ENDC}")
                continue
            
            # Check if chapter folder contains images
            image_count = sum(1 for f in chapter_folder.iterdir() if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp'])
            if image_count == 0:
                print(f"{Colors.WARNING}⚠️ Le dossier '{chapter_folder.name}' ne contient aucune image. Skippé.{Colors.ENDC}")
                continue

            print(f"{Colors.OKBLUE}➡️ Création du CBR pour: {chapter_folder.name} ({image_count} images){Colors.ENDC}")
            if create_cbr_from_folder(chapter_folder, cbr_path):
                manga_cbr_created_this_run += 1
                created_cbr_count += 1
            time.sleep(0.1) # Small pause

        if manga_cbr_created_this_run > 0:
            processed_manga_count += 1
        else:
            print(f"{Colors.OKCYAN}ℹ️ Tous les CBRs existaient ou aucun n'a été créé pour '{manga_series_folder.name}'.{Colors.ENDC}")


    print(f"\n{Colors.HEADER}{Colors.BOLD}--- Traitement Terminé ! ---{Colors.ENDC}")
    print(f"{Colors.OKGREEN}✅ Séries de manga traitées: {processed_manga_count}{Colors.ENDC}")
    print(f"{Colors.OKGREEN}✅ Nouveaux fichiers CBR créés: {created_cbr_count}{Colors.ENDC}")
    print(f"{Colors.OKBLUE}Vérifiez le dossier '{root_download_folder.absolute()}' pour vos CBRs !{Colors.ENDC}")
    
    # Optional: show a final message box (uncomment if you want a GUI pop-up at the end)
    # messagebox.showinfo("Générateur de CBR", "Le processus de création des CBRs est terminé !")

if __name__ == "__main__":
    main()