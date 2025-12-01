import time
import re
import requests
import json
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
    
    # Try Docker paths first, then fall back to local
    import os
    if os.path.exists("/usr/bin/chromium"):
        chrome_options.binary_location = "/usr/bin/chromium"
        service = Service(executable_path="/usr/bin/chromedriver")
    else:
        # Local development - use system Chrome/Chromium
        service = Service()  # Will use chromedriver from PATH
    
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def fetch_title_from_jsonld(arxiv_id: str) -> str:
    """
    Fetch title from JSON-LD on paper page.
    
    Args:
        arxiv_id: The arXiv ID
        
    Returns:
        Title string or None if not found
    """
    paper_url = f"https://www.alphaxiv.org/abs/{arxiv_id}"
    
    try:
        response = requests.get(paper_url, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"  Warning: Failed to fetch paper page for {arxiv_id}: {e}")
        return None
    
    # Extract JSON-LD data from the page
    match = re.search(
        r'<script data-alphaxiv-id="json-ld-paper-detail-view" type="application/ld\+json">(.+?)</script>',
        response.text
    )
    
    if not match:
        print(f"  Warning: Could not find JSON-LD data for {arxiv_id}")
        return None
    
    try:
        json_ld = json.loads(match.group(1))
        # JSON-LD typically has 'name' or 'headline' for title
        title = json_ld.get('name') or json_ld.get('headline')
        return title
    except json.JSONDecodeError as e:
        print(f"  Warning: Failed to parse JSON-LD for {arxiv_id}: {e}")
        return None

def test_title_extraction():
    """
    Test title extraction using the exact DAG logic and alternatives.
    """
    driver = setup_driver()
    url = "https://www.alphaxiv.org/?sort=Hot&interval=3+Days"
    print(f"Testing title extraction on: {url}\n")
    
    try:
        driver.get(url)
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(10)
        
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/abs/']")
        print(f"Found {len(links)} paper links\n")
        
        # Test first 5 papers
        for i, link in enumerate(links[:5]):
            href = link.get_attribute('href')
            if href and '/abs/' in href:
                arxiv_id = href.split('/abs/')[1].split('?')[0]
                
                print(f"=== Paper {i+1}: {arxiv_id} ===")
                
                # METHOD 1: Current DAG logic (link.text)
                title_method1 = None
                try:
                    text = link.text.strip()
                    if text and len(text) > 10:
                        title_method1 = text
                        print(f"  Method 1 (link.text): '{title_method1[:80]}...'")
                    else:
                        print(f"  Method 1 (link.text): FAILED - text='{text}', len={len(text) if text else 0}")
                except Exception as e:
                    print(f"  Method 1 (link.text): ERROR - {e}")
                
                # METHOD 2: Look for h2 or h3 inside the link
                title_method2 = None
                try:
                    h2_elem = link.find_element(By.TAG_NAME, "h2")
                    if h2_elem:
                        title_method2 = h2_elem.text.strip()
                        print(f"  Method 2 (h2 inside link): '{title_method2[:80]}...'")
                except:
                    try:
                        h3_elem = link.find_element(By.TAG_NAME, "h3")
                        if h3_elem:
                            title_method2 = h3_elem.text.strip()
                            print(f"  Method 2 (h3 inside link): '{title_method2[:80]}...'")
                    except:
                        print(f"  Method 2 (h2/h3 inside link): NOT FOUND")
                
                # METHOD 3: Look for span with specific classes
                title_method3 = None
                try:
                    # Try to find span elements that might contain title
                    spans = link.find_elements(By.TAG_NAME, "span")
                    for span in spans:
                        text = span.text.strip()
                        if text and len(text) > 10:
                            # Check if it looks like a title (not a number or short text)
                            if not text.replace(',', '').isdigit() and len(text) > 20:
                                title_method3 = text
                                print(f"  Method 3 (span in link): '{title_method3[:80]}...'")
                                break
                    if not title_method3:
                        print(f"  Method 3 (span in link): NOT FOUND")
                except Exception as e:
                    print(f"  Method 3 (span in link): ERROR - {e}")
                
                # METHOD 4: Get from container (parent div)
                title_method4 = None
                try:
                    container = driver.execute_script(
                        "return arguments[0].closest('div[class*=\"mb-\"]');",
                        link
                    )
                    if container:
                        # Look for h2 or h3 in container
                        try:
                            h2 = container.find_element(By.TAG_NAME, "h2")
                            title_method4 = h2.text.strip()
                            print(f"  Method 4 (h2 in container): '{title_method4[:80]}...'")
                        except:
                            try:
                                h3 = container.find_element(By.TAG_NAME, "h3")
                                title_method4 = h3.text.strip()
                                print(f"  Method 4 (h3 in container): '{title_method4[:80]}...'")
                            except:
                                print(f"  Method 4 (h2/h3 in container): NOT FOUND")
                except Exception as e:
                    print(f"  Method 4 (container): ERROR - {e}")
                
                # METHOD 5: Fetch from JSON-LD on paper page
                print(f"  Method 5 (JSON-LD from paper page): Fetching...")
                title_method5 = fetch_title_from_jsonld(arxiv_id)
                if title_method5:
                    print(f"  Method 5 (JSON-LD): '{title_method5[:80]}...'")
                else:
                    print(f"  Method 5 (JSON-LD): FAILED")
                
                # Summary
                print(f"\n  SUMMARY:")
                print(f"    Method 1 (link.text): {'✓' if title_method1 else '✗'}")
                print(f"    Method 2 (h2/h3 in link): {'✓' if title_method2 else '✗'}")
                print(f"    Method 3 (span in link): {'✓' if title_method3 else '✗'}")
                print(f"    Method 4 (h2/h3 in container): {'✓' if title_method4 else '✗'}")
                print(f"    Method 5 (JSON-LD): {'✓' if title_method5 else '✗'}")
                
                # Best title
                best_title = title_method1 or title_method2 or title_method3 or title_method4 or title_method5
                if best_title:
                    print(f"    BEST TITLE: '{best_title[:80]}...'")
                else:
                    print(f"    ⚠️  NO TITLE FOUND FOR {arxiv_id}")
                
                print("")
        
    finally:
        driver.quit()

if __name__ == "__main__":
    test_title_extraction()

