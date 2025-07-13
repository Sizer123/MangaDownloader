from flask import Flask, request, Response, jsonify
import requests
from flask_cors import CORS
import re
import time
from bs4 import BeautifulSoup

app = Flask(__name__)
CORS(app)

# Cloudflare-bypassing configuration
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Referer': 'https://www.google.com/',
    'DNT': '1',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'cross-site',
    'Sec-Fetch-User': '?1'
}

COOKIES = {
    '_ga': 'GA1.1.1972107960.1752260467',
    '_ga_V97PMX1THH': 'GS2.1.s1752263986$o2$g1$t1752266638$j60$l0$h0',
    'cf_clearance': '8gQUULzzHCPY.2kyagSl.dplDFz172ggBmuhpekVbS8-1752266638-1.2.1.1-lKO0LH39_SBuQR4BKdQWNv7RDc.OcaYBCTZeT2nHipi6kfb7PrVHcoWf3Y5OEfiFMXnm4l.Kk3N2_M_0oA.IiezahDZLH7MU5NIJgUcuSc4m1.t7yfTWkuvIgr9uHjT0Wj1p2OGu3eS.8fKQNgaU9su0T8T8lySMwiQQ6va3_6FRzCMVfEvo8HEndPqdyfFVQbY9fo2_bXfSmfzK76JYrbHtBM_42VxeRfpKoCmHfrI'  # Get this from your browser after manual access
}

def clean_content(html, base_url):
    """Clean and modify the HTML content"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove Cloudflare-specific elements
    for element in soup.find_all(string=re.compile('cloudflare|rocket-loader')):
        element.extract()
    
    # Fix relative URLs
    for tag in soup.find_all(['a', 'img', 'script', 'link']):
        for attr in ['href', 'src']:
            if tag.get(attr):
                if tag[attr].startswith('/'):
                    tag[attr] = f"{base_url}{tag[attr]}"
    
    return str(soup)

@app.route('/proxy-content', methods=['GET'])
def proxy_content():
    target_url = request.args.get('url')
    if not target_url:
        return jsonify({'error': 'URL parameter required'}), 400
    
    try:
        # First attempt with standard headers
        response = requests.get(
            target_url,
            headers=HEADERS,
            cookies=COOKIES,
            timeout=20,
            allow_redirects=True
        )
        
        # Check for Cloudflare challenge
        if response.status_code == 403 or 'cf-chl-bypass' in response.text.lower():
            return jsonify({
                'error': 'Cloudflare protection triggered',
                'solution': 'Manually visit the site in browser to obtain cf_clearance cookie'
            }), 503
        
        response.raise_for_status()
        
        # Clean and return content
        clean_html = clean_content(response.text, target_url)
        return Response(clean_html, content_type=response.headers.get('content-type', 'text/html'))
    
    except requests.exceptions.RequestException as e:
        return jsonify({
            'error': str(e),
            'type': type(e).__name__
        }), 502

if __name__ == '__main__':
    app.run(port=5000, debug=True)