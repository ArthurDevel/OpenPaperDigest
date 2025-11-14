#!/usr/bin/env python3
"""
Test script to verify pagination navigation on Microsoft Research.
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


def test_pagination_navigation():
    """Test navigating through pagination."""
    driver = setup_driver()

    try:
        print("=" * 80)
        print("Testing Microsoft Research Pagination Navigation")
        print("=" * 80)

        driver.get(MICROSOFT_RESEARCH_URL)
        print(f"\nLoading: {MICROSOFT_RESEARCH_URL}")
        time.sleep(3)

        # Get publications from page 1
        page1_urls = get_publication_urls(driver)
        print(f"\nPage 1: Found {len(page1_urls)} publication URLs")
        print(f"  First URL: {page1_urls[0] if page1_urls else 'None'}")
        print(f"  Current URL: {driver.current_url}")

        # Try to find and click "Next" button
        print("\n--- Attempting to navigate to page 2 ---")

        # Try different next button selectors
        next_selectors = [
            ".pagination a.next",
            "a[aria-label='Next']",
            ".pagination li.next a",
            ".pagination a[rel='next']",
        ]

        next_clicked = False
        for selector in next_selectors:
            try:
                print(f"Trying selector: {selector}")
                next_button = driver.find_element(By.CSS_SELECTOR, selector)
                print(f"  Found next button!")
                print(f"  Text: {next_button.text}")
                print(f"  Href: {next_button.get_attribute('href')}")

                # Click it
                driver.execute_script("arguments[0].click();", next_button)
                next_clicked = True
                print(f"  ✓ Clicked!")
                break
            except Exception as e:
                print(f"  Failed: {e}")
                continue

        if not next_clicked:
            print("\n✗ Could not find or click Next button")
            print("\n--- Looking for all links in pagination ---")
            pagination = driver.find_element(By.CSS_SELECTOR, ".pagination")
            all_links = pagination.find_elements(By.TAG_NAME, "a")
            for i, link in enumerate(all_links):
                print(f"  Link {i+1}: text='{link.text}' href='{link.get_attribute('href')}'")
            return

        # Wait for page to load
        time.sleep(3)

        # Get publications from page 2
        page2_urls = get_publication_urls(driver)
        print(f"\nPage 2: Found {len(page2_urls)} publication URLs")
        print(f"  First URL: {page2_urls[0] if page2_urls else 'None'}")
        print(f"  Current URL: {driver.current_url}")

        # Verify we got different publications
        if page1_urls and page2_urls:
            overlap = set(page1_urls) & set(page2_urls)
            print(f"\n--- Results ---")
            print(f"Page 1 URLs: {len(page1_urls)}")
            print(f"Page 2 URLs: {len(page2_urls)}")
            print(f"Overlap: {len(overlap)}")

            if len(overlap) == 0:
                print("✓ SUCCESS! Pagination works - different publications on each page")
            else:
                print("✗ WARNING! Some publications appear on both pages")

        # Try clicking next again to get to page 3
        print("\n--- Attempting to navigate to page 3 ---")
        try:
            next_button = driver.find_element(By.CSS_SELECTOR, ".pagination a[aria-label='Next']")
            driver.execute_script("arguments[0].click();", next_button)
            time.sleep(3)

            page3_urls = get_publication_urls(driver)
            print(f"\nPage 3: Found {len(page3_urls)} publication URLs")
            print(f"  First URL: {page3_urls[0] if page3_urls else 'None'}")
            print(f"  Current URL: {driver.current_url}")

            if page2_urls and page3_urls:
                overlap = set(page2_urls) & set(page3_urls)
                print(f"Overlap with page 2: {len(overlap)}")
        except Exception as e:
            print(f"Could not navigate to page 3: {e}")

    finally:
        driver.quit()
        print("\nBrowser closed")


if __name__ == "__main__":
    test_pagination_navigation()
