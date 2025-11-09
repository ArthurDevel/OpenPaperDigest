#!/usr/bin/env python3
"""
Test script to understand Google Research blog pagination.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time


def setup_driver():
    """Set up Selenium Chrome driver."""
    chrome_options = Options()
    # chrome_options.add_argument("--headless")  # Comment out to see what's happening
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(options=chrome_options)
    return driver


def main():
    """Test pagination on Google Research blog."""
    url = "https://research.google/blog/"

    print("=" * 80)
    print("Testing Google Research Blog Pagination")
    print("=" * 80)

    driver = setup_driver()

    try:
        # Load page
        print(f"\n1. Loading {url}")
        driver.get(url)
        time.sleep(3)

        # Find pagination elements
        print("\n2. Looking for pagination elements...")

        # Try to find pagination container
        try:
            pagination = driver.find_element(By.CSS_SELECTOR, ".pagination")
            print("   ✓ Found pagination container")
        except Exception as e:
            print(f"   ✗ No pagination container: {e}")
            return

        # Find all pagination links
        try:
            pagination_links = driver.find_elements(By.CSS_SELECTOR, ".pagination__link")
            print(f"   ✓ Found {len(pagination_links)} pagination links")

            for idx, link in enumerate(pagination_links[:5]):  # Show first 5
                data_page = link.get_attribute('data-page')
                text = link.text
                href = link.get_attribute('href')
                classes = link.get_attribute('class')
                print(f"     Link {idx}: data-page={data_page}, text='{text}', href={href}")
                print(f"              classes={classes}")
        except Exception as e:
            print(f"   ✗ No pagination links: {e}")

        # Find next button
        print("\n3. Looking for next page button...")
        try:
            next_button = driver.find_element(By.CSS_SELECTOR, ".pagination__next-button")
            print(f"   ✓ Found next button")
            print(f"     data-page: {next_button.get_attribute('data-page')}")
            print(f"     href: {next_button.get_attribute('href')}")
            print(f"     classes: {next_button.get_attribute('class')}")
        except Exception as e:
            print(f"   ✗ No next button: {e}")

        # Try to find link with data-page="2"
        print("\n4. Looking for page 2 link...")
        try:
            page2_link = driver.find_element(By.CSS_SELECTOR, "a[data-page='2']")
            print(f"   ✓ Found page 2 link")
            print(f"     text: {page2_link.text}")
            print(f"     href: {page2_link.get_attribute('href')}")
            print(f"     classes: {page2_link.get_attribute('class')}")
        except Exception as e:
            print(f"   ✗ No page 2 link: {e}")

        # Try clicking next multiple times to reach page 10
        print("\n5. Attempting to navigate to page 10...")
        try:
            for i in range(1, 10):
                print(f"\n   Clicking next button (page {i} -> {i+1})...")
                next_button = driver.find_element(By.CSS_SELECTOR, ".pagination__next-button")
                driver.execute_script("arguments[0].click();", next_button)
                time.sleep(2)

                # Check current page
                try:
                    current_page_elem = driver.find_element(By.CSS_SELECTOR, ".pagination__item--current .pagination__link")
                    current_page_text = current_page_elem.text
                    print(f"     Current page indicator: {current_page_text}")
                except:
                    print("     No current page indicator found")

                # Check URL
                current_url = driver.current_url
                print(f"     Current URL: {current_url}")

            print(f"\n   ✓ Successfully reached page 10")

        except Exception as e:
            print(f"   ✗ Failed during pagination: {e}")

        print("\n6. Waiting 5 seconds for inspection...")
        time.sleep(5)

    finally:
        driver.quit()
        print("\nBrowser closed")


if __name__ == "__main__":
    main()
