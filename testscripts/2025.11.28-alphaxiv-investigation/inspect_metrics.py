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

def inspect_paper_cards():
    driver = setup_driver()
    url = "https://www.alphaxiv.org/?sort=Hot&interval=3+Days"
    print(f"Navigating to {url}...")
    
    try:
        driver.get(url)
        
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        print("Body loaded!")
        
        time.sleep(10)
        
        # Find the first paper card/article
        # Try different selectors to find paper containers
        print("\n=== Searching for paper containers ===")
        
        # Try finding by common article/card selectors
        containers = driver.find_elements(By.CSS_SELECTOR, "article, div[class*='paper'], div[class*='card']")
        print(f"Found {len(containers)} potential containers")
        
        if len(containers) > 0:
            print(f"\n=== Inspecting first container ===")
            first = containers[0]
            print(f"Tag: {first.tag_name}")
            print(f"Classes: {first.get_attribute('class')}")
            print(f"Text (first 200 chars): {first.text[:200]}")
            
            # Look for links inside
            links = first.find_elements(By.TAG_NAME, "a")
            print(f"\nLinks found: {len(links)}")
            for i, link in enumerate(links[:3]):
                href = link.get_attribute('href')
                text = link.text.strip()
                print(f"  Link {i}: {href}")
                if text:
                    print(f"    Text: {text[:50]}")
            
            # Look for elements with numbers (votes/likes/views)
            # Common patterns: svg icons with numbers, spans with counts
            print("\n=== Looking for metrics (votes/likes/views) ===")
            
            # Find all elements with text that looks like numbers
            all_elements = first.find_elements(By.XPATH, ".//*[text()]")
            for elem in all_elements:
                text = elem.text.strip()
                if text.isdigit() or any(char.isdigit() for char in text):
                    print(f"  {elem.tag_name}.{elem.get_attribute('class')}: '{text}'")
            
            # Also check for aria-labels or data attributes
            print("\n=== Checking for aria-labels / data attributes ===")
            interactive_elements = first.find_elements(By.CSS_SELECTOR, "button, [role='button'], [aria-label]")
            for elem in interactive_elements[:5]:
                aria_label = elem.get_attribute('aria-label')
                data_attrs = driver.execute_script(
                    "return Array.from(arguments[0].attributes).filter(a => a.name.startsWith('data-')).map(a => a.name + '=' + a.value);",
                    elem
                )
                if aria_label or data_attrs:
                    print(f"  {elem.tag_name}: aria-label='{aria_label}', data={data_attrs}")

        # Save HTML of first few cards for inspection
        print("\n=== Saving HTML ===")
        if len(containers) > 0:
            with open('/opt/airflow/testscripts/2025.11.28-alphaxiv-investigation/output/first_card.html', 'w') as f:
                f.write(containers[0].get_attribute('outerHTML'))
            print("Saved first card HTML to first_card.html")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()

if __name__ == "__main__":
    inspect_paper_cards()
