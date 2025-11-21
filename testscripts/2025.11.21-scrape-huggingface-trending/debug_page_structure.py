#!/usr/bin/env python3
"""
Debug script to inspect the structure of the Hugging Face trending papers page.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time


### CONSTANTS ###

HUGGINGFACE_TRENDING_URL = "https://huggingface.co/papers/trending"


### HELPER FUNCTIONS ###

def setup_driver():
    """
    Set up Chrome driver for debugging.
    
    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance
    """
    chrome_options = Options()
    # Don't use headless so we can see what's happening
    # chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    return driver


def inspect_trending_page(url: str):
    """
    Inspect the trending papers page and print structure information.
    
    Args:
        url: URL of the trending papers page
    """
    driver = setup_driver()

    try:
        print(f"Loading: {url}\n")
        driver.get(url)
        time.sleep(5)  # Give time for JavaScript to render

        # Get page title
        print(f"Page Title: {driver.title}\n")

        # Look for paper cards/items
        print("=" * 80)
        print("LOOKING FOR PAPER CARDS/ITEMS:")
        print("=" * 80)

        # Try various selectors that might contain papers
        selectors_to_try = [
            ("article", "Article elements"),
            ("[class*='paper']", "Elements with 'paper' in class"),
            ("[class*='card']", "Elements with 'card' in class"),
            ("[class*='item']", "Elements with 'item' in class"),
            ("[class*='trending']", "Elements with 'trending' in class"),
            ("a[href*='/papers/']", "Links to paper pages"),
            ("a[href*='arxiv']", "ArXiv links"),
        ]

        for selector, description in selectors_to_try:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"\n✓ Found {len(elements)}: {description}")
                    print(f"  Selector: {selector}")
                    # Show first few elements
                    for i, elem in enumerate(elements[:3]):
                        print(f"\n  Element {i+1}:")
                        print(f"    Tag: {elem.tag_name}")
                        print(f"    Text: {elem.text[:150]}")
                        print(f"    Classes: {elem.get_attribute('class')}")
                        if elem.tag_name == 'a':
                            href = elem.get_attribute('href')
                            print(f"    Href: {href}")
            except Exception as e:
                print(f"\n✗ Error with {description}: {e}")

        # Look for all links on the page
        print("\n" + "=" * 80)
        print("ALL LINKS ON PAGE (first 20):")
        print("=" * 80)
        all_links = driver.find_elements(By.TAG_NAME, "a")

        for idx, link in enumerate(all_links[:20], 1):
            href = link.get_attribute('href')
            text = link.text.strip()
            classes = link.get_attribute('class')

            if href:
                print(f"{idx}. Text: '{text[:80]}' | Classes: '{classes}'")
                print(f"   URL: {href}")

                # Highlight paper/arXiv links
                if '/papers/' in href or 'arxiv' in href.lower():
                    print(f"   *** PAPER LINK ***")

                print()

        # Check for pagination or infinite scroll
        print("\n" + "=" * 80)
        print("CHECKING FOR PAGINATION:")
        print("=" * 80)

        pagination_selectors = [
            (".pagination", "Pagination container"),
            ("button[class*='load']", "Load more button"),
            ("button[class*='more']", "More button"),
            ("[class*='pagination']", "Any pagination class"),
            ("[class*='infinite']", "Infinite scroll indicator"),
        ]

        found_pagination = False
        for selector, description in pagination_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"\n✓ Found: {description}")
                    print(f"  Selector: {selector}")
                    print(f"  Count: {len(elements)}")
                    for i, elem in enumerate(elements[:2]):
                        print(f"  Element {i+1}: Text: '{elem.text[:100]}'")
                    found_pagination = True
            except Exception as e:
                pass

        if not found_pagination:
            print("\n✗ No obvious pagination elements found")

        # Test infinite scroll
        print("\n--- Testing for infinite scroll ---")
        initial_count = len(driver.find_elements(By.CSS_SELECTOR, "article, [class*='paper'], [class*='card']"))
        print(f"Initial item count: {initial_count}")

        # Scroll to bottom
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

        after_scroll_count = len(driver.find_elements(By.CSS_SELECTOR, "article, [class*='paper'], [class*='card']"))
        print(f"After scroll count: {after_scroll_count}")

        if after_scroll_count > initial_count:
            print(f"✓ Infinite scroll detected! {after_scroll_count - initial_count} more items loaded")
        else:
            print("✗ No infinite scroll detected")

        # Save page source for manual inspection in output folder
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(script_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "huggingface_trending_page_source.html")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print(f"\n✓ Page source saved to: {output_file}")

        input("\nPress Enter to close browser...")

    finally:
        driver.quit()
        print("\nBrowser closed")


### MAIN ENTRYPOINT ###

if __name__ == "__main__":
    print("Hugging Face Trending Papers Page Inspector")
    print("=" * 80)
    print(f"Testing with: {HUGGINGFACE_TRENDING_URL}\n")

    inspect_trending_page(HUGGINGFACE_TRENDING_URL)

