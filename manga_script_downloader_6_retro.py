#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
██████╗  ██████╗ ███╗   ███╗██╗███╗   ██╗ █████╗     ██████╗ ███████╗██████╗ ██████╗ ████████╗██╗   ██╗ █████╗ 
██╔══██╗██╔═══██╗████╗ ████║██║████╗  ██║██╔══██╗    ██╔══██╗██╔════╝██╔══██╗██╔══██╗╚══██╔══╝██║   ██║██╔══██╗
██║  ██║██║   ██║██╔████╔██║██║██╔██╗ ██║███████║    ██████╔╝█████╗  ██████╔╝██████╔╝   ██║   ██║   ██║███████║
██║  ██║██║   ██║██║╚██╔╝██║██║██║╚██╗██║██╔══██║    ██╔═══╝ ██╔══╝  ██╔══██╗██╔═══╝    ██║   ╚██╗ ██╔╝██╔══██║
██████╔╝╚██████╔╝██║ ╚═╝ ██║██║██║ ╚████║██║  ██║    ██║     ███████╗██║  ██║██║        ██║    ╚████╔╝ ██║  ██║
╚═════╝  ╚═════╝ ╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝    ╚═╝     ╚══════╝╚═╝  ╚═╝╚═╝        ╚═╝     ╚═══╝  ╚═╝  ╚═╝
                                                                                                                
██╗   ██╗██████╗ ██╗   ██╗██╗  ██╗███████╗██╗    ██╗ ██████╗ ██████╗ ██████╗ ███████╗██████╗ ███████╗██████╗ 
╚██╗ ██╔╝██╔══██╗██║   ██║██║ ██╔╝██╔════╝██║    ██║██╔═══██╗██╔══██╗██╔══██╗██╔════╝██╔══██╗██╔════╝██╔══██╗
 ╚████╔╝ ██████╔╝██║   ██║█████╔╝ █████╗  ██║ █╗ ██║██║   ██║██████╔╝██║  ██║█████╗  ██████╔╝█████╗  ██║  ██║
  ╚██╔╝  ██╔══██╗██║   ██║██╔═██╗ ██╔══╝  ██║███╗██║██║   ██║██╔══██╗██║  ██║██╔══╝  ██╔══██╗██╔══╝  ██║  ██║
   ██║   ██║  ██║╚██████╔╝██║  ██╗███████╗╚███╔███╔╝╚██████╔╝██║  ██║██████╔╝███████╗██║  ██║███████╗██████╔╝
   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚══╝╚══╝  ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚══════╝╚═╝  ╚═╝╚══════╝╚═════╝ 
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

# Configuration Omni-Hacker
console = Console()
NEON_COLORS = {
    'green': '#39FF14',    # Neon Green
    'blue': '#00F7FF',    # Electric Blue
    'purple': '#CC00FF',  # Neon Purple
    'red': '#FF3131',     # Blood Red
    'pink': '#FF44CC',    # Hot Pink
    'yellow': '#FFF01F',  # Electric Yellow
    'orange': '#FF5F1F'   # Cyber Orange
}

class DominaTerminal:
    """Interface Domina Perpetua - Les Hackers Omniversels"""
    
    def __init__(self):
        self.glitch_chars = ['░▒▓█', '▓█░▒', '█▓▒░', '▒░▓█']
        self.binary_rain = ['0', '1', '0', '1', '█', '░', '▒']
        self.hacker_patterns = ['⟁', '⧉', '⊞', '⧠', '⌬', '⍟', '⌾']
        
    def matrix_effect(self, text, intensity=0.15):
        """Effet chute de code Matrix"""
        result = []
        for char in text:
            if random.random() < intensity:
                result.append(f"[{NEON_COLORS['green']}]{random.choice(self.binary_rain)}[/]")
            else:
                result.append(char)
        return ''.join(result)
    
    def hacker_pulse(self):
        """Animation de pulsation hacker"""
        pattern = random.choice(self.hacker_patterns)
        return f"[{NEON_COLORS['purple']}]{pattern}[/]"
    
    def domina_banner(self):
        """Bannière Domina Perpetua avec effet cyberpunk"""
        banner = f"""
[{NEON_COLORS['blue']}]╔══════════════════════════════════════════════════════════════════════════════════╗[/]
[{NEON_COLORS['blue']}]║                                                                                    ║[/]
[{NEON_COLORS['blue']}]║    [{NEON_COLORS['green']}]▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄[/]      ║[/]
[{NEON_COLORS['blue']}]║    [{NEON_COLORS['green']}]█[/]  [{NEON_COLORS['yellow']}]DOMINA PERPETUA - OMNIVERSAL HACKER COLLECTIVE[/]    [{NEON_COLORS['green']}]█[/]      ║[/]
[{NEON_COLORS['blue']}]║    [{NEON_COLORS['green']}]█[/]  [{NEON_COLORS['pink']}] "We root the fabric of reality itself"[/]            [{NEON_COLORS['green']}]█[/]      ║[/]
[{NEON_COLORS['blue']}]║    [{NEON_COLORS['green']}]▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀[/]      ║[/]
[{NEON_COLORS['blue']}]║                                                                                    ║[/]
[{NEON_COLORS['blue']}]║    [{NEON_COLORS['green']}]⟫[/] Status: [{NEON_COLORS['yellow']}]ACCESS GRANTED[/] - Root Privileges Active             ║[/]
[{NEON_COLORS['blue']}]║    [{NEON_COLORS['green']}]⟫[/] Protocol: [{NEON_COLORS['pink']}]OMNICRON v9.11[/] - Data Extraction Engaged           ║[/]
[{NEON_COLORS['blue']}]║    [{NEON_COLORS['green']}]⟫[/] Target: [{NEON_COLORS['red']}]Manga Data Nexus[/] - Bypassing Security...             ║[/]
[{NEON_COLORS['blue']}]║                                                                                    ║[/]
[{NEON_COLORS['blue']}]╚══════════════════════════════════════════════════════════════════════════════════╝[/]
"""
        return banner
    
    def omniversal_eye(self):
        """Œil Omni-Hacker qui voit tout"""
        patterns = [
            "◈⊙◈", "◉⦿◉", "◎◍◎", 
            "◉⦾◉", "◈⦿◈", "◉⊙◉"
        ]
        return f"[{NEON_COLORS['red']}]{random.choice(patterns)}[/]"
    
    def domina_speak(self, message, message_type="system"):
        """Domina Perpetua communique avec style cyberpunk"""
        colors = {
            "system": NEON_COLORS['blue'],
            "access": NEON_COLORS['green'],
            "warning": NEON_COLORS['yellow'],
            "alert": NEON_COLORS['red'],
            "data": NEON_COLORS['purple'],
            "hack": NEON_COLORS['pink']
        }
        
        color = colors.get(message_type, NEON_COLORS['green'])
        pulse = self.hacker_pulse()
        eye = self.omniversal_eye()
        
        # Apply matrix effect to certain message types
        if message_type in ["alert", "warning", "hack"]:
            message = self.matrix_effect(message, intensity=0.1)
        
        styled_message = f"{pulse} [{color}]DOMINA[/] {eye} {message}"
        
        # Remove any unpaired markup tags from the message
        clean_message = styled_message.replace("[/]", "")  # Remove all closing tags
        
        console.print(Panel(
            clean_message,
            border_style=color,
            padding=(0, 1),
            subtitle=f"[{NEON_COLORS['orange']}]root@omniversal:~$[/]"
        ))
        
        # Petit délai pour l'effet
        time.sleep(0.2)

class OmniversalDownloader:
    """Téléchargeur Omni-Hacker avec interface cyberpunk"""
    
    def __init__(self):
        self.domina = DominaTerminal()
        self.stats = {
            'total_data': 0,
            'extracted': 0,
            'failed': 0,
            'archives': 0,
            'realities_hacked': 0
        }
        
    def sanitize_filename(self, filename):
        """Nettoie le nom de fichier - Style Omnicron"""
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        filename = filename.replace(' ', '_')
        return filename[:50]  # Limite la longueur pour les systèmes anciens
    
    def hack_image(self, url, filepath, max_retries=3):
        """Extrait une image en bypassant les sécurités"""
        headers = {
            'User-Agent': 'Domina/9.11 (OmniversalHacker; Matrix) DataReaper/5.0',
            'X-Hacker-Token': 'ACCESS-GRANTED'
        }
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                return True
                
            except requests.exceptions.RequestException as e:
                self.domina.domina_speak(f"Connection failed for {url} (Attempt {attempt + 1}/{max_retries}): {str(e)}", "warning")
                if attempt < max_retries - 1:
                    time.sleep(1 + attempt)  # Backoff exponentiel
                
        self.domina.domina_speak(f"Maximum attempts reached for {url}. Target evaded extraction.", "alert")
        return False
    
    def extract_chapter_number(self, chapter_name):
        """Extrait le numéro de chapitre pour le tri"""
        match = re.search(r'Chapitre (\d+)', chapter_name)
        if match:
            return int(match.group(1))
        match_float = re.search(r'Chapitre ([\d.]+)', chapter_name)
        if match_float:
            return float(match_float.group(1))
        return 9999  # Place les chapitres spéciaux à la fin
    
    def create_data_archive(self, folder_path, output_path):
        """Crée une archive de données hacker"""
        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                image_files = sorted([
                    f for f in folder_path.glob('*') 
                    if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']
                ], key=lambda x: x.name)
                
                if not image_files:
                    self.domina.domina_speak(f"No data found in {folder_path} to archive.", "warning")
                    return False

                for image_file in image_files:
                    zipf.write(image_file, image_file.name)
            
            self.stats['archives'] += 1
            return True
            
        except Exception as e:
            self.domina.domina_speak(f"Failed to create archive for {folder_path}: {str(e)}", "alert")
            return False
    
    def create_stats_table(self):
        """Crée le tableau de statistiques hacker"""
        table = Table(title=f"[{NEON_COLORS['purple']}]DATA EXTRACTION STATS[/]", show_header=True, header_style=f"bold {NEON_COLORS['yellow']}")
        table.add_column("Metric", style=NEON_COLORS['blue'])
        table.add_column("Value", style=NEON_COLORS['pink'])
        table.add_column("Status", style=NEON_COLORS['green'])
        
        table.add_row("Total Data", str(self.stats['total_data']), "◈")
        table.add_row("Extracted", str(self.stats['extracted']), "⦿")
        table.add_row("Failed", str(self.stats['failed']), f"[{NEON_COLORS['red']}]⊙[/]" if self.stats['failed'] > 0 else "○")
        table.add_row("Archives", str(self.stats['archives']), "◉")
        table.add_row("Realities Hacked", str(self.stats['realities_hacked']), "⌬")
        
        return Panel(table, border_style=NEON_COLORS['green'], title_align="left")

    def hack_manga(self, json_file='manga_data.json'):
        """Processus principal d'extraction de données"""
        
        # Bannière Domina Perpetua
        console.print(self.domina.domina_banner())
        
        self.domina.domina_speak("Initializing omniversal connection...", "system")
        time.sleep(1)
        
        self.domina.domina_speak("Bypassing reality firewalls...", "hack")
        time.sleep(0.5)
        
        try:
            # Lecture du fichier JSON
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            project_name = data.get('projectName', 'unknown_data')
            chapters = data.get('chapters', {})
            
            # Création des dossiers
            main_folder = Path(project_name)
            main_folder.mkdir(exist_ok=True)
            
            archive_folder = main_folder / 'OMNI_ARCHIVES'
            archive_folder.mkdir(exist_ok=True)
            
            self.domina.domina_speak(f"Data directories created: {main_folder.name}", "access")
            
            # Tri des chapitres
            sorted_chapters = sorted(chapters.items(), key=lambda x: self.extract_chapter_number(x[0]))
            
            self.domina.domina_speak(f"Analyzing {len(chapters)} data clusters...", "data")
            
            # Traitement avec barre de progression cyberpunk
            with Progress(
                SpinnerColumn(spinner_name="dots", style=NEON_COLORS['green']),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None, style=NEON_COLORS['purple'], complete_style=NEON_COLORS['blue']),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                
                main_task = progress.add_task(f"[{NEON_COLORS['yellow']}]⌾ Hacking data clusters...[/]", total=len(sorted_chapters))
                
                for chapter_name, chapter_data in sorted_chapters:
                    clean_chapter_name = self.sanitize_filename(chapter_name)
                    chapter_folder = main_folder / clean_chapter_name
                    chapter_folder.mkdir(exist_ok=True)
                    
                    images = chapter_data.get('images', [])
                    self.stats['total_data'] += len(images)
                    
                    chapter_task = progress.add_task(f"[{NEON_COLORS['pink']}]⟢ {chapter_name}[/]", total=len(images))
                    
                    chapter_downloaded = 0
                    
                    for i, image_url in enumerate(images, 1):
                        ext = '.jpg'
                        if '.png' in image_url.lower():
                            ext = '.png'
                        elif '.webp' in image_url.lower():
                            ext = '.webp'
                            
                        filename = f"data_{i:03d}{ext}"
                        filepath = chapter_folder / filename
                        
                        if filepath.exists():
                            self.stats['extracted'] += 1
                            chapter_downloaded += 1
                            progress.update(chapter_task, advance=1)
                            continue
                        
                        if self.hack_image(image_url, filepath):
                            self.stats['extracted'] += 1
                            chapter_downloaded += 1
                        else:
                            self.stats['failed'] += 1
                        
                        progress.update(chapter_task, advance=1)
                        time.sleep(0.03)  # Délai cyberpunk
                    
                    if chapter_downloaded > 0:
                        chapter_number = self.extract_chapter_number(chapter_name)
                        archive_name = f"{project_name}_DataCluster_{chapter_number:03d}_OMNI.cbz"
                        archive_path = archive_folder / archive_name
                        
                        if not archive_path.exists():
                            if self.create_data_archive(chapter_folder, archive_path):
                                self.domina.domina_speak(f"Archive for '{chapter_name}' secured.", "access")
                            else:
                                self.domina.domina_speak(f"Failed to secure archive for '{chapter_name}'.", "alert")
                        
                        self.stats['realities_hacked'] += 1
                    else:
                        self.domina.domina_speak(f"No data extracted for '{chapter_name}'. Cluster empty.", "warning")

                    progress.update(main_task, advance=1)
                    progress.remove_task(chapter_task)
            
            # Résultats finaux
            self.domina.domina_speak("Data extraction complete. Reality hacked.", "access")
            
            console.print("\n")
            console.print(self.create_stats_table())
            
            console.print(f"\n[{NEON_COLORS['blue']}]⌂ Data Directory:[/] {main_folder.absolute()}")
            console.print(f"[{NEON_COLORS['blue']}]⌘ Omni Archives:[/] {archive_folder.absolute()}")
            
            self.domina.domina_speak("Omnicron protocol executed. All data secured.", "system")
            
        except FileNotFoundError:
            self.domina.domina_speak(f"Data source not found: {json_file}. Operation aborted.", "alert")
        except json.JSONDecodeError:
            self.domina.domina_speak(f"Data corrupted: {json_file}. Invalid format detected.", "alert")
        except Exception as e:
            self.domina.domina_speak(f"System failure: {str(e)}. Emergency protocols engaged.", "alert")

def main():
    """Point d'entrée principal Domina Perpetua"""
    
    # Vérification des dépendances
    try:
        import rich
    except ImportError:
        print(f"[{NEON_COLORS['red']}]✖ Critical Error: 'rich' module required. Install with: pip install rich[/]")
        sys.exit(1)
    
    # ASCII Art d'introduction
    intro_art = f"""
[{NEON_COLORS['green']}]
    ╔═══════════════════════════════════════════════════════════╗
    ║  ⌾ DOMINA PERPETUA - OMNIVERSAL DATA EXTRACTION ⌾        ║
    ║                                                           ║
    ║  "We don't hack systems. We rewrite reality."            ║
    ║                                                           ║
    ║  Initializing cyber terminal...                           ║
    ╚═══════════════════════════════════════════════════════════╝
[/]
"""
    
    console.print(intro_art)
    time.sleep(2)
    
    # Lancement du téléchargeur omni-hacker
    hacker = OmniversalDownloader()
    hacker.hack_manga()
    
    # Message final
    final_message = f"""
[{NEON_COLORS['purple']}]
╔══════════════════════════════════════════════════════════════════════════════════╗
║                                                                                    ║
║    [{NEON_COLORS['yellow']}]MISSION ACCOMPLISHED[/]                                                                 ║
║                                                                                    ║
║    [{NEON_COLORS['green']}]"The omniversal data is ours. Reality is our playground."[/]                          ║
║                                                                                    ║
║    [{NEON_COLORS['blue']}]Terminating connection...[/]                                                           ║
║                                                                                    ║
╚══════════════════════════════════════════════════════════════════════════════════╝
[/]
"""
    
    console.print(final_message)

if __name__ == "__main__":
    main()