import os
import re
import zipfile
import shutil
from pathlib import Path
import time
import sys # Pour sys.exit()

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
    """Nettoie le nom de fichier pour éviter les caractères problématiques"""
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = filename.replace(' ', '_')
    return filename

def extract_chapter_number(chapter_name):
    """Extrait le numéro de chapitre pour le tri, gérant divers formats."""
    # Prioriser 'Chapitre N'
    match_fr = re.search(r'[Cc]hapitre\s*(\d+)', chapter_name)
    if match_fr:
        return int(match_fr.group(1))
    
    # Essayer 'Chapter N'
    match_en = re.search(r'[Cc]hapter\s*(\d+)', chapter_name)
    if match_en:
        return int(match_en.group(1))

    # Essayer un préfixe numérique (ex: "001 - Titre")
    match_prefix = re.search(r'^(\d+)', chapter_name)
    if match_prefix:
        return int(match_prefix.group(1))

    return 0 # Par défaut si aucun numéro trouvé

def create_cbr_from_folder(folder_path, output_path):
    """Crée un fichier CBR (ZIP) à partir d'un dossier d'images"""
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Trie les fichiers par nom numérique (ex: page_001.jpg, page_002.jpg)
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
    # Définir le dossier racine comme le dossier où le script est exécuté
    script_dir = Path(__file__).resolve().parent
    root_download_folder = script_dir / 'manga_downloads' 

    print(f"{Colors.HEADER}{Colors.BOLD}\n--- Lancement du Générateur de CBR ---{Colors.ENDC}")
    print(f"{Colors.OKCYAN}Recherche du dossier 'manga_downloads' dans: {script_dir}{Colors.ENDC}")

    if not root_download_folder.exists():
        print(f"{Colors.FAIL}❌ Le sous-dossier '{root_download_folder.name}' n'a pas été trouvé dans le répertoire du script. Veuillez le créer et y placer vos séries de manga.{Colors.ENDC}")
        sys.exit(1) # Quitte le script avec un code d'erreur

    # Lister les dossiers de séries de manga
    manga_series_folders = []
    for item in root_download_folder.iterdir():
        if item.is_dir():
            manga_series_folders.append(item)
    
    if not manga_series_folders:
        print(f"{Colors.WARNING}⚠️ Aucun dossier de série de manga trouvé dans '{root_download_folder.name}'.{Colors.ENDC}")
        sys.exit(0) # Quitte le script

    print(f"\n{Colors.MAGENTA}{Colors.BOLD}Séries de manga trouvées : {Colors.ENDC}")
    for i, folder in enumerate(manga_series_folders):
        print(f"  {Colors.OKCYAN}{i + 1}. {folder.name}{Colors.ENDC}")
    
    print(f"\n{Colors.OKBLUE}Entrez le numéro de la série à traiter (ou 'q' pour quitter) : {Colors.ENDC}")
    
    selected_index = -1
    while True:
        choice = input(f"{Colors.BOLD}Votre choix : {Colors.ENDC}").strip().lower()
        if choice == 'q':
            print(f"{Colors.WARNING}Annulation du script.{Colors.ENDC}")
            sys.exit(0)
        
        try:
            selected_index = int(choice) - 1
            if 0 <= selected_index < len(manga_series_folders):
                break
            else:
                print(f"{Colors.FAIL}Numéro invalide. Veuillez entrer un numéro entre 1 et {len(manga_series_folders)}.{Colors.ENDC}")
        except ValueError:
            print(f"{Colors.FAIL}Entrée invalide. Veuillez entrer un numéro ou 'q'.{Colors.ENDC}")

    selected_manga_series_folder = manga_series_folders[selected_index]
    print(f"\n{Colors.OKGREEN}Vous avez sélectionné : {selected_manga_series_folder.name}{Colors.ENDC}")

    processed_manga_count = 0
    created_cbr_count = 0

    print(f"\n{Colors.LIGHTBLUE}--- Traitement de la série: {selected_manga_series_folder.name} ---{Colors.ENDC}")

    cbr_output_folder = selected_manga_series_folder / 'CBR'
    if cbr_output_folder.exists():
        print(f"{Colors.OKBLUE}➡️ Dossier CBR existant pour '{selected_manga_series_folder.name}'. Vérification des chapitres...{Colors.ENDC}")
    else:
        cbr_output_folder.mkdir(exist_ok=True)
        print(f"{Colors.OKBLUE}➕ Création du dossier CBR: {cbr_output_folder.name}{Colors.ENDC}")

    # Récupérer les CBRs existants pour éviter la recréation
    existing_cbrs = {f.name for f in cbr_output_folder.glob('*.cbr')}

    chapter_folders = []
    for item in selected_manga_series_folder.iterdir():
        if item.is_dir() and item.name.lower() != 'cbr': # Exclure le dossier CBR lui-même
            chapter_folders.append(item)
    
    if not chapter_folders:
        print(f"{Colors.WARNING}⚠️ Aucun dossier de chapitre trouvé dans '{selected_manga_series_folder.name}'.{Colors.ENDC}")
        print(f"\n{Colors.HEADER}{Colors.BOLD}--- Traitement Terminé ! ---{Colors.ENDC}")
        print(f"{Colors.OKGREEN}✅ Séries de manga traitées: {processed_manga_count}{Colors.ENDC}")
        print(f"{Colors.OKGREEN}✅ Nouveaux fichiers CBR créés: {created_cbr_count}{Colors.ENDC}")
        return

    # Trier les dossiers de chapitre numériquement
    sorted_chapter_folders = sorted(chapter_folders, key=lambda x: extract_chapter_number(x.name))

    manga_cbr_created_this_run = 0

    for chapter_folder in sorted_chapter_folders:
        clean_chapter_name = sanitize_filename(chapter_folder.name)
        
        # Formuler le nom de fichier CBR attendu
        chapter_num = extract_chapter_number(chapter_folder.name)
        
        # Extraire le titre du chapitre de manière plus robuste
        cbr_base_name = chapter_folder.name
        # Supprimer les préfixes de chapitre courants pour un nom plus propre
        cbr_base_name = re.sub(r'^[Cc]hapitre\s*\d+\s*[-_]?\s*', '', cbr_base_name, flags=re.IGNORECASE).strip()
        cbr_base_name = re.sub(r'^[Cc]hapter\s*\d+\s*[-_]?\s*', '', cbr_base_name, flags=re.IGNORECASE).strip()
        # Si après suppression c'est vide, utiliser le nom complet
        if not cbr_base_name:
            cbr_base_name = chapter_folder.name

        # Construire le nom de fichier CBR incluant le nom de la série
        cbr_filename = f"{selected_manga_series_folder.name} - Chapter_{chapter_num:03d} - {sanitize_filename(cbr_base_name)}.cbr"
        cbr_path = cbr_output_folder / cbr_filename

        if cbr_path.name in existing_cbrs:
            print(f"{Colors.OKCYAN}⏭️ CBR déjà existant pour '{chapter_folder.name}'. Skippé.{Colors.ENDC}")
            continue
        
        # Vérifier si le dossier du chapitre contient des images
        image_count = sum(1 for f in chapter_folder.iterdir() if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp'])
        if image_count == 0:
            print(f"{Colors.WARNING}⚠️ Le dossier '{chapter_folder.name}' ne contient aucune image. Skippé.{Colors.ENDC}")
            continue

        print(f"{Colors.OKBLUE}➡️ Création du CBR pour: {chapter_folder.name} ({image_count} images){Colors.ENDC}")
        if create_cbr_from_folder(chapter_folder, cbr_path):
            manga_cbr_created_this_run += 1
            created_cbr_count += 1
        time.sleep(0.1) # Petite pause

    if manga_cbr_created_this_run > 0:
        processed_manga_count += 1
    else:
        print(f"{Colors.OKCYAN}ℹ️ Tous les CBRs existaient ou aucun n'a été créé pour '{selected_manga_series_folder.name}'.{Colors.ENDC}")


    print(f"\n{Colors.HEADER}{Colors.BOLD}--- Traitement Terminé ! ---{Colors.ENDC}")
    print(f"{Colors.OKGREEN}✅ Séries de manga traitées: {processed_manga_count}{Colors.ENDC}")
    print(f"{Colors.OKGREEN}✅ Nouveaux fichiers CBR créés: {created_cbr_count}{Colors.ENDC}")
    print(f"{Colors.OKBLUE}Vérifiez le dossier '{selected_manga_series_folder.absolute()}' pour vos CBRs !{Colors.ENDC}")

if __name__ == "__main__":
    main()