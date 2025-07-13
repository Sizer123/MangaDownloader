import json
import os
import requests
from pathlib import Path
from urllib.parse import urlparse
import time
import re
import zipfile
import shutil

def sanitize_filename(filename):
    """Nettoie le nom de fichier pour éviter les caractères problématiques"""
    # Supprime les caractères spéciaux et remplace les espaces par des underscores
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = filename.replace(' ', '_')
    return filename

def download_image(url, filepath, max_retries=3):
    """Télécharge une image avec gestion des erreurs et retry"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            print(f"✓ Téléchargé: {filepath}")
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"✗ Erreur lors du téléchargement (tentative {attempt + 1}/{max_retries}): {url}")
            print(f"  Erreur: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Pause avant retry
            
    return False

def extract_chapter_number(chapter_name):
    """Extrait le numéro de chapitre pour le tri"""
    match = re.search(r'Chapitre (\d+)', chapter_name)
    return int(match.group(1)) if match else 0

def create_cbr_from_folder(folder_path, output_path):
    """Crée un fichier CBR (ZIP) à partir d'un dossier d'images"""
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Trie les fichiers par nom pour maintenir l'ordre
            image_files = sorted([f for f in folder_path.glob('*') if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']])
            
            for image_file in image_files:
                # Ajoute le fichier au zip avec juste son nom (pas le chemin complet)
                zipf.write(image_file, image_file.name)
        
        print(f"📦 CBR créé: {output_path}")
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors de la création du CBR: {e}")
        return False

def main():
    # Chemin vers le fichier JSON
    json_file = 'manga_script_json.txt'  # Remplacez par le chemin de votre fichier
    
    try:
        # Lecture du fichier JSON
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        project_name = data.get('projectName', 'manga')
        chapters = data.get('chapters', {})
        
        # Création du dossier principal
        main_folder = Path(project_name)
        main_folder.mkdir(exist_ok=True)
        
        # Création du dossier CBR
        cbr_folder = main_folder / 'CBR'
        cbr_folder.mkdir(exist_ok=True)
        
        print(f"📁 Dossier principal créé: {main_folder}")
        print(f"📁 Dossier CBR créé: {cbr_folder}")
        print(f"📊 Nombre de chapitres à traiter: {len(chapters)}")
        
        # Tri des chapitres par numéro
        sorted_chapters = sorted(chapters.items(), key=lambda x: extract_chapter_number(x[0]))
        
        total_images = 0
        downloaded_images = 0
        cbr_created = 0
        
        for chapter_name, chapter_data in sorted_chapters:
            print(f"\n🔄 Traitement du chapitre: {chapter_name}")
            
            # Nettoyage du nom de chapitre pour le dossier
            clean_chapter_name = sanitize_filename(chapter_name)
            chapter_folder = main_folder / clean_chapter_name
            chapter_folder.mkdir(exist_ok=True)
            
            images = chapter_data.get('images', [])
            total_images += len(images)
            
            print(f"📂 Dossier chapitre créé: {chapter_folder}")
            print(f"🖼️  Nombre d'images à télécharger: {len(images)}")
            
            chapter_downloaded = 0
            
            # Téléchargement des images
            for i, image_url in enumerate(images, 1):
                # Extraction de l'extension du fichier
                parsed_url = urlparse(image_url)
                path_parts = parsed_url.path.split('/')
                filename = path_parts[-1] if path_parts else f"image_{i}"
                
                # Si pas d'extension, on utilise l'extension depuis l'URL ou par défaut
                if '.' not in filename:
                    # Cherche l'extension dans les paramètres de l'URL
                    if image_url.lower().find('.jpg') != -1 or image_url.lower().find('.jpeg') != -1:
                        filename = f"page_{i:03d}.jpg"
                    elif image_url.lower().find('.png') != -1:
                        filename = f"page_{i:03d}.png"
                    else:
                        filename = f"page_{i:03d}.jpg"  # Par défaut
                else:
                    # Renomme avec un numéro de page pour garder l'ordre
                    name, ext = filename.rsplit('.', 1)
                    filename = f"page_{i:03d}.{ext}"
                
                filepath = chapter_folder / filename
                
                # Évite de télécharger si le fichier existe déjà
                if filepath.exists():
                    print(f"⏭️  Fichier déjà existant: {filepath}")
                    downloaded_images += 1
                    chapter_downloaded += 1
                    continue
                
                if download_image(image_url, filepath):
                    downloaded_images += 1
                    chapter_downloaded += 1
                
                # Pause entre les téléchargements pour éviter la surcharge
                time.sleep(0.5)
            
            # Création du CBR pour ce chapitre si des images ont été téléchargées
            if chapter_downloaded > 0:
                # Nom du fichier CBR
                chapter_number = extract_chapter_number(chapter_name)
                cbr_filename = f"Chapter_{chapter_number:03d} - {sanitize_filename(chapter_name.split(' - ')[0])}.cbr"
                cbr_path = cbr_folder / cbr_filename
                
                # Vérifie si le CBR existe déjà
                if cbr_path.exists():
                    print(f"📦 CBR déjà existant: {cbr_path}")
                    cbr_created += 1
                else:
                    if create_cbr_from_folder(chapter_folder, cbr_path):
                        cbr_created += 1
                
                # Option: supprimer le dossier d'images après création du CBR
                # (décommentez les lignes suivantes si vous voulez garder seulement les CBR)
                # print(f"🗑️  Suppression du dossier temporaire: {chapter_folder}")
                # shutil.rmtree(chapter_folder)
        
        # Statistiques finales
        print(f"\n📈 RÉSUMÉ:")
        print(f"📊 Total des images: {total_images}")
        print(f"✅ Images téléchargées: {downloaded_images}")
        print(f"❌ Images échouées: {total_images - downloaded_images}")
        print(f"📦 Fichiers CBR créés: {cbr_created}")
        print(f"📁 Dossier de destination: {main_folder.absolute()}")
        print(f"📁 Dossier CBR: {cbr_folder.absolute()}")
        
    except FileNotFoundError:
        print(f"❌ Fichier JSON non trouvé: {json_file}")
    except json.JSONDecodeError:
        print(f"❌ Erreur de format JSON dans le fichier: {json_file}")
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")

if __name__ == "__main__":
    main()