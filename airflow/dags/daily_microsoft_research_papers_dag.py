import sys
import os
import pendulum
import time
import hashlib
import requests
from airflow.decorators import dag, task
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
from airflow.models import Param

# Add project root to Python path to find shared modules
sys.path.insert(0, '/opt/airflow')

from sqlalchemy.orm import Session
from shared.db import SessionLocal
from papers.models import ExternalPopularitySignal
from papers.client import create_paper

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import re


# ============================================================================
# CONSTANTS
# ============================================================================

MICROSOFT_RESEARCH_URL = "https://www.microsoft.com/en-us/research/publications"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def setup_driver():
    """
    Set up Selenium Chrome driver with headless options.

    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance
    """
    from selenium.webdriver.chrome.service import Service

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")

    # Point to system chromium binary
    chrome_options.binary_location = "/usr/bin/chromium"

    # Point to system chromedriver
    service = Service(executable_path="/usr/bin/chromedriver")

    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


def extract_arxiv_id_from_url(url: str) -> Optional[str]:
    """
    Extract arXiv ID from URL.

    Args:
        url: URL that may contain an arXiv ID

    Returns:
        Optional[str]: Extracted arXiv ID or None if not found
    """
    arxiv_match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+)', url, re.I)
    if arxiv_match:
        return arxiv_match.group(1)
    return None


def compute_pdf_hash(pdf_url: str) -> str:
    """
    Download PDF and compute its hash for uniqueness.
    Raises an error if the PDF cannot be downloaded or is invalid.

    Args:
        pdf_url: URL of the PDF to download

    Returns:
        str: SHA256 hash of the PDF content

    Raises:
        ValueError: If the downloaded content is not a valid PDF
        Exception: If download fails
    """
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
        raise ValueError(f"Downloaded content is not a valid PDF (Content-Type: {response.headers.get('Content-Type')})")

    pdf_hash = hashlib.sha256(response.content).hexdigest()
    return pdf_hash


def scrape_individual_publication(driver, pub_url: str, index: int) -> Optional[Dict[str, Any]]:
    """
    Visit an individual publication page and extract paper link from Related Resources sidebar.

    Args:
        driver: Selenium WebDriver instance
        pub_url: URL of the publication page
        index: Index number for display

    Returns:
        Optional[Dict[str, Any]]: Dict containing publication data, or None if error or no paper link
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
                    print(f"    Found PDF link, computing hash...")
                    # Compute hash and verify it's a valid PDF
                    pdf_hash = compute_pdf_hash(paper_url)
                    print(f"    PDF hash: {pdf_hash[:16]}...")
                    break

        except Exception as e:
            print(f"    No Related resources section found or error: {e}")

        # Skip publications without paper links
        if not paper_url:
            print(f"    No paper link found, skipping")
            return None

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
        print(f"  Paper URL: {paper_url}")
        if arxiv_id:
            print(f"  ArXiv ID: {arxiv_id}")
        elif pdf_hash:
            print(f"  PDF Hash: {pdf_hash[:16]}...")

        return pub_data

    except Exception as e:
        print(f"  Error scraping publication {index}: {e}")
        raise


# ============================================================================
# DATABASE HELPERS
# ============================================================================

@contextmanager
def database_session():
    """
    Create a database session with automatic commit/rollback handling.

    Yields:
        Session: SQLAlchemy session for database operations

    Raises:
        Exception: Any database error that occurs during the transaction
    """
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ============================================================================
# DAG DEFINITION
# ============================================================================

@dag(
    dag_id="daily_microsoft_research_papers",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule="0 7 * * *",  # 7 AM daily (same as other research paper DAGs)
    catchup=False,
    tags=["microsoft-research", "papers"],
    params={
        "papers_to_add": Param(
            type="integer",
            default=10,
            title="Number of Papers to Add",
            description="Number of papers to add to the processing queue. Will scrape publications until this many papers with accessible PDFs/arXiv links are found.",
            minimum=1,
            maximum=200
        )
    },
    doc_md="""
    ### Daily Microsoft Research Papers DAG

    This DAG scrapes papers from Microsoft Research publications page and adds them to the processing queue.
    - Scrapes recent publications using Selenium
    - Extracts paper URLs (both arXiv and Microsoft-hosted PDFs)
    - Computes PDF hashes for uniqueness verification
    - Adds papers to the processing queue for summarization
    - When run on its daily schedule, it fetches the most recent publications.
    - When run manually, you can customize the number of papers to add.

    Note: Only publications with accessible paper links (arXiv or PDF) are added.
    """,
)
def daily_microsoft_research_papers_dag():

    @task
    def scrape_publications(**context) -> List[Dict[str, Any]]:
        """
        Scrape Microsoft Research publications and extract paper links.
        Stops after finding the requested number of papers with accessible links.

        Returns:
            List[Dict[str, Any]]: List of publications with paper information
        """
        papers_to_add = int(context["params"]["papers_to_add"])
        print(f"Scraping Microsoft Research: {MICROSOFT_RESEARCH_URL}")
        print(f"  Looking for {papers_to_add} papers with accessible links")

        driver = setup_driver()

        try:
            driver.get(MICROSOFT_RESEARCH_URL)
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

            # Process publications page by page until we have enough papers
            print(f"\n--- Processing publications to find {papers_to_add} papers ---\n")
            result = []
            processed_count = 0
            current_page = 1
            max_pages = 10  # Safety limit to avoid infinite loops

            while len(result) < papers_to_add and current_page <= max_pages:
                # Navigate to the current page
                if current_page == 1:
                    page_url = MICROSOFT_RESEARCH_URL
                else:
                    page_url = f"{MICROSOFT_RESEARCH_URL}?pg={current_page}"

                print(f"\n--- Page {current_page}: {page_url} ---")
                driver.get(page_url)
                time.sleep(3)

                # Extract publication URLs from current page
                publication_links = []
                try:
                    cards = driver.find_elements(By.CSS_SELECTOR, "article.m-publication, .publication-item, article")

                    for card in cards:
                        try:
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

                print(f"  Found {len(publication_links)} publication URLs on page {current_page}")

                # Process publications from this page
                for pub_url in publication_links:
                    # Stop if we've found enough papers
                    if len(result) >= papers_to_add:
                        print(f"\n  Found {papers_to_add} papers. Stopping.")
                        break

                    processed_count += 1
                    print(f"\n  --- Processing publication #{processed_count}: {pub_url} ---")

                    pub_data = scrape_individual_publication(driver, pub_url, processed_count)

                    if pub_data:
                        result.append(pub_data)
                        print(f"    Papers found: {len(result)}/{papers_to_add}")

                    time.sleep(2)  # Be nice to the server

                # Stop if we've found enough papers
                if len(result) >= papers_to_add:
                    break

                # Move to next page
                current_page += 1

            print(f"\n--- Scraping complete: Found {len(result)} papers ---")
            return result

        finally:
            driver.quit()
            print("\nBrowser closed")

    @task
    def print_papers_info(papers_data: List[Dict[str, Any]]) -> None:
        """
        Print paper information to console.

        Args:
            papers_data: List of paper data from scraper
        """
        if not papers_data:
            print("No papers found with accessible links")
            return

        print(f"\n=== Microsoft Research Publications - {len(papers_data)} Found ===\n")

        for rank, paper in enumerate(papers_data, 1):
            title = paper.get('title', 'Unknown Title')
            paper_url = paper.get('paper_url', 'N/A')
            arxiv_id = paper.get('arxiv_id')
            pdf_hash = paper.get('pdf_hash')

            print(f"#{rank} - {title}")
            print(f"     Paper URL: {paper_url}")
            if arxiv_id:
                print(f"     ArXiv ID: {arxiv_id}")
                print(f"     ArXiv URL: https://arxiv.org/abs/{arxiv_id}")
            elif pdf_hash:
                print(f"     PDF Hash: {pdf_hash}")
            print("")

        print(f"\n=== End of Microsoft Research Publications ===\n")

    @task
    def add_papers_to_queue(papers_data: List[Dict[str, Any]]) -> None:
        """
        Add papers to processing queue.

        Args:
            papers_data: List of paper data from scraper
        """
        if not papers_data:
            print("No papers to add to queue")
            return

        with database_session() as session:
            added_count = 0
            skipped_count = 0

            for rank, paper in enumerate(papers_data, 1):
                try:
                    arxiv_id = paper.get('arxiv_id')
                    paper_url = paper.get('paper_url')
                    title = paper.get('title')

                    if not paper_url:
                        print(f"Skipping paper at rank {rank} - no paper URL")
                        skipped_count += 1
                        continue

                    # Create popularity signal for Microsoft Research
                    microsoft_signal = ExternalPopularitySignal(
                        source="MicrosoftResearch",
                        values={},
                        fetch_info={
                            "publication_url": paper.get('url'),
                        }
                    )

                    # Add paper to processing queue
                    if arxiv_id:
                        # ArXiv paper - use existing flow
                        create_paper(
                            db=session,
                            arxiv_id=arxiv_id,
                            title=title,
                            external_popularity_signals=[microsoft_signal],
                            initiated_by_user_id=None
                        )
                        print(f"Added arXiv paper {arxiv_id} to queue (rank #{rank})")
                    else:
                        # Non-arXiv paper - use PDF URL
                        create_paper(
                            db=session,
                            pdf_url=paper_url,
                            title=title,
                            external_popularity_signals=[microsoft_signal],
                            initiated_by_user_id=None
                        )
                        print(f"Added Microsoft-hosted paper to queue (rank #{rank})")

                    added_count += 1
                    print(f"  Title: {title[:80]}...")

                except ValueError as e:
                    # Paper already exists - this is expected and not an error
                    if "already exists" in str(e):
                        print(f"Skipping paper at rank {rank} - already exists in database")
                        skipped_count += 1
                    else:
                        print(f"Error with paper at rank {rank}: {e}")
                        skipped_count += 1
                    continue

                except Exception as e:
                    print(f"Error adding paper at rank {rank}: {e}")
                    print(f"  Skipping and continuing with next paper")
                    skipped_count += 1
                    continue

            print(f"\n=== Processing Queue Summary ===")
            print(f"Added: {added_count} papers")
            print(f"Skipped: {skipped_count} papers")
            print(f"===========================\n")

    # Define task dependencies
    papers = scrape_publications()
    print_papers_info(papers)
    add_papers_to_queue(papers)


daily_microsoft_research_papers_dag()
