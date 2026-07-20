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
import ssl
import urllib3

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
        
        # Configuration SSL
        self.ssl_verify = False  # Désactivé pour contourner les problèmes de certificat
        self.certifi_path = certifi.where()
        
        if self.use_selenium:
            self.setup_selenium()
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
        try:
            self.driver = webdriver.Chrome(options=self.chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de Selenium: {e}")
            self.use_selenium = False
    
    def setup_session(self):
        """Configure la session avec headers et cookies"""
        headers = {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://www.google.com/',
        }
        self.session.headers.update(headers)
        
        # Ne pas définir verify ici, on le fera au niveau des requêtes individuelles
        self.session.timeout = 30
        
        # Configuration de CloudScraper
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True,
            }
        )
    def __del__(self):
        """Nettoyage à la destruction de l'objet"""
        if self.use_selenium and self.driver:
            self.driver.quit()

    def get_manga_title(self, url):
        """Récupère le titre du manga depuis la page"""
        logger.info(f"Récupération du titre du manga depuis {url}")
        try:
            response = self.get_page_with_retry(url)
            if not response:
                return "manga_inconnu"
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Sélecteurs possibles pour le titre
            selectors = [
                'h1.entry-title',
                'h1.manga-title',
                'h1.post-title',
                'h1',
                '.manga-title',
                '.entry-title',
                '.post-title',
                'div.post-title h1',
                'header.entry-header h1',
                'div.profile-manga h1'
            ]
            
            for selector in selectors:
                title_element = soup.select_one(selector)
                if title_element:
                    title = title_element.get_text(strip=True)
                    logger.info(f"Titre trouvé: {title}")
                    return self.sanitize_filename(title)
            
            logger.warning("Aucun titre trouvé avec les sélecteurs disponibles")
            return "manga_inconnu"
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du titre: {e}")
            return "manga_inconnu"

    def get_chapter_links(self, url):
        """Récupère tous les liens de chapitres"""
        logger.info(f"Récupération des chapitres depuis {url}")
        try:
            response = self.get_page_with_retry(url)
            if not response:
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Sélecteurs possibles pour les chapitres
            selectors = [
                '.wp-manga-chapter a',
                '.chapter-link',
                '.listing-chapters_wrap a',
                'a[href*="chapter"]',
                '.chapter a',
                'li a[href*="chapter"]',
                'ul li.wp-manga-chapter a',
                'div.chapter-list a',
                'div.eplister a'
            ]
            
            chapters = []
            for selector in selectors:
                elements = soup.select(selector)
                if elements:
                    for element in elements:
                        href = element.get('href')
                        if href:
                            full_url = urljoin(url, href)
                            chapter_name = element.get_text(strip=True)
                            chapters.append({
                                'name': chapter_name,
                                'url': full_url
                            })
                    break
            
            if chapters:
                logger.info(f"Nombre de chapitres trouvés: {len(chapters)}")
                return chapters[::-1]  # Inverser pour avoir l'ordre chronologique
            return []
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des chapitres: {e}")
            return []

    def get_chapter_images(self, chapter_url):
        """Récupère toutes les images d'un chapitre"""
        logger.info(f"Récupération des images depuis {chapter_url}")
        try:
            response = self.get_page_with_retry(chapter_url)
            if not response:
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Sélecteurs possibles pour les images
            selectors = [
                '.reading-content img',
                '.chapter-content img',
                '.page-break img',
                'img[src*="uploads"]',
                '.wp-manga-chapter-img img',
                'img',
                'div.page img',
                'div.entry-content img',
                'div.text-left img'
            ]
            
            images = []
            for selector in selectors:
                img_elements = soup.select(selector)
                if img_elements:
                    for img in img_elements:
                        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                        if src and any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                            full_url = urljoin(chapter_url, src)
                            images.append(full_url)
                    break
            
            logger.info(f"Nombre d'images trouvées: {len(images)}")
            return images
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des images: {e}")
            return []

    def download_image(self, img_url, file_path):
        """Télécharge une image et la sauvegarde"""
        try:
            headers = {
                'User-Agent': self.ua.random,
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Referer': urlparse(img_url).scheme + '://' + urlparse(img_url).netloc + '/',
            }
            
            response = self.scraper.get(img_url, headers=headers, stream=True, verify=False)
            
            if response.status_code == 200:
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                return True
            
            # Fallback avec Selenium si activé
            if self.use_selenium and self.driver:
                try:
                    self.driver.get(img_url)
                    time.sleep(2)
                    img_element = self.driver.find_element(By.TAG_NAME, 'img')
                    img_element.screenshot(file_path)
                    return True
                except Exception as e:
                    logger.error(f"Échec du fallback Selenium: {e}")
            
            return False
            
        except Exception as e:
            logger.error(f"Erreur lors du téléchargement de l'image: {e}")
            return False

    def sanitize_filename(self, filename):
        """Nettoie le nom de fichier pour le système de fichiers"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename.strip()

    def get_page_with_retry(self, url, max_retries=3):
        """Tente de récupérer une page avec plusieurs essais"""
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(random.uniform(1, 3))
                
                # Ajoutez verify=False au niveau de la requête individuelle
                response = self.session.get(url, verify=False)
                
                if response.status_code == 200:
                    return response
                elif response.status_code in [403, 429, 503]:
                    logger.warning(f"Erreur {response.status_code} - Tentative {attempt + 1}/{max_retries}")
                    continue
                    
            except requests.exceptions.SSLError as e:
                logger.error(f"Erreur SSL (tentative {attempt + 1}): {e}")
                continue
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Erreur de requête (tentative {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    continue

    def safe_get(self, url, **kwargs):
        """Méthode wrapper pour les requêtes GET sécurisées"""
        kwargs.setdefault('verify', False)  # False par défaut
        kwargs.setdefault('timeout', 30)
        return self.session.get(url, **kwargs)


    def fallback_to_selenium(self, url):
        """Utilise Selenium comme solution de secours"""
        if not self.use_selenium or not self.driver:
            return None
            
        try:
            logger.info("Tentative avec Selenium...")
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

    def download_manga(self, manga_url, max_chapters=None):
        """Télécharge un manga complet"""
        logger.info(f"Début du téléchargement pour {manga_url}")
        
        try:
            # Récupération du titre
            manga_title = self.get_manga_title(manga_url)
            download_dir = os.path.join('manga_downloads', manga_title)
            os.makedirs(download_dir, exist_ok=True)
            
            # Récupération des chapitres
            chapters = self.get_chapter_links(manga_url)
            if not chapters:
                logger.error("Aucun chapitre trouvé")
                return
                
            if max_chapters:
                chapters = chapters[:max_chapters]
            
            # Téléchargement des chapitres
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
                        self.download_image(img_url, img_path)
                        time.sleep(random.uniform(0.5, 2))
                
                time.sleep(random.uniform(1, 3))
            
            logger.info("Téléchargement terminé avec succès!")
            
        except Exception as e:
            logger.error(f"Erreur fatale lors du téléchargement: {e}")
        finally:
            if self.use_selenium and self.driver:
                self.driver.quit()

def main():
    try:
        manga_url = "https://phenix-scans.com/manga/a-modern-man-who-transmigrated-into-the-murim-world"
        downloader = MangaDownloader(use_selenium=True)
        downloader.download_manga(manga_url, max_chapters=3)
    except Exception as e:
        logger.error(f"Erreur dans main(): {e}")

if __name__ == "__main__":
    main()