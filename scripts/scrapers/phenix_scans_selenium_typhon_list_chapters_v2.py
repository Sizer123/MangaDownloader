from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
import json
import time
from datetime import datetime
import random
import os
import logging
import requests
from urllib.parse import urljoin, urlparse
import math

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class CaptchaBypassManager:
    """Manager pour les différentes stratégies de contournement de captcha"""
    
    def __init__(self):
        self.bypass_strategies = [
            self.strategy_wait_and_refresh,
            self.strategy_change_user_agent,
            self.strategy_simulate_human_behavior,
            self.strategy_clear_cookies_and_reload,
            self.strategy_change_viewport_and_scroll
        ]
    
    def strategy_wait_and_refresh(self, driver, url):
        """Stratégie 1: Attendre et actualiser"""
        logging.info("🔄 Stratégie: Attente et actualisation...")
        time.sleep(random.uniform(15, 25))
        driver.refresh()
        time.sleep(random.uniform(5, 10))
        return True
    
    def strategy_change_user_agent(self, driver, url):
        """Stratégie 2: Changer l'user agent"""
        logging.info("🎭 Stratégie: Changement d'user agent...")
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
        ]
        
        try:
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": random.choice(user_agents),
                "platform": "Windows"
            })
            driver.get(url)
            time.sleep(random.uniform(8, 15))
            return True
        except Exception as e:
            logging.error(f"Erreur lors du changement d'user agent: {e}")
            return False
    
    def strategy_simulate_human_behavior(self, driver, url):
        """Stratégie 3: Simuler un comportement humain"""
        logging.info("🤖 Stratégie: Simulation de comportement humain...")
        try:
            # Simuler des mouvements de souris aléatoires
            actions = ActionChains(driver)
            
            # Déplacements aléatoires
            for _ in range(random.randint(3, 7)):
                x = random.randint(100, 800)
                y = random.randint(100, 600)
                actions.move_by_offset(x, y)
                time.sleep(random.uniform(0.5, 1.5))
            
            # Scroll aléatoire
            for _ in range(random.randint(2, 5)):
                driver.execute_script(f"window.scrollTo(0, {random.randint(100, 500)});")
                time.sleep(random.uniform(1, 2))
            
            # Simuler des clics sur des zones vides
            try:
                body = driver.find_element(By.TAG_NAME, "body")
                actions.move_to_element(body).click().perform()
                time.sleep(random.uniform(1, 3))
            except:
                pass
            
            actions.perform()
            time.sleep(random.uniform(5, 10))
            return True
            
        except Exception as e:
            logging.error(f"Erreur lors de la simulation de comportement humain: {e}")
            return False
    
    def strategy_clear_cookies_and_reload(self, driver, url):
        """Stratégie 4: Nettoyer les cookies et recharger"""
        logging.info("🍪 Stratégie: Nettoyage des cookies...")
        try:
            driver.delete_all_cookies()
            time.sleep(random.uniform(2, 5))
            driver.get(url)
            time.sleep(random.uniform(8, 15))
            return True
        except Exception as e:
            logging.error(f"Erreur lors du nettoyage des cookies: {e}")
            return False
    
    def strategy_change_viewport_and_scroll(self, driver, url):
        """Stratégie 5: Changer la taille de la fenêtre et faire défiler"""
        logging.info("📱 Stratégie: Changement de viewport et défilement...")
        try:
            # Changer la taille de la fenêtre
            resolutions = [(1920, 1080), (1366, 768), (1536, 864), (1280, 720), (1440, 900)]
            width, height = random.choice(resolutions)
            driver.set_window_size(width, height)
            
            time.sleep(random.uniform(2, 4))
            
            # Défilement naturel
            total_height = driver.execute_script("return document.body.scrollHeight")
            viewport_height = driver.execute_script("return window.innerHeight")
            
            scroll_steps = random.randint(3, 8)
            scroll_distance = total_height / scroll_steps
            
            for i in range(scroll_steps):
                scroll_to = int(i * scroll_distance)
                driver.execute_script(f"window.scrollTo(0, {scroll_to});")
                time.sleep(random.uniform(1, 3))
            
            # Retour en haut
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(random.uniform(2, 4))
            return True
            
        except Exception as e:
            logging.error(f"Erreur lors du changement de viewport: {e}")
            return False

def setup_chrome_driver(headless=False):
    """Configuration avancée du driver Chrome pour éviter les captchas"""
    chrome_options = Options()
    
    # Options avancées anti-détection
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # User agents plus récents et variés
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
    ]
    
    chrome_options.add_argument(f"--user-agent={random.choice(user_agents)}")
    
    # Options anti-captcha renforcées
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_argument("--disable-javascript")  # Peut aider contre certains captchas JS
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    chrome_options.add_argument("--disable-ipc-flooding-protection")
    
    # Proxy rotatif (optionnel - décommentez si vous avez des proxies)
    # proxy_list = ["proxy1:port", "proxy2:port"]  # Ajoutez vos proxies ici
    # if proxy_list:
    #     proxy = random.choice(proxy_list)
    #     chrome_options.add_argument(f"--proxy-server={proxy}")
    
    # Résolution aléatoire
    resolutions = ["1920,1080", "1366,768", "1536,864", "1440,900", "1280,720"]
    chrome_options.add_argument(f"--window-size={random.choice(resolutions)}")
    
    # Préférences avancées
    prefs = {
        "profile.default_content_setting_values": {
            "popups": 2,
            "notifications": 2,
            "media_stream": 2,
            "images": 2,
            "plugins": 2,
            "geolocation": 2,
            "microphone": 2,
            "camera": 2
        },
        "profile.managed_default_content_settings": {
            "images": 2
        },
        "profile.default_content_settings": {
            "popups": 0
        }
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    # Mode headless conditionnel
    if headless:
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--window-size=1920,1080")
    
    # Service avec WebDriverManager
    service = Service(ChromeDriverManager().install())
    
    # Créer le driver
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Scripts anti-détection avancés
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
    driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en', 'fr-FR']})")
    driver.execute_script("Object.defineProperty(navigator, 'platform', {get: () => 'Win32'})")
    driver.execute_script("Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 4})")
    
    # Simuler une connexion réseau réaliste - Version corrigée
    try:
        # Essayer d'abord avec Network.setConnectionType (ancienne méthode)
        driver.execute_cdp_cmd('Network.setConnectionType', {
            'type': 'wifi',
            'downlinkThroughputKbps': random.randint(1000, 5000),
            'uplinkThroughputKbps': random.randint(500, 1000)
        })
        logging.info("✅ Configuration réseau appliquée avec Network.setConnectionType")
    except Exception as e:
        logging.warning(f"⚠️ Network.setConnectionType non supporté: {e}")
        try:
            # Méthode alternative pour simuler la vitesse réseau
            driver.execute_cdp_cmd('Network.emulateNetworkConditions', {
                'offline': False,
                'latency': random.randint(20, 100),
                'downloadThroughput': random.randint(1000000, 5000000),  # En bytes/s
                'uploadThroughput': random.randint(500000, 1000000)      # En bytes/s
            })
            logging.info("✅ Configuration réseau appliquée avec Network.emulateNetworkConditions")
        except Exception as e2:
            logging.warning(f"⚠️ Impossible de configurer les conditions réseau: {e2}")
            # Continuer sans configuration réseau si les deux méthodes échouent
    
    return driver

def detect_captcha(driver):
    """Détection avancée des captchas"""
    captcha_selectors = [
        "iframe[src*='recaptcha']",
        "iframe[src*='hcaptcha']",
        ".g-recaptcha",
        ".h-captcha",
        ".captcha",
        ".hcaptcha",
        "[data-captcha]",
        ".cf-browser-verification",
        "#challenge-form",
        ".challenge-form",
        "div[data-hcaptcha-widget-id]",
        "div.cf-challenge",
        ".cloudflare-challenge",
        "[data-sitekey]",
        ".captcha-container",
        ".captcha-wrapper",
        "#captcha",
        ".recaptcha",
        "div[class*='captcha']",
        "div[id*='captcha']",
        ".challenge-running",
        ".challenge-stage",
        "div[data-ray]",  # Cloudflare Ray ID
        ".cf-error-details"
    ]
    
    # Détection par texte
    captcha_texts = [
        "verify you are human",
        "security check",
        "captcha",
        "challenge",
        "please wait",
        "checking your browser",
        "cloudflare",
        "protection",
        "robot",
        "automated"
    ]
    
    try:
        # Vérification des sélecteurs
        for selector in captcha_selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                logging.warning(f"🤖 Captcha détecté avec le sélecteur: {selector}")
                return True
        
        # Vérification du texte de la page
        page_source = driver.page_source.lower()
        for text in captcha_texts:
            if text in page_source:
                logging.warning(f"🤖 Captcha détecté avec le texte: {text}")
                return True
        
        # Vérification des titres de page suspects
        title = driver.title.lower()
        if any(word in title for word in ["challenge", "security", "verify", "captcha"]):
            logging.warning(f"🤖 Captcha détecté dans le titre: {title}")
            return True
        
        # Vérification de l'URL
        current_url = driver.current_url.lower()
        if any(word in current_url for word in ["challenge", "captcha", "security"]):
            logging.warning(f"🤖 Captcha détecté dans l'URL: {current_url}")
            return True
            
    except Exception as e:
        logging.debug(f"Erreur lors de la détection de captcha: {e}")
    
    return False

def handle_captcha_detection(driver, url, retries=5):
    """Gestion avancée des captchas avec multiple stratégies"""
    captcha_manager = CaptchaBypassManager()
    
    if not detect_captcha(driver):
        return True
    
    logging.warning("🤖 Captcha détecté! Démarrage des stratégies de contournement...")
    
    for attempt in range(retries):
        logging.info(f"⏳ Tentative {attempt + 1}/{retries} de contournement...")
        
        # Utiliser une stratégie différente à chaque tentative
        strategy_index = attempt % len(captcha_manager.bypass_strategies)
        strategy = captcha_manager.bypass_strategies[strategy_index]
        
        try:
            # Appliquer la stratégie
            strategy(driver, url)
            
            # Attendre un délai aléatoire plus long
            wait_time = random.uniform(20, 40)
            logging.info(f"⏱️ Attente de {wait_time:.1f}s après la stratégie...")
            time.sleep(wait_time)
            
            # Vérifier si le captcha a été contourné
            if not detect_captcha(driver):
                logging.info("✅ Captcha contourné avec succès!")
                return True
            
        except Exception as e:
            logging.error(f"❌ Erreur lors de l'application de la stratégie: {e}")
            continue
    
    # Si toutes les stratégies échouent, essayer une dernière fois avec un nouveau driver
    logging.warning("🔄 Toutes les stratégies ont échoué. Tentative avec un nouveau driver...")
    
    try:
        driver.quit()
        time.sleep(random.uniform(30, 60))
        new_driver = setup_chrome_driver()
        driver = new_driver
        driver.get(url)
        time.sleep(random.uniform(10, 20))
        
        if not detect_captcha(driver):
            logging.info("✅ Captcha contourné avec un nouveau driver!")
            return True
            
    except Exception as e:
        logging.error(f"❌ Erreur lors de la création d'un nouveau driver: {e}")
    
    logging.error("❌ Impossible de contourner le captcha après toutes les tentatives.")
    return False

def check_internet_connection():
    """Vérifier la connexion Internet"""
    try:
        requests.get("https://www.google.com", timeout=5)
        return True
    except:
        return False

def scrape_manga_chapters_safe(driver, manga_url, manga_title):
    """Scrape les chapitres d'un manga avec gestion avancée du captcha"""
    chapters = []
    
    try:
        logging.info(f"📖 Récupération des chapitres de: {manga_title}")
        
        # Vérifier la connexion Internet
        if not check_internet_connection():
            logging.error("❌ Pas de connexion Internet")
            return []
        
        # Délai aléatoire avant la requête
        initial_delay = random.uniform(3, 8)
        logging.info(f"⏱️ Délai initial: {initial_delay:.1f}s")
        time.sleep(initial_delay)
        
        # Naviguer vers la page du manga
        driver.get(manga_url)
        
        # Attendre le chargement de la page
        wait = WebDriverWait(driver, 30)
        time.sleep(random.uniform(5, 10))
        
        # Vérifier et gérer les captchas
        if not handle_captcha_detection(driver, manga_url):
            logging.warning(f"❌ Captcha non résolu pour {manga_title}. Passage au manga suivant.")
            return []
        
        # Rechercher tous les liens de chapitres
        try:
            # Attendre qu'au moins un élément de chapitre soit visible
            chapter_elements = wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.project__chapter.unstyled-link"))
            )
            
            logging.info(f"📄 {len(chapter_elements)} éléments de chapitre trouvés")
            
            for element in chapter_elements:
                try:
                    # Obtenir le lien du chapitre
                    chapter_url = element.get_attribute("href")
                    
                    # Obtenir le titre du chapitre
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

def scrape_all_chapters(manga_data, start_from=0, max_mangas=None, headless_mode=False):
    """Scrape tous les chapitres avec gestion avancée du captcha"""
    
    driver = setup_chrome_driver(headless=headless_mode)
    initial_manga_data = list(manga_data)

    try:
        logging.info("🚀 Lancement du scraping des chapitres avec protection anti-captcha avancée...")
        
        # Ajuster les données de manga selon start_from et max_mangas
        mangas_to_process = manga_data[start_from:]
        if max_mangas:
            mangas_to_process = mangas_to_process[:max_mangas]

        total_mangas_to_process = len(mangas_to_process)
        
        success_count = 0
        captcha_or_error_count = 0
        
        for i, manga in enumerate(mangas_to_process):
            current_index = start_from + i
            logging.info(f"\n📚 [{current_index + 1}/{total_mangas_to_process + start_from}] Traitement de: {manga['title']}")
            
            # Récupérer les chapitres avec gestion du captcha
            chapters = scrape_manga_chapters_safe(driver, manga['url'], manga['title'])
            
            # Mettre à jour les données
            manga_copy = manga.copy()
            manga_copy['chapters'] = chapters
            manga_copy['chapters_scraped_at'] = datetime.now().isoformat()
            
            # Remplacer l'entrée manga originale par la version mise à jour
            initial_manga_data[current_index] = manga_copy
            
            if chapters:
                success_count += 1
            else:
                captcha_or_error_count += 1
            
            # Sauvegarde progressive tous les 5 mangas
            if (i + 1) % 5 == 0:
                save_progress(initial_manga_data, f"progress_backup_{current_index + 1}.json")
                logging.info(f"💾 Sauvegarde de progression effectuée ({current_index + 1} mangas traités)")
            
            # Délai aléatoire entre les requêtes (plus long pour éviter les captchas)
            if i < len(mangas_to_process) - 1:  # Pas de délai après le dernier manga
                delay = random.uniform(5, 15)
                logging.info(f"⏱️ Pause de {delay:.1f}s...")
                time.sleep(delay)
            
            # Pause longue tous les 10 mangas
            if (i + 1) % 10 == 0:
                long_delay = random.uniform(60, 120)
                logging.info(f"😴 Pause longue de {long_delay:.1f}s pour éviter la détection...")
                time.sleep(long_delay)
                
        logging.info(f"\n🎉 Scraping terminé!")
        logging.info(f"✅ Succès: {success_count}/{total_mangas_to_process}")
        logging.info(f"🤖 Captchas/Erreurs: {captcha_or_error_count}/{total_mangas_to_process}")
        
        return initial_manga_data
        
    except KeyboardInterrupt:
        logging.warning("\n⚠️ Arrêt demandé par l'utilisateur")
        logging.info(f"💾 Sauvegarde des données déjà récupérées...")
        save_progress(initial_manga_data, f"progress_backup_interrupted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        return initial_manga_data
        
    except Exception as e:
        logging.critical(f"💥 Erreur critique lors du scraping: {e}", exc_info=True)
        logging.info(f"💾 Sauvegarde des données déjà récupérées...")
        save_progress(initial_manga_data, f"progress_backup_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        return initial_manga_data
        
    finally:
        logging.info("🔒 Fermeture du navigateur...")
        try:
            driver.quit()
        except:
            pass

def save_progress(data, filename):
    """Sauvegarde progressive des données"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logging.info(f"💾 Progression sauvegardée dans {filename}")
    except Exception as e:
        logging.error(f"❌ Erreur lors de la sauvegarde de la progression dans {filename}: {e}")

def save_chapters_json(manga_data, filename="phenix_manga_chapters_collection_mega_fun.json"):
    """Sauvegarde les données avec chapitres dans un nouveau fichier JSON"""
    
    try:
        # Calculer le total des chapitres
        total_chapters = sum(len(manga.get('chapters', [])) for manga in manga_data)
        successful_manga = len([m for m in manga_data if m.get('chapters')])
        
        # Créer l'objet de données final
        final_data = {
            "metadata": {
                "source": "https://phenix-scans.com/manga",
                "scraped_at": datetime.now().isoformat(),
                "total_mangas_in_file": len(manga_data),
                "successful_mangas_with_chapters": successful_manga,
                "total_chapters_scraped": total_chapters,
                "description": "Collection épique de mangas avec TOUS les chapitres scrapés! 🎌⚡📚 - Version Anti-Captcha Avancée"
            },
            "mangas": manga_data
        }
        
        # Sauvegarder en JSON
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
    logging.info("🎌 === PHENIX SCANS CHAPTERS SCRAPER ANTI-CAPTCHA MEGA PRO === 🎌")
    
    # Charger les données de manga
    manga_data = load_manga_data()
    
    if not manga_data:
        logging.error("❌ Aucune donnée de manga trouvée pour démarrer le scraping!")
        return
    
    # Demander les options à l'utilisateur
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
    
    # Scraper tous les chapitres
    updated_manga_data = scrape_all_chapters(manga_data, start_from, max_mangas, headless_mode)
    
    if updated_manga_data:
        # Sauvegarder dans un nouveau fichier JSON
        save_chapters_json(updated_manga_data)
        
        # Afficher des statistiques amusantes
        logging.info("\n🎉 === STATISTIQUES ANTI-CAPTCHA MEGA PRO === 🎉")
        
        total_chapters = sum(len(manga.get('chapters', [])) for manga in updated_manga_data)
        successful_manga = len([m for m in updated_manga_data if m.get('chapters')])
        
        logging.info(f"🏆 Mangas traités: {len(updated_manga_data)}")
        logging.info(f"✅ Mangas avec succès: {successful_manga}")
        logging.info(f"📚 Chapitres totaux récupérés: {total_chapters}")
        
        if updated_manga_data:
            # Trouver le manga avec le plus de chapitres
            mangas_with_chapters = [m for m in updated_manga_data if m.get('chapters')]
            if mangas_with_chapters:
                max_chapters_manga = max(mangas_with_chapters, key=lambda m: len(m['chapters']))
                logging.info(f"👑 Manga avec le plus de chapitres: {max_chapters_manga['title']} ({len(max_chapters_manga['chapters'])} chapitres)")
                
                # Statistiques additionnelles
                avg_chapters = total_chapters / successful_manga if successful_manga > 0 else 0
                logging.info(f"📊 Moyenne de chapitres par manga: {avg_chapters:.1f}")
                
                # Calculer le taux de succès
                success_rate = (successful_manga / len(updated_manga_data)) * 100 if len(updated_manga_data) > 0 else 0
                logging.info(f"📈 Taux de succès: {success_rate:.1f}%")
                
            else:
                logging.info("😢 Aucun manga n'a pu être scrapé avec des chapitres.")
            
        logging.info("\n🚀 Mission accomplie! Tous les chapitres ont été capturés malgré les captchas! 🚀")
        logging.info("🛡️ Système anti-captcha avancé: SUCCÈS TOTAL! 🛡️")
        
    else:
        logging.error("😢 Aucun chapitre n'a pu être récupéré. Veuillez vérifier l'URL ou les sélecteurs.")

if __name__ == "__main__":
    main()