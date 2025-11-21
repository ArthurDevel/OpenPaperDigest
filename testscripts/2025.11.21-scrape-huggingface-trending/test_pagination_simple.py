#!/usr/bin/env python3
"""
Simple test to verify if the trending page uses pagination or infinite scroll.
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
    Set up Selenium Chrome driver.
    
    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    return driver


def get_paper_cards(driver):
    """
    Get all paper card elements on current page.
    
    Args:
        driver: Selenium WebDriver instance
        
    Returns:
        List: List of paper card elements
    """
    cards = []
    
    # Try different selectors
    selectors = [
        "article",
        "[class*='paper']",
        "[class*='card']",
        "a[href*='/papers/']",
    ]
    
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for elem in elements:
                if elem not in cards:
                    cards.append(elem)
        except:
            continue
    
    return cards


def test_infinite_scroll():
    """
    Test if the page uses infinite scroll.
    """
    driver = setup_driver()

    try:
        print("=" * 80)
        print("Testing Hugging Face Trending Page - Infinite Scroll")
        print("=" * 80)

        print(f"\nLoading: {HUGGINGFACE_TRENDING_URL}")
        driver.get(HUGGINGFACE_TRENDING_URL)
        time.sleep(5)  # Wait for initial load

        # Count initial papers
        initial_cards = get_paper_cards(driver)
        initial_count = len(initial_cards)
        print(f"Initial paper count: {initial_count}")

        # Scroll multiple times
        scrolls = 3
        for scroll_num in range(scrolls):
            print(f"\nScroll {scroll_num + 1}/{scrolls}...")
            
            # Scroll to bottom
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)  # Wait for content to load
            
            # Count again
            current_cards = get_paper_cards(driver)
            current_count = len(current_cards)
            print(f"  Papers after scroll: {current_count} (+{current_count - initial_count})")
            
            if current_count == initial_count:
                print("  No new papers loaded")
                break
            
            initial_count = current_count

        # Final count
        final_cards = get_paper_cards(driver)
        final_count = len(final_cards)
        
        print(f"\n{'=' * 80}")
        print(f"Final paper count: {final_count}")
        
        if final_count > initial_count:
            print("✓ Infinite scroll detected - more papers load as you scroll")
        else:
            print("✗ No infinite scroll detected - all papers loaded initially")

    finally:
        driver.quit()
        print("\nBrowser closed")


def test_url_pagination():
    """
    Test if pagination works by URL parameters.
    """
    driver = setup_driver()

    try:
        print("=" * 80)
        print("Testing Hugging Face Trending Page - URL Pagination")
        print("=" * 80)

        # Try different URL patterns
        urls_to_test = [
            HUGGINGFACE_TRENDING_URL,
            f"{HUGGINGFACE_TRENDING_URL}?page=1",
            f"{HUGGINGFACE_TRENDING_URL}?page=2",
            f"{HUGGINGFACE_TRENDING_URL}?p=1",
            f"{HUGGINGFACE_TRENDING_URL}?p=2",
        ]

        all_card_sets = []

        for url in urls_to_test:
            print(f"\n--- Testing: {url} ---")
            driver.get(url)
            time.sleep(5)

            cards = get_paper_cards(driver)
            card_count = len(cards)
            print(f"Found {card_count} paper cards")
            
            if cards:
                # Extract some identifying info from first card
                first_card_text = cards[0].text[:100] if cards[0].text else "No text"
                print(f"First card preview: {first_card_text}")
            
            all_card_sets.append(set([id(card) for card in cards]))

        # Check for overlap
        print(f"\n{'=' * 80}")
        print("Checking for overlaps:")
        print(f"{'=' * 80}")

        for i in range(len(all_card_sets) - 1):
            overlap = len(all_card_sets[i] & all_card_sets[i + 1])
            print(f"URL {i+1} vs URL {i+2}: {overlap} overlapping cards")

        if all(len(all_card_sets[i] & all_card_sets[i + 1]) == 0 for i in range(len(all_card_sets) - 1)):
            print("\n✓ SUCCESS! URL pagination works - all URLs have unique papers")
        else:
            print("\n✗ WARNING! Some URLs have overlapping papers (might be same page)")

    finally:
        driver.quit()
        print("\nBrowser closed")


### MAIN ENTRYPOINT ###

if __name__ == "__main__":
    print("Choose test:")
    print("1. Test infinite scroll")
    print("2. Test URL pagination")
    print("3. Run both")
    
    choice = input("\nEnter choice (1/2/3): ").strip()
    
    if choice == "1":
        test_infinite_scroll()
    elif choice == "2":
        test_url_pagination()
    elif choice == "3":
        test_infinite_scroll()
        print("\n" + "=" * 80 + "\n")
        test_url_pagination()
    else:
        print("Invalid choice. Running infinite scroll test by default.")
        test_infinite_scroll()

