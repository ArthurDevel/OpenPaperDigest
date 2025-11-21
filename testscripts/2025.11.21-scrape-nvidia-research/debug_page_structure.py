#!/usr/bin/env python3
"""
Debug script to inspect the structure of NVIDIA Research publications page.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time


def setup_driver():
    """
    Set up Chrome driver.

    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance
    """
    chrome_options = Options()
    # Don't use headless so we can see what's happening
    # chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    return driver


def inspect_publications_page(url: str):
    """
    Inspect the publications listing page and print structure.

    Args:
        url: Publications page URL
    """
    driver = setup_driver()

    try:
        print(f"Loading: {url}\n")
        driver.get(url)
        time.sleep(5)  # Wait for JavaScript to render

        # Get page title
        print(f"Page Title: {driver.title}\n")

        # Find all publication cards/items
        print("=" * 80)
        print("LOOKING FOR PUBLICATION CARDS:")
        print("=" * 80)

        # Try different selectors
        selectors = [
            ("article elements", "article"),
            ("elements with 'publication' class", ".publication"),
            ("list items", "li"),
            ("divs with publication-related classes", "div[class*='publication'], div[class*='paper']"),
            ("all links", "a"),
        ]

        for selector_name, selector in selectors:
            print(f"\n{selector_name} ({selector}):")
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                print(f"  Found {len(elements)} elements")
                if elements:
                    # Show first few examples
                    for idx, elem in enumerate(elements[:5], 1):
                        text = elem.text.strip()[:100] if elem.text else ""
                        href = elem.get_attribute('href') or ""
                        classes = elem.get_attribute('class') or ""
                        print(f"  {idx}. Text: '{text[:50]}...' | Classes: '{classes[:50]}' | Href: '{href[:80]}'")
            except Exception as e:
                print(f"  Error: {e}")

        # Look for pagination
        print("\n" + "=" * 80)
        print("LOOKING FOR PAGINATION:")
        print("=" * 80)

        pagination_selectors = [
            (".pagination"),
            ("nav[aria-label*='pagination']"),
            ("a[href*='page']"),
            ("button[aria-label*='next']"),
            ("a[aria-label*='next']"),
            (".next"),
            (".pagination a"),
        ]

        for selector in pagination_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"\nFound with selector '{selector}': {len(elements)} elements")
                    for elem in elements[:3]:
                        text = elem.text.strip()
                        href = elem.get_attribute('href') or ""
                        print(f"  - Text: '{text}' | Href: '{href}'")
            except Exception as e:
                pass

        # Inspect the publications list container
        print("\n" + "=" * 80)
        print("INSPECTING PUBLICATION LIST CONTAINER:")
        print("=" * 80)
        
        try:
            pub_list = driver.find_element(By.CSS_SELECTOR, ".nv-publications-list")
            print(f"Found publications list container")
            
            # Find all links within the publications list
            links_in_list = pub_list.find_elements(By.CSS_SELECTOR, "a")
            print(f"Found {len(links_in_list)} links in publications list")
            
            # Show first few publication links
            print("\nFirst 10 publication links:")
            for idx, link in enumerate(links_in_list[:10], 1):
                href = link.get_attribute('href') or ""
                text = link.text.strip()[:80] if link.text else ""
                if href and ('/publication' in href or '/publications' in href):
                    print(f"  {idx}. Text: '{text}' | Href: '{href}'")
        except Exception as e:
            print(f"Error inspecting publication list: {e}")

        # Print page source snippet to understand structure
        print("\n" + "=" * 80)
        print("PAGE SOURCE SNIPPET (first 2000 chars):")
        print("=" * 80)
        print(driver.page_source[:2000])

    finally:
        driver.quit()


if __name__ == "__main__":
    test_url = "https://research.nvidia.com/publications"

    print("NVIDIA Research Publications Page Inspector")
    print("=" * 80)
    print(f"Testing with: {test_url}\n")

    inspect_publications_page(test_url)

