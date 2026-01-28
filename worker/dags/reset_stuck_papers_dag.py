import sys
import pendulum
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import List

from airflow.decorators import dag, task
from airflow.models.param import Param
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy import or_

# Add project root to Python path to find shared modules
sys.path.insert(0, '/opt/airflow')

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


### RESET FUNCTIONS ###

def _find_papers_to_reset(session: Session, minutes_ago: int, reset_processing: bool, reset_failed: bool) -> List[PaperRecord]:
    """
    Find papers to reset based on their status and age.
    
    Args:
        session: Active database session
        minutes_ago: How many minutes ago to check
        reset_processing: Whether to include papers with 'processing' status
        reset_failed: Whether to include papers with 'failed' status
        
    Returns:
        List[PaperRecord]: Papers that match the criteria
    """
    cutoff_time = datetime.utcnow() - timedelta(minutes=minutes_ago)
    
    query_conditions = []
    
    if reset_processing:
        query_conditions.append(
            (PaperRecord.status == 'processing') & (PaperRecord.started_at < cutoff_time)
        )
        
    if reset_failed:
        query_conditions.append(
            (PaperRecord.status == 'failed') & (PaperRecord.updated_at < cutoff_time)
        )
    
    if not query_conditions:
        return []
        
    papers_to_reset = session.query(PaperRecord).filter(
        or_(*query_conditions)
    ).all()
    
    return papers_to_reset


def _reset_paper_to_not_started(session: Session, paper: PaperRecord) -> None:
    """
    Reset a single paper back to not_started status.
    
    Args:
        session: Active database session  
        paper: Paper record to reset
    """
    paper.status = 'not_started'
    paper.started_at = None
    paper.error_message = None
    paper.updated_at = datetime.utcnow()
    session.add(paper)
    
    print(f"Reset paper {paper.id} (arXiv: {paper.arxiv_id}) back to not_started")


@dag(
    dag_id="reset_stuck_papers",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,  # Manual trigger only
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance"],
    params={
        "minutes_ago": Param(
            default=30,
            type="integer",
            title="Minutes Ago",
            description="Reset papers that have been in the selected status for this many minutes or longer.",
            minimum=5
        ),
        "reset_processing": Param(
            default=True,
            type="boolean",
            title="Reset 'processing' papers",
            description="Select to reset papers stuck in the 'processing' state."
        ),
        "reset_failed": Param(
            default=False,
            type="boolean",
            title="Reset 'failed' papers",
            description="Select to reset papers in the 'failed' state."
        )
    },
    doc_md="""
    ### Reset Papers DAG
    
    Manual DAG to reset papers stuck in 'processing' or 'failed' status back to 'not_started'.
    
    **Usage:**
    1. Trigger manually from Airflow UI.
    2. Set 'minutes_ago' parameter (default: 30 minutes).
    3. Select whether to reset 'processing' papers, 'failed' papers, or both.
    
    **What it does:**
    - Finds papers with the selected statuses older than the specified time.
      - For 'processing' status, it checks how long ago the processing `started_at`.
      - For 'failed' status, it checks how long ago the paper was last `updated_at`.
    - Resets status to 'not_started'.
    - Clears started_at and error_message fields
    - Allows papers to be reprocessed
    
    **Safety:** Only affects papers that have been processing for the specified time or longer.
    """,
)
def reset_stuck_papers_dag():
    
    @task
    def reset_stuck_processing_papers(minutes_ago: int = 30, reset_processing: bool = True, reset_failed: bool = False) -> dict:
        """
        Reset papers stuck in processing or failed status back to not_started.
        
        Args:
            minutes_ago: Reset papers that have been in a state for this many minutes or longer.
            reset_processing: Whether to reset papers in 'processing' status.
            reset_failed: Whether to reset papers in 'failed' status.
            
        Returns:
            dict: Summary of reset operation
        """
        if not reset_processing and not reset_failed:
            message = "No paper statuses selected for reset. Exiting."
            print(message)
            return {
                "reset_count": 0,
                "minutes_threshold": minutes_ago,
                "message": message
            }

        # Convert to int in case parameter comes as string from Airflow
        minutes_ago = int(minutes_ago)
        
        print(f"Looking for papers to reset that have been in a final state for {minutes_ago}+ minutes...")
        
        with database_session() as session:
            # Step 1: Find stuck papers
            papers_to_reset = _find_papers_to_reset(session, minutes_ago, reset_processing, reset_failed)
            
            if not papers_to_reset:
                print("No papers found to reset.")
                return {
                    "reset_count": 0,
                    "minutes_threshold": minutes_ago,
                    "message": "No papers were found to reset."
                }
            
            # Step 2: Reset each stuck paper
            reset_count = 0
            for paper in papers_to_reset:
                _reset_paper_to_not_started(session, paper)
                reset_count += 1
            
            print(f"Reset {reset_count} papers back to not_started status")
            
            return {
                "reset_count": reset_count,
                "minutes_threshold": minutes_ago,
                "message": f"Successfully reset {reset_count} papers"
            }
    
    # Single task with parameter input
    reset_stuck_processing_papers(
        minutes_ago="{{ params.minutes_ago }}",
        reset_processing="{{ params.reset_processing }}",
        reset_failed="{{ params.reset_failed }}"
    )


reset_stuck_papers_dag()
