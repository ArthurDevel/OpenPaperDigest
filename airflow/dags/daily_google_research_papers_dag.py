import sys
import os
import pendulum
import time
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


### CONSTANTS ###
GOOGLE_RESEARCH_BLOG_URL = "https://research.google/blog/"


### HELPER FUNCTIONS ###

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


def scrape_individual_post(driver, post_url: str, index: int) -> Optional[Dict[str, Any]]:
    """
    Visit an individual blog post and extract paper links.

    Args:
        driver: Selenium WebDriver instance
        post_url: URL of the blog post
        index: Index number for display

    Returns:
        Optional[Dict[str, Any]]: Dict containing post data and paper links, or None if error
    """
    try:
        driver.get(post_url)
        time.sleep(2)

        # Extract title
        title = None
        try:
            title_element = driver.find_element(By.CSS_SELECTOR, "h1")
            title = title_element.text.strip()
        except:
            title = driver.title

        # Look for the "Paper" link in quicklinks (the primary paper link)
        paper_url = None
        arxiv_id = None

        try:
            quicklink_items = driver.find_elements(By.CSS_SELECTOR, ".quicklinks__item")
            for item in quicklink_items:
                link = item.find_element(By.TAG_NAME, "a")
                link_text = item.text.strip()

                if link_text.lower() == "paper":
                    href = link.get_attribute('href')
                    paper_url = href

                    # Extract arxiv_id if it's an arxiv link
                    arxiv_id = extract_arxiv_id_from_url(href)
                    break
        except:
            pass

        post_data = {
            "index": index,
            "title": title,
            "url": post_url,
            "paper_url": paper_url,
            "arxiv_id": arxiv_id
        }

        return post_data

    except Exception as e:
        print(f"  Error scraping post {index}: {e}")
        return None


### DATABASE HELPERS ###

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


@dag(
    dag_id="daily_google_research_papers",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule="0 7 * * *",  # 7 AM daily (same as AlphaXiv)
    catchup=False,
    tags=["google-research", "papers"],
    params={
        "papers_to_add": Param(
            type="integer",
            default=5,
            title="Number of Papers to Add",
            description="Number of papers to add to the processing queue. Will scrape blog posts until this many papers with paper URLs are found.",
            minimum=1,
            maximum=200
        )
    },
    doc_md="""
    ### Daily Google Research Papers DAG

    This DAG scrapes papers from Google Research blog and adds them to the processing queue.
    - Scrapes recent blog posts using Selenium
    - Extracts paper URLs (both arXiv and non-arXiv)
    - Adds papers to the processing queue for summarization
    - When run on its daily schedule, it fetches the most recent posts.
    - When run manually, you can customize the number of posts to check and papers to add.
    """,
)
def daily_google_research_papers_dag():

    @task
    def scrape_blog_posts(**context) -> List[Dict[str, Any]]:
        """
        Scrape Google Research blog and extract paper links.
        Stops after finding the requested number of papers with paper URLs.

        Returns:
            List[Dict[str, Any]]: List of blog posts with paper information
        """
        print(f"DEBUG - Full context keys: {list(context.keys())}")
        print(f"DEBUG - params value: {context.get('params')}")
        print(f"DEBUG - dag_run: {context.get('dag_run')}")
        if context.get('dag_run'):
            print(f"DEBUG - dag_run.conf: {context['dag_run'].conf}")

        papers_to_add = int(context["params"]["papers_to_add"])
        print(f"Scraping Google Research blog: {GOOGLE_RESEARCH_BLOG_URL}")
        print(f"  Looking for {papers_to_add} papers with paper URLs")

        driver = setup_driver()

        try:
            driver.get(GOOGLE_RESEARCH_BLOG_URL)
            print("Page loaded, waiting for content to render...")

            # Wait for blog posts to load
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/blog/']"))
                )
                print("Blog posts detected!")
            except Exception as e:
                print(f"Warning: Timeout waiting for blog posts: {e}")

            # Give extra time for JavaScript to fully render
            time.sleep(2)

            # Scrape pages and process posts until we find enough papers
            print("\n--- Scraping blog and processing posts ---\n")
            seen_urls = set()
            result = []
            current_page = 1
            posts_checked = 0

            while len(result) < papers_to_add:
                print(f"\nScraping page {current_page}... ({len(result)}/{papers_to_add} papers found so far)")

                # Find all blog post links on current page
                blog_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/blog/']")

                # Filter for actual blog post URLs on this page
                page_post_urls = []
                for link in blog_links:
                    href = link.get_attribute('href')
                    if (href and
                        href != GOOGLE_RESEARCH_BLOG_URL and
                        href not in seen_urls and
                        '/blog/' in href and
                        '/label/' not in href and
                        '/rss' not in href and
                        href.count('/') > 4):

                        seen_urls.add(href)
                        page_post_urls.append(href)

                print(f"  Found {len(page_post_urls)} new posts on page {current_page}")

                # Process posts from this page
                for post_url in page_post_urls:
                    posts_checked += 1

                    # Stop if we've found enough papers
                    if len(result) >= papers_to_add:
                        print(f"\n  Found {papers_to_add} papers. Stopping.")
                        break

                    print(f"\n  --- Processing post #{posts_checked}: {post_url} ---")
                    post_data = scrape_individual_post(driver, post_url, posts_checked)
                    if post_data and post_data.get('paper_url'):
                        result.append(post_data)
                        print(f"    Title: {post_data['title']}")
                        print(f"    Paper URL: {post_data['paper_url']}")
                        if post_data.get('arxiv_id'):
                            print(f"    ArXiv ID: {post_data['arxiv_id']}")
                        print(f"    Papers found: {len(result)}/{papers_to_add}")
                    else:
                        print(f"    No paper URL found, skipping")
                    time.sleep(1)

                # Stop if we've found enough papers
                if len(result) >= papers_to_add:
                    break

                # Navigate back to blog page to click next
                print(f"  Navigating back to blog page {current_page}...")
                driver.get(f"{GOOGLE_RESEARCH_BLOG_URL}?page={current_page}&")
                time.sleep(2)

                # Try to go to next page
                try:
                    # Wait for pagination to be present
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".pagination__next-button"))
                    )
                    next_button = driver.find_element(By.CSS_SELECTOR, ".pagination__next-button")
                    print(f"  Clicking next button to go to page {current_page + 1}...")
                    driver.execute_script("arguments[0].click();", next_button)
                    time.sleep(3)
                    current_page += 1
                except Exception as e:
                    print(f"\n  No more pages available: {e}")
                    break

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
            print("No papers found with paper URLs")
            return

        print(f"\n=== Google Research Blog Papers - {len(papers_data)} Found ===\n")

        for rank, paper in enumerate(papers_data, 1):
            title = paper.get('title', 'Unknown Title')
            paper_url = paper.get('paper_url', 'N/A')
            arxiv_id = paper.get('arxiv_id')

            print(f"#{rank} - {title}")
            print(f"     Paper URL: {paper_url}")
            if arxiv_id:
                print(f"     ArXiv ID: {arxiv_id}")
                print(f"     ArXiv URL: https://arxiv.org/abs/{arxiv_id}")
            else:
                print(f"     Non-arXiv paper (will use content hash)")
            print("")

        print(f"\n=== End of Google Research Blog Papers ===\n")

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

                    # Create popularity signal for Google Research
                    google_signal = ExternalPopularitySignal(
                        source="GoogleResearch",
                        values={
                            "blog_post_url": paper.get('url')
                        },
                        fetch_info={
                            "blog_post_title": title
                        }
                    )

                    # Add paper to processing queue
                    if arxiv_id:
                        # ArXiv paper - use existing flow
                        create_paper(
                            db=session,
                            arxiv_id=arxiv_id,
                            title=title,
                            external_popularity_signals=[google_signal],
                            initiated_by_user_id=None
                        )
                        print(f"Added arXiv paper {arxiv_id} to queue (rank #{rank})")
                    else:
                        # Non-arXiv paper - use PDF URL
                        create_paper(
                            db=session,
                            pdf_url=paper_url,
                            title=title,
                            external_popularity_signals=[google_signal],
                            initiated_by_user_id=None
                        )
                        print(f"Added non-arXiv paper to queue (rank #{rank})")

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
    papers = scrape_blog_posts()
    print_papers_info(papers)
    add_papers_to_queue(papers)


daily_google_research_papers_dag()
