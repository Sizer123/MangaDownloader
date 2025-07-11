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

# Désactivation des warnings SSL
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

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
        self.scraper = cloudscraper.create_scraper()
        
        # Configuration SSL
        self.ssl_verify = True  # Par défaut, on vérifie les certificats
        self.certifi_path = certifi.where()
        
        if self.use_selenium:
            self.setup_selenium()
        else:
            self.setup_session()
    
    def setup_selenium(self):
        """Configure Selenium avec des options pour éviter la détection"""
        logger.info("Configuration de Selenium...")
        self.chrome_options = Options()
        
        # Options pour éviter la détection
        self.chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        self.chrome_options.add_argument(f"user-agent={self.ua.random}")
        self.chrome_options.add_argument("--window-size=1920,1080")
        self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--disable-gpu")
        self.chrome_options.add_argument("--disable-dev-shm-usage")
        self.chrome_options.add_argument("--no-sandbox")
        
        # Désactiver les logs inutiles
        self.chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        # Initialisation du driver
        self.driver = webdriver.Chrome(options=self.chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    def setup_session(self):
        """Configure la session avec headers et cookies"""
        headers = {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
            'Referer': 'https://www.google.com/',
        }
        self.session.headers.update(headers)
        self.session.verify = self.certifi_path  # Utilise les certificats de certifi
        self.session.timeout = 30
        
        # Configuration de CloudScraper
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True,
            }
        )
    
    def rotate_user_agent(self):
        """Change l'User-Agent"""
        new_ua = self.ua.random
        self.session.headers['User-Agent'] = new_ua
        if self.use_selenium:
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": new_ua})
    
    def get_page_with_retry(self, url, max_retries=5):
        """Récupère une page avec gestion des erreurs SSL"""
        for attempt in range(max_retries):
            try:
                self.rotate_user_agent()
                
                if attempt > 0:
                    delay = random.uniform(2, 10)
                    logger.info(f"Tentative {attempt + 1}/{max_retries} - Attente de {delay:.1f}s...")
                    time.sleep(delay)
                
                # Essai avec vérification SSL
                try:
                    response = self.session.get(url, verify=self.certifi_path)
                    if response.status_code == 200:
                        return response
                except requests.exceptions.SSLError:
                    logger.warning("Échec de vérification SSL, tentative sans vérification...")
                    response = self.session.get(url, verify=False)
                    return response
                
                # Si on arrive ici, c'est qu'il y a une autre erreur
                if response.status_code in [403, 429, 503]:
                    logger.warning(f"Erreur {response.status_code} - Tentative {attempt + 1}/{max_retries}")
                    self.try_different_headers()
                    continue
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Erreur de requête: {e}")
                if attempt < max_retries - 1:
                    time.sleep(random.uniform(3, 8))
                    continue
                    
        # Si toutes les tentatives échouent, essayer avec Selenium
        if self.use_selenium:
            return self.fallback_to_selenium(url)
        return None
    
    def fallback_to_selenium(self, url):
        """Utilise Selenium comme solution de secours"""
        try:
            logger.info("Essai avec Selenium...")
            self.driver.get(url)
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body')))
            return type('obj', (object,), {
                'content': self.driver.page_source.encode('utf-8'),
                'status_code': 200
            })
        except Exception as e:
            logger.error(f"Échec de Selenium: {e}")
            return None
    
    # ... (le reste des méthodes reste inchangé)

    def download_image(self, img_url, file_path):
        """Télécharge une image avec gestion SSL"""
        try:
            headers = {
                'User-Agent': self.ua.random,
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Referer': urlparse(img_url).scheme + '://' + urlparse(img_url).netloc + '/',
            }
            
            # Essai avec vérification SSL
            try:
                response = self.scraper.get(img_url, headers=headers, stream=True, verify=self.certifi_path)
            except requests.exceptions.SSLError:
                logger.warning("Échec de vérification SSL pour l'image, tentative sans vérification...")
                response = self.scraper.get(img_url, headers=headers, stream=True, verify=False)
            
            if response.status_code == 200:
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                return True
            
            # Solution de secours avec Selenium
            if self.use_selenium:
                try:
                    self.driver.get(img_url)
                    time.sleep(3)
                    img_element = self.driver.find_element(By.TAG_NAME, 'img')
                    img_element.screenshot(file_path)
                    return True
                except Exception as e:
                    logger.error(f"Échec du téléchargement avec Selenium: {e}")
            
        except Exception as e:
            logger.error(f"Erreur lors du téléchargement de l'image: {e}")
        return False

def main():
    manga_url = "https://phenix-scans.com/manga/a-modern-man-who-transmigrated-into-the-murim-world"
    downloader = MangaDownloader(use_selenium=True)
    downloader.download_manga(manga_url, max_chapters=3)

if __name__ == "__main__":
    main()