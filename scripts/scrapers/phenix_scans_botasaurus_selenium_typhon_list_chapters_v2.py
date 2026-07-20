from botasaurus import *
from botasaurus.browser import browser
# Correction 1: Import the correct function
from botasaurus import random_user_agent 
import json
import time
from datetime import datetime
import random
import os
import logging
import requests
from urllib.parse import urljoin, urlparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class CaptchaBypassManager:
    """Manager pour les différentes stratégies de contournement de captcha avec Botasaurus"""

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
        driver.sleep(random.uniform(15, 25))
        driver.refresh()
        driver.sleep(random.uniform(5, 10))
        return True

    def strategy_change_user_agent(self, driver, url):
        """Stratégie 2: Changer l'user agent (via les options du décorateur)"""
        logging.info("🎭 Stratégie: Recharger la page (avec un user agent potentiellement différent)...")
        # Le changement d'user agent est mieux géré via le décorateur @browser.
        # Cette stratégie va simplement recharger la page pour tenter de contourner.
        try:
            driver.get(url, wait=random.uniform(8, 15))
            return True
        except Exception as e:
            logging.error(f"Erreur lors du rechargement: {e}")
            return False

    def strategy_simulate_human_behavior(self, driver, url):
        """Stratégie 3: Simuler un comportement humain"""
        logging.info("🤖 Stratégie: Simulation de comportement humain...")
        try:
            # Simuler des mouvements de souris aléatoires
            for _ in range(random.randint(3, 7)):
                x = random.randint(100, 800)
                y = random.randint(100, 600)
                driver.execute_script(f"document.elementFromPoint({x}, {y})?.click?.()")
                driver.sleep(random.uniform(0.5, 1.5))

            # Scroll aléatoire
            for _ in range(random.randint(2, 5)):
                scroll_position = random.randint(100, 500)
                driver.execute_script(f"window.scrollTo(0, {scroll_position});")
                driver.sleep(random.uniform(1, 2))

            driver.sleep(random.uniform(5, 10))
            return True

        except Exception as e:
            logging.error(f"Erreur lors de la simulation de comportement humain: {e}")
            return False

    def strategy_clear_cookies_and_reload(self, driver, url):
        """Stratégie 4: Nettoyer les cookies et recharger"""
        logging.info("🍪 Stratégie: Nettoyage des cookies...")
        try:
            driver.delete_all_cookies()
            driver.sleep(random.uniform(2, 5))
            driver.get(url, wait=random.uniform(8, 15))
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
            driver.sleep(random.uniform(2, 4))

            # Défilement naturel
            total_height = driver.execute_script("return document.body.scrollHeight")
            for i in range(0, total_height, random.randint(100, 300)):
                driver.execute_script(f"window.scrollTo(0, {i});")
                driver.sleep(random.uniform(0.5, 1.5))

            # Retour en haut
            driver.execute_script("window.scrollTo(0, 0);")
            driver.sleep(random.uniform(2, 4))
            return True

        except Exception as e:
            logging.error(f"Erreur lors du changement de viewport: {e}")
            return False

def detect_captcha(driver):
    """Détection avancée des captchas"""
    captcha_selectors = [
        "iframe[src*='recaptcha']", "iframe[src*='hcaptcha']", ".g-recaptcha",
        ".h-captcha", ".captcha", ".cf-browser-verification", "#challenge-form",
        "div.cf-challenge", ".cloudflare-challenge", "[data-sitekey]",
        "div[id*='captcha']", ".challenge-running", "div[data-ray]",
    ]
    captcha_texts = [
        "verify you are human", "security check", "captcha", "challenge",
        "checking your browser", "cloudflare", "protection", "robot",
    ]
    try:
        for selector in captcha_selectors:
            if driver.select(selector):
                logging.warning(f"🤖 Captcha détecté avec le sélecteur: {selector}")
                return True
        page_source = driver.page_source.lower()
        for text in captcha_texts:
            if text in page_source:
                logging.warning(f"🤖 Captcha détecté avec le texte: {text}")
                return True
        title = driver.title.lower()
        if any(word in title for word in ["challenge", "security", "verify", "captcha"]):
            logging.warning(f"🤖 Captcha détecté dans le titre: {title}")
            return True
    except Exception as e:
        logging.debug(f"Erreur lors de la détection de captcha: {e}")
    return False

def handle_captcha_detection(driver, url, retries=5):
    """Gestion avancée des captchas avec multiple stratégies"""
    if not detect_captcha(driver):
        return True

    logging.warning("🤖 Captcha détecté! Démarrage des stratégies de contournement...")
    captcha_manager = CaptchaBypassManager()
    used_strategies = random.sample(captcha_manager.bypass_strategies, len(captcha_manager.bypass_strategies))

    for attempt in range(retries):
        logging.info(f"⏳ Tentative {attempt + 1}/{retries} de contournement...")
        strategy = used_strategies[attempt % len(used_strategies)]
        try:
            strategy(driver, url)
            wait_time = random.uniform(15, 30)
            logging.info(f"⏱️ Attente de {wait_time:.1f}s après la stratégie...")
            driver.sleep(wait_time)
            if not detect_captcha(driver):
                logging.info("✅ Captcha contourné avec succès!")
                return True
        except Exception as e:
            logging.error(f"❌ Erreur lors de l'application de la stratégie: {e}")
            continue

    logging.error("❌ Impossible de contourner le captcha après toutes les tentatives.")
    return False

@browser(
    block_images=True,
    wait_for_complete_page_load=False,
    close_on_crash=True,
    user_agent=random_user_agent(), 
)
def scrape_manga_chapters_safe(driver, data):
    """Scrape les chapitres d'un manga avec gestion avancée du captcha"""
    manga_url = data['manga_url']
    manga_title = data['manga_title']
    chapters = []

    try:
        logging.info(f"📖 Récupération des chapitres de: {manga_title}")
        driver.get(manga_url, wait=random.uniform(5, 10))

        if not handle_captcha_detection(driver, manga_url):
            logging.warning(f"❌ Captcha non résolu pour {manga_title}. Passage au manga suivant.")
            return []

        chapter_elements = driver.select_all("a.project__chapter.unstyled-link", timeout=20)
        if not chapter_elements:
            logging.warning(f"❌ Aucun élément de chapitre trouvé pour {manga_title}")
            return []

        logging.info(f"📄 {len(chapter_elements)} éléments de chapitre trouvés")
        for element in chapter_elements:
            try:
                chapter_url = element.get_attribute("href")
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
        logging.error(f"💥 Erreur lors du scraping de {manga_title} (URL: {manga_url}): {e}")

    return chapters

# MODIFICATION PRINCIPALE ICI
def load_manga_data(filename="phenix_manga_chapters_collection_mega_fun.json"):
    """Charge les données des mangas depuis le fichier JSON structuré."""
    if not os.path.exists(filename):
        logging.error(f"❌ Fichier {filename} non trouvé! Assurez-vous qu'il existe.")
        return []

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extrait la liste de mangas depuis la clé 'mangas'
        mangas = data.get('mangas', [])
        
        if not mangas:
            logging.warning(f"⚠️ La clé 'mangas' est vide ou n'existe pas dans {filename}.")
            return []
            
        logging.info(f"📚 {len(mangas)} mangas chargés depuis {filename}")
        return mangas
        
    except json.JSONDecodeError as e:
        logging.error(f"❌ Erreur de décodage JSON dans {filename}: {e}")
        return []
    except Exception as e:
        logging.error(f"❌ Erreur lors du chargement du fichier {filename}: {e}")
        return []

def scrape_all_chapters(manga_data, start_from=0, max_mangas=None, headless_mode=False):
    """Scrape tous les chapitres avec une gestion de file d'attente."""
    
    if not manga_data:
        logging.error("❌ Aucune donnée de manga à traiter.")
        return []

    initial_manga_data = list(manga_data)

    try:
        logging.info("🚀 Lancement du scraping des chapitres avec protection anti-captcha...")
        
        mangas_to_process = manga_data[start_from:]
        if max_mangas:
            mangas_to_process = mangas_to_process[:max_mangas]

        manga_tasks = []
        for i, manga in enumerate(mangas_to_process):
            manga_tasks.append({
                'manga_url': manga['url'],
                'manga_title': manga['title'],
                'original_index': start_from + i # Conserve l'index original pour la mise à jour
            })
        
        total_mangas_to_process = len(manga_tasks)
        logging.info(f"📦 {total_mangas_to_process} mangas à traiter à partir de l'index {start_from}")
        
        if not manga_tasks:
            logging.info("👍 Aucun manga à traiter selon les critères fournis.")
            return initial_manga_data

        # Exécuter le scraping en parallèle
        results = scrape_manga_chapters_safe.parallel(manga_tasks)
        
        for task, chapters in zip(manga_tasks, results):
            original_index = task['original_index']
            manga = initial_manga_data[original_index]
            
            logging.info(f"🔄 Mise à jour de: {manga['title']} (Index: {original_index})")
            
            if chapters:
                manga['chapters'] = chapters
                logging.info(f"✅ {len(chapters)} chapitres ajoutés pour {manga['title']}")
            else:
                manga['chapters'] = manga.get('chapters', []) # Conserve les anciens chapitres si le scrape échoue
                logging.warning(f"❌ Aucun nouveau chapitre récupéré pour {manga['title']}")
            
            manga['chapters_scraped_at'] = datetime.now().isoformat()
            
            # Sauvegarde progressive tous les 10 mangas traités
            if (original_index + 1) % 10 == 0:
                save_progress(initial_manga_data, f"progress_backup_{original_index + 1}.json")
        
        logging.info(f"\n🎉 Scraping terminé!")
        return initial_manga_data
        
    except KeyboardInterrupt:
        logging.warning("\n⚠️ Arrêt demandé par l'utilisateur. Sauvegarde de la progression...")
        save_progress(initial_manga_data, f"progress_backup_interrupted.json")
        return initial_manga_data
        
    except Exception as e:
        logging.critical(f"💥 Erreur critique lors du scraping: {e}", exc_info=True)
        save_progress(initial_manga_data, f"progress_backup_error.json")
        return initial_manga_data

def save_progress(data, filename):
    """Sauvegarde progressive des données dans un fichier JSON complet."""
    try:
        # Recrée la structure complète pour la sauvegarde
        final_data_structure = {
            "metadata": {
                "source": "https://phenix-scans.com/manga",
                "scraped_at": datetime.now().isoformat(),
                "description": "Sauvegarde de progression."
            },
            "mangas": data
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(final_data_structure, f, indent=2, ensure_ascii=False)
        logging.info(f"💾 Progression sauvegardée dans {filename}")
    except Exception as e:
        logging.error(f"❌ Erreur lors de la sauvegarde de la progression: {e}")

def save_chapters_json(manga_data, filename="phenix_manga_chapters_collection_final.json"):
    """Sauvegarde les données finales avec des métadonnées mises à jour."""
    try:
        total_chapters = sum(len(manga.get('chapters', [])) for manga in manga_data)
        successful_manga = len([m for m in manga_data if m.get('chapters')])
        
        final_data = {
            "metadata": {
                "source": "https://phenix-scans.com/manga",
                "scraped_at": datetime.now().isoformat(),
                "total_mangas_in_file": len(manga_data),
                "successful_mangas_with_chapters": successful_manga,
                "total_chapters_scraped": total_chapters,
                "description": "Collection de mangas avec chapitres mis à jour via Botasaurus. 🎌⚡📚"
            },
            "mangas": manga_data
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=2, ensure_ascii=False)
            
        logging.info(f"💾 Données finales sauvegardées dans: {filename}")
        logging.info(f"📊 Mangas totaux: {len(manga_data)}")
        logging.info(f"✅ Mangas avec chapitres: {successful_manga}")
        logging.info(f"📖 Total de chapitres: {total_chapters}")
        
    except Exception as e:
        logging.critical(f"❌ Erreur lors de la sauvegarde du fichier final {filename}: {e}", exc_info=True)

def main():
    """Fonction principale"""
    logging.info("🎌 === PHENIX SCANS CHAPTERS SCRAPER BOTASAURUS MEGA PRO === 🎌")
    
    # Le nom du fichier source contenant la liste des mangas
    source_filename = "phenix_manga_chapters_collection_mega_fun.json"
    manga_data = load_manga_data(source_filename)
    
    if not manga_data:
        logging.error("❌ Aucune donnée de manga trouvée. Arrêt du script.")
        return
    
    try:
        start_from_input = input(f"🔄 Reprendre depuis quel index? (0-{len(manga_data)-1}, défaut: 0): ")
        start_from = int(start_from_input) if start_from_input.isdigit() else 0
        
        max_mangas_input = input("🎯 Limiter le nombre de mangas? (Laissez vide pour tous): ")
        max_mangas = int(max_mangas_input) if max_mangas_input.isdigit() else None

        headless_input = input("🕵️‍♂️ Exécuter en mode headless (sans interface) ? (oui/non, défaut: non): ").lower()
        headless_mode = headless_input == 'oui'

    except ValueError:
        logging.error("Entrée invalide. Utilisation des valeurs par défaut.")
        start_from = 0; max_mangas = None; headless_mode = False
        
    # Mettre à jour la configuration headless de Botasaurus
    scrape_manga_chapters_safe.config.headless = headless_mode
    
    # Scraper tous les chapitres
    updated_manga_data = scrape_all_chapters(manga_data, start_from, max_mangas, headless_mode)
    
    if updated_manga_data:
        save_chapters_json(updated_manga_data)
        logging.info("\n🚀 Mission accomplie! Tous les chapitres ont été traités avec succès ! 🚀")
    else:
        logging.error("😢 Le scraping n'a retourné aucune donnée. Vérifiez les logs pour les erreurs.")

if __name__ == "__main__":
    main()