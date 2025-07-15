import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
import os
import re
from urllib.parse import urljoin
import zipfile # Pour créer les fichiers .cbr (qui sont des archives ZIP renommées)

# Liste des motifs de noms de fichiers d'images à exclure (publicités, etc.)
EXCLUDED_IMAGE_FILENAMES = ["free_ads.jpg", "ad.jpg", "ads.png"]

def get_html_content(url, retries=3, delay=2):
    """
    Récupère le contenu HTML d'une URL sans lancer de navigateur graphique.
    Utilise des en-têtes réalistes et tente plusieurs fois en cas d'échec.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
        # "Accept-Encoding": "gzip, deflate, br", # RETIRÉ COMME DEMANDÉ
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    
    for attempt in range(retries):
        try:
            print(f"  Tentative {attempt + 1}/{retries} de récupérer : {url}")
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"  ❌ Erreur lors de la récupération de {url} (Tentative {attempt + 1}) : {e}")
            if attempt < retries - 1:
                print(f"  Réessai dans {delay} secondes...")
                time.sleep(delay)
            else:
                print(f"  Toutes les {retries} tentatives ont échoué pour {url}.")
    return None

def clean_filename(filename):
    """Nettoie une chaîne pour en faire un nom de fichier ou de dossier valide."""
    cleaned = re.sub(r'[\\/:*?"<>|]', '', filename)
    cleaned = re.sub(r'\.$', '', cleaned)
    cleaned = re.sub(r'\s+', '_', cleaned).strip('_')
    return cleaned[:200]

def extract_manga_title(html_content):
    """Récupère le titre du manga depuis le HTML en utilisant le sélecteur 'h1.big-fat-titles'."""
    if not html_content:
        return "Titre_Manga_Inconnu"
    soup = BeautifulSoup(html_content, 'html.parser')
    title_element = soup.select_one("h1.big-fat-titles")
    if title_element:
        return title_element.get_text(strip=True)
    return "Titre_Manga_Inconnu"

def extract_chapter_links(html_content, base_url):
    """
    Extrait les liens de chapitres avec le sélecteur 'a.chplinks' du HTML
    et les convertit en URLs absolues.
    """
    chapters_found = []
    if not html_content:
        return chapters_found

    soup = BeautifulSoup(html_content, 'html.parser')
    
    elements = soup.select("a.chplinks")
    
    for element in elements:
        chapter_title = element.get_text(strip=True)
        chapter_relative_url = element.get('href')
        
        if chapter_title and chapter_relative_url:
            chapter_url = urljoin(base_url, chapter_relative_url)
            chapters_found.append({"title": chapter_title, "url": chapter_url, "images": []})
            
    chapters_found.reverse()
    
    return chapters_found

def extract_image_links(html_content):
    """
    Extrait les URL des images avec le sélecteur 'img.imgholder' du HTML.
    """
    images_url = []
    if not html_content:
        return images_url

    soup = BeautifulSoup(html_content, 'html.parser')
    
    image_elements = soup.select("img.imgholder")
    
    for element in image_elements:
        src = element.get('src')
        if src:
            filename = os.path.basename(src).lower()
            if filename in EXCLUDED_IMAGE_FILENAMES:
                continue
            images_url.append(src)
            
    return images_url

def download_image(image_url, download_path, image_index, total_images):
    """Télécharge une image à partir de son URL et l'enregistre."""
    try:
        response = requests.get(image_url, stream=True, timeout=30)
        response.raise_for_status()

        file_extension = os.path.splitext(os.path.basename(image_url))[1]
        if not file_extension or len(file_extension) > 5: 
            file_extension = ".jpg" 
        
        # Le nom de fichier est simplement numéroté pour l'ordre dans le CBR
        filename = f"{str(image_index).zfill(3)}{file_extension}" 
        file_path = os.path.join(download_path, filename)
        
        if os.path.exists(file_path):
            print(f"            ⏩ Fichier déjà existant, ignoré : {filename}")
            return file_path # Retourne le chemin si déjà existant
            
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"            ✅ Téléchargé : {filename} ({image_index}/{total_images})")
        return file_path
    except requests.exceptions.RequestException as e:
        print(f"            ❌ Erreur de téléchargement de {image_url}: {e}")
        return None
    except Exception as e:
        print(f"            ❌ Erreur inattendue lors du téléchargement de {image_url}: {e}")
        return None

def create_cbr_from_chapter_images(chapter_dir, chapter_name_cleaned):
    """Crée un fichier .cbr (archive ZIP) à partir des images d'un chapitre."""
    cbr_filename = f"{chapter_name_cleaned}.cbr"
    cbr_path = os.path.join(os.path.dirname(chapter_dir), cbr_filename) # Le CBR sera dans le dossier parent du chapitre

    image_files = sorted([os.path.join(chapter_dir, f) for f in os.listdir(chapter_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))])

    if not image_files:
        print(f"    ⚠️ Pas d'images trouvées dans {chapter_dir} pour créer le CBR.")
        return None

    try:
        with zipfile.ZipFile(cbr_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for image_file in image_files:
                # Ajoute l'image dans l'archive en utilisant son nom de fichier (pas le chemin complet)
                zf.write(image_file, os.path.basename(image_file))
        print(f"    📦 Fichier CBR créé : {cbr_path}")
        return cbr_path
    except Exception as e:
        print(f"    ❌ Erreur lors de la création du fichier CBR pour {chapter_name_cleaned} : {e}")
        return None

def save_to_json(data, filename):
    """Sauvegarde les données dans un fichier JSON."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Données sauvegardées dans: {filename}")
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde du fichier JSON: {e}")

def main():
    """Fonction principale pour scraper, organiser, télécharger et créer les fichiers CBR."""
    print("⚡ === DEMONIC SCANS FAST SCRAPER & CBR CREATOR === ⚡")
    print()

    manga_link = input("Veuillez coller l'URL complète de la page du manga (ex: [https://demonicscans.org/manga/The-Indomitable-Martial-King](https://demonicscans.org/manga/The-Indomitable-Martial-King)): ").strip()

    if not manga_link:
        print("❌ Aucune URL de manga fournie. Arrêt du script.")
        return

    if not manga_link.startswith("http://") and not manga_link.startswith("https://"):
        print("⚠️ L'URL de manga doit commencer par 'http://' ou 'https://'. Veuillez vérifier et réessayer.")
        return
        
    if "demonicscans.org" not in manga_link or "/manga/" not in manga_link:
        print("⚠️ L'URL ne semble pas être un lien de page de manga valide de Demonic Scans. Veuillez vérifier et réessayer.")
        return

    manga_data_output = {
        "manga_url": manga_link,
        "scraped_at": datetime.now().isoformat(),
        "manga_title": "N/A",
        "chapters": []
    }
    
    try:
        print(f"🚀 Récupération du HTML de la page manga: {manga_link}")
        manga_html = get_html_content(manga_link)

        if manga_html:
            manga_title_raw = extract_manga_title(manga_html)
            manga_data_output["manga_title"] = manga_title_raw
            manga_name = clean_filename(manga_title_raw)
            if not manga_name or manga_name == "Titre_Manga_Inconnu":
                manga_name = "Manga_Telecharge_" + datetime.now().strftime("%Y%m%d_%H%M%S")
            
            manga_dir = os.path.join(os.getcwd(), manga_name)
            os.makedirs(manga_dir, exist_ok=True)
            print(f"\n📂 Dossier du manga créé : {manga_dir}")
            print(f"Titre du manga: {manga_title_raw}")

            chapters = extract_chapter_links(manga_html, manga_link)
            
            if chapters:
                manga_data_output["chapters"] = chapters 
                
                print("\n📚 === DÉBUT DU SCRAPING, TÉLÉCHARGEMENT ET CRÉATION DE CBR === 📚")
                
                for i, chapter in enumerate(manga_data_output["chapters"]):
                    print(f"\n[{i+1}/{len(manga_data_output['chapters'])}] Traitement du chapitre: {chapter['title']}")
                    
                    chapter_name_cleaned = clean_filename(chapter['title'])
                    chapter_folder_name = f"{str(i+1).zfill(len(str(len(chapters))))}_{chapter_name_cleaned}"
                    chapter_dir = os.path.join(manga_dir, chapter_folder_name)
                    os.makedirs(chapter_dir, exist_ok=True)
                    print(f"    📂 Dossier du chapitre créé : {chapter_dir}")

                    chapter_html = get_html_content(chapter['url'])
                    if chapter_html:
                        chapter_images = extract_image_links(chapter_html)
                        chapter['images'] = chapter_images
                        
                        if chapter_images:
                            print(f"    ⬇️ Début du téléchargement de {len(chapter_images)} images pour ce chapitre...")
                            downloaded_image_paths = []
                            for img_idx, img_url in enumerate(chapter_images):
                                img_path = download_image(img_url, chapter_dir, img_idx + 1, len(chapter_images))
                                if img_path:
                                    downloaded_image_paths.append(img_path)
                                time.sleep(0.05)
                            
                            if downloaded_image_paths:
                                # Créer le fichier CBR après le téléchargement des images du chapitre
                                create_cbr_from_chapter_images(chapter_dir, chapter_folder_name)
                            else:
                                print(f"    ⚠️ Aucune image téléchargée pour le chapitre {chapter['title']}, pas de CBR créé.")
                                
                        else:
                            print("    ⚠️ Aucune image à télécharger pour ce chapitre avec 'img.imgholder'.")
                    else:
                        print("    ❌ Impossible de récupérer le HTML du chapitre. Passage au suivant.")

                    time.sleep(0.5)

                print("\n🎉 === SCRAPING ET CRÉATION DE CBR TERMINÉS === 🎉")
                json_filename = f"{manga_name}_data.json"
                save_to_json(manga_data_output, json_filename)
                
                print(f"\n🚀 Mission accomplie! Manga et chapitres convertis en CBR, données enregistrées.")
            else:
                print("😢 Aucun chapitre n'a pu être récupéré avec 'a.chplinks' de cette page de manga. Aucun téléchargement ni CBR.")

        else:
            print("😢 Impossible de récupérer le HTML de la page du manga.")

    except Exception as e:
        print(f"💥 Une erreur inattendue est survenue: {e}")
        
if __name__ == "__main__":
    main()