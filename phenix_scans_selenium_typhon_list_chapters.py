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
import random
import os
import logging # Added for structured logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_chrome_driver(headless=False): # Added headless parameter
    """Configuration du driver Chrome pour éviter les captchas"""
    chrome_options = Options()
    
    # Options pour éviter la détection de bot
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # User agents rotatifs
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    
    chrome_options.add_argument(f"--user-agent={random.choice(user_agents)}")
    
    # Options anti-captcha
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    
    # Block images - this was already there and is good!
    chrome_options.add_argument("--blink-settings=imagesEnabled=false") # More robust way to disable images
    
    # Random resolution
    resolutions = ["1920,1080", "1366,768", "1536,864", "1440,900"]
    chrome_options.add_argument(f"--window-size={random.choice(resolutions)}")
    
    # Blocage des popups and notifications
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-notifications")
    
    prefs = {
        "profile.default_content_setting_values": {
            "popups": 2,
            "notifications": 2,
            "media_stream": 2,
            "images": 2 # Ensure images are blocked via preferences as well
        }
    }
    chrome_options.add_experimental_option("prefs", prefs)

    if headless: # Conditional headless mode
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--window-size=1920,1080") # Set a fixed size for headless

    # Service with WebDriverManager
    service = Service(ChromeDriverManager().install())
    
    # Create the driver
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Anti-detection scripts
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
    driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
    
    return driver

def detect_captcha(driver):
    """Détecte si un captcha est présent sur la page"""
    captcha_selectors = [
        "iframe[src*='recaptcha']",
        ".g-recaptcha",
        ".captcha",
        ".hcaptcha",
        "[data-captcha]",
        ".cf-browser-verification",
        "#challenge-form",
        ".challenge-form",
        "div[data-hcaptcha-widget-id]", # Added for hCaptcha specific attribute
        "div.cf-challenge" # Added for Cloudflare challenge
    ]
    
    for selector in captcha_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                logging.warning(f"🤖 Captcha detected with selector: {selector}")
                return True
        except Exception as e:
            # This catch is mostly for safety, find_elements should not raise for no element
            logging.debug(f"Error checking captcha selector {selector}: {e}")
            continue
            
    return False

def handle_captcha_detection(driver, url, retries=3):
    """Gère la détection de captcha avec stratégies de contournement"""
    
    if detect_captcha(driver):
        logging.warning("🤖 Captcha détecté! Tentatives de contournement...")
        
        for attempt in range(retries):
            logging.info(f"⏳ Tentative {attempt + 1}/{retries} de contournement...")
            
            # Strategy 1: Wait and refresh
            time.sleep(random.uniform(10, 20))
            driver.refresh()
            time.sleep(5) # Give some time for refresh to settle
            
            if not detect_captcha(driver):
                logging.info("✅ Captcha contourné avec succès!")
                return True
            
            # Strategy 2: Change user agent and reload (only if more retries)
            if attempt < retries - 1:
                logging.info("🔄 Changement d'user agent et rechargement de la page...")
                user_agents = [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
                ]
                driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                    "userAgent": random.choice(user_agents),
                    "platform": "Windows" # Add platform for more realism
                })
                
                # Navigate again
                driver.get(url)
                time.sleep(random.uniform(5, 10))
    
        logging.error("❌ Impossible de contourner le captcha après plusieurs tentatives.")
        return False
        
    return True # No captcha detected initially

def scrape_manga_chapters_safe(driver, manga_url, manga_title):
    """Scrape les chapitres d'un manga avec gestion du captcha"""
    chapters = []
    
    try:
        logging.info(f"📖 Récupération des chapitres de: {manga_title}")
        
        # Random delay before the request
        time.sleep(random.uniform(2, 5))
        
        # Navigate to the manga page
        driver.get(manga_url)
        
        # Wait for the page to load
        wait = WebDriverWait(driver, 20) # Increased wait time for slow pages
        time.sleep(random.uniform(3, 6))
        
        # Check for captcha
        if not handle_captcha_detection(driver, manga_url):
            logging.warning(f"❌ Captcha non résolu pour {manga_title}. Skipping this manga.")
            return []
            
        # Look for all chapter links
        try:
            # Wait for at least one chapter element to be visible
            chapter_elements = wait.until(
                EC.visibility_of_all_elements_located((By.CSS_SELECTOR, "a.project__chapter.unstyled-link"))
            )
            
            for element in chapter_elements:
                try:
                    # Get chapter link
                    chapter_url = element.get_attribute("href")
                    
                    # Get chapter title
                    chapter_title = element.text.strip()
                    
                    if chapter_url and chapter_title:
                        chapters.append({
                            "title": chapter_title,
                            "url": chapter_url,
                            "scraped_at": datetime.now().isoformat()
                        })
                    
                except Exception as e:
                    logging.error(f"❌ Erreur lors de l'extraction d'un chapitre pour {manga_title}: {e}")
                    continue
            
            logging.info(f"✅ {len(chapters)} chapitres récupérés pour {manga_title}")
            
        except Exception as e:
            logging.warning(f"❌ Aucun chapitre trouvé ou erreur lors de la recherche des chapitres pour {manga_title}: {e}")
            
    except Exception as e:
        logging.error(f"💥 Erreur lors du scraping de {manga_title} (URL: {manga_url}): {e}")
    
    return chapters

def load_manga_data(filename="mega_super_fun_phenix_manga_collection_extraordinaire.json"):
    """Charge les données des mangas depuis le fichier JSON"""
    if not os.path.exists(filename):
        logging.error(f"❌ Fichier {filename} non trouvé! Assurez-vous qu'il existe et contient des données.")
        return []

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        mangas = data.get('mangas', [])
        logging.info(f"📚 {len(mangas)} mangas chargés depuis {filename}")
        return mangas
        
    except json.JSONDecodeError as e:
        logging.error(f"❌ Erreur de décodage JSON dans {filename}: {e}")
        return []
    except Exception as e:
        logging.error(f"❌ Erreur lors du chargement du fichier {filename}: {e}")
        return []

def scrape_all_chapters(manga_data, start_from=0, max_mangas=None, headless_mode=False): # Added headless_mode
    """Scrape tous les chapitres avec gestion du captcha et reprise"""
    
    driver = setup_chrome_driver(headless=headless_mode) # Pass headless_mode
    updated_manga_data = []
    
    # Store initial data to append to if resuming
    initial_manga_data = list(manga_data)

    try:
        logging.info("🚀 Lancement du scraping des chapitres...")
        
        # Adjust manga_data based on start_from and max_mangas
        mangas_to_process = manga_data[start_from:]
        if max_mangas:
            mangas_to_process = mangas_to_process[:max_mangas]

        total_mangas_to_process = len(mangas_to_process)
        
        success_count = 0
        captcha_or_error_count = 0 # Renamed for clarity
        
        for i, manga in enumerate(mangas_to_process):
            current_index = start_from + i
            logging.info(f"\n📚 [{current_index + 1}/{total_mangas_to_process + start_from}] Traitement de: {manga['title']}")
            
            # Retrieve chapters with captcha handling
            chapters = scrape_manga_chapters_safe(driver, manga['url'], manga['title'])
            
            # Update data
            manga_copy = manga.copy()
            manga_copy['chapters'] = chapters
            manga_copy['chapters_scraped_at'] = datetime.now().isoformat()
            
            # Replace the original manga entry with the updated one
            # This ensures that if we save later, the full list is correct
            initial_manga_data[current_index] = manga_copy
            
            if chapters:
                success_count += 1
            else:
                captcha_or_error_count += 1
            
            # Progressive saving every 10 mangas
            if (i + 1) % 10 == 0: # Use (i + 1) for actual count
                save_progress(initial_manga_data, f"progress_backup_{current_index + 1}.json")
                logging.info(f"💾 Sauvegarde de progression effectuée ({current_index + 1} mangas traités)")
            
            # Random delay between requests
            delay = random.uniform(3, 8)
            logging.info(f"⏱️ Pause de {delay:.1f}s...")
            time.sleep(delay)
            
            # Longer pause every 20 mangas
            if (i + 1) % 20 == 0:
                long_delay = random.uniform(30, 60)
                logging.info(f"😴 Pause longue de {long_delay:.1f}s pour éviter la détection...")
                time.sleep(long_delay)
                
        logging.info(f"\n🎉 Scraping terminé!")
        logging.info(f"✅ Succès: {success_count}/{total_mangas_to_process}")
        logging.info(f"🤖 Captchas/Erreurs: {captcha_or_error_count}/{total_mangas_to_process}")
        
        return initial_manga_data # Return the full updated list
        
    except KeyboardInterrupt:
        logging.warning("\n⚠️ Arrêt demandé par l'utilisateur")
        logging.info(f"💾 Sauvegarde des données déjà récupérées ({len(updated_manga_data)} mangas traités)...")
        save_progress(initial_manga_data, f"progress_backup_interrupted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        return initial_manga_data
        
    except Exception as e:
        logging.critical(f"💥 Erreur critique lors du scraping: {e}", exc_info=True) # exc_info for traceback
        logging.info(f"💾 Sauvegarde des données déjà récupérées ({len(updated_manga_data)} mangas traités)...")
        save_progress(initial_manga_data, f"progress_backup_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        return initial_manga_data
        
    finally:
        logging.info("🔒 Fermeture du navigateur...")
        driver.quit()

def save_progress(data, filename):
    """Sauvegarde progressive des données"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logging.info(f"Progress saved to {filename}")
    except Exception as e:
        logging.error(f"❌ Erreur lors de la sauvegarde de la progression dans {filename}: {e}")

def save_chapters_json(manga_data, filename="phenix_manga_chapters_collection_mega_fun.json"):
    """Sauvegarde les données avec chapitres dans un nouveau fichier JSON"""
    
    try:
        # Calculate total chapters
        total_chapters = sum(len(manga.get('chapters', [])) for manga in manga_data) # Use .get for safety
        successful_manga = len([m for m in manga_data if m.get('chapters')])
        
        # Create final data object
        final_data = {
            "metadata": {
                "source": "https://phenix-scans.com/manga",
                "scraped_at": datetime.now().isoformat(),
                "total_mangas_in_file": len(manga_data),
                "successful_mangas_with_chapters": successful_manga,
                "total_chapters_scraped": total_chapters,
                "description": "Collection épique de mangas avec TOUS les chapitres scrapés! 🎌⚡📚"
            },
            "mangas": manga_data
        }
        
        # Save to JSON
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=2, ensure_ascii=False)
            
        logging.info(f"💾 Données finales sauvegardées dans: {filename}")
        logging.info(f"📊 Mangas totaux dans le fichier: {len(manga_data)}")
        logging.info(f"✅ Mangas avec chapitres scrapés avec succès: {successful_manga}")
        logging.info(f"📖 Total de chapitres récupérés: {total_chapters}")
        
    except Exception as e:
        logging.critical(f"❌ Erreur lors de la sauvegarde du fichier final {filename}: {e}", exc_info=True)

def main():
    """Fonction principale"""
    logging.info("🎌 === PHENIX SCANS CHAPTERS SCRAPER ANTI-CAPTCHA MEGA FUN === 🎌")
    
    # Load manga data
    manga_data = load_manga_data()
    
    if not manga_data:
        logging.error("❌ Aucune donnée de manga trouvée pour démarrer le scraping!")
        return
    
    # Ask user for options
    try:
        start_from_input = input(f"🔄 Reprendre depuis quel index? (0-{len(manga_data)-1}, défaut: 0): ")
        start_from = int(start_from_input) if start_from_input.isdigit() else 0
        
        max_mangas_input = input("🎯 Limiter le nombre de mangas? (Entrez un nombre ou laissez vide pour tous): ")
        max_mangas = int(max_mangas_input) if max_mangas_input.isdigit() else None

        headless_input = input("🕵️‍♂️ Exécuter en mode headless (sans interface graphique)? (oui/non, défaut: non): ").lower()
        headless_mode = headless_input == 'oui'

    except ValueError:
        logging.error("Entrée invalide. Utilisation des valeurs par défaut.")
        start_from = 0
        max_mangas = None
        headless_mode = False
        
    logging.info(f"🎯 Démarrage du scraping depuis l'index {start_from}")
    if max_mangas:
        logging.info(f"🎯 Limitation du scraping à {max_mangas} mangas")
    logging.info(f"🕵️‍♂️ Mode Headless: {headless_mode}")
    
    # Scrape all chapters
    updated_manga_data = scrape_all_chapters(manga_data, start_from, max_mangas, headless_mode)
    
    if updated_manga_data:
        # Save to a new JSON file
        save_chapters_json(updated_manga_data)
        
        # Display some fun statistics
        logging.info("\n🎉 === STATISTIQUES ANTI-CAPTCHA SUPER FUN === 🎉")
        
        total_chapters = sum(len(manga.get('chapters', [])) for manga in updated_manga_data)
        successful_manga = len([m for m in updated_manga_data if m.get('chapters')])
        
        logging.info(f"🏆 Mangas traités (après ajustement initial): {len(updated_manga_data)}")
        logging.info(f"✅ Mangas avec succès: {successful_manga}")
        logging.info(f"📚 Chapitres totaux récupérés: {total_chapters}")
        
        if updated_manga_data:
            # Find manga with most chapters
            # Filter out mangas that didn't get any chapters to avoid errors with max() on empty list
            mangas_with_chapters = [m for m in updated_manga_data if m.get('chapters')]
            if mangas_with_chapters:
                max_chapters_manga = max(mangas_with_chapters, key=lambda m: len(m['chapters']))
                logging.info(f"👑 Manga avec le plus de chapitres: {max_chapters_manga['title']} ({len(max_chapters_manga['chapters'])} chapitres)")
            else:
                logging.info("Aucun manga n'a pu être scrapé avec des chapitres.")
            
        logging.info("\n🚀 Mission accomplie! Tous les chapitres ont été capturés malgré les captchas! 🚀")
    else:
        logging.error("😢 Aucun chapitre n'a pu être récupéré. Veuillez vérifier l'URL ou les sélecteurs.")

if __name__ == "__main__":
    main()