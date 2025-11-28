import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
    chrome_options.binary_location = "/usr/bin/chromium"
    service = Service(executable_path="/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def test_exact_dag_logic():
    driver = setup_driver()
    url = "https://www.alphaxiv.org/?sort=Hot&interval=3+Days"
    print(f"Testing EXACT DAG logic on: {url}\n")
    
    try:
        driver.get(url)
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(10)
        
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/abs/']")
        print(f"Found {len(links)} paper links\n")
        
        # Test first 3 papers
        for i, link in enumerate(links[:3]):
            href = link.get_attribute('href')
            if href and '/abs/' in href:
                arxiv_id = href.split('/abs/')[1].split('?')[0]
                
                print(f"=== Paper {i+1}: {arxiv_id} ===")
                
                # EXACT DAG LOGIC
                likes = 0
                views = 0
                
                try:
                    container = driver.execute_script(
                        "return arguments[0].closest('div[class*=\"mb-\"]');",
                        link
                    )
                    
                    if container:
                        print("  Container: FOUND")
                        
                        # Extract LIKES - button with lucide-thumbs-up SVG
                        try:
                            thumbs_up_button = container.find_element(By.XPATH, ".//button[.//svg[contains(@class, 'lucide-thumbs-up')]]")
                            likes_element = thumbs_up_button.find_element(By.CSS_SELECTOR, "p")
                            likes = int(likes_element.text.replace(',', ''))
                            print(f"  Likes: {likes}")
                        except Exception as e:
                            print(f"  Likes: FAILED - {e}")
                        
                        # Extract VIEWS - div with lucide-chart-no-axes-column SVG
                        try:
                            chart_div = container.find_element(By.XPATH, ".//div[.//svg[contains(@class, 'lucide-chart-no-axes-column')]]")
                            views_text = chart_div.text.strip()
                            match = re.search(r'([\d,]+)', views_text)
                            if match:
                                views = int(match.group(1).replace(',', ''))
                            print(f"  Views: {views} (raw text: '{views_text}')")
                        except Exception as e:
                            print(f"  Views: FAILED - {e}")
                    else:
                        print("  Container: NOT FOUND")
                        
                except Exception as e:
                    print(f"  ERROR: {e}")
                
                print(f"  RESULT: likes={likes}, views={views}\n")

    finally:
        driver.quit()

if __name__ == "__main__":
    test_exact_dag_logic()
