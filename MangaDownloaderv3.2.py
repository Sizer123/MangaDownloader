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

# Désactivation des warnings
warnings.filterwarnings('ignore')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context
# Désactivation des warnings SSL
requests.packages.urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# Désactivation des warnings SSL
ssl._create_default_https_context = ssl._create_unverified_context
# Désactivation des warnings SSL    
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# Désactivation des warnings SSL
warnings.filterwarnings('ignore', message='Unverified HTTPS request')
ssl._create_default_https_context = ssl._create_unverified_context

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
        self.driver = None
        
        # Configuration
        self.ssl_verify = False
        self.certifi_path = certifi.where()
        
        if self.use_selenium:
            self.setup_selenium()
        self.setup_session()
    
    def setup_selenium(self):
        """Configure Selenium pour éviter la détection"""
        logger.info("Initialisation de Selenium...")
        options = Options()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(f"user-agent={self.ua.random}")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_experimental_option('excludeSwitches', ['enable-logging'])

        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except Exception as e:
            logger.error(f"Erreur Selenium: {e}")
            self.use_selenium = False
    
    def setup_session(self):
        """Configure la session requests"""
        headers = {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
            'Referer': 'https://www.google.com/',
        }
        self.session.headers.update(headers)
        self.session.timeout = 30
        
        # Configuration CloudScraper
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True,
            }
        )
    
    def __del__(self):
        """Nettoyage à la destruction"""
        if self.use_selenium and self.driver:
            self.driver.quit()

    def get_manga_title(self, url):
        """Récupère le titre du manga"""
        try:
            response = self.safe_request(url)
            if not response:
                return "manga_inconnu"
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Sélecteurs possibles pour le titre
            selectors = [
                'h1.entry-title', 'h1.manga-title', 'h1.post-title', 'h1',
                '.manga-title', '.entry-title', '.post-title',
                'div.post-title h1', 'header.entry-header h1'
            ]
            
            for selector in selectors:
                title = soup.select_one(selector)
                if title:
                    return self.sanitize_filename(title.get_text(strip=True))
            
            return "manga_inconnu"
            
        except Exception as e:
            logger.error(f"Erreur titre: {e}")
            return "manga_inconnu"

    def get_chapter_links(self, url):
        """Récupère les liens des chapitres"""
        try:
            response = self.safe_request(url)
            if not response:
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Sélecteurs possibles
            selectors = [
                '.wp-manga-chapter a', '.chapter-link',
                '.listing-chapters_wrap a', 'a[href*="chapter"]',
                '.chapter a', 'li a[href*="chapter"]'
            ]
            
            chapters = []
            for selector in selectors:
                for a in soup.select(selector):
                    href = a.get('href')
                    if href:
                        chapters.append({
                            'name': a.get_text(strip=True),
                            'url': urljoin(url, href)
                        })
                if chapters:
                    break
            
            return chapters[::-1]  # Inversion pour ordre chronologique
            
        except Exception as e:
            logger.error(f"Erreur chapitres: {e}")
            return []

    def get_chapter_images(self, chapter_url):
        """Récupère les images d'un chapitre"""
        try:
            response = self.safe_request(chapter_url)
            if not response:
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Sélecteurs possibles
            selectors = [
                '.reading-content img', '.chapter-content img',
                '.page-break img', 'img[src*="uploads"]',
                '.wp-manga-chapter-img img', 'div.page img'
            ]
            
            images = []
            for selector in selectors:
                for img in soup.select(selector):
                    src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                    if src and any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                        images.append(urljoin(chapter_url, src))
                if images:
                    break
            
            return images
            
        except Exception as e:
            logger.error(f"Erreur images: {e}")
            return []

    def safe_request(self, url, max_retries=3):
        """Effectue une requête avec gestion des erreurs"""
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(random.uniform(1, 3))
                
                # Essai avec cloudscraper d'abord
                response = self.scraper.get(url, verify=False)
                
                if response.status_code == 200:
                    return response
                
                # Fallback avec requests si échec
                response = self.session.get(url, verify=False)
                if response.status_code == 200:
                    return response
                
            except Exception as e:
                logger.warning(f"Tentative {attempt+1} échouée: {e}")
                if attempt == max_retries - 1 and self.use_selenium:
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

    def download_image(self, img_url, file_path):
        """Télécharge une image"""
        try:
            headers = {
                'User-Agent': self.ua.random,
                'Referer': urlparse(img_url).scheme + '://' + urlparse(img_url).netloc + '/',
            }
            
            # Essai avec cloudscraper
            response = self.scraper.get(img_url, headers=headers, stream=True, verify=False)
            if response.status_code == 200:
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                return True
            
            # Fallback Selenium
            if self.use_selenium:
                self.driver.get(img_url)
                time.sleep(2)
                self.driver.find_element(By.TAG_NAME, 'img').screenshot(file_path)
                return True
                
        except Exception as e:
            logger.error(f"Erreur téléchargement image: {e}")
        
        return False

    def sanitize_filename(self, filename):
        """Nettoie les noms de fichiers"""
        invalid = '<>:"/\\|?*'
        for char in invalid:
            filename = filename.replace(char, '_')
        return filename.strip()

    def download_manga(self, manga_url, max_chapters=None):
        """Télécharge le manga complet"""
        try:
            # Récupération du titre
            title = self.get_manga_title(manga_url)
            download_dir = os.path.join('manga_downloads', title)
            os.makedirs(download_dir, exist_ok=True)
            
            # Récupération des chapitres
            chapters = self.get_chapter_links(manga_url)
            if not chapters:
                logger.error("Aucun chapitre trouvé")
                return
            
            if max_chapters:
                chapters = chapters[:max_chapters]
            
            # Téléchargement
            for i, chapter in enumerate(chapters, 1):
                chapter_dir = os.path.join(download_dir, self.sanitize_filename(chapter['name']))
                os.makedirs(chapter_dir, exist_ok=True)
                
                images = self.get_chapter_images(chapter['url'])
                if not images:
                    continue
                
                for j, img_url in enumerate(images, 1):
                    ext = os.path.splitext(urlparse(img_url).path)[1] or '.jpg'
                    img_path = os.path.join(chapter_dir, f"page_{j:03d}{ext}")
                    
                    if not os.path.exists(img_path):
                        if self.download_image(img_url, img_path):
                            logger.info(f"Image {j}/{len(images)} téléchargée")
                        else:
                            logger.error(f"Échec image {j}")
                        time.sleep(random.uniform(0.5, 1.5))
                
                time.sleep(random.uniform(2, 5))
            
            logger.info("Téléchargement terminé avec succès!")
            
        except Exception as e:
            logger.error(f"Erreur fatale: {e}")
        finally:
            if self.use_selenium and self.driver:
                self.driver.quit()

def main():
    try:
        # Configuration
        manga_url = "https://phenix-scans.com/manga/a-modern-man-who-transmigrated-into-the-murim-world"
        
        # Initialisation
        downloader = MangaDownloader(use_selenium=True)
        
        # Téléchargement (3 premiers chapitres pour test)
        downloader.download_manga(manga_url, max_chapters=3)
        
    except Exception as e:
        logger.error(f"Erreur principale: {e}")

if __name__ == "__main__":
    main()