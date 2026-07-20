import requests
import os
import re
import subprocess
import time
import signal
import sys
from bs4 import BeautifulSoup
from PIL import Image
from urllib.parse import urljoin, urlparse
import logging
import urllib3
import threading
import psutil

# Désactive les warnings SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VPNManager:
    def __init__(self, config_file_path, auth_file_path=None):
        """
        Gestionnaire VPN OpenVPN
        
        Args:
            config_file_path (str): Chemin vers le fichier .ovpn
            auth_file_path (str): Chemin vers le fichier d'authentification (optionnel)
        """
        self.config_file = config_file_path
        self.auth_file = auth_file_path
        self.process = None
        self.is_connected = False
        
    def connect(self):
        """Démarre la connexion VPN"""
        try:
            logger.info("🔒 Connexion au VPN...")
            
            # Vérifie que le fichier de configuration existe
            if not os.path.exists(self.config_file):
                logger.error(f"❌ Fichier de configuration VPN non trouvé: {self.config_file}")
                return False
            
            # Prépare la commande OpenVPN
            cmd = ["openvpn", "--config", self.config_file]
            
            # Ajoute le fichier d'authentification si fourni
            if self.auth_file and os.path.exists(self.auth_file):
                cmd.extend(["--auth-user-pass", self.auth_file])
            
            # Démarre OpenVPN
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Attendre quelques secondes pour que la connexion s'établisse
            time.sleep(10)
            
            # Vérifie si la connexion est active
            if self.process.poll() is None:
                self.is_connected = True
                logger.info("✅ VPN connecté avec succès")
                
                # Vérifie l'IP publique
                self.check_ip()
                return True
            else:
                logger.error("❌ Échec de la connexion VPN")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erreur lors de la connexion VPN: {e}")
            return False
    
    def disconnect(self):
        """Déconnecte le VPN"""
        try:
            if self.process and self.process.poll() is None:
                logger.info("🔒 Déconnexion du VPN...")
                self.process.terminate()
                
                # Attendre la fin du processus
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
                
                self.is_connected = False
                logger.info("✅ VPN déconnecté")
            
        except Exception as e:
            logger.error(f"❌ Erreur lors de la déconnexion VPN: {e}")
    
    def check_ip(self):
        """Vérifie l'IP publique actuelle"""
        try:
            response = requests.get("https://httpbin.org/ip", timeout=10)
            if response.status_code == 200:
                ip_data = response.json()
                logger.info(f"🌐 IP publique: {ip_data.get('origin', 'Inconnue')}")
            else:
                logger.warning("⚠️ Impossible de vérifier l'IP publique")
        except Exception as e:
            logger.warning(f"⚠️ Erreur lors de la vérification de l'IP: {e}")
    
    def is_vpn_connected(self):
        """Vérifie si le VPN est toujours connecté"""
        return self.process and self.process.poll() is None and self.is_connected

class MangaScraper:
    def __init__(self, base_url, delay=1, vpn_manager=None):
        self.base_url = base_url
        self.delay = delay
        self.vpn_manager = vpn_manager
        self.session = requests.Session()
        
        # Configuration pour éviter les erreurs SSL
        self.session.verify = False
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://phenix-scans.com/',
            # 'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36",
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Ch-Ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
        })
    
    def check_connection(self):
        """Vérifie la connexion internet et VPN"""
        try:
            # Test de connexion simple
            response = requests.get("https://httpbin.org/ip", timeout=10)
            if response.status_code == 200:
                logger.info("✅ Connexion internet OK")
                return True
            else:
                logger.error("❌ Problème de connexion internet")
                return False
        except Exception as e:
            logger.error(f"❌ Erreur de connexion: {e}")
            return False
    
    def safe_request(self, url, max_retries=3):
        """Effectue une requête avec gestion d'erreurs et retry"""
        for attempt in range(max_retries):
            try:
                # Vérifie si le VPN est toujours connecté
                if self.vpn_manager and not self.vpn_manager.is_vpn_connected():
                    logger.warning("⚠️ VPN déconnecté, tentative de reconnexion...")
                    if not self.vpn_manager.connect():
                        logger.error("❌ Impossible de reconnecter le VPN")
                        return None
                
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return response
                
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"⚠️ Erreur de connexion (tentative {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))  # Délai progressif
                    continue
                else:
                    logger.error(f"❌ Échec de la connexion après {max_retries} tentatives")
                    return None
            except Exception as e:
                logger.error(f"❌ Erreur lors de la requête: {e}")
                return None
        
        return None
        
    def get_manga_title(self):
        """Récupère le titre du manga depuis l'URL principale"""
        try:
            logger.info("Récupération du titre du manga... : " + self.base_url)
            response = self.safe_request(self.base_url)
            if not response:
                return "manga_unknown"

            logger.info(f"Statut de la requête: {response.status_code}")
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Essaie différents sélecteurs pour trouver le titre
            title_selectors = [
                'h1.project__content-informations-title'
            ]
            
            for selector in title_selectors:
                title_element = soup.select_one(selector)
                if title_element:
                    title = self.sanitize_filename(title_element.get_text().strip())
                    logger.info(f"Titre trouvé: {title}")
                    return title
            
            # Si aucun titre trouvé, utilise l'URL
            title = self.sanitize_filename(self.base_url.split('/')[-1])
            logger.info(f"Titre par défaut: {title}")
            return title
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du titre: {e}")
            return "manga_unknown"
    
    def get_chapter_links(self):
        """Récupère tous les liens des chapitres"""
        try:
            logger.info("Récupération des liens des chapitres...")
            response = self.safe_request(self.base_url)
            if not response:
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            chapter_links = []
            
            # Recherche les liens de chapitres avec différents sélecteurs
            selectors = [
                '.project__chapters a.project__chapter.unstyled-link',
                '.project__chapters a',
                'a.project__chapter',
                '.project__chapter',
                'a[href*="chapter"]',
                '.chapter-list a',
                '.wp-manga-chapter a',
                '.listing-chapters_wrap a',
                '.chapter-link'
            ]
            
            for selector in selectors:
                links = soup.select(selector)
                logger.info(f"Sélecteur '{selector}': {len(links)} liens trouvés")
                if links:
                    for link in links:
                        href = link.get('href')
                        if href and ('chapter' in href.lower() or 'chapitre' in href.lower()):
                            full_url = urljoin(self.base_url, href)
                            chapter_title = self.get_chapter_title(link)
                            chapter_links.append({
                                'url': full_url,
                                'title': chapter_title
                            })
                    if chapter_links:
                        break
            
            # Supprime les doublons
            unique_links = []
            seen_urls = set()
            for chapter in chapter_links:
                if chapter['url'] not in seen_urls:
                    unique_links.append(chapter)
                    seen_urls.add(chapter['url'])
            
            # Trie les chapitres par numéro si possible
            chapter_links = self.sort_chapters(unique_links)
            
            logger.info(f"Trouvé {len(chapter_links)} chapitres uniques")
            
            # Affiche les premiers chapitres pour vérification
            if chapter_links:
                logger.info("Premiers chapitres trouvés:")
                for i, chapter in enumerate(chapter_links[:5]):
                    logger.info(f"  {i+1}. {chapter['title']} -> {chapter['url']}")
            
            return chapter_links
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des liens: {e}")
            return []
    
    def get_chapter_title(self, link_element):
        """Extrait le titre du chapitre depuis l'élément du lien"""
        # Essaie différentes méthodes pour extraire le titre
        title = link_element.get_text().strip()
        
        # Si le texte est vide, essaie l'attribut title
        if not title:
            title = link_element.get('title', '').strip()
        
        # Si toujours vide, essaie de construire depuis l'URL
        if not title:
            href = link_element.get('href', '')
            if href:
                # Extrait le dernier segment de l'URL
                segments = href.rstrip('/').split('/')
                title = segments[-1] if segments else 'chapter_unknown'
        
        # Nettoie et retourne le titre
        return self.sanitize_filename(title) if title else 'chapter_unknown'
    
    def sort_chapters(self, chapter_links):
        """Trie les chapitres par numéro"""
        def extract_chapter_number(chapter):
            # Recherche un nombre dans le titre ou l'URL
            text_to_search = f"{chapter['title']} {chapter['url']}"
            matches = re.findall(r'(\d+(?:\.\d+)?)', text_to_search)
            
            if matches:
                # Prend le dernier nombre trouvé (souvent le numéro de chapitre)
                return float(matches[-1])
            return 0
        
        sorted_chapters = sorted(chapter_links, key=extract_chapter_number)
        
        # Log du tri pour vérification
        logger.info("Ordre des chapitres après tri:")
        for i, chapter in enumerate(sorted_chapters[:10]):  # Affiche les 10 premiers
            logger.info(f"  {i+1}. {chapter['title']}")
        
        return sorted_chapters
    
    def get_chapter_images(self, chapter_url):
        """Récupère toutes les images d'un chapitre"""
        try:
            logger.info(f"Récupération des images de: {chapter_url}")
            response = self.safe_request(chapter_url)
            if not response:
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            image_urls = []
            
            # Recherche les images avec différents sélecteurs
            selectors = [
                '.chapter-images img',
                '.reading-content img',
                '.chapter-content img',
                '.manga-reader img',
                '.wp-manga-chapter-img',
                'img[src*="cdn"]',
                'img[data-src]',
                '.page-break img',
                '.separator img',
                'img'  # Sélecteur générique en dernier recours
            ]
            
            for selector in selectors:
                images = soup.select(selector)
                logger.info(f"Sélecteur '{selector}': {len(images)} images trouvées")
                
                if images:
                    for img in images:
                        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                        if src and self.is_valid_image_url(src):
                            full_url = urljoin(chapter_url, src)
                            image_urls.append(full_url)
                    
                    # Si on a trouvé des images valides, on s'arrête
                    if image_urls:
                        break
            
            logger.info(f"Trouvé {len(image_urls)} images valides pour ce chapitre")
            
            # Affiche les premières images pour vérification
            if image_urls:
                logger.info("Premières images trouvées:")
                for i, url in enumerate(image_urls[:3]):
                    logger.info(f"  {i+1}. {url}")
            
            return image_urls
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des images: {e}")
            return []
    
    def is_valid_image_url(self, url):
        """Vérifie si l'URL est une image valide"""
        if not url:
            return False
        
        # Vérifie les extensions d'image
        image_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp']
        url_lower = url.lower()
        
        # Vérifie si l'URL contient une extension d'image
        has_image_ext = any(ext in url_lower for ext in image_extensions)
        
        # Évite les images de profil, icônes, etc.
        avoid_keywords = ['avatar', 'profile', 'icon', 'logo', 'button', 'banner']
        has_avoid_keyword = any(keyword in url_lower for keyword in avoid_keywords)
        
        return has_image_ext and not has_avoid_keyword
    
    def download_image(self, url, filepath):
        """Télécharge une image avec gestion d'erreurs"""
        try:
            logger.info(f"Téléchargement: {os.path.basename(filepath)}")
            response = self.safe_request(url)
            if not response:
                return False
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Vérifie que le fichier a été téléchargé et n'est pas vide
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                logger.info(f"✓ Image téléchargée: {os.path.basename(filepath)} ({os.path.getsize(filepath)} bytes)")
                return True
            else:
                logger.error(f"✗ Fichier vide ou non créé: {filepath}")
                return False
            
        except Exception as e:
            logger.error(f"Erreur lors du téléchargement de {url}: {e}")
            return False
    
    def images_to_pdf(self, image_paths, output_pdf):
        """Convertit une liste d'images en PDF"""
        try:
            if not image_paths:
                logger.error("Aucune image à convertir en PDF")
                return False
            
            logger.info(f"Conversion de {len(image_paths)} images en PDF...")
            
            images = []
            for img_path in image_paths:
                try:
                    img = Image.open(img_path)
                    # Convertit en RGB si nécessaire
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    images.append(img)
                    logger.info(f"✓ Image chargée: {os.path.basename(img_path)}")
                except Exception as e:
                    logger.error(f"✗ Erreur lors de l'ouverture de l'image {img_path}: {e}")
                    continue
            
            if images:
                images[0].save(output_pdf, save_all=True, append_images=images[1:])
                logger.info(f"✓ PDF créé: {output_pdf}")
                return True
            else:
                logger.error("✗ Aucune image valide pour créer le PDF")
                return False
            
        except Exception as e:
            logger.error(f"Erreur lors de la création du PDF: {e}")
            return False
    
    def sanitize_filename(self, filename):
        """Nettoie le nom de fichier pour éviter les caractères interdits"""
        # Remplace les caractères interdits
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Supprime les espaces en début/fin
        filename = filename.strip()
        # Remplace les espaces multiples par un seul
        filename = re.sub(r'\s+', ' ', filename)
        # Limite la longueur
        if len(filename) > 100:
            filename = filename[:100]
        return filename
    
    def scrape_manga(self):
        """Fonction principale pour scraper tout le manga"""
        logger.info("🚀 Début du scraping...")
        
        # Vérifie la connexion
        if not self.check_connection():
            logger.error("❌ Problème de connexion, arrêt du scraping")
            return
        
        # Récupère le titre du manga
        manga_title = self.get_manga_title()
        logger.info(f"📖 Titre du manga: {manga_title}")
        
        # Crée le dossier principal
        main_folder = os.path.join("manga_downloads", manga_title)
        os.makedirs(main_folder, exist_ok=True)
        logger.info(f"📁 Dossier créé: {main_folder}")
        
        # Récupère les liens des chapitres
        chapter_links = self.get_chapter_links()
        if not chapter_links:
            logger.error("❌ Aucun chapitre trouvé")
            return
        
        logger.info(f"📚 {len(chapter_links)} chapitres à télécharger")
        
        # Traite chaque chapitre
        successful_chapters = 0
        for i, chapter in enumerate(chapter_links, 1):
            logger.info(f"\n📄 Traitement du chapitre {i}/{len(chapter_links)}: {chapter['title']}")
            
            # Crée un dossier temporaire pour les images
            temp_folder = os.path.join(main_folder, f"temp_{chapter['title']}")
            os.makedirs(temp_folder, exist_ok=True)
            
            try:
                # Récupère les images du chapitre
                image_urls = self.get_chapter_images(chapter['url'])
                if not image_urls:
                    logger.warning(f"⚠️ Aucune image trouvée pour {chapter['title']}")
                    continue
                
                # Télécharge les images
                downloaded_images = []
                for j, img_url in enumerate(image_urls):
                    img_extension = self.get_image_extension(img_url)
                    img_filename = f"page_{j+1:03d}{img_extension}"
                    img_path = os.path.join(temp_folder, img_filename)
                    
                    if self.download_image(img_url, img_path):
                        downloaded_images.append(img_path)
                    
                    # Délai entre les téléchargements
                    time.sleep(self.delay)
                
                # Convertit en PDF
                if downloaded_images:
                    pdf_filename = f"{chapter['title']}.pdf"
                    pdf_path = os.path.join(main_folder, pdf_filename)
                    
                    if self.images_to_pdf(downloaded_images, pdf_path):
                        logger.info(f"✅ Chapitre {chapter['title']} terminé avec succès")
                        successful_chapters += 1
                    else:
                        logger.error(f"❌ Échec de la création du PDF pour {chapter['title']}")
                else:
                    logger.warning(f"⚠️ Aucune image téléchargée pour {chapter['title']}")
                
                # Nettoie le dossier temporaire
                for img_path in downloaded_images:
                    try:
                        os.remove(img_path)
                    except:
                        pass
                
                # Supprime le dossier temporaire s'il est vide
                try:
                    os.rmdir(temp_folder)
                except:
                    pass
                
            except Exception as e:
                logger.error(f"❌ Erreur lors du traitement du chapitre {chapter['title']}: {e}")
                continue
            
            # Délai entre les chapitres
            time.sleep(self.delay * 2)
        
        logger.info(f"\n🎉 Scraping terminé! {successful_chapters}/{len(chapter_links)} chapitres téléchargés avec succès")
    
    def get_image_extension(self, url):
        """Extrait l'extension d'image de l'URL"""
        extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp']
        url_lower = url.lower()
        
        for ext in extensions:
            if ext in url_lower:
                return ext
        
        return '.jpg'  # Extension par défaut

def signal_handler(sig, frame):
    """Gestionnaire pour l'arrêt propre du programme"""
    logger.info("\n⚠️ Arrêt du programme demandé...")
    if 'vpn' in globals() and vpn.is_connected:
        vpn.disconnect()
    sys.exit(0)

def main():
    """Fonction principale"""
    # Gestionnaire de signal pour arrêt propre
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Configuration VPN
    vpn_auth_file = "/Users/orangedigitalcenter/Documents/Projects/Manhwa/auth.txt"  # Remplacez par votre fichier .ovpn
    vpn_config_file = "/Users/orangedigitalcenter/Documents/Projects/Manhwa/us-free-8.protonvpn.tcp.ovpn"       # Optionnel: fichier avec username/password
    
    # URL du manga
    manga_url = "https://phenix-scans.com/manga/a-modern-man-who-transmigrated-into-the-murim-world"
    
    # Initialise le gestionnaire VPN
    vpn = VPNManager(vpn_config_file, vpn_auth_file)
    
    try:
        # Connecte le VPN
        if vpn.connect():
            logger.info("✅ VPN connecté, début du scraping...")
            
            # Crée le scraper avec le gestionnaire VPN
            scraper = MangaScraper(manga_url, delay=1, vpn_manager=vpn)
            
            # Lance le scraping
            scraper.scrape_manga()
        else:
            logger.error("❌ Impossible de connecter le VPN")
            
            # Demande à l'utilisateur s'il veut continuer sans VPN
            response = input("Voulez-vous continuer sans VPN? (y/N): ")
            if response.lower() == 'y':
                scraper = MangaScraper(manga_url, delay=1)
                scraper.scrape_manga()
            else:
                logger.info("Arrêt du programme")
                return
    
    except KeyboardInterrupt:
        logger.info("\n⚠️ Arrêt du programme par l'utilisateur")
    
    except Exception as e:
        logger.error(f"❌ Erreur inattendue: {e}")
    
    finally:
        # Déconnecte le VPN proprement
        if vpn.is_connected:
            vpn.disconnect()
        logger.info("🏁 Programme terminé")

if __name__ == "__main__":
    main()