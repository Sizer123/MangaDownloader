import requests
import os
import time
import random
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import logging
from fake_useragent import UserAgent

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MangaDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.ua = UserAgent()
        self.setup_session()
        
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
        }
        self.session.headers.update(headers)
        
        # Désactiver la vérification SSL si nécessaire
        self.session.verify = False
        
        # Timeout plus long
        self.session.timeout = 30
        
    def rotate_user_agent(self):
        """Change l'User-Agent pour éviter la détection"""
        self.session.headers['User-Agent'] = self.ua.random
        
    def get_page_with_retry(self, url, max_retries=3):
        """Récupère une page avec retry et gestion des erreurs"""
        for attempt in range(max_retries):
            try:
                # Rotation de l'User-Agent
                self.rotate_user_agent()
                
                # Délai aléatoire entre les requêtes
                if attempt > 0:
                    delay = random.uniform(2, 5)
                    logger.info(f"Tentative {attempt + 1}/{max_retries} - Attente de {delay:.1f}s...")
                    time.sleep(delay)
                
                response = self.session.get(url)
                
                if response.status_code == 200:
                    return response
                elif response.status_code == 403:
                    logger.warning(f"Erreur 403 - Tentative {attempt + 1}/{max_retries}")
                    if attempt < max_retries - 1:
                        # Essayer avec des headers différents
                        self.try_different_headers()
                        continue
                else:
                    logger.warning(f"Code de statut {response.status_code} - Tentative {attempt + 1}/{max_retries}")
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Erreur de requête: {e}")
                if attempt < max_retries - 1:
                    time.sleep(random.uniform(3, 6))
                    continue
                    
        return None
    
    def try_different_headers(self):
        """Essaie différents headers pour contourner les blocages"""
        headers_options = [
            {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://www.google.com/',
            },
            {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://phenix-scans.com/',
            },
            {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
        ]
        
        selected_headers = random.choice(headers_options)
        self.session.headers.update(selected_headers)
        logger.info("Headers mis à jour pour contourner les blocages")
    
    def get_manga_title(self, url):
        """Récupère le titre du manga"""
        logger.info(f"Récupération du titre du manga... : {url}")
        
        response = self.get_page_with_retry(url)
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
                '.post-title'
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
                'li a[href*="chapter"]'
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
                'img'
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
        """Télécharge une image"""
        try:
            response = self.get_page_with_retry(img_url)
            if response:
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                return True
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
                
                # Délai entre les téléchargements
                time.sleep(random.uniform(0.5, 1.5))
            
            # Délai entre les chapitres
            time.sleep(random.uniform(2, 4))
        
        logger.info("🎉 Téléchargement terminé!")

def main():
    # URL du manga à télécharger
    manga_url = "https://phenix-scans.com/manga/a-modern-man-who-transmigrated-into-the-murim-world"
    
    # Création du downloader
    downloader = MangaDownloader()
    
    # Téléchargement (limité à 3 chapitres pour les tests)
    downloader.download_manga(manga_url, max_chapters=3)

if __name__ == "__main__":
    main()