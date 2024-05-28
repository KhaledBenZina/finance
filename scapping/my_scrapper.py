from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Set up Selenium with ChromeDriver
options = webdriver.ChromeOptions()
options.add_argument('--headless')  # Run in headless mode (without opening a browser window)
options.add_argument('--disable-gpu')  # Disable GPU acceleration
options.add_argument('--no-sandbox')  # Bypass OS security model
options.add_argument('start-maximized')  # Start maximized
options.add_argument('disable-infobars')  # Disable infobars
options.add_argument('--disable-extensions')  # Disable extensions

# Initialize the Chrome driver
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

try:
    # URL of the web page you want to scrape
    url = 'https://www.intermarche.com/rayons/fruits-et-legumes/fruits-et-legumes-bio/7575'
    driver.get(url)

    # Wait for the product elements to load
    print("Waiting for page to load...")
    WebDriverWait(driver, 20).until(
        EC.presence_of_all_elements_located((By.CLASS_NAME, 'stime-product--details__title'))
    )

    # Get page source and parse with BeautifulSoup
    print("Page loaded. Parsing content...")
    soup = BeautifulSoup(driver.page_source, 'html.parser')

    # Find all product containers based on the HTML structure
    products = soup.find_all('div', class_='stime-product-list__item')

    # Check if content loaded
    if not products:
        print("Page content not loaded properly.")
    else:
        print(f"Found {len(products)} products.")

    # Loop through each product and extract the details
    for product in products:
        # Extract product name
        name_tag = product.find('h2', class_='stime-product--details__title')
        name = name_tag.get_text(strip=True) if name_tag else 'Name not found'
        
        # Extract product price
        price_tag = product.find('span', class_='product--price__main')
        price = price_tag.get_text(strip=True) if price_tag else 'Price not found'
        
        # Print or store the extracted data
        print(f'Product: {name}, Price: {price}')
except Exception as e:
    print(f"An error occurred: {e}")
    print(e)
finally:
    driver.quit()
