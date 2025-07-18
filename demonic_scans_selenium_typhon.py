from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import json
import time
from datetime import datetime

def setup_chrome_driver():
    """Configure le driver Chrome avec des options pour éviter la détection, les popups et BLOQUE LE CHARGEMENT DES IMAGES."""
    chrome_options = Options()

    # Options pour éviter la détection
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    # User agent plus réaliste
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # Blocage des popups et notifications
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    
    # BLOQUER LE CHARGEMENT DES IMAGES
    chrome_options.add_argument("--disable-images") 
    
    chrome_options.add_argument("--block-new-web-contents") # Bloquer le contenu non sollicité

    # Préférences pour bloquer les popups
    prefs = {
        "profile.default_content_setting_values": {
            "popups": 2,  # Bloquer les popups
            "notifications": 2,  # Bloquer les notifications
            "media_stream": 2,  # Bloquer l'accès caméra/micro
            "images": 2 # Assurez-vous que les images sont bloquées via les préférences aussi
        },
        "profile.managed_default_content_settings": {
            "popups": 2,
            "images": 2
        }
    }
    chrome_options.add_experimental_option("prefs", prefs)

    # Autres options utiles
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    
    # Mode headless (sans interface graphique) - décommenter pour l'activer pour un usage en arrière-plan
    # chrome_options.add_argument("--headless")

    # Service avec WebDriverManager
    service = Service(ChromeDriverManager().install())

    # Créer le driver
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # Masquer les propriétés webdriver
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    return driver

def get_manga_chapter_links(driver, manga_url):
    """Récupère les liens des chapitres avec le sélecteur 'a.chplinks' depuis la page d'un manga."""
    chapter_links_found = []
    try:
        print(f"📖 Navigation vers la page du manga: {manga_url}")
        driver.get(manga_url)
        
        wait = WebDriverWait(driver, 15)
        time.sleep(3) # Laisser un peu de temps pour le chargement initial

        print(f"🔍 Recherche des liens de chapitres avec le sélecteur 'a.chplinks'...")
        
        try:
            chapter_elements = wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.chplinks"))
            )
            
            for element in chapter_elements:
                try:
                    chapter_title = element.text.strip()
                    chapter_url = element.get_attribute("href")
                    if chapter_title and chapter_url:
                        chapter_links_found.append({"title": chapter_title, "url": chapter_url, "images": []})
                except Exception as e:
                    print(f"    ❌ Erreur lors de l'extraction d'un élément de chapitre: {e}")
                    continue

            # Inverser l'ordre des chapitres si nécessaire (souvent, les premiers chapitres sont en bas de liste)
            chapter_links_found.reverse()
            
            print(f"    ✅ {len(chapter_links_found)} chapitres trouvés avec 'a.chplinks'.")
            return chapter_links_found
            
        except Exception as e:
            print(f"    ❌ Aucun élément trouvé avec le sélecteur 'a.chplinks' ou erreur: {e}")
            return []
        
    except Exception as e:
        print(f"    💥 Erreur lors de la récupération des chapitres depuis {manga_url}: {e}")
        return []

def scrape_chapter_images(driver, chapter_url):
    """Scrape les URL des images avec le sélecteur 'img.imgholder' d'un chapitre spécifique sur Demonic Scans."""
    images_url = []
    
    try:
        print(f"    📖 Récupération des images pour le chapitre: {chapter_url}")
        driver.get(chapter_url)
        
        wait = WebDriverWait(driver, 20) # Augmenter le timeout pour les pages plus lourdes
        time.sleep(3) # Un petit délai initial peut aider

        try:
            # Chercher toutes les balises <img> avec la classe 'imgholder'
            # Note : Même si les images ne sont pas chargées visuellement, leurs attributs 'src' devraient être présents dans le DOM.
            image_elements = wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "img.imgholder"))
            )
            
            for element in image_elements:
                src = element.get_attribute("src")
                if src:
                    images_url.append(src)

            print(f"        ✅ {len(images_url)} images trouvées avec 'img.imgholder'.")

        except Exception as e:
            print(f"        ❌ Impossible de trouver les images du chapitre avec 'img.imgholder': {e}")
            
    except Exception as e:
        print(f"    💥 Erreur lors du scraping du chapitre: {e}")
    
    return images_url

def save_to_json(data, filename="demonic_scans_manga_data.json"):
    """Sauvegarde les données dans un fichier JSON."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Données sauvegardées dans: {filename}")
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde du fichier JSON: {e}")

def main():
    """Fonction principale pour scraper les chapitres et leurs images de Demonic Scans."""
    print("🎌 === DEMONIC SCANS MANGA & CHAPITRES/IMAGES SCRAPER === 🎌")
    print()

    manga_link = input("Veuillez coller l'URL complète de la page du manga (ex: https://demonicscans.org/manga/The-Indomitable-Martial-King): ").strip()

    if not manga_link:
        print("❌ Aucune URL de manga fournie. Arrêt du script.")
        return

    if "demonicscans.org" not in manga_link or "/manga/" not in manga_link:
        print("⚠️ L'URL ne semble pas être un lien de page de manga valide de Demonic Scans. Veuillez vérifier et réessayer.")
        return

    driver = None
    manga_data_output = {
        "manga_url": manga_link,
        "scraped_at": datetime.now().isoformat(),
        "chapters": []
    }

    try:
        driver = setup_chrome_driver()
        
        # 1. Récupérer les liens de tous les chapitres
        chapters = get_manga_chapter_links(driver, manga_link)
        
        if chapters:
            manga_data_output["chapters"] = chapters
            
            print("\n📚 === DÉBUT DU SCRAPING DES IMAGES POUR CHAQUE CHAPITRE === 📚")
            for i, chapter in enumerate(manga_data_output["chapters"]):
                print(f"\n[{i+1}/{len(manga_data_output['chapters'])}] Traitement du chapitre: {chapter['title']}")
                # 2. Parcourir chaque lien de chapitre et récupérer les images
                chapter_images = scrape_chapter_images(driver, chapter['url'])
                chapter['images'] = chapter_images
                
                time.sleep(1) # Petit délai pour éviter de surcharger le serveur

            print("\n🎉 === SCRAPING TERMINÉ === 🎉")
            # 3. Enregistrer toutes les données dans un fichier JSON
            save_to_json(manga_data_output)
            
            print(f"\n🚀 Mission accomplie! Données du manga et des chapitres/images enregistrées.")
        else:
            print("😢 Aucun chapitre n'a pu être récupéré de cette page de manga. Aucune image à scraper.")

    except Exception as e:
        print(f"💥 Une erreur inattendue est survenue: {e}")
        
    finally:
        if driver:
            print("🔒 Fermeture du navigateur...")
            driver.quit()

if __name__ == "__main__":
    main()