import sys
import pendulum
from airflow.decorators import dag, task
from typing import List, Dict, Any
from contextlib import contextmanager

# Add project root to Python path to find shared modules
sys.path.insert(0, '/opt/airflow')

from sqlalchemy.orm import Session
from shared.db import SessionLocal
from papers.db.models import PaperRecord


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
    dag_id="backfill_arxiv_urls",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,  # Manual trigger only
    catchup=False,
    tags=["backfill", "maintenance"],
    description="Backfill arxiv_url for papers that have null values"
)
def backfill_arxiv_urls():
    """
    One-time backfill DAG to update arxiv_url for all papers with null values.

    This DAG constructs the arxiv_url from the arxiv_id field using the format:
    https://arxiv.org/abs/{arxiv_id}

    Run this DAG manually after deploying the fix to create_paper().
    """

    @task
    def get_papers_with_null_arxiv_url() -> List[Dict[str, Any]]:
        """
        Query database for all papers with null arxiv_url.

        Returns:
            List of dicts containing paper_uuid and arxiv_id
        """
        with database_session() as session:
            # Query papers where arxiv_url is null
            papers = session.query(PaperRecord).filter(
                PaperRecord.arxiv_url.is_(None),
                PaperRecord.arxiv_id.isnot(None)
            ).all()

            result = [
                {
                    "paper_uuid": paper.paper_uuid,
                    "arxiv_id": paper.arxiv_id
                }
                for paper in papers
            ]

            print(f"Found {len(result)} papers with null arxiv_url")
            return result

    @task
    def update_arxiv_urls(papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Update arxiv_url for all papers.

        Args:
            papers: List of paper dicts with paper_uuid and arxiv_id

        Returns:
            Summary statistics of the update operation
        """
        updated_count = 0
        error_count = 0
        errors = []

        with database_session() as session:
            for paper_data in papers:
                try:
                    paper_uuid = paper_data["paper_uuid"]
                    arxiv_id = paper_data["arxiv_id"]

                    # Construct arxiv_url
                    arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"

                    # Update the paper
                    paper = session.query(PaperRecord).filter(
                        PaperRecord.paper_uuid == paper_uuid
                    ).first()

                    if paper:
                        paper.arxiv_url = arxiv_url
                        updated_count += 1
                    else:
                        error_count += 1
                        errors.append(f"Paper not found: {paper_uuid}")

                except Exception as e:
                    error_count += 1
                    errors.append(f"Error updating {paper_data.get('paper_uuid')}: {str(e)}")

            # Commit all updates
            session.commit()

        summary = {
            "total_papers": len(papers),
            "updated_count": updated_count,
            "error_count": error_count,
            "errors": errors[:10]  # Only include first 10 errors
        }

        print(f"Backfill complete:")
        print(f"  Total papers: {summary['total_papers']}")
        print(f"  Updated: {summary['updated_count']}")
        print(f"  Errors: {summary['error_count']}")

        return summary

    # Define task dependencies
    papers = get_papers_with_null_arxiv_url()
    summary = update_arxiv_urls(papers)


# Instantiate the DAG
backfill_arxiv_urls_dag = backfill_arxiv_urls()
