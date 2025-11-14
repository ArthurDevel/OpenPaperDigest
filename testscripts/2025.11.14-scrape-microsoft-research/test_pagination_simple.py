#!/usr/bin/env python3
"""
Simple test to verify pagination works by URL parameter.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time


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


def get_publication_urls(driver):
    """Get all publication URLs on current page."""
    cards = driver.find_elements(By.CSS_SELECTOR, "article.m-publication, .publication-item, article")
    urls = []
    for card in cards:
        try:
            link = card.find_element(By.CSS_SELECTOR, "a[href*='/publication/']")
            href = link.get_attribute('href')
            if href and href not in urls:
                urls.append(href)
        except:
            continue
    return urls


def test_pagination_by_url():
    """Test pagination by directly visiting page URLs."""
    driver = setup_driver()

    try:
        print("=" * 80)
        print("Testing Microsoft Research Pagination by URL")
        print("=" * 80)

        pages_to_test = [
            "https://www.microsoft.com/en-us/research/publications/",  # Page 1
            "https://www.microsoft.com/en-us/research/publications/?pg=2",  # Page 2
            "https://www.microsoft.com/en-us/research/publications/?pg=3",  # Page 3
        ]

        all_urls = []

        for page_num, url in enumerate(pages_to_test, 1):
            print(f"\n--- Page {page_num}: {url} ---")
            driver.get(url)
            time.sleep(3)

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

        if all(len(all_urls[i] & all_urls[i + 1]) == 0 for i in range(len(all_urls) - 1)):
            print("\n✓ SUCCESS! Pagination works - all pages have unique publications")
        else:
            print("\n✗ WARNING! Some pages have overlapping publications")

    finally:
        driver.quit()
        print("\nBrowser closed")


if __name__ == "__main__":
    test_pagination_by_url()
