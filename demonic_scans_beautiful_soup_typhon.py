import requests
from bs4 import BeautifulSoup
import json
import time # Ensure 'time' module is imported for time.sleep()
from datetime import datetime
from urllib.parse import urljoin # Import urljoin for handling relative URLs

def get_html_content(url):
    """
    Récupère le contenu HTML d'une URL sans lancer de navigateur.
    Utilise un User-Agent pour se faire passer pour un navigateur.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Lève une exception pour les codes d'état d'erreur HTTP
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors de la récupération de l'URL {url}: {e}")
        return None

def extract_chapter_links(html_content, base_url): # Added base_url parameter
    """
    Extrait les liens de chapitres avec le sélecteur 'a.chplinks' du HTML
    et les convertit en URLs absolues.
    """
    chapters_found = []
    if not html_content:
        return chapters_found

    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Rechercher toutes les balises <a> avec la classe 'chplinks'
    elements = soup.select("a.chplinks")
    
    for element in elements:
        chapter_title = element.get_text(strip=True)
        chapter_relative_url = element.get('href')
        
        if chapter_title and chapter_relative_url:
            # Convert relative URL to absolute URL
            chapter_url = urljoin(base_url, chapter_relative_url)
            chapters_found.append({"title": chapter_title, "url": chapter_url, "images": []})
            
    # Inverser l'ordre des chapitres si nécessaire (souvent, les premiers chapitres sont en bas de liste)
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
    
    # Rechercher toutes les balises <img> avec la classe 'imgholder'
    image_elements = soup.select("img.imgholder")
    
    for element in image_elements:
        src = element.get('src')
        if src:
            images_url.append(src)
            
    return images_url

def save_to_json(data, filename="demonic_scans_manga_data_fast.json"):
    """Sauvegarde les données dans un fichier JSON."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Données sauvegardées dans: {filename}")
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde du fichier JSON: {e}")

def main():
    """Fonction principale pour scraper rapidement les chapitres et leurs images."""
    print("⚡ === DEMONIC SCANS FAST SCRAPER (HTML direct) === ⚡")
    print()

    manga_link = input("Veuillez coller l'URL complète de la page du manga (ex: https://demonicscans.org/manga/The-Indomitable-Martial-King): ").strip()

    if not manga_link:
        print("❌ Aucune URL de manga fournie. Arrêt du script.")
        return

    # Added check for a valid scheme (http or https) in the manga link
    if not manga_link.startswith("http://") and not manga_link.startswith("https://"):
        print("⚠️ L'URL de manga doit commencer par 'http://' ou 'https://'. Veuillez vérifier et réessayer.")
        return
        
    if "demonicscans.org" not in manga_link or "/manga/" not in manga_link:
        print("⚠️ L'URL ne semble pas être un lien de page de manga valide de Demonic Scans. Veuillez vérifier et réessayer.")
        return

    manga_data_output = {
        "manga_url": manga_link,
        "scraped_at": datetime.now().isoformat(),
        "chapters": []
    }

    print(f"🚀 Récupération du HTML de la page manga: {manga_link}")
    manga_html = get_html_content(manga_link)

    if manga_html:
        # Pass manga_link as base_url to extract_chapter_links
        chapters = extract_chapter_links(manga_html, manga_link) 
        if chapters:
            manga_data_output["chapters"] = chapters
            print(f"✅ {len(chapters)} chapitres trouvés sur la page manga.")
            print("\n📚 === DÉBUT DU SCRAPING DES IMAGES POUR CHAQUE CHAPITRE (HTML direct) === 📚")
            
            for i, chapter in enumerate(manga_data_output["chapters"]):
                print(f"\n[{i+1}/{len(manga_data_output['chapters'])}] Traitement du chapitre: {chapter['title']}")
                print(f"  ⚡ Récupération du HTML du chapitre: {chapter['url']}")
                chapter_html = get_html_content(chapter['url'])
                
                if chapter_html:
                    chapter_images = extract_image_links(chapter_html)
                    chapter['images'] = chapter_images
                    print(f"  ✅ {len(chapter_images)} images trouvées pour ce chapitre.")
                else:
                    print("  ❌ Impossible de récupérer le HTML du chapitre.")
                
                # Corrected: Use time.sleep()
                time.sleep(0.1) 

            print("\n🎉 === SCRAPING TERMINÉ === 🎉")
            save_to_json(manga_data_output)
            print(f"\n🚀 Mission accomplie! Données du manga et des chapitres/images enregistrées.")
        else:
            print("😢 Aucun chapitre trouvé avec 'a.chplinks' sur la page du manga. Cela peut indiquer que les liens sont chargés dynamiquement.")
    else:
        print("😢 Impossible de récupérer le HTML de la page du manga.")

if __name__ == "__main__":
    main()