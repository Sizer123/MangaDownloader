from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def setup_chrome_driver():
    """Configuration du driver Chrome avec options"""
    
    # Options Chrome
    chrome_options = Options()
    
    # Options utiles
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Mode headless (optionnel - pour exécuter sans interface graphique)
    # chrome_options.add_argument("--headless")
    
    # Désactiver les notifications
    chrome_options.add_argument("--disable-notifications")
    
    # Taille de fenêtre
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Service avec WebDriverManager
    service = Service(ChromeDriverManager().install())
    
    # Créer le driver
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    return driver

def exemple_utilisation():
    """Exemple d'utilisation du driver"""
    
    driver = setup_chrome_driver()
    
    try:
        # Naviguer vers une page
        driver.get("https://www.google.com")
        
        # Attendre que la page se charge
        wait = WebDriverWait(driver, 10)
        
        # Chercher un élément
        search_box = wait.until(
            EC.presence_of_element_located((By.NAME, "q"))
        )
        
        # Saisir du texte
        search_box.send_keys("Selenium Python")
        search_box.submit()
        
        # Attendre les résultats
        wait.until(
            EC.presence_of_element_located((By.ID, "search"))
        )
        
        print("Recherche effectuée avec succès!")
        
    except Exception as e:
        print(f"Erreur: {e}")
        
    finally:
        # Fermer le navigateur
        driver.quit()

if __name__ == "__main__":
    exemple_utilisation()