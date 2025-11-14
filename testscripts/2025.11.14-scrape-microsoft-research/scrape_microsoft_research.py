#!/usr/bin/env python3
"""
Test script to scrape papers from Microsoft Research publications page.
This script uses Selenium to handle JavaScript-rendered content and pagination.

The page structure:
- Main listing: https://www.microsoft.com/en-us/research/publications
- Each publication card has a link to individual publication page
- Individual page has a "Publication" button that links to the actual paper PDF
- We need to hash the PDF for uniqueness (non-arXiv papers)
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import json
import time
import hashlib
import requests
from typing import List, Dict, Any, Optional


# ============================================================================
# CONSTANTS
# ============================================================================

MICROSOFT_RESEARCH_URL = "https://www.microsoft.com/en-us/research/publications"
MAX_PUBLICATIONS_TO_PROCESS = 10


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def setup_driver():
    """
    Set up Selenium Chrome driver with headless options.

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


def compute_pdf_hash(pdf_url: str) -> Optional[str]:
    """
    Download PDF and compute its hash for uniqueness.

    Args:
        pdf_url: URL of the PDF to download

    Returns:
        Optional[str]: SHA256 hash of the PDF content, or None if error
    """
    try:
        print(f"    Downloading PDF to compute hash...")

        # Add headers to avoid being blocked by Microsoft
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/pdf,*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.microsoft.com/',
        }

        response = requests.get(pdf_url, timeout=30, headers=headers, allow_redirects=True)
        response.raise_for_status()

        # Verify we actually got a PDF
        if not response.content.startswith(b'%PDF'):
            print(f"    WARNING: Downloaded content is not a PDF (Content-Type: {response.headers.get('Content-Type')})")
            return None

        pdf_hash = hashlib.sha256(response.content).hexdigest()
        print(f"    PDF hash: {pdf_hash[:16]}... (size: {len(response.content)} bytes)")
        return pdf_hash

    except Exception as e:
        print(f"    Error computing PDF hash: {e}")
        return None


def extract_arxiv_id_from_url(url: str) -> Optional[str]:
    """
    Extract arXiv ID from URL.

    Args:
        url: URL that may contain an arXiv ID

    Returns:
        Optional[str]: Extracted arXiv ID or None if not found
    """
    import re
    arxiv_match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+)', url, re.I)
    if arxiv_match:
        return arxiv_match.group(1)
    return None


def scrape_individual_publication(driver, pub_url: str, index: int) -> Optional[Dict[str, Any]]:
    """
    Visit an individual publication page and extract paper link from Related Resources sidebar.

    Args:
        driver: Selenium WebDriver instance
        pub_url: URL of the publication page
        index: Index number for display

    Returns:
        Optional[Dict[str, Any]]: Dict containing publication data, or None if error
    """
    try:
        driver.get(pub_url)
        time.sleep(2)

        # Extract title
        title = None
        try:
            title_element = driver.find_element(By.CSS_SELECTOR, "h1")
            title = title_element.text.strip()
        except:
            title = driver.title

        # Extract publication date
        pub_date = None
        try:
            date_element = driver.find_element(By.CSS_SELECTOR, ".date, .publication-date, time")
            pub_date = date_element.text.strip()
        except:
            pass

        # Look for paper link in the "Related resources" sidebar ONLY
        paper_url = None
        arxiv_id = None
        pdf_hash = None

        try:
            # Find the "Related resources" aside section
            related_resources = driver.find_element(By.CSS_SELECTOR, 'aside[aria-label="Related resources"]')

            # Find all buttons in this section
            buttons = related_resources.find_elements(By.CSS_SELECTOR, "a.btn.btn-primary.btn-lg")

            for button in buttons:
                href = button.get_attribute('href')
                if not href:
                    continue

                # Check if it's an arXiv link
                arxiv_id_found = extract_arxiv_id_from_url(href)
                if arxiv_id_found:
                    paper_url = href
                    arxiv_id = arxiv_id_found
                    print(f"    Found arXiv link: {arxiv_id}")
                    break

                # Check if it's a PDF link
                if '.pdf' in href.lower():
                    paper_url = href
                    print(f"    Found PDF link")
                    pdf_hash = compute_pdf_hash(paper_url)
                    break

        except Exception as e:
            print(f"    No Related resources section found or error: {e}")

        pub_data = {
            "index": index,
            "title": title,
            "url": pub_url,
            "paper_url": paper_url,
            "arxiv_id": arxiv_id,
            "pdf_hash": pdf_hash,
            "publication_date": pub_date
        }

        # Print summary
        print(f"  Title: {title}")
        if paper_url:
            print(f"  Paper URL: {paper_url}")
            if arxiv_id:
                print(f"  ArXiv ID: {arxiv_id}")
            elif pdf_hash:
                print(f"  PDF Hash: {pdf_hash[:16]}...")
        else:
            print(f"  Paper URL: None")

        if pub_date:
            print(f"  Date: {pub_date}")

        return pub_data

    except Exception as e:
        print(f"  Error scraping publication {index}: {e}")
        return None


def scrape_publications_page(url: str = MICROSOFT_RESEARCH_URL) -> Dict[str, Any]:
    """
    Scrape Microsoft Research publications page and extract paper information.

    Args:
        url: URL of the publications page

    Returns:
        Dict containing list of publications with paper information
    """
    print(f"Fetching publications page: {url}")
    print("Initializing Selenium Chrome driver...")

    driver = setup_driver()

    try:
        driver.get(url)
        print("Page loaded, waiting for content to render...")

        # Wait for publication cards to load
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "article, .publication-item, .m-publication"))
            )
            print("Publications detected!")
        except Exception as e:
            print(f"Warning: Timeout waiting for publications: {e}")

        # Give extra time for JavaScript to fully render
        time.sleep(3)

        # Find all publication links
        print("\n--- Extracting publication URLs ---\n")

        # Try different selectors for publication cards/links
        publication_links = []

        # Try to find publication cards
        try:
            # Look for article elements or publication cards
            cards = driver.find_elements(By.CSS_SELECTOR, "article.m-publication, .publication-item, article")

            for card in cards:
                try:
                    # Find the link within each card
                    link = card.find_element(By.CSS_SELECTOR, "a[href*='/publication/']")
                    href = link.get_attribute('href')
                    if href and href not in publication_links:
                        publication_links.append(href)
                except:
                    continue
        except:
            pass

        # Fallback: find all links containing '/publication/'
        if not publication_links:
            all_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/publication/']")
            seen_urls = set()
            for link in all_links:
                href = link.get_attribute('href')
                if href and href not in seen_urls:
                    seen_urls.add(href)
                    publication_links.append(href)

        print(f"Found {len(publication_links)} publication URLs")

        # Process limited number of publications
        result = {
            "url": url,
            "publications": []
        }

        pubs_to_process = publication_links[:MAX_PUBLICATIONS_TO_PROCESS]
        print(f"\nProcessing {len(pubs_to_process)} publications (out of {len(publication_links)} found)...\n")

        for idx, pub_url in enumerate(pubs_to_process, 1):
            print(f"\n--- Processing publication #{idx}/{len(pubs_to_process)}: {pub_url} ---")
            pub_data = scrape_individual_publication(driver, pub_url, idx)
            if pub_data:
                result["publications"].append(pub_data)
            time.sleep(2)  # Be nice to the server

        # Check if there's pagination
        print("\n--- Checking for pagination ---")
        try:
            next_button = driver.find_element(By.CSS_SELECTOR, ".pagination a.next, button.next, a[aria-label*='next']")
            print(f"Pagination found! Next button available.")
            print(f"Next button text: {next_button.text}")
        except:
            print("No obvious pagination found")

        return result

    finally:
        driver.quit()
        print("\nBrowser closed")


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

def main():
    """Main function to run the scraper test."""
    import os

    print("=" * 80)
    print("Microsoft Research Publications Scraper Test (Selenium)")
    print("=" * 80)
    print()

    # Scrape first page
    result = scrape_publications_page()

    # Save results to file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, "microsoft_research_scrape_results.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 80}")
    print(f"Results saved to: {output_file}")
    print(f"Total publications processed: {len(result.get('publications', []))}")

    # Print summary
    all_pubs = result.get('publications', [])
    pubs_with_paper_url = [p for p in all_pubs if p.get('paper_url')]
    pubs_with_arxiv = [p for p in all_pubs if p.get('arxiv_id')]
    pubs_with_pdf = [p for p in all_pubs if p.get('pdf_hash')]
    pubs_without_paper = [p for p in all_pubs if not p.get('paper_url')]

    print(f"Publications with paper links: {len(pubs_with_paper_url)}")
    print(f"  - ArXiv papers: {len(pubs_with_arxiv)}")
    print(f"  - PDF papers (with hash): {len(pubs_with_pdf)}")
    print(f"Publications without paper links: {len(pubs_without_paper)}")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
