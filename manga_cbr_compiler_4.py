import os
import re
import zipfile
import shutil
from pathlib import Path
import time
import sys

# Import curses if available, otherwise fall back to basic input
CURSES_AVAILABLE = False # Initialize globally
try:
    import curses
    CURSES_AVAILABLE = True # Set to True if import succeeds
except ImportError:
    print("Avertissement: Le module 'curses' n'est pas disponible. La sélection interactive sera basique (numérique).")
    print("Pour une expérience complète (Matrix/flèches), installez 'curses' (Linux/macOS) ou 'windows-curses' (Windows).")
    time.sleep(2) # Give user time to read warning

# --- ANSI Color Codes (Fallback for non-curses output) ---
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
    # Matrix-like colors
    MATRIX_GREEN = '\033[32m' # Bright green for text
    MATRIX_DARK_GREEN = '\033[30;42m' # Dark background, green text (for highlights)
    MATRIX_BLUE_HIGHLIGHT = '\033[44m\033[97m' # Blue background, white text
    RESET_COLOR = '\033[0m'

# --- Helper Functions ---

def sanitize_filename(filename):
    """Nettoie le nom de fichier pour éviter les caractères problématiques"""
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = filename.replace(' ', '_')
    return filename

def extract_chapter_number(chapter_name):
    """Extrait le numéro de chapitre pour le tri, gérant divers formats."""
    match_fr = re.search(r'[Cc]hapitre\s*(\d+)', chapter_name)
    if match_fr: return int(match_fr.group(1))
    match_en = re.search(r'[Cc]hapter\s*(\d+)', chapter_name)
    if match_en: return int(match_en.group(1))
    match_prefix = re.search(r'^(\d+)', chapter_name)
    if match_prefix: return int(match_prefix.group(1))
    return 0

def create_cbr_from_folder(folder_path, output_path):
    """Crée un fichier CBR (ZIP) à partir d'un dossier d'images."""
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            image_files = sorted(
                [f for f in folder_path.iterdir() if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']],
                key=lambda x: int(re.search(r'(\d+)', x.stem).group(1)) if re.search(r'(\d+)', x.stem) else 0
            )
            for image_file in image_files:
                zipf.write(image_file, image_file.name)
        sys.stdout.write(f"{Colors.OKGREEN}📦 CBR créé: {output_path}{Colors.ENDC}\n")
        sys.stdout.flush()
        return True
    except Exception as e:
        sys.stdout.write(f"{Colors.FAIL}❌ Erreur lors de la création du CBR pour {folder_path.name}: {e}{Colors.ENDC}\n")
        sys.stdout.flush()
        return False

# --- Curses UI Functions ---
def curses_menu(stdscr, items, title):
    curses.curs_set(0) # Hide cursor
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    current_row_idx = 0

    # Initialize color pairs
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK) # Matrix Green text
    curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_GREEN) # Highlight: Green background, black text

    # Calculate menu window size based on content
    menu_h = min(len(items) + 4, h - 2) # Height: Border + title + items, limited by screen height
    menu_w = min(max(len(item) for item in items) + 6, w - 2) # Width: Max item length + padding, limited by screen width
    
    # Center the menu window
    start_y = max(0, (h - menu_h) // 2)
    start_x = max(0, (w - menu_w) // 2)

    menu_win = curses.newwin(menu_h, menu_w, start_y, start_x)
    menu_win.keypad(True) # Crucial: Enable keypad mode immediately after window creation
    menu_win.nodelay(True) # Make getch() non-blocking, so we can refresh without waiting for input
    menu_win.refresh() # Initial refresh of the window

    def print_menu(highlight_idx):
        menu_win.clear()
        menu_win.border(0)
        # Ensure title fits
        display_title = f" {title} "
        if len(display_title) > menu_win.getmaxyx()[1] - 4:
            display_title = display_title[:menu_win.getmaxyx()[1] - 7] + "..." # Truncate if too long
        menu_win.addstr(0, 2, display_title, curses.A_BOLD | curses.color_pair(1)) # Title with color

        x = 2
        y = 2
        # Ensure items fit
        max_item_width = menu_win.getmaxyx()[1] - 5 # Border and padding
        for idx, item in enumerate(items):
            display_item = item
            if len(display_item) > max_item_width:
                display_item = display_item[:max_item_width - 3] + "..."
            
            if idx == highlight_idx:
                menu_win.addstr(y, x, f"> {display_item}", curses.color_pair(2)) # Highlighted item
            else:
                menu_win.addstr(y, x, f"  {display_item}", curses.color_pair(1)) # Normal item
            y += 1
        menu_win.refresh()

    print_menu(current_row_idx)

    while True:
        key = menu_win.getch() # Ensure getch() is called on the specific window

        if key != -1: # Only process if a key was pressed
            if key == curses.KEY_UP:
                current_row_idx = max(0, current_row_idx - 1)
            elif key == curses.KEY_DOWN:
                current_row_idx = min(len(items) - 1, current_row_idx + 1)
            elif key == curses.KEY_ENTER or key in [10, 13]: # Enter key
                return current_row_idx
            elif key == ord('q'): # 'q' to quit
                return -1 # Indicate quit
            
            print_menu(current_row_idx) # Redraw only when necessary
        
        # A tiny sleep to prevent busy-waiting if nodelay is on
        time.sleep(0.01)


# --- Main Logic ---

def main_script_logic(selected_manga_series_folder=None):
    global CURSES_AVAILABLE 

    script_dir = Path(__file__).resolve().parent
    root_download_folder = script_dir / 'manga_downloads' 

    sys.stdout.write(f"{Colors.HEADER}{Colors.BOLD}\n--- Lancement du Générateur de CBR ---{Colors.ENDC}\n")
    sys.stdout.write(f"{Colors.OKCYAN}Recherche du dossier 'manga_downloads' dans: {script_dir}{Colors.ENDC}\n")
    sys.stdout.flush()

    if not root_download_folder.exists():
        sys.stdout.write(f"{Colors.FAIL}❌ Le sous-dossier '{root_download_folder.name}' n'a pas été trouvé dans le répertoire du script. Veuillez le créer et y placer vos séries de manga.{Colors.ENDC}\n")
        sys.stdout.flush()
        sys.exit(1)

    if selected_manga_series_folder is None:
        manga_series_folders = []
        for item in root_download_folder.iterdir():
            if item.is_dir():
                manga_series_folders.append(item)
        
        if not manga_series_folders:
            sys.stdout.write(f"{Colors.WARNING}⚠️ Aucun dossier de série de manga trouvé dans '{root_download_folder.name}'.{Colors.ENDC}\n")
            sys.stdout.flush()
            sys.exit(0)

        selected_index = -1
        if CURSES_AVAILABLE:
            try:
                selected_index = curses.wrapper(curses_menu, [f.name for f in manga_series_folders], "SÉLECTIONNEZ UNE SÉRIE MANGA (Flèches Haut/Bas, Entrée, 'q' pour quitter)")
            except Exception as e: 
                sys.stdout.write(f"{Colors.FAIL}Erreur lors de l'exécution de l'interface Curses: {e}. Reversion à la sélection numérique.\n{Colors.ENDC}")
                sys.stdout.flush()
                CURSES_AVAILABLE = False 

        if not CURSES_AVAILABLE or selected_index == -1: 
            if CURSES_AVAILABLE and sys.stdin.isatty(): 
                sys.stdout.write(f"{Colors.RESET_COLOR}\n" * 5) 
                sys.stdout.flush()
                
            sys.stdout.write(f"\n{Colors.MAGENTA}{Colors.BOLD}Séries de manga trouvées : {Colors.ENDC}\n")
            for i, folder in enumerate(manga_series_folders):
                sys.stdout.write(f"  {Colors.OKCYAN}{i + 1}. {folder.name}{Colors.ENDC}\n")
            sys.stdout.write(f"\n{Colors.OKBLUE}Entrez le numéro de la série à traiter (ou 'q' pour quitter) : {Colors.ENDC}\n")
            sys.stdout.flush()

            while True:
                choice = input(f"{Colors.BOLD}Votre choix : {Colors.ENDC}").strip().lower()
                if choice == 'q':
                    sys.stdout.write(f"{Colors.WARNING}Annulation du script.{Colors.ENDC}\n")
                    sys.stdout.flush()
                    sys.exit(0)
                
                try:
                    selected_index = int(choice) - 1
                    if 0 <= selected_index < len(manga_series_folders):
                        break
                    else:
                        sys.stdout.write(f"{Colors.FAIL}Numéro invalide. Veuillez entrer un numéro entre 1 et {len(manga_series_folders)}.{Colors.ENDC}\n")
                        sys.stdout.flush()
                except ValueError:
                    sys.stdout.write(f"{Colors.FAIL}Entrée invalide. Veuillez entrer un numéro ou 'q'.{Colors.ENDC}\n")
                    sys.stdout.flush()
        
        selected_manga_series_folder = manga_series_folders[selected_index]
        sys.stdout.write(f"\n{Colors.OKGREEN}Vous avez sélectionné : {selected_manga_series_folder.name}{Colors.ENDC}\n")
        sys.stdout.flush()

    processed_manga_count = 0
    created_cbr_count = 0

    sys.stdout.write(f"\n{Colors.LIGHTBLUE}--- Traitement de la série: {selected_manga_series_folder.name} ---{Colors.ENDC}\n")
    sys.stdout.flush()

    cbr_output_folder = selected_manga_series_folder / 'CBR'
    if cbr_output_folder.exists():
        sys.stdout.write(f"{Colors.OKBLUE}➡️ Dossier CBR existant pour '{selected_manga_series_folder.name}'. Vérification des chapitres...{Colors.ENDC}\n")
    else:
        cbr_output_folder.mkdir(exist_ok=True)
        sys.stdout.write(f"{Colors.OKBLUE}➕ Création du dossier CBR: {cbr_output_folder.name}{Colors.ENDC}\n")
    sys.stdout.flush()

    existing_cbrs = {f.name for f in cbr_output_folder.glob('*.cbr')}

    chapter_folders = []
    for item in selected_manga_series_folder.iterdir():
        if item.is_dir() and item.name.lower() != 'cbr':
            chapter_folders.append(item)
    
    if not chapter_folders:
        sys.stdout.write(f"{Colors.WARNING}⚠️ Aucun dossier de chapitre trouvé dans '{selected_manga_series_folder.name}'.{Colors.ENDC}\n")
        sys.stdout.flush()
        print_summary(processed_manga_count, created_cbr_count, selected_manga_series_folder)
        return

    sorted_chapter_folders = sorted(chapter_folders, key=lambda x: extract_chapter_number(x.name))

    manga_cbr_created_this_run = 0

    for chapter_folder in sorted_chapter_folders:
        clean_chapter_name = sanitize_filename(chapter_folder.name)
        chapter_num = extract_chapter_number(chapter_folder.name)
        
        cbr_base_name = chapter_folder.name
        cbr_base_name = re.sub(r'^[Cc]hapitre\s*\d+\s*[-_]?\s*', '', cbr_base_name, flags=re.IGNORECASE).strip()
        cbr_base_name = re.sub(r'^[Cc]hapter\s*\d+\s*[-_]?\s*', '', cbr_base_name, flags=re.IGNORECASE).strip()
        if not cbr_base_name:
            cbr_base_name = chapter_folder.name

        cbr_filename = f"{selected_manga_series_folder.name} - Chapter_{chapter_num:03d} - {sanitize_filename(cbr_base_name)}.cbr"
        cbr_path = cbr_output_folder / cbr_filename

        if cbr_path.name in existing_cbrs:
            sys.stdout.write(f"{Colors.OKCYAN}⏭️ CBR déjà existant pour '{chapter_folder.name}'. Skippé.{Colors.ENDC}\n")
            sys.stdout.flush()
            continue
        
        image_count = sum(1 for f in chapter_folder.iterdir() if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp'])
        if image_count == 0:
            sys.stdout.write(f"{Colors.WARNING}⚠️ Le dossier '{chapter_folder.name}' ne contient aucune image. Skippé.{Colors.ENDC}\n")
            sys.stdout.flush()
            continue

        sys.stdout.write(f"{Colors.OKBLUE}➡️ Création du CBR pour: {chapter_folder.name} ({image_count} images){Colors.ENDC}\n")
        sys.stdout.flush()
        if create_cbr_from_folder(chapter_folder, cbr_path):
            manga_cbr_created_this_run += 1
            created_cbr_count += 1
        time.sleep(0.1)

    if manga_cbr_created_this_run > 0:
        processed_manga_count += 1
    else:
        sys.stdout.write(f"{Colors.OKCYAN}ℹ️ Tous les CBRs existaient ou aucun n'a été créé pour '{selected_manga_series_folder.name}'.{Colors.ENDC}\n")
        sys.stdout.flush()

    print_summary(processed_manga_count, created_cbr_count, selected_manga_series_folder)


def print_summary(processed_manga, created_cbr, folder_path):
    sys.stdout.write(f"\n{Colors.HEADER}{Colors.BOLD}--- Traitement Terminé ! ---{Colors.ENDC}\n")
    sys.stdout.write(f"{Colors.OKGREEN}✅ Séries de manga traitées: {processed_manga}{Colors.ENDC}\n")
    sys.stdout.write(f"{Colors.OKGREEN}✅ Nouveaux fichiers CBR créés: {created_cbr}{Colors.ENDC}\n")
    sys.stdout.write(f"{Colors.OKBLUE}Vérifiez le dossier '{folder_path.absolute()}' pour vos CBRs !{Colors.ENDC}\n")
    sys.stdout.flush()


if __name__ == "__main__":
    if CURSES_AVAILABLE:
        script_dir = Path(__file__).resolve().parent
        root_download_folder = script_dir / 'manga_downloads' 

        if not root_download_folder.exists():
            sys.stdout.write(f"{Colors.FAIL}❌ Le sous-dossier '{root_download_folder.name}' n'a pas été trouvé dans le répertoire du script. Veuillez le créer et y placer vos séries de manga.{Colors.ENDC}\n")
            sys.stdout.flush()
            sys.exit(1)

        manga_series_folders = []
        for item in root_download_folder.iterdir():
            if item.is_dir():
                manga_series_folders.append(item)
        
        if not manga_series_folders:
            sys.stdout.write(f"{Colors.WARNING}⚠️ Aucun dossier de série de manga trouvé dans '{root_download_folder.name}'.{Colors.ENDC}\n")
            sys.stdout.flush()
            sys.exit(0)

        selected_index = -1
        try:
            selected_index = curses.wrapper(curses_menu, [f.name for f in manga_series_folders], "SÉLECTIONNEZ UNE SÉRIE MANGA (Flèches Haut/Bas, Entrée, 'q' pour quitter)")
        except Exception as e:
            sys.stdout.write(f"{Colors.FAIL}Erreur lors de l'exécution de l'interface Curses: {e}. Reversion à la sélection numérique.\n{Colors.ENDC}")
            sys.stdout.flush()
            CURSES_AVAILABLE = False # Force fallback if curses fails here

        if CURSES_AVAILABLE and selected_index != -1: 
            selected_folder = manga_series_folders[selected_index]
            main_script_logic(selected_folder)
        elif CURSES_AVAILABLE and selected_index == -1: 
            sys.stdout.write(f"{Colors.WARNING}Annulation du script.{Colors.ENDC}\n")
            sys.stdout.flush()
            sys.exit(0)
        else: 
            main_script_logic()
    else:
        main_script_logic()