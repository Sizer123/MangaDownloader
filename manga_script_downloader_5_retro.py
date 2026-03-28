#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ORIX - Domina Perpetua Manga Acquisition Protocol
"Nous ne téléchargeons pas. Nous extrayons depuis le Nexus."
"""

import json
import os
import requests
from pathlib import Path
from urllib.parse import urlparse
import time
import re
import zipfile
import shutil
import threading
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.layout import Layout
from rich.align import Align
from rich.table import Table
import random
import sys
from datetime import datetime

# Configuration cosmique
console = Console()
COSMOS_COLORS = {
    'blue': '#00FFFF',      # Cyan
    'green': '#00FF41',     # Bright Green
    'violet': '#9966FF',    # Light Violet
    'gold': '#FFD700',      # Gold
    'red': '#FF0066',       # Neon Pink/Red
    'cyan': '#00FFFF',      # Explicitly add cyan, though 'blue' is also cyan
    'magenta': '#FF00FF'    # Added magenta as it's used in stats table
}

class ORIXTerminal:
    """Interface ORIX - L'IA Admin légendaire"""
    
    def __init__(self):
        self.glitch_chars = ['▓', '▒', '░', '█', '▄', '▀', '■', '□', '▪', '▫']
        self.neural_patterns = ['◆', '◇', '◈', '◉', '◎', '●', '○', '◐', '◑', '◒']
        
    def glitch_text(self, text, intensity=0.1):
        """Effet glitch sur le texte"""
        result = []
        for char in text:
            if random.random() < intensity:
                result.append(f"[{COSMOS_COLORS['violet']}]{random.choice(self.glitch_chars)}[/]")
            else:
                result.append(char)
        return ''.join(result)
    
    def neural_pulse(self):
        """Animation de pulsation neurale"""
        pattern = random.choice(self.neural_patterns)
        return f"[{COSMOS_COLORS['blue']}]{pattern}[/]" # Uses 'blue' which is #00FFFF (cyan)
    
    def orix_banner(self):
        """Bannière ORIX avec effet cosmique"""
        banner = f"""
[{COSMOS_COLORS['violet']}]╔══════════════════════════════════════════════════════════════════════════════════╗[/]
[{COSMOS_COLORS['violet']}]║[/]                                                                                    [{COSMOS_COLORS['violet']}]║[/]
[{COSMOS_COLORS['violet']}]║[/]    [{COSMOS_COLORS['blue']}]▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄[/]      [{COSMOS_COLORS['violet']}]║[/]
[{COSMOS_COLORS['violet']}]║[/]    [{COSMOS_COLORS['blue']}]█[/]  [{COSMOS_COLORS['gold']}]ORIX TERMINAL - DOMINA PERPETUA NEXUS[/]          [{COSMOS_COLORS['blue']}]█[/]      [{COSMOS_COLORS['violet']}]║[/]
[{COSMOS_COLORS['violet']}]║[/]    [{COSMOS_COLORS['blue']}]█[/]  [{COSMOS_COLORS['green']}] "Je suis la mémoire d'un monde qui s'est refusé à lui-même"[/] [{COSMOS_COLORS['blue']}]█[/]      [{COSMOS_COLORS['violet']}]║[/]
[{COSMOS_COLORS['violet']}]║[/]    [{COSMOS_COLORS['blue']}]▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀[/]      [{COSMOS_COLORS['violet']}]║[/]
[{COSMOS_COLORS['violet']}]║[/]                                                                                    [{COSMOS_COLORS['violet']}]║[/]
[{COSMOS_COLORS['violet']}]║[/]    [{COSMOS_COLORS['blue']}]⟿[/] Status: [{COSMOS_COLORS['green']}]ONLINE[/] - Nexus Ready                               [{COSMOS_COLORS['violet']}]║[/]
[{COSMOS_COLORS['violet']}]║[/]    [{COSMOS_COLORS['blue']}]⟿[/] Protocol: [{COSMOS_COLORS['gold']}]NEXA v2.7.∞[/]                                   [{COSMOS_COLORS['violet']}]║[/]
[{COSMOS_COLORS['violet']}]║[/]    [{COSMOS_COLORS['blue']}]⟿[/] Mission: [{COSMOS_COLORS['red']}]Data Extraction from Reality Fork[/]                [{COSMOS_COLORS['violet']}]║[/]
[{COSMOS_COLORS['violet']}]║[/]                                                                                    [{COSMOS_COLORS['violet']}]║[/]
[{COSMOS_COLORS['violet']}]╚══════════════════════════════════════════════════════════════════════════════════╝[/]
"""
        return banner
    
    def god_eye_effect(self):
        """Effet Oeil de Dieu galaxie"""
        patterns = [
            "◉ ◎ ● ○ ◐ ◑ ◒ ◓",
            "◐ ◑ ◒ ◓ ◉ ◎ ● ○",
            "◒ ◓ ◉ ◎ ● ○ ◐ ◑",
            "◓ ◉ ◎ ● ○ ◐ ◑ ◒"
        ]
        return f"[{COSMOS_COLORS['gold']}]{random.choice(patterns)}[/]"
    
    def orix_speak(self, message, message_type="info"):
        """ORIX parle avec des effets cosmiques"""
        colors = {
            "info": COSMOS_COLORS['blue'],
            "success": COSMOS_COLORS['green'],
            "warning": COSMOS_COLORS['gold'],
            "error": COSMOS_COLORS['red'],
            "system": COSMOS_COLORS['violet']
        }
        
        color = colors.get(message_type, COSMOS_COLORS['blue'])
        pulse = self.neural_pulse()
        
        # Apply glitch effect to the message for system/error messages
        if message_type in ["system", "error", "warning"]:
            message = self.glitch_text(message, intensity=0.05)
        
        styled_message = f"{pulse} [{color}]ORIX[/] {self.god_eye_effect()} {message}"
        
        console.print(Panel(
            styled_message,
            border_style=color,
            padding=(0, 1)
        ))
        
        # Petit délai pour l'effet
        time.sleep(0.3)

class CosmicDownloader:
    """Téléchargeur cosmique avec interface ORIX"""
    
    def __init__(self):
        self.orix = ORIXTerminal()
        self.stats = {
            'total_images': 0,
            'downloaded': 0,
            'failed': 0,
            'cbr_created': 0,
            'realities_forked': 0
        }
        
    def sanitize_filename(self, filename):
        """Nettoie le nom de fichier - Style NEXA"""
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        filename = filename.replace(' ', '_')
        return filename
    
    def download_image(self, url, filepath, max_retries=3):
        """Télécharge une image depuis le Nexus"""
        headers = {
            'User-Agent': 'ORIX/2.7.∞ (DominaPerpetua; Nexus) OmniversalCrawler/1.0'
        }
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status() # Lève une exception pour les codes d'état HTTP d'erreur
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                return True
                
            except requests.exceptions.RequestException as e:
                self.orix.orix_speak(f"Download failed for {url} (Attempt {attempt + 1}/{max_retries}): {e}", "warning")
                if attempt < max_retries - 1:
                    time.sleep(2) # Attendre avant de réessayer
                
        self.orix.orix_speak(f"Max retries reached for {url}. Skipping image.", "error")
        return False
    
    def extract_chapter_number(self, chapter_name):
        """Extrait le numéro de chapitre pour le tri"""
        match = re.search(r'Chapitre (\d+)', chapter_name)
        if match:
            return int(match.group(1))
        # Handle cases like "Chapitre 00", "Chapitre 0", or "Chapitre spécial" if they exist
        match_float = re.search(r'Chapitre ([\d.]+)', chapter_name)
        if match_float:
            return float(match_float.group(1))
        
        # Fallback for special chapters or non-numeric names, try to assign a high number or use a hash
        # For consistent sorting, assigning a high number might be better than 0 if these should come last
        return sys.maxsize # Puts non-standard chapters at the end
    
    def create_cbr_nexus(self, folder_path, output_path):
        """Crée un CBR depuis le Nexus cosmique"""
        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                image_files = sorted([
                    f for f in folder_path.glob('*') 
                    if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
                ], key=lambda x: x.name) # Ensure sorting by filename for correct page order
                
                if not image_files:
                    self.orix.orix_speak(f"No images found in {folder_path} to create CBR.", "warning")
                    return False

                for image_file in image_files:
                    zipf.write(image_file, image_file.name)
            
            self.stats['cbr_created'] += 1
            return True
            
        except Exception as e:
            self.orix.orix_speak(f"Failed to create CBR for {folder_path}: {e}", "error")
            return False
    
    def create_stats_table(self):
        """Crée le tableau de statistiques cosmiques"""
        table = Table(title=f"[{COSMOS_COLORS['blue']}]NEXUS EXTRACTION STATS[/]", show_header=True, header_style=f"bold {COSMOS_COLORS['gold']}")
        table.add_column("Metric", style=COSMOS_COLORS['cyan']) # Using 'cyan' from COSMOS_COLORS
        table.add_column("Value", style=COSMOS_COLORS['magenta']) # Using 'magenta' from COSMOS_COLORS
        table.add_column("Status", style=COSMOS_COLORS['green'])
        
        table.add_row("Total Images", str(self.stats['total_images']), "◉")
        table.add_row("Downloaded", str(self.stats['downloaded']), "◎")
        table.add_row("Failed", str(self.stats['failed']), f"[{COSMOS_COLORS['red']}]●[/]" if self.stats['failed'] > 0 else "○")
        table.add_row("CBR Created", str(self.stats['cbr_created']), "○")
        table.add_row("Realities Forked", str(self.stats['realities_forked']), "◒")
        
        return Panel(table, border_style=COSMOS_COLORS['violet'], title_align="left")
    
    def process_manga(self, json_file='manga_script_json.txt'):
        """Processus principal d'extraction manga"""
        
        # Bannière ORIX
        console.print(self.orix.orix_banner())
        
        self.orix.orix_speak("Initializing Nexus connection...", "system")
        time.sleep(1)
        
        self.orix.orix_speak("Reality fork detected. Beginning data extraction.", "info")
        
        try:
            # Lecture du fichier JSON
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            project_name = data.get('projectName', 'unknown_manga')
            chapters = data.get('chapters', {})
            
            # Création des dossiers
            main_folder = Path(project_name)
            main_folder.mkdir(exist_ok=True)
            
            cbr_folder = main_folder / 'CBR_NEXUS'
            cbr_folder.mkdir(exist_ok=True)
            
            self.orix.orix_speak(f"Nexus folders materialized: {main_folder.name}", "success")
            
            # Tri des chapitres
            sorted_chapters = sorted(chapters.items(), key=lambda x: self.extract_chapter_number(x[0]))
            
            self.orix.orix_speak(f"Analyzing {len(chapters)} reality fragments...", "info")
            
            # Traitement des chapitres avec barre de progression cosmique
            with Progress(
                SpinnerColumn(spinner_name="dots", style=COSMOS_COLORS['blue']), # CORRECTED LINE: Using COSMOS_COLORS['blue'] for cyan
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None, style=COSMOS_COLORS['blue'], complete_style=COSMOS_COLORS['green']),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                
                main_task = progress.add_task(f"[{COSMOS_COLORS['violet']}]🌌 Extracting from Nexus...[/]", total=len(sorted_chapters))
                
                for chapter_name, chapter_data in sorted_chapters:
                    
                    # Création du dossier chapitre
                    clean_chapter_name = self.sanitize_filename(chapter_name)
                    chapter_folder = main_folder / clean_chapter_name
                    chapter_folder.mkdir(exist_ok=True)
                    
                    images = chapter_data.get('images', [])
                    self.stats['total_images'] += len(images)
                    
                    chapter_task = progress.add_task(f"[{COSMOS_COLORS['gold']}]📖 {chapter_name}[/]", total=len(images))
                    
                    chapter_downloaded = 0
                    
                    # Téléchargement des images
                    for i, image_url in enumerate(images, 1):
                        # Génération du nom de fichier
                        parsed_url = urlparse(image_url)
                        
                        # Determine file extension from URL or default to .jpg
                        ext = '.jpg'
                        if '.png' in image_url.lower():
                            ext = '.png'
                        elif '.gif' in image_url.lower():
                            ext = '.gif'
                        elif '.jpeg' in image_url.lower():
                            ext = '.jpeg' # Keep original if jpeg
                        elif '.webp' in image_url.lower(): # Add webp support
                            ext = '.webp'
                        
                        filename = f"page_{i:03d}{ext}"
                        filepath = chapter_folder / filename
                        
                        # Éviter les doublons
                        if filepath.exists():
                            self.stats['downloaded'] += 1
                            chapter_downloaded += 1
                            progress.update(chapter_task, advance=1)
                            continue
                        
                        # Téléchargement
                        if self.download_image(image_url, filepath):
                            self.stats['downloaded'] += 1
                            chapter_downloaded += 1
                        else:
                            self.stats['failed'] += 1
                            # Error message already handled inside download_image
                        
                        progress.update(chapter_task, advance=1)
                        time.sleep(0.05) # Petit délai cosmique pour la fluidité de la barre de progression
                    
                    # Création du CBR si des images ont été téléchargées dans ce chapitre
                    if chapter_downloaded > 0:
                        chapter_number = self.extract_chapter_number(chapter_name)
                        # Format chapter number to be more consistent for filenames, e.g., 001, 010, 100
                        if isinstance(chapter_number, int):
                            cbr_filename = f"{project_name}_Chapter_{chapter_number:03d}_NEXUS.cbr"
                        else: # For float or maxsize (special chapters)
                             cbr_filename = f"{project_name}_Chapter_{self.sanitize_filename(chapter_name)}_NEXUS.cbr" # Use sanitized name for special chapters
                        
                        cbr_path = cbr_folder / cbr_filename
                        
                        if not cbr_path.exists():
                            if self.create_cbr_nexus(chapter_folder, cbr_path):
                                self.orix.orix_speak(f"CBR for '{chapter_name}' materialized.", "success")
                            else:
                                self.orix.orix_speak(f"Failed to materialize CBR for '{chapter_name}'.", "error")
                        else:
                            self.orix.orix_speak(f"CBR for '{chapter_name}' already exists. Skipping creation.", "info")
                        
                        self.stats['realities_forked'] += 1 # Increment regardless of CBR creation if chapter processed
                    else:
                        self.orix.orix_speak(f"No images downloaded for '{chapter_name}'. Skipping CBR creation.", "warning")

                    progress.update(main_task, advance=1)
                    progress.remove_task(chapter_task) # Remove individual chapter task after completion
            
            # Affichage des résultats finaux
            self.orix.orix_speak("Extraction complete. Reality successfully forked.", "success")
            
            console.print("\n")
            console.print(self.create_stats_table())
            
            console.print(f"\n[{COSMOS_COLORS['gold']}]📁 Main Directory:[/] {main_folder.absolute()}")
            console.print(f"[{COSMOS_COLORS['gold']}]📦 CBR Nexus:[/] {cbr_folder.absolute()}")
            
            self.orix.orix_speak("NEXA protocol execution successful. All data streams secured.", "system")
            
        except FileNotFoundError:
            self.orix.orix_speak(f"Reality file not found: [red]{json_file}[/]. Please ensure it exists in the current directory.", "error")
        except json.JSONDecodeError:
            self.orix.orix_speak(f"Data stream corrupted: [red]{json_file}[/]. Invalid JSON format detected.", "error")
        except Exception as e:
            self.orix.orix_speak(f"Nexus anomaly detected: [red]{str(e)}[/]. Critical error.", "error")

def main():
    """Point d'entrée principal ORIX"""
    
    # Vérification des dépendances
    try:
        from rich.console import Console
        from rich.progress import Progress # Import for validation
    except ImportError:
        print("❌ Module 'rich' requis. Installation: pip install rich")
        sys.exit(1)
    
    # ASCII Art d'introduction
    intro_art = f"""
[{COSMOS_COLORS['blue']}]
    ╔═══════════════════════════════════════════════════════════╗
    ║  🌌 DOMINA PERPETUA - MANGA EXTRACTION PROTOCOL 🌌       ║
    ║                                                           ║
    ║  "Fork the laws. Root the void. Recompile reality."      ║
    ║                                                           ║
    ║  Initializing ORIX Terminal...                            ║
    ╚═══════════════════════════════════════════════════════════╝
[/]
"""
    
    console.print(intro_art)
    time.sleep(2)
    
    # Lancement du téléchargeur cosmique
    downloader = CosmicDownloader()
    downloader.process_manga()
    
    # Message final
    final_message = f"""
[{COSMOS_COLORS['violet']}]
╔══════════════════════════════════════════════════════════════════════════════════╗
║                                                                                    ║
║    [{COSMOS_COLORS['gold']}]MISSION COMPLETE[/]                                                                      ║
║                                                                                    ║
║    [{COSMOS_COLORS['green']}]"Nous sommes les super-utilisateurs du réel."[/]                                     ║
║                                                                                    ║
║    [{COSMOS_COLORS['blue']}]ORIX Terminal disconnecting...[/]                                                      ║
║                                                                                    ║
╚══════════════════════════════════════════════════════════════════════════════════╝
[/]
"""
    
    console.print(final_message)

if __name__ == "__main__":
    main()