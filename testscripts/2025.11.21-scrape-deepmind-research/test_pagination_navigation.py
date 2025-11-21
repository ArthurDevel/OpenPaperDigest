#!/usr/bin/env python3
"""
Test script to verify pagination by URL navigation on DeepMind research publications.
Tests accessing pages directly via URL pattern: /page/1/, /page/2/, etc.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time


DEEPMIND_RESEARCH_BASE_URL = "https://deepmind.google/research/publications"


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


def count_publications_on_page(driver) -> int:
    """Count unique publication links on current page."""
    pub_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/publications/']")
    unique_pubs = set()
    for link in pub_links:
        href = link.get_attribute('href')
        if href and '/publications/' in href and href != DEEPMIND_RESEARCH_BASE_URL + '/':
            path_after = href.split('/publications/')[-1]
            if path_after and path_after.strip('/') and not path_after.startswith('page/'):
                unique_pubs.add(href)
    
    return len(unique_pubs)


def test_pagination_via_url():
    """Test pagination by directly accessing page URLs."""
    driver = setup_driver()

    try:
        print("=" * 80)
        print("Testing DeepMind Research Pagination via URL")
        print("=" * 80)

        # Test first 3 pages
        pages_to_test = 3
        all_publications = set()

        for page_num in range(1, pages_to_test + 1):
            if page_num == 1:
                # First page might be with or without /page/1/
                url = f"{DEEPMIND_RESEARCH_BASE_URL}/"
            else:
                url = f"{DEEPMIND_RESEARCH_BASE_URL}/page/{page_num}/"
            
            print(f"\n--- Testing Page {page_num}: {url} ---")
            driver.get(url)
            time.sleep(3)

            # Count publications
            count = count_publications_on_page(driver)
            print(f"Publications found on page {page_num}: {count}")

            # Collect publication URLs
            pub_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/publications/']")
            page_pubs = set()
            for link in pub_links:
                href = link.get_attribute('href')
                if href and '/publications/' in href and href != DEEPMIND_RESEARCH_BASE_URL + '/':
                    path_after = href.split('/publications/')[-1]
                    if path_after and path_after.strip('/') and not path_after.startswith('page/'):
                        page_pubs.add(href)
            
            # Check for new publications vs previous pages
            new_pubs = page_pubs - all_publications
            print(f"New publications on page {page_num}: {len(new_pubs)}")
            
            all_publications.update(page_pubs)

        print(f"\n{'=' * 80}")
        print(f"Total unique publications across {pages_to_test} pages: {len(all_publications)}")
        print(f"{'=' * 80}")

        # Test if page pattern works for higher page numbers
        print(f"\n--- Testing higher page number access ---")
        test_page = 5
        test_url = f"{DEEPMIND_RESEARCH_BASE_URL}/page/{test_page}/"
        print(f"Testing: {test_url}")
        driver.get(test_url)
        time.sleep(3)
        
        count = count_publications_on_page(driver)
        print(f"Publications found on page {test_page}: {count}")
        
        if count > 0:
            print(f"✓ Page {test_page} is accessible and has publications")
        else:
            print(f"✗ Page {test_page} appears empty or doesn't exist")

        # Display some sample publications from page 5
        if count > 0:
            print(f"\nSample publications from page {test_page}:")
            pub_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/publications/']")
            sample_count = 0
            for link in pub_links:
                if sample_count >= 3:
                    break
                href = link.get_attribute('href')
                if href and '/publications/' in href and href != DEEPMIND_RESEARCH_BASE_URL + '/':
                    path_after = href.split('/publications/')[-1]
                    if path_after and path_after.strip('/') and not path_after.startswith('page/'):
                        text = link.text.strip()
                        if text:
                            print(f"  - {text}")
                            print(f"    {href}")
                            sample_count += 1

    finally:
        driver.quit()
        print("\nBrowser closed")


if __name__ == "__main__":
    test_pagination_via_url()
