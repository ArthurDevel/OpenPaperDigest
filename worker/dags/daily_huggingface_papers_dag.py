import sys
import os
import pendulum
import requests
from airflow.decorators import dag, task
from typing import List, Dict, Any
from contextlib import contextmanager
from airflow.models import Param

# Add project root to Python path to find shared modules
sys.path.insert(0, '/opt/airflow')

from sqlalchemy.orm import Session
from shared.db import SessionLocal
from papers.models import ExternalPopularitySignal
from papers.client import create_paper


### CONSTANTS ###
HUGGINGFACE_API_URL = "https://huggingface.co/api/daily_papers"


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
    dag_id="daily_huggingface_papers",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule="0 6 * * *",  # 6 AM daily
    catchup=False,
    tags=["huggingface", "papers"],
    params={
        "date_to_fetch": Param(
            type="string",
            default=pendulum.yesterday().to_date_string(),
            title="Date to Fetch",
            description="The date for which to fetch papers, in YYYY-MM-DD format."
        ),
        "papers_to_add": Param(
            type="integer",
            default=20,
            title="Number of Papers to Add",
            description="The number of top papers to add to the processing queue.",
            minimum=1,
            maximum=50
        )
    },
    doc_md="""
    ### Daily Hugging Face Papers DAG

    This DAG fetches daily papers from Hugging Face for a specified date and adds the top N papers to the processing queue.
    - When run on its daily schedule, it fetches papers for the previous day.
    - When run manually, you can specify a date and the number of papers to add.
    """,
)
def daily_huggingface_papers_dag():
    
    @task
    def fetch_daily_papers(date_to_fetch: str) -> List[Dict[str, Any]]:
        """
        Fetch papers from Hugging Face daily papers API for a specific date.
        
        Args:
            date_to_fetch: The date to fetch papers for, in YYYY-MM-DD format.

        Returns:
            List[Dict[str, Any]]: List of paper data from the API
            
        Raises:
            Exception: If API call fails or returns invalid data
        """
        api_url_with_date = f"{HUGGINGFACE_API_URL}?date={date_to_fetch}"
        
        print(f"Fetching papers for {date_to_fetch} from: {api_url_with_date}")
        
        try:
            response = requests.get(api_url_with_date, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch papers from Hugging Face API: {e}")
        
        try:
            papers_data = response.json()
        except ValueError as e:
            raise Exception(f"Invalid JSON response from Hugging Face API: {e}")
            
        if not papers_data:
            print(f"No papers found for {date_to_fetch}")
            return [] # Return empty list, not an exception, to allow DAG to complete gracefully
            
        print(f"Successfully fetched {len(papers_data)} papers for {date_to_fetch}")
        return papers_data
    
    @task  
    def print_papers_info(papers_data: List[Dict[str, Any]], date_to_fetch: str) -> None:
        """
        Print paper titles, rankings, and details to console.
        
        Args:
            papers_data: List of paper data from the API
            
        Raises:
            Exception: If papers_data is empty or malformed
        """
        if not papers_data:
            raise Exception("No papers to display - papers_data is empty")
        
        # Step 1: Sort papers by upvotes (highest first)
        try:
            sorted_papers = sorted(
                papers_data, 
                key=lambda x: x.get('paper', {}).get('upvotes', 0), 
                reverse=True
            )
        except Exception as e:
            raise Exception(f"Failed to sort papers by upvotes: {e}")
            
        print(f"\n=== Papers for {date_to_fetch} - Ranked by Upvotes ({len(sorted_papers)} papers) ===\n")
        
        # Step 2: Print each paper with ranking
        for rank, paper_item in enumerate(sorted_papers, 1):
            try:
                # Extract paper data from the structure
                paper = paper_item.get('paper', {})
                title = paper.get('title', paper_item.get('title', 'Unknown Title'))
                github_stars = paper.get('githubStars', 0)
                upvotes = paper.get('upvotes', 0)
                arxiv_id = paper.get('id', 'Unknown')
                
                # Construct ArXiv URL
                arxiv_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id != 'Unknown' else 'N/A'
                
                print(f"#{rank} - {title}")
                print(f"     ArXiv ID: {arxiv_id}")
                print(f"     ArXiv URL: {arxiv_url}")
                print(f"     Upvotes: {upvotes} | GitHub Stars: {github_stars}")
                print("")  # Empty line for readability
                
            except Exception as e:
                print(f"Error processing paper at rank {rank}: {e}")
                print(f"Paper data: {paper_item}")
        
        print(f"\n=== End of Daily Papers Ranking ===\n")
    
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
            
            for rank, paper_item in enumerate(papers_data[:papers_to_add], 1):
                try:
                    paper = paper_item.get('paper', {})
                    arxiv_id = paper.get('id')
                    
                    if not arxiv_id:
                        print(f"Skipping paper at rank {rank} - no ArXiv ID")
                        skipped_count += 1
                        continue
                    
                    # Step 1: Convert authors array to string
                    authors_list = [author.get('name', '') for author in paper.get('authors', [])]
                    authors_str = ', '.join(filter(None, authors_list))
                    
                    if not authors_str:
                        print(f"Skipping {arxiv_id} - no authors found")
                        skipped_count += 1
                        continue
                    
                    # Step 2: Create popularity signal
                    hf_signal = ExternalPopularitySignal(
                        source="HuggingFace",
                        values={
                            "upvotes": paper.get('upvotes', 0),
                            "github_stars": paper.get('githubStars', 0)
                        },
                        fetch_info={
                            "hf_paper_id": paper_item.get('discussionId'),
                            "api_endpoint": "https://huggingface.co/api/daily_papers"
                        }
                    )
                    
                    # Step 3: Add paper to processing queue
                    created_paper = create_paper(
                        db=session,
                        arxiv_id=arxiv_id,
                        title=paper.get('title'),
                        authors=authors_str,
                        external_popularity_signals=[hf_signal],
                        initiated_by_user_id=None  # System job
                    )
                    
                    added_count += 1
                    print(f"Added {arxiv_id} to queue (rank #{rank})")
                    print(f"  Title: {paper.get('title', 'Unknown')[:80]}...")
                    print(f"  Upvotes: {paper.get('upvotes', 0)} | GitHub Stars: {paper.get('githubStars', 0)}")
                    
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
    date_str = "{{ params.date_to_fetch }}"
    num_papers = "{{ params.papers_to_add }}"

    papers = fetch_daily_papers(date_to_fetch=date_str)
    print_papers_info(papers, date_to_fetch=date_str)
    add_top_papers_to_queue(papers, papers_to_add=num_papers)


daily_huggingface_papers_dag()
