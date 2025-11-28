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

    # Point to system chromium binary
    chrome_options.binary_location = "/usr/bin/chromium"

    # Point to system chromedriver
    service = Service(executable_path="/usr/bin/chromedriver")

    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def scrape_alphaxiv():
    driver = setup_driver()
    url = "https://www.alphaxiv.org/"
    print(f"Navigating to {url}...")
    
    try:
        driver.get(url)
        
        # Wait for content to load
        print("Waiting for content...")
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            print("Body element found!")
        except Exception as e:
            print(f"Timeout waiting for body: {e}")
            print("Page title:", driver.title)
        
        # Give it a bit more time for dynamic rendering
        time.sleep(10)
        
        print("Looking for paper links...")
        
        # Find paper links
        # Based on the HTML I saw earlier, links are like <a href="/abs/2401.12345">
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/abs/']")
        
        print(f"Found {len(links)} potential paper links.")
        
        if len(links) == 0:
            print("No links found! Trying alternative approach...")
            # Try to find any links
            all_links_elements = driver.find_elements(By.TAG_NAME, "a")
            print(f"Total links on page: {len(all_links_elements)}")
            # Print first 10 hrefs
            for i, link in enumerate(all_links_elements[:10]):
                try:
                    href = link.get_attribute('href')
                    print(f"  Link {i}: {href}")
                except:
                    pass
        
        unique_papers = set()
        
        for link in links:
            href = link.get_attribute('href')
            if href and '/abs/' in href:
                # Extract ID
                parts = href.split('/abs/')
                if len(parts) > 1:
                    paper_id = parts[1]
                    # Sometimes there are query params
                    paper_id = paper_id.split('?')[0]
                    
                    if paper_id not in unique_papers:
                        unique_papers.add(paper_id)
                        print(f"Found Paper: {paper_id} -> {href}")
                        
                        # Try to get title?
                        # The title might be inside the <a> tag or a sibling/parent.
                        # In the HTML snippet I saw: <h2><span ...>Title</span></h2> wrapped in <a>
                        try:
                            text = link.text
                            if text and len(text) > 10:
                                print(f"  Title candidate: {text[:100]}...")
                        except:
                            pass

        print(f"\nTotal unique papers found: {len(unique_papers)}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        # Print page source for debugging if needed
        try:
            print("Page source (first 1000 chars):")
            print(driver.page_source[:1000])
        except:
            pass
    finally:
        driver.quit()

if __name__ == "__main__":
    scrape_alphaxiv()
