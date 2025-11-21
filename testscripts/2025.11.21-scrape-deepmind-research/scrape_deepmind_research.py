#!/usr/bin/env python3
"""
Test script to scrape papers from DeepMind research publications page.
This script uses Selenium to handle JavaScript-rendered content and pagination.

The page structure:
- Main listing: https://deepmind.google/research/publications/
- Each publication card has a link to individual publication page
- Individual page should have links to paper PDFs or arXiv
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

DEEPMIND_RESEARCH_URL = "https://deepmind.google/research/publications/"
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

        # Add headers to avoid being blocked
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/pdf,*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://deepmind.google/',
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
    Visit an individual publication page and extract paper link.

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

        # Look for paper links
        paper_url = None
        arxiv_id = None
        pdf_hash = None

        try:
            # Find all links on the page
            all_links = driver.find_elements(By.TAG_NAME, "a")

            for link in all_links:
                href = link.get_attribute('href')
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
            print(f"    Error finding paper links: {e}")

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


def scrape_publications_page(url: str = DEEPMIND_RESEARCH_URL) -> Dict[str, Any]:
    """
    Scrape DeepMind research publications page and extract paper information.

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
                EC.presence_of_element_located((By.CSS_SELECTOR, "article, .publication-item, li a[href*='/publications/']"))
            )
            print("Publications detected!")
        except Exception as e:
            print(f"Warning: Timeout waiting for publications: {e}")

        # Give extra time for JavaScript to fully render
        time.sleep(3)

        # Find all publication links
        print("\n--- Extracting publication URLs ---\n")

        publication_links = []

        # Try to find publication links
        try:
            # Look for links that contain '/publications/' in the href
            all_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/publications/']")
            seen_urls = set()
            
            for link in all_links:
                href = link.get_attribute('href')
                # Make sure it's a specific publication page, not the main listing
                if href and href not in seen_urls and href != url and '/publications/' in href:
                    # Check if it looks like a publication detail page (has something after /publications/)
                    path_after_publications = href.split('/publications/')[-1]
                    if path_after_publications and path_after_publications.strip('/'):
                        seen_urls.add(href)
                        publication_links.append(href)
        except Exception as e:
            print(f"Error finding publication links: {e}")

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

        # Check if there's pagination or load more button
        print("\n--- Checking for pagination/load more ---")
        try:
            load_more = driver.find_element(By.CSS_SELECTOR, "button[aria-label*='load'], button[aria-label*='more'], .load-more")
            print(f"Load more button found!")
            print(f"Button text: {load_more.text}")
        except:
            print("No obvious pagination or load more button found")

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
    print("DeepMind Research Publications Scraper Test (Selenium)")
    print("=" * 80)
    print()

    # Scrape first page
    result = scrape_publications_page()

    # Save results to file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, "deepmind_research_scrape_results.json")
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
