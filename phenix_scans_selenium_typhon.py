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
    """Configuration du driver Chrome avec blocage des popups"""
    chrome_options = Options()
    
    # Options pour éviter la détection
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # User agent plus réaliste
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Blocage des popups et publicités
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-images")  # Optionnel: accélère le chargement
    chrome_options.add_argument("--disable-javascript")  # Attention: peut casser certaines fonctionnalités
    chrome_options.add_argument("--block-new-web-contents")
    
    # Préférences pour bloquer les popups
    prefs = {
        "profile.default_content_setting_values": {
            "popups": 2,  # Bloquer les popups
            "notifications": 2,  # Bloquer les notifications
            "media_stream": 2,  # Bloquer l'accès caméra/micro
        },
        "profile.managed_default_content_settings": {
            "popups": 2
        }
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    # Autres options utiles
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    
    # Service avec WebDriverManager
    service = Service(ChromeDriverManager().install())
    
    # Créer le driver
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Masquer les propriétés webdriver
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def scrape_manga_chapters(driver, manga_url, manga_title):
    """Scrape les chapitres d'un manga spécifique"""
    chapters = []
    
    try:
        print(f"  📖 Récupération des chapitres de: {manga_title}")
        
        # Naviguer vers la page du manga
        driver.get(manga_url)
        
        # Attendre que la page se charge
        wait = WebDriverWait(driver, 10)
        time.sleep(2)
        
        # Chercher tous les liens de chapitres
        try:
            chapter_elements = wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.project__chapter.unstyled-link"))
            )
            
            for element in chapter_elements:
                try:
                    # Récupérer le lien du chapitre
                    chapter_url = element.get_attribute("href")
                    
                    # Récupérer le titre du chapitre
                    chapter_title = element.text.strip()
                    
                    chapters.append({
                        "title": chapter_title,
                        "url": chapter_url,
                        "scraped_at": datetime.now().isoformat()
                    })
                    
                except Exception as e:
                    print(f"    ❌ Erreur lors de l'extraction d'un chapitre: {e}")
                    continue
            
            print(f"    ✅ {len(chapters)} chapitres récupérés")
            
        except Exception as e:
            print(f"    ❌ Aucun chapitre trouvé pour {manga_title}: {e}")
            
    except Exception as e:
        print(f"    💥 Erreur lors du scraping de {manga_title}: {e}")
    
    return chapters

def scrape_phenix_mangas():
    """Scrape tous les liens manga de Phenix Scans avec pagination et chapitres"""
    
    driver = setup_chrome_driver()
    manga_links = []
    
    try:
        print("🚀 Lancement du scraping de Phenix Scans...")
        
        # Naviguer vers la page
        driver.get("https://phenix-scans.com/manga")
        
        # Attendre que la page se charge
        wait = WebDriverWait(driver, 15)
        
        # Attendre un peu pour que le contenu se charge complètement
        time.sleep(3)
        
        page_count = 1
        no_new_mangas_count = 0
        
        while True:
            print(f"📖 Scraping de la page {page_count}...")
            
            # Attendre que les éléments soient présents
            try:
                manga_elements = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.manga-list__link.unstyled-link"))
                )
            except Exception as e:
                print(f"❌ Impossible de trouver les éléments manga: {e}")
                break
            
            # Compter les mangas avant d'extraire (pour éviter les doublons)
            current_count = len(manga_links)
            
            # Extraire les informations des nouveaux mangas
            for element in manga_elements:
                try:
                    # Récupérer le lien
                    link = element.get_attribute("href")
                    
                    # Récupérer le titre (contenu du lien)
                    title = element.text.strip()
                    
                    # Vérifier si ce manga n'est pas déjà dans notre liste (éviter les doublons)
                    if not any(manga['url'] == link for manga in manga_links):
                        manga_links.append({
                            "title": title,
                            "url": link,
                            "scraped_at": datetime.now().isoformat(),
                            "chapters": []  # Sera rempli plus tard
                        })
                        
                        print(f"✅ Ajouté: {title}")
                    
                except Exception as e:
                    print(f"❌ Erreur lors de l'extraction d'un manga: {e}")
                    continue
            
            # Vérifier combien de nouveaux mangas ont été ajoutés
            new_mangas = len(manga_links) - current_count
            print(f"📚 {new_mangas} nouveaux mangas trouvés sur cette page (Total: {len(manga_links)})")
            
            # Si aucun nouveau manga n'a été trouvé, arrêter
            if new_mangas == 0:
                no_new_mangas_count += 1
                if no_new_mangas_count >= 2:  # Arrêter après 2 pages sans nouveaux mangas
                    print("🏁 Aucun nouveau manga trouvé - Arrêt du scraping")
                    break
            else:
                no_new_mangas_count = 0
            
            # Chercher le bouton "Charger plus"
            try:
                load_more_button = driver.find_element(By.CSS_SELECTOR, ".manga-list__load-more button")
                
                # Vérifier si le bouton est visible et cliquable
                if load_more_button.is_displayed() and load_more_button.is_enabled():
                    print("🔄 Clic sur 'Charger plus'...")
                    
                    # Scroller vers le bouton pour s'assurer qu'il est visible
                    driver.execute_script("arguments[0].scrollIntoView(true);", load_more_button)
                    time.sleep(1)
                    
                    # Cliquer sur le bouton
                    load_more_button.click()
                    
                    # Attendre que le contenu se charge
                    time.sleep(3)
                    
                    page_count += 1
                    
                    # Sécurité : éviter une boucle infinie
                    if page_count > 50:  # Limite de sécurité
                        print("⚠️ Limite de sécurité atteinte (50 pages)")
                        break
                        
                else:
                    print("🏁 Bouton 'Charger plus' non disponible - Fin du scraping")
                    break
                    
            except Exception as e:
                print(f"🏁 Plus de bouton 'Charger plus' trouvé - Scraping terminé")
                break
        
        print(f"🎉 Scraping des mangas terminé! Total de {len(manga_links)} mangas récupérés sur {page_count} pages")
        
        # Maintenant, récupérer les chapitres pour chaque manga
        print("\n🔍 === RÉCUPÉRATION DES CHAPITRES === 🔍")
        
        for i, manga in enumerate(manga_links, 1):
            print(f"\n📚 [{i}/{len(manga_links)}] Traitement de: {manga['title']}")
            
            # Récupérer les chapitres
            chapters = scrape_manga_chapters(driver, manga['url'], manga['title'])
            manga['chapters'] = chapters
            
            # Petit délai pour éviter de surcharger le serveur
            time.sleep(1)
        
        return manga_links
        
    except Exception as e:
        print(f"💥 Erreur lors du scraping: {e}")
        return []
        
    finally:
        print("🔒 Fermeture du navigateur...")
        driver.quit()

def save_to_json(manga_data, filename="mega_super_fun_phenix_manga_collection_extraordinaire.json"):
    """Sauvegarde les données dans un fichier JSON avec un nom super fun"""
    
    try:
        # Calculer le nombre total de chapitres
        total_chapters = sum(len(manga['chapters']) for manga in manga_data)
        
        # Créer l'objet de données final
        final_data = {
            "metadata": {
                "source": "https://phenix-scans.com/manga",
                "scraped_at": datetime.now().isoformat(),
                "total_mangas": len(manga_data),
                "total_chapters": total_chapters,
                "description": "Collection épique de mangas avec chapitres scrapés depuis Phenix Scans! 🎌⚡"
            },
            "mangas": manga_data
        }
        
        # Sauvegarder en JSON
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Données sauvegardées dans: {filename}")
        print(f"📊 Total de mangas: {len(manga_data)}")
        print(f"📖 Total de chapitres: {total_chapters}")
        
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde: {e}")

def main():
    """Fonction principale"""
    print("🎌 === PHENIX SCANS MANGA + CHAPITRES SCRAPER ULTRA MEGA SUPER FUN === 🎌")
    print()
    
    # Scraper les mangas et leurs chapitres
    manga_data = scrape_phenix_mangas()
    
    if manga_data:
        # Sauvegarder dans un fichier JSON
        save_to_json(manga_data)
        
        # Afficher quelques statistiques fun
        print("\n🎉 === STATISTIQUES SUPER FUN === 🎉")
        print(f"🏆 Mangas capturés: {len(manga_data)}")
        
        total_chapters = sum(len(manga['chapters']) for manga in manga_data)
        print(f"📚 Chapitres totaux: {total_chapters}")
        
        if manga_data:
            print(f"🥇 Premier manga: {manga_data[0]['title']}")
            print(f"🥉 Dernier manga: {manga_data[-1]['title']}")
            
            # Trouver le manga avec le plus de chapitres
            max_chapters_manga = max(manga_data, key=lambda m: len(m['chapters']))
            print(f"👑 Manga avec le plus de chapitres: {max_chapters_manga['title']} ({len(max_chapters_manga['chapters'])} chapitres)")
        
        print("\n🚀 Mission accomplie! Tous les mangas et chapitres ont été capturés! 🚀")
    else:
        print("😢 Aucun manga n'a pu être récupéré...")

if __name__ == "__main__":
    main()