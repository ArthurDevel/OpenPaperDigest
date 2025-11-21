#!/usr/bin/env python3
"""
Test script to verify pagination on DeepMind research publications page.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time


DEEPMIND_RESEARCH_URL = "https://deepmind.google/research/publications/"


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
        print("Testing DeepMind Research Pagination")
        print("=" * 80)

        driver.get(DEEPMIND_RESEARCH_URL)
        print(f"\nLoading: {DEEPMIND_RESEARCH_URL}")
        time.sleep(3)

        # Count publications on first page
        pub_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/publications/']")
        # Filter to only unique publication detail pages
        unique_pubs = set()
        for link in pub_links:
            href = link.get_attribute('href')
            if href and '/publications/' in href and href != DEEPMIND_RESEARCH_URL:
                path_after = href.split('/publications/')[-1]
                if path_after and path_after.strip('/'):
                    unique_pubs.add(href)
        
        print(f"Publications found on page 1: {len(unique_pubs)}")

        # Look for pagination controls
        print("\n--- Looking for pagination elements ---")

        # Try different pagination selectors
        pagination_selectors = [
            (".pagination", "Pagination container"),
            (".pagination a.next", "Next button (link)"),
            ("button.next", "Next button"),
            ("a[aria-label*='next']", "Next link (aria-label)"),
            ("button[aria-label*='next']", "Next button (aria-label)"),
            ("button[aria-label*='load']", "Load more button (aria-label)"),
            ("button[aria-label*='more']", "Show more button (aria-label)"),
            (".pager", "Pager container"),
            ("[class*='pagination']", "Any pagination class"),
            ("[class*='pager']", "Any pager class"),
            ("nav[role='navigation']", "Navigation role"),
            (".load-more", "Load more class"),
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
                        if elem.tag_name == 'button':
                            print(f"    Aria-label: {elem.get_attribute('aria-label')}")
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
        initial_count = len(unique_pubs)
        print(f"Initial publication count: {initial_count}")

        # Scroll to bottom
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

        # Re-count
        pub_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/publications/']")
        unique_pubs_after = set()
        for link in pub_links:
            href = link.get_attribute('href')
            if href and '/publications/' in href and href != DEEPMIND_RESEARCH_URL:
                path_after = href.split('/publications/')[-1]
                if path_after and path_after.strip('/'):
                    unique_pubs_after.add(href)
        
        after_scroll_count = len(unique_pubs_after)
        print(f"After scroll count: {after_scroll_count}")

        if after_scroll_count > initial_count:
            print(f"✓ Infinite scroll detected! {after_scroll_count - initial_count} more publications loaded")
        else:
            print("✗ No infinite scroll detected")

        # Save page source for manual inspection
        with open('deepmind_research_page_source.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print("\n✓ Page source saved to: deepmind_research_page_source.html")

    finally:
        driver.quit()
        print("\nBrowser closed")


if __name__ == "__main__":
    test_pagination()
