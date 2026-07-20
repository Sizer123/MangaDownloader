import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
import os
import re
from urllib.parse import urljoin
import zipfile
import shutil

# Liste des motifs de noms de fichiers d'images à exclure (publicités, etc.)
EXCLUDED_IMAGE_FILENAMES = ["free_ads.jpg", "ad.jpg", "ads.png", "publicite.jpg", "pub.png"]

def get_html_content(url, retries=3, delay=2):
    """
    Récupère le contenu HTML d'une URL sans lancer de navigateur graphique.
    Utilise des en-têtes réalistes et tente plusieurs fois en cas d'échec.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
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
    # Remplace les caractères spéciaux par des underscores
    cleaned = re.sub(r'[\\/:*?"<>|]', '_', filename)
    # Supprime les points en fin de nom
    cleaned = re.sub(r'\.$', '', cleaned)
    # Remplace les espaces multiples par un seul underscore
    cleaned = re.sub(r'\s+', '_', cleaned).strip('_')
    # Supprime les underscores multiples
    cleaned = re.sub(r'_+', '_', cleaned)
    return cleaned[:150]  # Limite à 150 caractères pour éviter les noms trop longs

def extract_manga_title(html_content):
    """Récupère le titre du manga depuis le HTML - adapté pour Phenix Scans."""
    if not html_content:
        return "Titre_Manga_Inconnu"
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Sélecteurs possibles pour Phenix Scans
    selectors = [
        "h1.project__content-informations-title"
    ]
    
    for selector in selectors:
        title_element = soup.select_one(selector)
        if title_element:
            title = title_element.get_text(strip=True)
            if title and len(title) > 0:
                return title
    
    return "Titre_Manga_Inconnu"

def extract_chapter_links(html_content, base_url):
    """
    Extrait les liens de chapitres du HTML - adapté pour Phenix Scans.
    """
    chapters_found = []
    if not html_content:
        return chapters_found

    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Sélecteurs possibles pour les chapitres sur Phenix Scans
    selectors = [
        "a.project__chapter.unstyled-link"
    ]
    
    elements = []
    for selector in selectors:
        found = soup.select(selector)
        if found:
            elements = found
            break
    
    for element in elements:
        chapter_title = element.get_text(strip=True)
        chapter_relative_url = element.get('href')
        
        if chapter_title and chapter_relative_url:
            chapter_url = urljoin(base_url, chapter_relative_url)
            chapters_found.append({"title": chapter_title, "url": chapter_url, "images": []})
    
    # Inverse l'ordre pour avoir les chapitres du plus ancien au plus récent
    chapters_found.reverse()
    
    return chapters_found

def extract_image_links(html_content):
    """
    Extrait les URL des images du HTML - adapté pour Phenix Scans.
    """
    images_url = []
    if not html_content:
        return images_url

    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Sélecteurs possibles pour les images sur Phenix Scans
    selectors = [
        "img.chapter-image"
    ]
    
    image_elements = []
    for selector in selectors:
        found = soup.select(selector)
        if found:
            image_elements.extend(found)
    
    for element in image_elements:
        src = element.get('src') or element.get('data-src')
        if src:
            filename = os.path.basename(src).lower()
            if filename in EXCLUDED_IMAGE_FILENAMES:
                continue
            # Évite les doublons
            if src not in images_url:
                images_url.append(src)
    
    return images_url

def download_image(image_url, download_path, image_index, total_images):
    """Télécharge une image à partir de son URL et l'enregistre."""
    try:
        response = requests.get(image_url, stream=True, timeout=30)
        response.raise_for_status()

        # Déterminer l'extension
        file_extension = os.path.splitext(os.path.basename(image_url))[1]
        if not file_extension or len(file_extension) > 5: 
            file_extension = ".jpg" 
        
        # Nom de fichier avec zéro padding pour l'ordre
        filename = f"page_{str(image_index).zfill(3)}{file_extension}" 
        file_path = os.path.join(download_path, filename)
        
        if os.path.exists(file_path):
            print(f"            ⏩ Fichier déjà existant : {filename}")
            return file_path
            
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"            ✅ Téléchargé : {filename} ({image_index}/{total_images})")
        return file_path
    except requests.exceptions.RequestException as e:
        print(f"            ❌ Erreur de téléchargement de {image_url}: {e}")
        return None
    except Exception as e:
        print(f"            ❌ Erreur inattendue : {e}")
        return None

def create_cbr_from_chapter_images(chapter_dir, manga_name, chapter_number, chapter_title):
    """Crée un fichier .cbr avec une structure de noms plus propre."""
    # Nom du fichier CBR plus propre
    cbr_filename = f"{manga_name}_Ch{str(chapter_number).zfill(3)}_{clean_filename(chapter_title)}.cbr"
    cbr_path = os.path.join(os.path.dirname(chapter_dir), cbr_filename)

    image_files = sorted([
        os.path.join(chapter_dir, f) 
        for f in os.listdir(chapter_dir) 
        if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
    ])

    if not image_files:
        print(f"    ⚠️ Pas d'images trouvées dans {chapter_dir}")
        return None

    try:
        with zipfile.ZipFile(cbr_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for image_file in image_files:
                # Nom simple dans l'archive
                archive_name = os.path.basename(image_file)
                zf.write(image_file, archive_name)
        
        print(f"    📦 CBR créé : {os.path.basename(cbr_path)}")
        return cbr_path
    except Exception as e:
        print(f"    ❌ Erreur création CBR : {e}")
        return None

def cleanup_chapter_folder(chapter_dir):
    """Supprime le dossier du chapitre après création du CBR."""
    try:
        shutil.rmtree(chapter_dir)
        print(f"    🗑️ Dossier temporaire supprimé : {os.path.basename(chapter_dir)}")
    except Exception as e:
        print(f"    ⚠️ Erreur suppression dossier : {e}")

def save_to_json(data, filename):
    """Sauvegarde les données dans un fichier JSON."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Données sauvegardées : {filename}")
    except Exception as e:
        print(f"❌ Erreur sauvegarde JSON : {e}")

def main():
    """Fonction principale pour Phenix Scans."""
    print("🔥 === PHENIX SCANS CBR CREATOR === 🔥")
    print()

    manga_link = input("URL de la page manga Phenix Scans : ").strip()

    if not manga_link:
        print("❌ Aucune URL fournie.")
        return

    if not manga_link.startswith(("http://", "https://")):
        print("⚠️ URL invalide (doit commencer par http:// ou https://).")
        return
        
    if "phenix-scans" not in manga_link.lower():
        print("⚠️ L'URL ne semble pas être de Phenix Scans.")
        return

    manga_data = {
        "manga_url": manga_link,
        "scraped_at": datetime.now().isoformat(),
        "manga_title": "N/A",
        "site": "Phenix Scans",
        "chapters": []
    }
    
    try:
        print(f"🚀 Récupération de la page manga...")
        manga_html = get_html_content(manga_link)

        if manga_html:
            manga_title_raw = extract_manga_title(manga_html)
            manga_data["manga_title"] = manga_title_raw
            manga_name = clean_filename(manga_title_raw)
            
            if not manga_name or manga_name == "Titre_Manga_Inconnu":
                manga_name = f"Manga_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Dossier principal du manga
            manga_dir = os.path.join(os.getcwd(), f"[Phenix_Scans]_{manga_name}")
            os.makedirs(manga_dir, exist_ok=True)
            print(f"\n📂 Dossier créé : {manga_dir}")
            print(f"📖 Titre : {manga_title_raw}")

            chapters = extract_chapter_links(manga_html, manga_link)
            
            if chapters:
                manga_data["chapters"] = chapters 
                
                print(f"\n📚 {len(chapters)} chapitres trouvés. Début du traitement...")
                
                for i, chapter in enumerate(chapters):
                    chapter_number = i + 1
                    print(f"\n[{chapter_number}/{len(chapters)}] {chapter['title']}")
                    
                    # Dossier temporaire pour les images
                    temp_chapter_dir = os.path.join(manga_dir, f"temp_ch_{chapter_number}")
                    os.makedirs(temp_chapter_dir, exist_ok=True)

                    chapter_html = get_html_content(chapter['url'])
                    if chapter_html:
                        chapter_images = extract_image_links(chapter_html)
                        chapter['images'] = chapter_images
                        
                        if chapter_images:
                            print(f"    📥 Téléchargement de {len(chapter_images)} images...")
                            downloaded_count = 0
                            
                            for img_idx, img_url in enumerate(chapter_images):
                                img_path = download_image(
                                    img_url, temp_chapter_dir, 
                                    img_idx + 1, len(chapter_images)
                                )
                                if img_path:
                                    downloaded_count += 1
                                time.sleep(0.1)  # Pause entre téléchargements
                            
                            if downloaded_count > 0:
                                # Créer le CBR
                                cbr_path = create_cbr_from_chapter_images(
                                    temp_chapter_dir, manga_name, 
                                    chapter_number, chapter['title']
                                )
                                
                                # Supprimer le dossier temporaire
                                cleanup_chapter_folder(temp_chapter_dir)
                                
                                if cbr_path:
                                    print(f"    ✅ Chapitre {chapter_number} terminé")
                                else:
                                    print(f"    ❌ Échec création CBR pour chapitre {chapter_number}")
                            else:
                                print(f"    ⚠️ Aucune image téléchargée pour ce chapitre")
                                cleanup_chapter_folder(temp_chapter_dir)
                        else:
                            print("    ⚠️ Aucune image trouvée")
                            cleanup_chapter_folder(temp_chapter_dir)
                    else:
                        print("    ❌ Impossible de récupérer le HTML du chapitre")
                        cleanup_chapter_folder(temp_chapter_dir)

                    time.sleep(1)  # Pause entre chapitres

                print("\n🎉 === TRAITEMENT TERMINÉ === 🎉")
                
                # Sauvegarder les métadonnées
                json_filename = os.path.join(manga_dir, f"{manga_name}_metadata.json")
                save_to_json(manga_data, json_filename)
                
                print(f"\n✨ Manga téléchargé avec succès !")
                print(f"📁 Dossier : {manga_dir}")
                print(f"📊 {len(chapters)} chapitres traités")
                
            else:
                print("😢 Aucun chapitre trouvé sur cette page.")

        else:
            print("😢 Impossible de récupérer la page du manga.")

    except Exception as e:
        print(f"💥 Erreur inattendue : {e}")
        import traceback
        traceback.print_exc()
        
if __name__ == "__main__":
    main()