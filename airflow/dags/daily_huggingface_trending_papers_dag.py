import sys
import os
import pendulum
import requests
from airflow.decorators import dag, task
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
from airflow.models import Param
from bs4 import BeautifulSoup
import re

# Add project root to Python path to find shared modules
sys.path.insert(0, '/opt/airflow')

from sqlalchemy.orm import Session
from shared.db import SessionLocal
from papers.models import ExternalPopularitySignal
from papers.client import create_paper


### CONSTANTS ###

HUGGINGFACE_TRENDING_URL = "https://huggingface.co/papers/trending"


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


### HELPER FUNCTIONS ###

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


def extract_arxiv_id_from_path(path: str) -> Optional[str]:
    """
    Extract arXiv ID from Hugging Face paper path like /papers/2511.16624.
    
    Args:
        path: Path like /papers/2511.16624
        
    Returns:
        Optional[str]: Extracted arXiv ID or None if not found
    """
    match = re.search(r'/papers/(\d{4}\.\d{4,5})', path)
    if match:
        return match.group(1)
    return None


@dag(
    dag_id="daily_huggingface_trending_papers",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule="0 12 * * *",  # Noon daily
    catchup=False,
    tags=["huggingface", "trending", "papers"],
    params={
        "max_papers": Param(
            type="integer",
            default=50,
            title="Maximum Papers to Process",
            description="The maximum number of trending papers to scrape and add to the processing queue.",
            minimum=1,
            maximum=200
        )
    },
    doc_md="""
    ### Daily Hugging Face Trending Papers DAG

    This DAG scrapes the Hugging Face trending papers page and adds papers to the processing queue.
    - Runs daily at noon
    - Scrapes all papers from the trending page (up to max_papers limit)
    - Extracts ArXiv IDs, titles, upvotes, and GitHub stars
    - Adds papers to the processing queue with popularity signals
    """,
)
def daily_huggingface_trending_papers_dag():
    
    @task
    def fetch_trending_papers(**context) -> List[Dict[str, Any]]:
        """
        Scrape trending papers from Hugging Face trending page.
        
        Args:
            **context: Airflow context containing params
            
        Returns:
            List[Dict[str, Any]]: List of paper data from the trending page
            
        Raises:
            Exception: If scraping fails or returns invalid data
        """
        max_papers = int(context["params"]["max_papers"])
        print(f"Fetching trending papers page: {HUGGINGFACE_TRENDING_URL}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        try:
            response = requests.get(HUGGINGFACE_TRENDING_URL, headers=headers, timeout=30)
            response.raise_for_status()
            print(f"✓ Status Code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch trending page: {e}")
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all article elements (each represents a paper)
        articles = soup.find_all('article', class_=lambda x: x and 'rounded-xl' in x if x else False)
        print(f"Found {len(articles)} paper articles")
        
        papers_data = []
        papers_to_process = articles[:max_papers]
        print(f"\nProcessing {len(papers_to_process)} papers (max: {max_papers})...\n")
        
        for idx, article in enumerate(papers_to_process, 1):
            try:
                paper_data = {
                    "index": idx,
                    "title": None,
                    "arxiv_id": None,
                    "arxiv_url": None,
                    "paper_url": None,
                    "upvotes": None,
                    "github_stars": None,
                }
                
                # Extract title from h3 > a
                title_elem = article.find('h3')
                if title_elem:
                    title_link = title_elem.find('a')
                    if title_link:
                        paper_data["title"] = title_link.get_text(strip=True)
                        href = title_link.get('href', '')
                        if href:
                            # Extract ArXiv ID from path like /papers/2511.16624
                            arxiv_id = extract_arxiv_id_from_path(href)
                            if arxiv_id:
                                paper_data["arxiv_id"] = arxiv_id
                                paper_data["paper_url"] = f"https://huggingface.co{href}"
                                paper_data["arxiv_url"] = f"https://arxiv.org/abs/{arxiv_id}"
                
                # Look for ArXiv link directly
                if not paper_data["arxiv_id"]:
                    arxiv_links = article.find_all('a', href=lambda x: x and 'arxiv.org' in x if x else False)
                    for link in arxiv_links:
                        arxiv_id = extract_arxiv_id_from_url(link.get('href', ''))
                        if arxiv_id:
                            paper_data["arxiv_id"] = arxiv_id
                            paper_data["arxiv_url"] = link.get('href')
                            if not paper_data["paper_url"]:
                                # Try to find the HF paper link
                                hf_link = article.find('a', href=lambda x: x and '/papers/' in x if x else False)
                                if hf_link:
                                    paper_data["paper_url"] = f"https://huggingface.co{hf_link.get('href')}"
                            break
                
                # Extract ArXiv ID from paper path if still not found
                if not paper_data["arxiv_id"]:
                    hf_links = article.find_all('a', href=lambda x: x and '/papers/' in x if x else False)
                    for link in hf_links:
                        arxiv_id = extract_arxiv_id_from_path(link.get('href', ''))
                        if arxiv_id:
                            paper_data["arxiv_id"] = arxiv_id
                            paper_data["arxiv_url"] = f"https://arxiv.org/abs/{arxiv_id}"
                            paper_data["paper_url"] = f"https://huggingface.co{link.get('href')}"
                            break
                
                # Extract upvotes from the div with class "font-semibold text-orange-500"
                upvote_div = article.find('div', class_=lambda x: x and 'text-orange-500' in x if x else False)
                if upvote_div:
                    upvote_text = upvote_div.get_text(strip=True)
                    try:
                        paper_data["upvotes"] = int(upvote_text)
                    except ValueError:
                        pass
                
                # Extract GitHub stars from the GitHub link span
                github_link = article.find('a', href=lambda x: x and 'github.com' in x if x else False)
                if github_link:
                    # Look for span with star count (usually has "k" notation like "2.61k")
                    star_spans = github_link.find_all('span')
                    for span in star_spans:
                        star_text = span.get_text(strip=True)
                        # Check if it looks like a star count (contains numbers and possibly 'k')
                        if re.match(r'^\d+\.?\d*k?$', star_text.lower()):
                            try:
                                # Handle "k" notation (e.g., "2.61k" = 2610)
                                if 'k' in star_text.lower():
                                    star_value = float(star_text.lower().replace('k', ''))
                                    paper_data["github_stars"] = int(star_value * 1000)
                                else:
                                    paper_data["github_stars"] = int(star_text)
                                break
                            except ValueError:
                                pass
                
                # Only add papers with ArXiv IDs
                if paper_data["arxiv_id"]:
                    papers_data.append(paper_data)
                    print(f"  Paper #{idx}: {paper_data['title'] or 'Unknown'} (ArXiv: {paper_data['arxiv_id']})")
                else:
                    print(f"  Paper #{idx}: Skipped - no ArXiv ID found")
                
            except Exception as e:
                print(f"  Error processing paper #{idx}: {e}")
                continue
        
        print(f"\nSuccessfully scraped {len(papers_data)} papers with ArXiv IDs")
        return papers_data
    
    @task  
    def print_papers_info(papers_data: List[Dict[str, Any]]) -> None:
        """
        Print paper titles, rankings, and details to console.
        
        Args:
            papers_data: List of paper data from the scraping
            
        Raises:
            Exception: If papers_data is empty or malformed
        """
        if not papers_data:
            print("No papers to display - papers_data is empty")
            return
        
        # Sort papers by upvotes (highest first)
        try:
            sorted_papers = sorted(
                papers_data, 
                key=lambda x: x.get('upvotes', 0) or 0, 
                reverse=True
            )
        except Exception as e:
            raise Exception(f"Failed to sort papers by upvotes: {e}")
            
        print(f"\n=== Trending Papers - Ranked by Upvotes ({len(sorted_papers)} papers) ===\n")
        
        # Print each paper with ranking
        for rank, paper in enumerate(sorted_papers, 1):
            try:
                title = paper.get('title', 'Unknown Title')
                arxiv_id = paper.get('arxiv_id', 'Unknown')
                upvotes = paper.get('upvotes', 0) or 0
                github_stars = paper.get('github_stars', 0) or 0
                
                print(f"#{rank} - {title}")
                print(f"     ArXiv ID: {arxiv_id}")
                print(f"     ArXiv URL: {paper.get('arxiv_url', 'N/A')}")
                print(f"     Upvotes: {upvotes} | GitHub Stars: {github_stars}")
                print("")  # Empty line for readability
                
            except Exception as e:
                print(f"Error processing paper at rank {rank}: {e}")
                print(f"Paper data: {paper}")
        
        print(f"\n=== End of Trending Papers Ranking ===\n")
    
    @task
    def add_papers_to_queue(papers_data: List[Dict[str, Any]]) -> None:
        """
        Add all scraped papers to processing queue with popularity signals.
        
        Args:
            papers_data: List of paper data from the scraping
            
        Raises:
            Exception: If database operations fail
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
                    
                    if not arxiv_id:
                        print(f"Skipping paper at rank {rank} - no ArXiv ID")
                        skipped_count += 1
                        continue
                    
                    # Create popularity signal
                    hf_signal = ExternalPopularitySignal(
                        source="HuggingFaceTrending",
                        values={
                            "upvotes": paper.get('upvotes', 0) or 0,
                            "github_stars": paper.get('github_stars', 0) or 0
                        },
                        fetch_info={
                            "hf_paper_url": paper.get('paper_url'),
                            "scraped_from": HUGGINGFACE_TRENDING_URL
                        }
                    )
                    
                    # Add paper to processing queue
                    # Note: authors will be extracted during processing if not provided
                    created_paper = create_paper(
                        db=session,
                        arxiv_id=arxiv_id,
                        title=paper.get('title'),
                        authors=None,  # Will be extracted during processing
                        external_popularity_signals=[hf_signal],
                        initiated_by_user_id=None  # System job
                    )
                    
                    added_count += 1
                    print(f"Added {arxiv_id} to queue (rank #{rank})")
                    print(f"  Title: {paper.get('title', 'Unknown')[:80]}...")
                    print(f"  Upvotes: {paper.get('upvotes', 0) or 0} | GitHub Stars: {paper.get('github_stars', 0) or 0}")
                    
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
    papers = fetch_trending_papers()
    print_papers_info(papers)
    add_papers_to_queue(papers)


daily_huggingface_trending_papers_dag()

