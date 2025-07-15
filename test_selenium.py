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
    """Configuration du driver Chrome"""
    chrome_options = Options()
    
    # Options pour éviter la détection
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # User agent plus réaliste
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Autres options utiles
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Service avec WebDriverManager
    service = Service(ChromeDriverManager().install())
    
    # Créer le driver
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Masquer les propriétés webdriver
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def scrape_phenix_mangas():
    """Scrape tous les liens manga de Phenix Scans avec pagination"""
    
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
                            "scraped_at": datetime.now().isoformat()
                        })
                        
                        print(f"✅ Ajouté: {title}")
                    
                except Exception as e:
                    print(f"❌ Erreur lors de l'extraction d'un manga: {e}")
                    continue
            
            # Vérifier combien de nouveaux mangas ont été ajoutés
            new_mangas = len(manga_links) - current_count
            print(f"📚 {new_mangas} nouveaux mangas trouvés sur cette page (Total: {len(manga_links)})")
            
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
                print(f"   (Détail: {e})")
                break
        
        print(f"🎉 Scraping terminé! Total de {len(manga_links)} mangas récupérés sur {page_count} pages")
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
        # Créer l'objet de données final
        final_data = {
            "metadata": {
                "source": "https://phenix-scans.com/manga",
                "scraped_at": datetime.now().isoformat(),
                "total_mangas": len(manga_data),
                "description": "Collection épique de mangas scrapés depuis Phenix Scans! 🎌⚡"
            },
            "mangas": manga_data
        }
        
        # Sauvegarder en JSON
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Données sauvegardées dans: {filename}")
        print(f"📊 Total de mangas: {len(manga_data)}")
        
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde: {e}")

def main():
    """Fonction principale"""
    print("🎌 === PHENIX SCANS MANGA SCRAPER ULTRA MEGA SUPER FUN === 🎌")
    print()
    
    # Scraper les mangas
    manga_data = scrape_phenix_mangas()
    
    if manga_data:
        # Sauvegarder dans un fichier JSON
        save_to_json(manga_data)
        
        # Afficher quelques statistiques fun
        print("\n🎉 === STATISTIQUES SUPER FUN === 🎉")
        print(f"🏆 Mangas capturés: {len(manga_data)}")
        
        if manga_data:
            print(f"🥇 Premier manga: {manga_data[0]['title']}")
            print(f"🥉 Dernier manga: {manga_data[-1]['title']}")
        
        print("\n🚀 Mission accomplie! Tous les mangas ont été capturés! 🚀")
    else:
        print("😢 Aucun manga n'a pu être récupéré...")

if __name__ == "__main__":
    main()