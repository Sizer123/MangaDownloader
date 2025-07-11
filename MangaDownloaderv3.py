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

requests.packages.urllib3.disable_warnings()  # Disable SSL warnings

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
        self.chrome_options.add_argument("--headless")  # Mode sans affichage
        self.chrome_options.add_argument("--disable-gpu")
        self.chrome_options.add_argument("--disable-dev-shm-usage")
        self.chrome_options.add_argument("--no-sandbox")
        
        # Désactiver les logs inutiles
        self.chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        # Initialisation du driver
        self.driver = webdriver.Chrome(options=self.chrome_options)
        
        # Masquer les indicateurs WebDriver
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    def setup_session(self):
        """Configure la session avec headers et cookies pour éviter les blocages"""
        # Headers réalistes
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
        
        # Cookies réalistes
        self.session.cookies.update({
            'cookie_consent': 'true',
            'preferences': 'language=fr',
        })
        
        # Désactiver la vérification SSL si nécessaire
        self.session.verify = False
        
        # Timeout plus long
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
        """Change l'User-Agent pour éviter la détection"""
        new_ua = self.ua.random
        self.session.headers['User-Agent'] = new_ua
        if self.use_selenium:
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": new_ua})
        logger.debug(f"User-Agent changé pour: {new_ua}")
        
    def get_page_with_retry(self, url, max_retries=5):
        """Récupère une page avec retry et gestion des erreurs"""
        for attempt in range(max_retries):
            try:
                # Rotation de l'User-Agent
                self.rotate_user_agent()
                
                # Délai aléatoire entre les requêtes
                if attempt > 0:
                    delay = random.uniform(2, 10)  # Délai plus long pour éviter le blocage
                    logger.info(f"Tentative {attempt + 1}/{max_retries} - Attente de {delay:.1f}s...")
                    time.sleep(delay)
                
                # Utilisation de Selenium si nécessaire
                if self.use_selenium and attempt > 1:  # Après 1 échec avec requests
                    logger.info("Essai avec Selenium...")
                    self.driver.get(url)
                    
                    # Attendre que la page soit chargée
                    try:
                        WebDriverWait(self.driver, 30).until(
                            EC.presence_of_element_located((By.TAG_NAME, 'body'))
                        )
                    except Exception as e:
                        logger.error(f"Erreur lors de l'attente de chargement de la page: {e}")
                        return None
                    
                    # Retourner le contenu de la page
                    return type('obj', (object,), {
                        'content': self.driver.page_source.encode('utf-8'),
                        'status_code': 200
                    })
                else:
                    # Essayer d'abord avec CloudScraper
                    if attempt > 0:
                        response = self.scraper.get(url)
                    else:
                        response = self.session.get(url)
                    
                    # Vérifier les redirections suspectes
                    if len(response.history) > 2:
                        logger.warning("Trop de redirections, possible blocage")
                        raise requests.exceptions.TooManyRedirects()
                    
                    if response.status_code == 200:
                        return response
                    elif response.status_code in [403, 429, 503]:
                        logger.warning(f"Erreur {response.status_code} - Tentative {attempt + 1}/{max_retries}")
                        if attempt < max_retries - 1:
                            self.try_different_headers()
                            continue
                    else:
                        logger.warning(f"Code de statut {response.status_code} - Tentative {attempt + 1}/{max_retries}")
                        
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                logger.error(f"Erreur de connexion: {e}")
                if attempt < max_retries - 1:
                    time.sleep(random.uniform(5, 15))  # Délai plus long pour les erreurs de connexion
                    continue
            except Exception as e:
                logger.error(f"Erreur inattendue: {type(e).__name__}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(random.uniform(3, 8))
                    continue
                    
        return None
    
    def try_different_headers(self):
        """Essaie différents headers pour contourner les blocages"""
        headers_options = [
            {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://www.google.com/',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://phenix-scans.com/',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'fr-FR,fr;q=0.9',
            },
            {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'DNT': '1',
                'Upgrade-Insecure-Requests': '1',
            }
        ]
        
        selected_headers = random.choice(headers_options)
        self.session.headers.update(selected_headers)
        logger.info("Headers mis à jour pour contourner les blocages")
        
        # Ajouter un délai aléatoire supplémentaire
        time.sleep(random.uniform(1, 3))
    
    def bypass_cloudflare(self, url):
        """Tente de contourner CloudFlare"""
        logger.info("Tentative de contournement de CloudFlare...")
        
        try:
            # Utilisation de cloudscraper
            resp = self.scraper.get(url)
            if resp.status_code == 200:
                logger.info("CloudFlare contourné avec succès")
                return resp
            
            # Si cloudscraper échoue, essayer avec Selenium
            if self.use_selenium:
                self.driver.get(url)
                
                # Attendre que le challenge CloudFlare soit résolu
                try:
                    WebDriverWait(self.driver, 30).until(
                        EC.presence_of_element_located((By.TAG_NAME, 'body')))
                    logger.info("CloudFlare contourné avec Selenium")
                    return type('obj', (object,), {
                        'content': self.driver.page_source.encode('utf-8'),
                        'status_code': 200
                    })
                except Exception as e:
                    logger.error(f"Échec du contournement de CloudFlare: {e}")
            
        except Exception as e:
            logger.error(f"Erreur lors du contournement de CloudFlare: {e}")
        
        return None
    
    def get_manga_title(self, url):
        """Récupère le titre du manga"""
        logger.info(f"Récupération du titre du manga... : {url}")
        
        # Essayer d'abord avec une requête normale
        response = self.get_page_with_retry(url)
        
        # Si échec, essayer de contourner CloudFlare
        if not response or response.status_code != 200:
            response = self.bypass_cloudflare(url)
            if not response:
                logger.error("Impossible de récupérer la page du manga")
                return "manga_unknown"
        
        try:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Différents sélecteurs possibles pour le titre
            title_selectors = [
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
            
            for selector in title_selectors:
                title_element = soup.select_one(selector)
                if title_element:
                    title = title_element.get_text(strip=True)
                    logger.info(f"📖 Titre trouvé: {title}")
                    return self.sanitize_filename(title)
            
            logger.warning("Titre non trouvé, utilisation du nom par défaut")
            return "manga_unknown"
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction du titre: {e}")
            return "manga_unknown"
    
    def get_chapter_links(self, url):
        """Récupère les liens des chapitres"""
        logger.info("Récupération des liens des chapitres...")
        
        response = self.get_page_with_retry(url)
        if not response or response.status_code != 200:
            response = self.bypass_cloudflare(url)
            if not response:
                logger.error("Impossible de récupérer la page des chapitres")
                return []
        
        try:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Différents sélecteurs pour les liens de chapitres
            chapter_selectors = [
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
            for selector in chapter_selectors:
                chapter_elements = soup.select(selector)
                if chapter_elements:
                    logger.info(f"Chapitres trouvés avec le sélecteur: {selector}")
                    for element in chapter_elements:
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
                logger.info(f"📚 {len(chapters)} chapitres trouvés")
                return chapters[::-1]  # Inverser pour commencer par le chapitre 1
            else:
                logger.error("Aucun chapitre trouvé avec les sélecteurs disponibles")
                return []
                
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des chapitres: {e}")
            return []
    
    def get_chapter_images(self, chapter_url):
        """Récupère les images d'un chapitre"""
        logger.info(f"Récupération des images du chapitre: {chapter_url}")
        
        response = self.get_page_with_retry(chapter_url)
        if not response or response.status_code != 200:
            response = self.bypass_cloudflare(chapter_url)
            if not response:
                logger.error("Impossible de récupérer la page du chapitre")
                return []
        
        try:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Différents sélecteurs pour les images
            image_selectors = [
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
            for selector in image_selectors:
                img_elements = soup.select(selector)
                if img_elements:
                    for img in img_elements:
                        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                        if src and any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                            full_url = urljoin(chapter_url, src)
                            images.append(full_url)
                    if images:
                        break
            
            logger.info(f"📷 {len(images)} images trouvées")
            return images
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des images: {e}")
            return []
    
    def download_image(self, img_url, file_path):
        """Télécharge une image avec des headers spécifiques"""
        try:
            # Headers spécifiques pour les images
            headers = {
                'User-Agent': self.ua.random,
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Referer': urlparse(img_url).scheme + '://' + urlparse(img_url).netloc + '/',
                'Sec-Fetch-Dest': 'image',
                'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Site': 'cross-site',
            }
            
            # Essayer d'abord avec cloudscraper
            response = self.scraper.get(img_url, headers=headers, stream=True)
            
            if response.status_code == 200:
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                return True
            else:
                logger.warning(f"Code de statut {response.status_code} pour l'image, tentative avec Selenium")
                
                # Si échec, essayer avec Selenium
                if self.use_selenium:
                    try:
                        self.driver.get(img_url)
                        time.sleep(3)  # Attendre le chargement
                        
                        # Trouver l'élément image et récupérer la source
                        img_element = self.driver.find_element(By.TAG_NAME, 'img')
                        actual_src = img_element.get_attribute('src')
                        
                        if actual_src and actual_src != img_url:
                            logger.info(f"Image redirigée vers: {actual_src}")
                            return self.download_image(actual_src, file_path)
                        
                        # Sauvegarder la capture d'écran comme dernier recours
                        img_element.screenshot(file_path)
                        return True
                    except Exception as e:
                        logger.error(f"Échec du téléchargement avec Selenium: {e}")
                
        except Exception as e:
            logger.error(f"Erreur lors du téléchargement de l'image: {e}")
        return False
    
    def sanitize_filename(self, filename):
        """Nettoie le nom de fichier"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename.strip()
    
    def download_manga(self, manga_url, max_chapters=None):
        """Télécharge le manga complet"""
        logger.info("🚀 Début du scraping...")
        
        # Récupération du titre
        manga_title = self.get_manga_title(manga_url)
        
        # Création du dossier
        download_dir = os.path.join('manga_downloads', manga_title)
        os.makedirs(download_dir, exist_ok=True)
        logger.info(f"📁 Dossier créé: {download_dir}")
        
        # Récupération des chapitres
        chapters = self.get_chapter_links(manga_url)
        
        if not chapters:
            logger.error("❌ Aucun chapitre trouvé")
            return
        
        # Limitation du nombre de chapitres si spécifié
        if max_chapters:
            chapters = chapters[:max_chapters]
        
        # Téléchargement des chapitres
        for i, chapter in enumerate(chapters, 1):
            logger.info(f"📖 Téléchargement du chapitre {i}/{len(chapters)}: {chapter['name']}")
            
            # Création du dossier du chapitre
            chapter_dir = os.path.join(download_dir, self.sanitize_filename(chapter['name']))
            os.makedirs(chapter_dir, exist_ok=True)
            
            # Récupération des images
            images = self.get_chapter_images(chapter['url'])
            
            if not images:
                logger.warning(f"Aucune image trouvée pour le chapitre: {chapter['name']}")
                continue
            
            # Téléchargement des images
            for j, img_url in enumerate(images, 1):
                img_extension = os.path.splitext(urlparse(img_url).path)[1] or '.jpg'
                img_filename = f"page_{j:03d}{img_extension}"
                img_path = os.path.join(chapter_dir, img_filename)
                
                if not os.path.exists(img_path):
                    logger.info(f"  📷 Téléchargement de l'image {j}/{len(images)}")
                    if self.download_image(img_url, img_path):
                        logger.info(f"    ✅ Image sauvegardée: {img_filename}")
                    else:
                        logger.error(f"    ❌ Échec du téléchargement: {img_filename}")
                else:
                    logger.info(f"  ⏭️  Image déjà téléchargée: {img_filename}")
                
                # Délai aléatoire entre les téléchargements
                time.sleep(random.uniform(1, 3))
            
            # Délai plus long entre les chapitres
            time.sleep(random.uniform(5, 10))
        
        logger.info("🎉 Téléchargement terminé!")
        
        # Fermer Selenium si utilisé
        if self.use_selenium:
            self.driver.quit()

def main():
    # URL du manga à télécharger
    manga_url = "https://phenix-scans.com/manga/a-modern-man-who-transmigrated-into-the-murim-world"
    
    # Création du downloader avec Selenium comme option de secours
    downloader = MangaDownloader(use_selenium=True)
    
    # Téléchargement (limité à 3 chapitres pour les tests)
    downloader.download_manga(manga_url, max_chapters=3)

if __name__ == "__main__":
    main()