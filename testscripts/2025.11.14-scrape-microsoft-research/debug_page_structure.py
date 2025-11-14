#!/usr/bin/env python3
"""
Debug script to inspect the structure of a Microsoft Research publication page.
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


def inspect_publication_page(url: str):
    """
    Inspect a publication page and print all possible link elements.

    Args:
        url: Publication page URL
    """
    driver = setup_driver()

    try:
        print(f"Loading: {url}\n")
        driver.get(url)
        time.sleep(3)

        # Get title
        try:
            title = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
            print(f"Title: {title}\n")
        except:
            print("Could not find title\n")

        # Find all links on the page
        print("=" * 80)
        print("ALL LINKS ON PAGE:")
        print("=" * 80)
        all_links = driver.find_elements(By.TAG_NAME, "a")

        for idx, link in enumerate(all_links, 1):
            href = link.get_attribute('href')
            text = link.text.strip()
            classes = link.get_attribute('class')

            if href:
                print(f"{idx}. Text: '{text}' | Classes: '{classes}'")
                print(f"   URL: {href}")

                # Highlight PDF links
                if '.pdf' in href.lower():
                    print(f"   *** PDF LINK ***")

                print()

        # Look for specific button/link patterns
        print("\n" + "=" * 80)
        print("LOOKING FOR SPECIFIC PATTERNS:")
        print("=" * 80)

        patterns = [
            ("PDF links", "a[href*='.pdf']"),
            ("Download buttons", "a.c-button, button.c-button"),
            ("Links with 'publication' text", None),  # Custom search
            ("Links with 'download' text", None),  # Custom search
            ("Links with 'paper' text", None),  # Custom search
        ]

        for pattern_name, selector in patterns:
            print(f"\n{pattern_name}:")
            if selector:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        for elem in elements:
                            href = elem.get_attribute('href')
                            text = elem.text.strip()
                            print(f"  - Text: '{text}' | URL: {href}")
                    else:
                        print(f"  None found")
                except Exception as e:
                    print(f"  Error: {e}")
            else:
                # Custom text search
                search_text = pattern_name.split("'")[1]
                matching = [l for l in all_links if search_text.lower() in l.text.lower()]
                if matching:
                    for link in matching:
                        href = link.get_attribute('href')
                        text = link.text.strip()
                        print(f"  - Text: '{text}' | URL: {href}")
                else:
                    print(f"  None found")

        input("\nPress Enter to close browser...")

    finally:
        driver.quit()


if __name__ == "__main__":
    # Test with one of the publications that didn't have a PDF
    test_url = "https://www.microsoft.com/en-us/research/publication/serving-models-fast-and-slowoptimizing-heterogeneous-llm-inferencing-workloads-at-scale/"

    print("Microsoft Research Publication Page Inspector")
    print("=" * 80)
    print(f"Testing with: {test_url}\n")

    inspect_publication_page(test_url)
