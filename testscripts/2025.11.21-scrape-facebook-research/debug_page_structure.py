#!/usr/bin/env python3
"""
Debug script to inspect the structure of Facebook Research publications page.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time


def setup_driver():
    """Set up Chrome driver."""
    chrome_options = Options()
    # Don't use headless so we can see what's happening
    # chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    return driver


def inspect_publication_listing_page(url: str):
    """
    Inspect the main publications listing page to understand its structure.

    Args:
        url: Publications listing page URL
    """
    driver = setup_driver()

    try:
        print(f"Loading: {url}\n")
        driver.get(url)
        print("Waiting for page to load...")
        time.sleep(5)  # Give time for JavaScript to render

        # Get page title
        print(f"Page title: {driver.title}\n")

        # Look for publication cards/items
        print("=" * 80)
        print("SEARCHING FOR PUBLICATION ELEMENTS:")
        print("=" * 80)

        # Try various selectors to find publication items
        selectors_to_try = [
            ("article", "Article elements"),
            (".publication", "Elements with class 'publication'"),
            (".paper", "Elements with class 'paper'"),
            ("[class*='publication']", "Elements with 'publication' in class"),
            ("[class*='paper']", "Elements with 'paper' in class"),
            ("[class*='research']", "Elements with 'research' in class"),
            ("a[href*='publication']", "Links containing 'publication'"),
            ("a[href*='paper']", "Links containing 'paper'"),
        ]

        for selector, description in selectors_to_try:
            print(f"\n{description} ({selector}):")
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                print(f"  Found {len(elements)} elements")
                
                # Show first few
                for idx, elem in enumerate(elements[:3], 1):
                    try:
                        text = elem.text.strip()[:100]
                        href = elem.get_attribute('href')
                        classes = elem.get_attribute('class')
                        print(f"  #{idx}:")
                        print(f"    Text: {text}...")
                        print(f"    Classes: {classes}")
                        if href:
                            print(f"    URL: {href}")
                    except:
                        pass
            except Exception as e:
                print(f"  Error: {e}")

        # Look for all links on page
        print("\n" + "=" * 80)
        print("SAMPLE OF LINKS ON PAGE:")
        print("=" * 80)
        all_links = driver.find_elements(By.TAG_NAME, "a")
        print(f"Total links found: {len(all_links)}\n")

        # Show first 20 links
        for idx, link in enumerate(all_links[:20], 1):
            href = link.get_attribute('href')
            text = link.text.strip()[:50]
            if href:
                print(f"{idx}. Text: '{text}' | URL: {href}")

        # Check page source for any obvious patterns
        print("\n" + "=" * 80)
        print("PAGE SOURCE ANALYSIS:")
        print("=" * 80)
        page_source = driver.page_source.lower()
        
        patterns_to_check = ['arxiv', 'pdf', 'publication', 'paper', 'research']
        for pattern in patterns_to_check:
            count = page_source.count(pattern)
            print(f"'{pattern}' appears {count} times in page source")

        input("\nPress Enter to close browser...")

    finally:
        driver.quit()


if __name__ == "__main__":
    url = "https://research.facebook.com/publications/"
    
    print("Facebook Research Publications Page Inspector")
    print("=" * 80)
    print(f"Testing with: {url}\n")

    inspect_publication_listing_page(url)
