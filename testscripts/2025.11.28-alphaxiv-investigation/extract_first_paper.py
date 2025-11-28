import time
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

def extract_metrics_from_first_paper():
    driver = setup_driver()
    url = "https://www.alphaxiv.org/?sort=Hot&interval=3+Days"
    print(f"Navigating to {url}...")
    
    try:
        driver.get(url)
        
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        print("Body loaded, waiting for JS rendering...")
        
        time.sleep(10)
        
        # Find all paper links
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/abs/']")
        print(f"Found {len(links)} paper links")
        
        if len(links) > 0:
            first_link = links[0]
            print(f"\nFirst paper href: {first_link.get_attribute('href')}")
            
            # Try to find the parent container
            parent = driver.execute_script("return arguments[0].closest('div[class*=\"mb\"]') || arguments[0].closest('div') || arguments[0].parentElement;", first_link)
            
            if parent:
                print(f"\n=== Parent container HTML ===")
                html = parent.get_attribute('outerHTML')
                print(html[:2000])
                
                # Save full HTML for inspection
                with open('/opt/airflow/testscripts/2025.11.28-alphaxiv-investigation/output/first_paper_container.html', 'w') as f:
                    f.write(html)
                print("\nSaved to first_paper_container.html")
                
                # Try to find vote/like elements
                print("\n=== Looking for vote/like elements ===")
                
                # Try common patterns
                vote_elements = parent.find_elements(By.XPATH, ".//*[contains(@class, 'vote') or contains(@class, 'like') or contains(@aria-label, 'vote') or contains(@aria-label, 'like')]")
                print(f"Found {len(vote_elements)} elements with vote/like in class or aria-label")
                
                for elem in vote_elements[:3]:
                    print(f"  {elem.tag_name}.{elem.get_attribute('class')}: text='{elem.text}', aria-label='{elem.get_attribute('aria-label')}'")
                
                # Find all spans/divs with numbers
                print("\n=== Elements with numbers ===")
                all_text_elements = parent.find_elements(By.XPATH, ".//*[text()]")
                for elem in all_text_elements[:20]:
                    text = elem.text.strip()
                    if text and (text.isdigit() or (len(text) < 10 and any(c.isdigit() for c in text))):
                        print(f"  {elem.tag_name}.{elem.get_attribute('class')}: '{text}'")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()

if __name__ == "__main__":
    extract_metrics_from_first_paper()
