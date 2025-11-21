#!/usr/bin/env python3
"""
Test script to scrape papers from NVIDIA Research publications page.
This script uses Selenium to handle JavaScript-rendered content and pagination.

The page structure:
- Main listing: https://research.nvidia.com/publications
- Each publication has a title link that goes to individual publication page
- Individual page may have links to PDFs or arXiv
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

NVIDIA_RESEARCH_URL = "https://research.nvidia.com/publications"
MAX_PUBLICATIONS_TO_PROCESS = 10
MAX_PAGES_TO_PROCESS = 3  # Test with first 3 pages


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

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/pdf,*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://research.nvidia.com/',
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

        # Extract publication date/year
        pub_date = None
        try:
            # Try to find date/year information
            date_elements = driver.find_elements(By.CSS_SELECTOR, ".date, .publication-date, time, [class*='year']")
            for elem in date_elements:
                text = elem.text.strip()
                if text:
                    pub_date = text
                    break
        except:
            pass

        # Look for paper links (PDF or arXiv)
        paper_url = None
        arxiv_id = None
        pdf_hash = None

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
            if '.pdf' in href.lower() or 'pdf' in link.text.lower():
                paper_url = href
                print(f"    Found PDF link: {href}")
                pdf_hash = compute_pdf_hash(paper_url)
                break

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


def get_publication_urls_from_page(driver):
    """
    Extract publication URLs from the current page.

    Args:
        driver: Selenium WebDriver instance

    Returns:
        List[str]: List of publication URLs found on current page
    """
    publication_links = []
    try:
        pub_list = driver.find_element(By.CSS_SELECTOR, ".nv-publications-list")
        all_links = pub_list.find_elements(By.CSS_SELECTOR, "a")
        seen_urls = set()
        
        for link in all_links:
            href = link.get_attribute('href')
            if href and href not in seen_urls:
                # Look for publication detail pages (not pagination, filter links, or hash links)
                if '/publication/' in href and '?page=' not in href and '?f%5B' not in href and '#' not in href:
                    seen_urls.add(href)
                    publication_links.append(href)
    except Exception as e:
        print(f"Error finding publication links: {e}")
    
    return publication_links


def scrape_publications_page(url: str = NVIDIA_RESEARCH_URL) -> Dict[str, Any]:
    """
    Scrape NVIDIA Research publications page and extract paper information.
    Handles pagination to scrape multiple pages.

    Args:
        url: URL of the publications page

    Returns:
        Dict containing list of publications with paper information
    """
    print(f"Fetching publications page: {url}")
    print("Initializing Selenium Chrome driver...")

    driver = setup_driver()

    try:
        # Collect all publication URLs from multiple pages
        all_publication_links = []
        page_num = 0

        while page_num < MAX_PAGES_TO_PROCESS:
            # Build URL for current page
            # Base URL (no param) = page 1 = ?page=0
            # So: page_num=0 -> ?page=0, page_num=1 -> ?page=1, page_num=2 -> ?page=2
            if page_num == 0:
                page_url = url  # Base URL is same as ?page=0
            else:
                page_url = f"{url}?page={page_num}"  # page=1 is second page, page=2 is third page, etc.

            print(f"\n{'=' * 80}")
            print(f"Scraping page {page_num + 1} (URL: {page_url})")
            print(f"{'=' * 80}")

            driver.get(page_url)
            print("Page loaded, waiting for content to render...")

            # Wait for publication items to load
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".nv-publications-list"))
                )
                print("Publications detected!")
            except Exception as e:
                print(f"Warning: Timeout waiting for publications: {e}")

            # Give extra time for JavaScript to fully render
            time.sleep(5)

            # Extract publication URLs from this page
            page_links = get_publication_urls_from_page(driver)
            print(f"Found {len(page_links)} publications on this page")

            if not page_links:
                print("No publications found on this page, stopping pagination")
                break

            all_publication_links.extend(page_links)
            print(f"Total publications collected so far: {len(all_publication_links)}")

            page_num += 1

        print(f"\n{'=' * 80}")
        print(f"Finished collecting URLs. Total: {len(all_publication_links)} publications")
        print(f"{'=' * 80}")

        # Process limited number of publications
        result = {
            "url": url,
            "publications": []
        }

        pubs_to_process = all_publication_links[:MAX_PUBLICATIONS_TO_PROCESS]
        print(f"\nProcessing {len(pubs_to_process)} publications (out of {len(all_publication_links)} found)...\n")

        for idx, pub_url in enumerate(pubs_to_process, 1):
            print(f"\n--- Processing publication #{idx}/{len(pubs_to_process)}: {pub_url} ---")
            pub_data = scrape_individual_publication(driver, pub_url, idx)
            if pub_data:
                result["publications"].append(pub_data)
            time.sleep(2)  # Be nice to the server

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
    print("NVIDIA Research Publications Scraper Test (Selenium)")
    print("=" * 80)
    print()

    # Scrape first page
    result = scrape_publications_page()

    # Save results to file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, "nvidia_research_scrape_results.json")
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

