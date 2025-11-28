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

def test_extraction():
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
        
        # Find first paper link
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/abs/']")
        print(f"Found {len(links)} links")
        
        if len(links) > 0:
            link = links[0]
            href = link.get_attribute('href')
            print(f"\nFirst paper: {href}")
            
            # Try the exact same logic as the DAG
            print("\n=== Testing DAG logic ===")
            
            try:
                container = driver.execute_script(
                    "return arguments[0].closest('div[class*=\"mb-\"]');",
                    link
                )
                print(f"Container found: {container is not None}")
                
                if container:
                    # Test CSS selector
                    print("\n--- Testing CSS selector ---")
                    try:
                        vote_elements = container.find_elements(By.CSS_SELECTOR, "span.text-\\[17px\\], p.text-\\[17px\\]")
                        print(f"Found {len(vote_elements)} vote elements with escaped brackets")
                        for i, elem in enumerate(vote_elements[:3]):
                            print(f"  Element {i}: '{elem.text}'")
                    except Exception as e:
                        print(f"Error with escaped brackets: {e}")
                    
                    # Try without escaping
                    print("\n--- Testing without escaping ---")
                    try:
                        vote_elements2 = container.find_elements(By.CSS_SELECTOR, 'span[class*="text-[17px]"], p[class*="text-[17px]"]')
                        print(f"Found {len(vote_elements2)} vote elements with contains")
                        for i, elem in enumerate(vote_elements2[:3]):
                            print(f"  Element {i}: '{elem.text}'")
                    except Exception as e:
                        print(f"Error: {e}")
                    
                    # Try XPath
                    print("\n--- Testing XPath ---")
                    try:
                        vote_elements3 = container.find_elements(By.XPATH, ".//span[contains(@class, 'text-[17px]')] | .//p[contains(@class, 'text-[17px]')]")
                        print(f"Found {len(vote_elements3)} vote elements with XPath")
                        for i, elem in enumerate(vote_elements3[:3]):
                            print(f"  Element {i}: '{elem.text}'")
                    except Exception as e:
                        print(f"Error: {e}")
                        
                    # Test views extraction
                    print("\n--- Testing views extraction ---")
                    try:
                        view_elements = container.find_elements(By.XPATH, ".//svg[contains(@class, 'lucide-chart')]/following-sibling::*[1]")
                        print(f"Found {len(view_elements)} view elements")
                        for i, elem in enumerate(view_elements[:3]):
                            print(f"  Element {i}: '{elem.text}'")
                    except Exception as e:
                        print(f"Error: {e}")
                    
                    # Alternative: look for the specific number pattern in all text elements
                    print("\n--- All numeric text elements ---")
                    all_elems = container.find_elements(By.XPATH, ".//*[text()]")
                    for elem in all_elems[:30]:
                        text = elem.text.strip()
                        if text and any(c.isdigit() for c in text) and len(text) < 20:
                            classes = elem.get_attribute('class')
                            print(f"  {elem.tag_name} class=\"{classes[:50] if classes else 'none'}\": '{text}'")
                            
            except Exception as e:
                print(f"Error in extraction: {e}")
                import traceback
                traceback.print_exc()

    finally:
        driver.quit()

if __name__ == "__main__":
    test_extraction()
