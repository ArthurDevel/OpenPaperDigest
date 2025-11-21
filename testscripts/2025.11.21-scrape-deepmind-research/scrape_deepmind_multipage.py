#!/usr/bin/env python3
"""
Comprehensive test script to scrape papers from DeepMind research publications
with multi-page pagination support.

This script uses Selenium to handle JavaScript-rendered content and supports
pagination via URL pattern: /page/1/, /page/2/, etc.

The page structure:
- Main listing: https://deepmind.google/research/publications/
- Paginated URLs: https://deepmind.google/research/publications/page/2/
- Each publication card has a link to individual publication page
- Individual page should have links to paper PDFs or arXiv
- We hash PDFs for uniqueness (non-arXiv papers)
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

DEEPMIND_RESEARCH_BASE_URL = "https://deepmind.google/research/publications"
MAX_PAGES_TO_SCRAPE = 3  # Number of pages to scrape
MAX_PUBLICATIONS_PER_PAGE = 30  # DeepMind has ~30 publications per page


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
                    # Skip PDF hash computation to speed up testing
                    # pdf_hash = compute_pdf_hash(paper_url)
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


def get_publication_links_from_page(driver, page_url: str) -> List[str]:
    """
    Extract all publication links from a listings page.

    Args:
        driver: Selenium WebDriver instance
        page_url: URL of the listings page

    Returns:
        List[str]: List of publication URLs
    """
    driver.get(page_url)
    time.sleep(3)

    publication_links = []
    
    try:
        # Look for links that contain '/publications/' in the href
        all_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/publications/']")
        seen_urls = set()
        
        for link in all_links:
            href = link.get_attribute('href')
            # Make sure it's a specific publication page, not the main listing
            if href and href not in seen_urls and '/publications/' in href:
                # Check if it looks like a publication detail page
                path_after_publications = href.split('/publications/')[-1]
                # Exclude the base URL and page URLs
                if (path_after_publications and 
                    path_after_publications.strip('/') and 
                    not path_after_publications.startswith('page/')):
                    seen_urls.add(href)
                    publication_links.append(href)
    except Exception as e:
        print(f"Error finding publication links: {e}")

    return publication_links


def scrape_publications_multi_page(max_pages: int = MAX_PAGES_TO_SCRAPE) -> Dict[str, Any]:
    """
    Scrape DeepMind research publications across multiple pages.

    Args:
        max_pages: Maximum number of pages to scrape

    Returns:
        Dict containing list of publications with paper information
    """
    print(f"Initializing Selenium Chrome driver...")
    driver = setup_driver()

    result = {
        "base_url": DEEPMIND_RESEARCH_BASE_URL,
        "pages_scraped": 0,
        "publications": []
    }

    try:
        global_index = 0

        for page_num in range(1, max_pages + 1):
            # Construct page URL
            if page_num == 1:
                page_url = f"{DEEPMIND_RESEARCH_BASE_URL}/"
            else:
                page_url = f"{DEEPMIND_RESEARCH_BASE_URL}/page/{page_num}/"

            print(f"\n{'=' * 80}")
            print(f"SCRAPING PAGE {page_num}: {page_url}")
            print(f"{'=' * 80}\n")

            # Get all publication links from this page
            pub_links = get_publication_links_from_page(driver, page_url)
            print(f"Found {len(pub_links)} publications on page {page_num}\n")

            if not pub_links:
                print(f"No publications found on page {page_num}, stopping pagination")
                break

            # Scrape each publication
            for pub_url in pub_links:
                global_index += 1
                print(f"--- Processing publication #{global_index}: {pub_url} ---")
                pub_data = scrape_individual_publication(driver, pub_url, global_index)
                if pub_data:
                    pub_data["page_number"] = page_num
                    result["publications"].append(pub_data)
                time.sleep(1)  # Be nice to the server

            result["pages_scraped"] = page_num

        return result

    finally:
        driver.quit()
        print("\nBrowser closed")


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

def main():
    """Main function to run the multi-page scraper test."""
    import os

    print("=" * 80)
    print("DeepMind Research Publications Multi-Page Scraper Test")
    print("=" * 80)
    print()

    # Scrape multiple pages
    result = scrape_publications_multi_page(max_pages=MAX_PAGES_TO_SCRAPE)

    # Save results to file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, "deepmind_research_multipage_results.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 80}")
    print(f"Results saved to: {output_file}")
    print(f"Pages scraped: {result['pages_scraped']}")
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
    
    # Show breakdown by page
    print(f"\nBreakdown by page:")
    for page_num in range(1, result['pages_scraped'] + 1):
        page_pubs = [p for p in all_pubs if p.get('page_number') == page_num]
        print(f"  Page {page_num}: {len(page_pubs)} publications")
    
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
