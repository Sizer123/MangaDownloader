import requests
import os
import time
import random
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import logging
from fake_useragent import UserAgent
import cloudscraper
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import certifi
import warnings
import urllib3
import ssl
from webdriver_manager.chrome import ChromeDriverManager

# Désactivation complète des vérifications SSL
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore')

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MangaDownloader:
    def __init__(self, use_selenium=False):
        self.session = requests.Session()
        self.ua = UserAgent()
        self.use_selenium = use_selenium
        self.driver = None
        
        # Configuration des sessions
        self.setup_requests_session()
        self.scraper = self.setup_cloudscraper()
        
        if self.use_selenium:
            self.setup_selenium()

    def setup_requests_session(self):
        """Configure la session requests avec SSL désactivé"""
        self.session.verify = False
        self.session.headers.update({
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
            'Referer': 'https://www.google.com/',
        })

    def setup_cloudscraper(self):
        """Configure cloudscraper avec SSL désactivé"""
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True,
            }
        )
        scraper.verify = False
        return scraper

    def setup_selenium(self):
        """Configure Selenium avec WebDriver Manager"""
        try:
            options = Options()
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument(f"user-agent={self.ua.random}")
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            
            self.driver = webdriver.Chrome(
                service=webdriver.chrome.service.Service(ChromeDriverManager().install()),
                options=options
            )
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            logger.info("Selenium initialisé avec succès")
        except Exception as e:
            logger.error(f"Échec initialisation Selenium: {e}")
            self.use_selenium = False

    def safe_request(self, url, max_retries=3):
        """Nouvelle version sans ssl_context qui fonctionne avec cloudscraper"""
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(random.uniform(1, 3))

                # Tentative avec cloudscraper
                try:
                    response = self.scraper.get(url)
                    if response.status_code == 200:
                        return response
                except Exception as e:
                    logger.warning(f"Cloudscraper attempt {attempt+1} failed: {e}")

                # Fallback avec requests
                response = self.session.get(url)
                if response.status_code == 200:
                    return response

            except requests.exceptions.SSLError as e:
                logger.error(f"Erreur SSL (tentative {attempt+1}): {e}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Erreur requête (tentative {attempt+1}): {e}")

        # Fallback Selenium
        if self.use_selenium:
            return self.selenium_fallback(url)
        return None

    def selenium_fallback(self, url):
        """Utilise Selenium comme dernier recours"""
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body')))
            return type('obj', (object,), {
                'content': self.driver.page_source.encode('utf-8'),
                'status_code': 200
            })
        except Exception as e:
            logger.error(f"Échec Selenium: {e}")
            return None

    def get_manga_title(self, url):
        """Récupère le titre du manga"""
        try:
            response = self.safe_request(url)
            if not response:
                return "manga_inconnu"
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            selectors = [
                'h1.entry-title', 'h1.manga-title', 'h1.post-title', 'h1',
                '.manga-title', '.entry-title', '.post-title'
            ]
            
            for selector in selectors:
                title = soup.select_one(selector)
                if title:
                    return self.sanitize_filename(title.get_text(strip=True))
            
            return "manga_inconnu"
        except Exception as e:
            logger.error(f"Erreur titre: {e}")
            return "manga_inconnu"

    def download_image(self, img_url, file_path):
        """Télécharge une image avec gestion simplifiée"""
        try:
            headers = {
                'User-Agent': self.ua.random,
                'Referer': urlparse(img_url).scheme + '://' + urlparse(img_url).netloc + '/',
            }

            # Tentative avec cloudscraper
            try:
                response = self.scraper.get(img_url, headers=headers, stream=True)
                if response.status_code == 200:
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(1024):
                            f.write(chunk)
                    return True
            except Exception as e:
                logger.warning(f"Cloudscraper image failed: {e}")

            # Fallback Selenium
            if self.use_selenium:
                self.driver.get(img_url)
                time.sleep(2)
                self.driver.find_element(By.TAG_NAME, 'img').screenshot(file_path)
                return True

        except Exception as e:
            logger.error(f"Erreur téléchargement image: {e}")
        return False

    # ... [autres méthodes identiques à la version précédente] ...

def main():
    try:
        manga_url = "https://phenix-scans.com/manga/a-modern-man-who-transmigrated-into-the-murim-world"
        downloader = MangaDownloader(use_selenium=True)
        downloader.download_manga(manga_url, max_chapters=3)
    except Exception as e:
        logger.error(f"Erreur principale: {e}")

if __name__ == "__main__":
    main()