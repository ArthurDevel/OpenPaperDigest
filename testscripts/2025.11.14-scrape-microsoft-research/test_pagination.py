#!/usr/bin/env python3
"""
Test script to verify pagination on Microsoft Research publications page.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time


MICROSOFT_RESEARCH_URL = "https://www.microsoft.com/en-us/research/publications"


def setup_driver():
    """Set up Selenium Chrome driver."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    return driver


def test_pagination():
    """Test if pagination exists and how to navigate it."""
    driver = setup_driver()

    try:
        print("=" * 80)
        print("Testing Microsoft Research Pagination")
        print("=" * 80)

        driver.get(MICROSOFT_RESEARCH_URL)
        print(f"\nLoading: {MICROSOFT_RESEARCH_URL}")
        time.sleep(3)

        # Count publications on first page
        cards = driver.find_elements(By.CSS_SELECTOR, "article.m-publication, .publication-item, article")
        print(f"Publications found on page 1: {len(cards)}")

        # Look for pagination controls
        print("\n--- Looking for pagination elements ---")

        # Try different pagination selectors
        pagination_selectors = [
            (".pagination", "Pagination container"),
            (".pagination a.next", "Next button (link)"),
            ("button.next", "Next button"),
            ("a[aria-label*='next']", "Next link (aria-label)"),
            (".pager", "Pager container"),
            ("[class*='pagination']", "Any pagination class"),
            ("[class*='pager']", "Any pager class"),
            ("nav[role='navigation']", "Navigation role"),
        ]

        found_pagination = False
        for selector, description in pagination_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"\n✓ Found: {description}")
                    print(f"  Selector: {selector}")
                    print(f"  Count: {len(elements)}")
                    for i, elem in enumerate(elements[:3]):  # Show first 3
                        print(f"  Element {i+1}:")
                        print(f"    Tag: {elem.tag_name}")
                        print(f"    Text: {elem.text[:100]}")
                        print(f"    Classes: {elem.get_attribute('class')}")
                        if elem.tag_name == 'a':
                            print(f"    Href: {elem.get_attribute('href')}")
                    found_pagination = True
            except Exception as e:
                pass

        if not found_pagination:
            print("\n✗ No pagination elements found")

        # Check page source for pagination-related terms
        print("\n--- Checking page source for pagination keywords ---")
        page_source = driver.page_source.lower()
        keywords = ['pagination', 'pager', 'next page', 'load more', 'show more']
        for keyword in keywords:
            if keyword in page_source:
                print(f"✓ Found keyword: '{keyword}'")

        # Try scrolling to see if it's infinite scroll
        print("\n--- Testing for infinite scroll ---")
        initial_count = len(driver.find_elements(By.CSS_SELECTOR, "article.m-publication, .publication-item, article"))
        print(f"Initial publication count: {initial_count}")

        # Scroll to bottom
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

        # Check if more loaded
        after_scroll_count = len(driver.find_elements(By.CSS_SELECTOR, "article.m-publication, .publication-item, article"))
        print(f"After scroll count: {after_scroll_count}")

        if after_scroll_count > initial_count:
            print(f"✓ Infinite scroll detected! {after_scroll_count - initial_count} more publications loaded")
        else:
            print("✗ No infinite scroll detected")

        # Save page source for manual inspection
        with open('microsoft_research_page_source.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print("\n✓ Page source saved to: microsoft_research_page_source.html")

    finally:
        driver.quit()
        print("\nBrowser closed")


if __name__ == "__main__":
    test_pagination()
