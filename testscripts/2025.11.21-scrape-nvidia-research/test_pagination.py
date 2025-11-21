#!/usr/bin/env python3
"""
Test pagination for NVIDIA Research publications.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time


def setup_driver():
    """
    Set up Selenium Chrome driver.

    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    return driver


def get_publication_urls(driver):
    """
    Get all publication URLs on current page.

    Args:
        driver: Selenium WebDriver instance

    Returns:
        List[str]: List of publication URLs
    """
    urls = []
    try:
        pub_list = driver.find_element(By.CSS_SELECTOR, ".nv-publications-list")
        all_links = pub_list.find_elements(By.CSS_SELECTOR, "a")
        seen_urls = set()
        
        for link in all_links:
            href = link.get_attribute('href')
            if href and href not in seen_urls:
                if '/publication/' in href and '?page=' not in href and '?f%5B' not in href and '#' not in href:
                    seen_urls.add(href)
                    urls.append(href)
    except Exception as e:
        print(f"Error getting publication URLs: {e}")
    
    return urls


def test_pagination_by_url():
    """
    Test pagination by directly visiting page URLs.
    """
    driver = setup_driver()

    try:
        print("=" * 80)
        print("Testing NVIDIA Research Pagination by URL")
        print("=" * 80)

        pages_to_test = [
            "https://research.nvidia.com/publications",  # Page 1 (page=0)
            "https://research.nvidia.com/publications?page=0",  # Page 1 explicit
            "https://research.nvidia.com/publications?page=1",  # Page 2
            "https://research.nvidia.com/publications?page=2",  # Page 3
        ]

        all_urls = []

        for page_num, url in enumerate(pages_to_test, 1):
            print(f"\n--- Page {page_num}: {url} ---")
            driver.get(url)
            time.sleep(5)  # Wait for JavaScript to render

            pub_urls = get_publication_urls(driver)
            print(f"Found {len(pub_urls)} publications")
            if pub_urls:
                print(f"First: {pub_urls[0]}")
                print(f"Last: {pub_urls[-1]}")

            all_urls.append(set(pub_urls))

        # Check for overlap
        print(f"\n{'=' * 80}")
        print("Checking for overlaps:")
        print(f"{'=' * 80}")

        for i in range(len(all_urls) - 1):
            overlap = all_urls[i] & all_urls[i + 1]
            print(f"Page {i+1} vs Page {i+2}: {len(overlap)} overlapping publications")
            if overlap:
                print(f"  Overlapping URLs (first 3): {list(overlap)[:3]}")

        if all(len(all_urls[i] & all_urls[i + 1]) == 0 for i in range(len(all_urls) - 1)):
            print("\n✓ SUCCESS! Pagination works - all pages have unique publications")
        else:
            print("\n✗ WARNING! Some pages have overlapping publications")

    finally:
        driver.quit()
        print("\nBrowser closed")


if __name__ == "__main__":
    test_pagination_by_url()

