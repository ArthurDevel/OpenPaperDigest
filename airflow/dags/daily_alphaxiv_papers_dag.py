import sys
import os
import pendulum
import requests
import re
import json
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
from selenium.webdriver.chrome.service import Service


### CONSTANTS ###
ALPHAXIV_BASE_URL = "https://www.alphaxiv.org"


### HELPER FUNCTIONS ###

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

    # Point to system chromium binary
    chrome_options.binary_location = "/usr/bin/chromium"

    # Point to system chromedriver
    service = Service(executable_path="/usr/bin/chromedriver")

    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


def fetch_paper_page_signals(arxiv_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch popularity signals from individual AlphaXiv paper page.

    Extracts data from the JSON-LD script tag on the paper detail page,
    which contains view counts, like counts, and comment counts.

    Args:
        arxiv_id: The arXiv ID (universal_paper_id) of the paper

    Returns:
        Dict with 'views', 'likes', 'comments' or None if fetch fails
    """
    paper_url = f"{ALPHAXIV_BASE_URL}/abs/{arxiv_id}"

    try:
        response = requests.get(paper_url, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"  Warning: Failed to fetch paper page for {arxiv_id}: {e}")
        return None

    # Extract JSON-LD data from the page
    match = re.search(
        r'<script data-alphaxiv-id="json-ld-paper-detail-view" type="application/ld\+json">(.+?)</script>',
        response.text
    )

    if not match:
        print(f"  Warning: Could not find JSON-LD data for {arxiv_id}")
        return None

    try:
        json_ld = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        print(f"  Warning: Failed to parse JSON-LD for {arxiv_id}: {e}")
        return None

    # Extract interaction statistics
    interaction_stats = json_ld.get('interactionStatistic', [])
    views = 0
    likes = 0

    for stat in interaction_stats:
        interaction_type = stat.get('interactionType', {}).get('@type', '')
        count = stat.get('userInteractionCount', 0)

        if interaction_type == 'ViewAction':
            views = count
        elif interaction_type == 'LikeAction':
            likes = count

    comments = json_ld.get('commentCount', 0)

    return {
        'views': views,
        'likes': likes,
        'comments': comments
    }


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
    dag_id="daily_alphaxiv_papers",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule="0 7 * * *",  # 7 AM daily (1 hour after HuggingFace)
    catchup=False,
    tags=["alphaxiv", "papers"],
    params={
        "time_interval": Param(
            type="string",
            default="3 Days",
            enum=["3 Days", "7 Days", "30 Days", "90 Days"],
            title="Time Interval",
            description="How far back in time to fetch hot papers from AlphaXiv."
        ),
        "papers_to_add": Param(
            type="integer",
            default=10,
            title="Number of Papers to Add",
            description="The number of top papers to scrape and add to the processing queue.",
            minimum=1,
            maximum=50
        )
    },
    doc_md="""
    ### Daily AlphaXiv Papers DAG

    This DAG scrapes hot papers from AlphaXiv homepage and adds the top N papers to the processing queue.
    - Scrapes papers from AlphaXiv homepage using Selenium (API is no longer available)
    - Extracts popularity signals (views, likes, comments) from individual paper pages
    - Adds top papers to the processing queue for summarization
    - When run on its daily schedule, it fetches papers from the homepage.
    - When run manually, you can customize the number of papers to add.
    """,
)
def daily_alphaxiv_papers_dag():

    @task
    def fetch_hot_papers(time_interval: str, papers_to_add: int) -> List[Dict[str, Any]]:
        """
        Scrape hot papers from AlphaXiv homepage using Selenium.

        The API endpoint is no longer available (404), so we scrape the homepage
        directly to extract paper IDs from the feed. Uses URL parameters to filter.

        Args:
            time_interval: Time window for fetching hot papers (e.g., "3 Days", "7 Days")
            papers_to_add: Number of papers to scrape from the homepage

        Returns:
            List[Dict[str, Any]]: List of paper data with ArXiv IDs

        Raises:
            Exception: If scraping fails
        """
        papers_to_add = int(papers_to_add)
        
        # Format interval for URL (e.g., "3 Days" -> "3+Days")
        interval_param = time_interval.replace(" ", "+")
        url = f"{ALPHAXIV_BASE_URL}/?sort=Hot&interval={interval_param}"
        
        print(f"Scraping hot papers from AlphaXiv homepage")
        print(f"  URL: {url}")
        print(f"  Time interval: {time_interval}")
        print(f"  Papers to fetch: {papers_to_add}")

        driver = setup_driver()

        try:
            driver.get(url)
            print("Page loaded, waiting for content to render...")

            # Wait for body to load
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            print("Body element found!")

            # Give it time for JavaScript rendering
            time.sleep(10)

            print("Looking for paper links...")

            # Find all paper links on homepage
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/abs/']")

            print(f"Found {len(links)} potential paper links")

            # Extract unique paper IDs
            papers = []
            seen_ids = set()

            for link in links:
                if len(papers) >= papers_to_add:
                    break

                href = link.get_attribute('href')
                if href and '/abs/' in href:
                    # Extract ArXiv ID
                    parts = href.split('/abs/')
                    if len(parts) > 1:
                        arxiv_id = parts[1].split('?')[0]  # Remove query params

                        if arxiv_id and arxiv_id not in seen_ids:
                            seen_ids.add(arxiv_id)

                            # Try to extract title from link text
                            title = None
                            try:
                                text = link.text.strip()
                                if text and len(text) > 10:
                                    title = text
                            except:
                                pass

                            # Extract metrics from the paper container using SVG identifiers
                            likes = 0
                            views = 0
                            
                            try:
                                # Find the parent container (the paper card)
                                container = driver.execute_script(
                                    "return arguments[0].closest('div[class*=\"mb-\"]');",
                                    link
                                )
                                
                                if container:
                                    # Extract LIKES - button with lucide-thumbs-up SVG
                                    try:
                                        thumbs_up_button = container.find_element(By.XPATH, ".//button[.//svg[contains(@class, 'lucide-thumbs-up')]]")
                                        likes_element = thumbs_up_button.find_element(By.CSS_SELECTOR, "p")
                                        likes = int(likes_element.text.replace(',', ''))
                                    except:
                                        pass
                                    
                                    # Extract VIEWS - div with lucide-chart-no-axes-column SVG
                                    try:
                                        chart_div = container.find_element(By.XPATH, ".//div[.//svg[contains(@class, 'lucide-chart-no-axes-column')]]")
                                        # Get text content, it's between the two SVGs
                                        views_text = chart_div.text.strip()
                                        # Parse the number (format: "1,609" with trailing icon)
                                        import re
                                        match = re.search(r'([\d,]+)', views_text)
                                        if match:
                                            views = int(match.group(1).replace(',', ''))
                                    except:
                                        pass
                            except Exception as e:
                                print(f"  Warning: Could not extract metrics for {arxiv_id}: {e}")

                            papers.append({
                                'universal_paper_id': arxiv_id,
                                'title': title,
                                'id': arxiv_id,
                                'metrics': {
                                    'public_total_votes': likes,  # Using likes as votes
                                    'total_votes': likes,
                                    'visits_count': {'all': views}
                                }
                            })

                            print(f"  Found paper {len(papers)}/{papers_to_add}: {arxiv_id} (likes: {likes}, views: {views})")

            if not papers:
                print("Warning: No papers found!")
                return []

            print(f"\nSuccessfully scraped {len(papers)} papers from AlphaXiv homepage")
            return papers

        finally:
            driver.quit()
            print("Browser closed")

    @task
    def print_papers_info(papers_data: List[Dict[str, Any]], papers_to_add: int) -> None:
        """
        Print paper titles and rankings to console.
        Note: Detailed signals (views, likes, comments) are fetched later
        when adding papers to the queue.

        Args:
            papers_data: List of paper data from the API (already sorted by popularity)
            papers_to_add: Number of top papers to display and add

        Raises:
            Exception: If papers_data is empty or malformed
        """
        if not papers_data:
            raise Exception("No papers to display - papers_data is empty")

        papers_to_add = int(papers_to_add)

        # Only display the top N papers that will be added
        papers_to_display = papers_data[:papers_to_add]

        print(f"\n=== AlphaXiv Hot Papers - Top {len(papers_to_display)} (from {len(papers_data)} fetched) ===\n")

        # Print each paper with ranking
        for rank, paper in enumerate(papers_to_display, 1):
            try:
                title = paper.get('title', 'Unknown Title')
                arxiv_id = paper.get('universal_paper_id', 'Unknown')
                metrics = paper.get('metrics', {})
                public_votes = metrics.get('public_total_votes', 0)
                visits = metrics.get('visits_count', {})
                views = visits.get('all', 0) if isinstance(visits, dict) else 0

                # Construct URLs
                arxiv_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id != 'Unknown' else 'N/A'
                alphaxiv_url = f"{ALPHAXIV_BASE_URL}/abs/{arxiv_id}" if arxiv_id != 'Unknown' else 'N/A'

                print(f"#{rank} - {title}")
                print(f"     ArXiv ID: {arxiv_id}")
                print(f"     Public Votes: {public_votes} | Views: {views}")
                print(f"     ArXiv URL: {arxiv_url}")
                print(f"     AlphaXiv URL: {alphaxiv_url}")
                print("")  # Empty line for readability

            except Exception as e:
                print(f"Error processing paper at rank {rank}: {e}")
                print(f"Paper data: {paper}")

        print(f"\n=== End of AlphaXiv Hot Papers ===\n")

    @task
    def add_top_papers_to_queue(papers_data: List[Dict[str, Any]], papers_to_add: int) -> None:
        """
        Add top N papers to processing queue with popularity signals.

        Args:
            papers_data: List of paper data from the API
            papers_to_add: The number of top papers to add to the queue.

        Raises:
            Exception: If database operations fail
        """
        if not papers_data:
            print("No papers to add to queue")
            return

        papers_to_add = int(papers_to_add)

        with database_session() as session:
            added_count = 0
            skipped_count = 0

            for rank, paper in enumerate(papers_data[:papers_to_add], 1):
                try:
                    arxiv_id = paper.get('universal_paper_id')

                    if not arxiv_id:
                        print(f"Skipping paper at rank {rank} - no ArXiv ID")
                        skipped_count += 1
                        continue

                    # Step 1: Extract author information
                    # AlphaXiv doesn't provide authors in the feed, so we'll extract from abstract or leave blank
                    # For now, we'll use None and let it be filled in later during processing
                    authors_str = None
                    title = paper.get('title')

                    if not title:
                        print(f"Skipping {arxiv_id} - no title found")
                        skipped_count += 1
                        continue

                    # Step 2: Fetch popularity signals from the individual paper page
                    print(f"  Fetching signals from paper page...")
                    page_signals = fetch_paper_page_signals(arxiv_id)

                    if not page_signals:
                        print(f"  Warning: Could not fetch page signals for {arxiv_id}, skipping")
                        skipped_count += 1
                        continue

                    # Create popularity signal with data from paper page
                    alphaxiv_signal = ExternalPopularitySignal(
                        source="AlphaXiv",
                        values={},
                        fetch_info={
                            "alphaxiv_paper_id": paper.get('id'),
                            "paper_group_id": paper.get('paper_group_id'),
                            "alphaxiv_url": f"{ALPHAXIV_BASE_URL}/abs/{arxiv_id}"
                        }
                    )

                    # Step 3: Add paper to processing queue
                    create_paper(
                        db=session,
                        arxiv_id=arxiv_id,
                        title=title,
                        authors=authors_str,
                        external_popularity_signals=[alphaxiv_signal],
                        initiated_by_user_id=None  # System job
                    )

                    added_count += 1
                    print(f"Added {arxiv_id} to queue (rank #{rank})")
                    print(f"  Title: {title[:80]}...")
                    print(f"  Views: {page_signals['views']} | Likes: {page_signals['likes']} | Comments: {page_signals['comments']}")

                except ValueError as e:
                    # Paper already exists - this is expected and not an error
                    if "already exists" in str(e):
                        print(f"Skipping {arxiv_id} - already exists in database")
                        skipped_count += 1
                    else:
                        print(f"Error with paper at rank {rank}: {e}")
                        skipped_count += 1
                    continue

                except Exception as e:
                    print(f"Unexpected error adding paper at rank {rank}: {e}")
                    skipped_count += 1
                    continue

            print(f"\n=== Processing Queue Summary ===")
            print(f"Added: {added_count} papers")
            print(f"Skipped: {skipped_count} papers")
            print(f"===========================\n")

    # Define task dependencies
    interval = "{{ params.time_interval }}"
    num_papers = "{{ params.papers_to_add }}"

    papers = fetch_hot_papers(time_interval=interval, papers_to_add=num_papers)
    print_papers_info(papers, papers_to_add=num_papers)
    add_top_papers_to_queue(papers, papers_to_add=num_papers)


daily_alphaxiv_papers_dag()
