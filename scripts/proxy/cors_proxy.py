from flask import Flask, request, Response, jsonify
import requests
from flask_cors import CORS
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
import time
import re  # Import manquant ajouté

app = Flask(__name__)
CORS(app)

# Configuration
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
COOKIES = {
    '_ga': 'GA1.1.1972107960.1752260467',
    '_ga_V97PMX1THH': 'GS2.1.s1752263986$o2$g1$t1752266638$j60$l0$h0',
    'cf_clearance': 'YOUR_CF_CLEARANCE_COOKIE'  # À remplacer
}

def get_with_selenium(url):
    """Utilisation de Chrome headless avec les cookies"""
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument(f"user-agent={USER_AGENT}")
    
    with uc.Chrome(options=options) as driver:
        driver.get("https://phenix-scans.com")
        time.sleep(2)
        for name, value in COOKIES.items():
            driver.add_cookie({'name': name, 'value': value, 'domain': 'phenix-scans.com'})
        
        driver.get(url)
        time.sleep(5)  # Attente pour Cloudflare
        return driver.page_source

def clean_html(html, base_url="https://phenix-scans.com"):
    """Nettoyage du HTML avec BeautifulSoup"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Suppression des éléments indésirables
    for element in soup.find_all(string=re.compile(r'cloudflare|rocket-loader', re.I)):
        element.extract()
    
    # Correction des URLs
    for tag in soup.find_all(['a', 'img', 'link', 'script']):
        for attr in ['href', 'src']:
            if tag.get(attr) and tag[attr].startswith('/'):
                tag[attr] = f"{base_url}{tag[attr]}"
    
    return str(soup)

@app.route('/proxy-content', methods=['GET'])
def proxy_content():
    target_url = request.args.get('url')
    if not target_url:
        return jsonify({'error': 'URL parameter required'}), 400
    
    try:
        # Essayer d'abord avec requests
        response = requests.get(
            target_url,
            headers={'User-Agent': USER_AGENT},
            cookies=COOKIES,
            timeout=15
        )
        
        # Si bloqué, utiliser Selenium
        if response.status_code == 403 or 'cf-chl-bypass' in response.text.lower():
            html = get_with_selenium(target_url)
            return Response(clean_html(html), content_type='text/html')
        
        return Response(clean_html(response.text), content_type='text/html')
    
    except Exception as e:
        return jsonify({'error': str(e)}), 502

if __name__ == '__main__':
    app.run(port=5000, debug=True)