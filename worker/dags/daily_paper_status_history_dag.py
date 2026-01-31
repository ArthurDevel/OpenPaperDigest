import sys
import pendulum
from datetime import datetime, date, timedelta
from contextlib import contextmanager
from typing import Optional, Tuple

from airflow.decorators import dag, task
from sqlalchemy import text
from sqlalchemy.orm import Session

# Add project root to Python path to find shared modules
sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.db.models import PaperRecord, PaperStatusHistory


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


### STATUS HISTORY FUNCTIONS ###

def _infer_status_for_date(created_at: Optional[datetime], started_at: Optional[datetime], 
                           finished_at: Optional[datetime], error_message: Optional[str], 
                           target_date: date) -> Optional[str]:
    """
    Infer paper status on a given date based on timestamps.
    
    Args:
        created_at: When paper was created
        started_at: When processing started
        finished_at: When processing finished
        error_message: Error message if failed
        target_date: Date to infer status for
        
    Returns:
        Status string or None if paper didn't exist on that date
    """
    # Paper must exist on target date
    if created_at is None or created_at.date() > target_date:
        return None
    
    # Convert target_date to datetime for comparison
    target_datetime = datetime.combine(target_date, datetime.min.time())
    
    # Infer status based on timestamps
    if started_at is None or started_at > target_datetime:
        return 'not_started'
    elif finished_at is None or finished_at > target_datetime:
        return 'processing'
    elif error_message is not None:
        return 'failed'
    else:
        return 'completed'


def _calculate_daily_snapshot(session: Session, snapshot_date: date) -> Optional[dict]:
    """
    Calculate cumulative status counts for a given date.
    
    Args:
        session: Database session
        snapshot_date: Date to calculate snapshot for
        
    Returns:
        Dict with counts or None if no papers exist yet
    """
    # Get all papers that existed on or before this date
    query = text("""
        SELECT 
            created_at,
            started_at,
            finished_at,
            error_message
        FROM papers
        WHERE DATE(created_at) <= :snapshot_date
    """)
    
    result = session.execute(query, {"snapshot_date": snapshot_date})
    papers = result.fetchall()
    
    if not papers:
        return None
    
    # Count papers by inferred status
    counts = {
        'total_count': 0,
        'failed_count': 0,
        'processed_count': 0,
        'not_started_count': 0,
        'processing_count': 0
    }
    
    for paper in papers:
        created_at = paper.created_at
        started_at = paper.started_at
        finished_at = paper.finished_at
        error_message = paper.error_message
        
        status = _infer_status_for_date(
            created_at, started_at, finished_at, error_message, snapshot_date
        )
        
        if status:
            counts['total_count'] += 1
            if status == 'failed':
                counts['failed_count'] += 1
            elif status == 'completed':
                counts['processed_count'] += 1
            elif status == 'not_started':
                counts['not_started_count'] += 1
            elif status == 'processing':
                counts['processing_count'] += 1
    
    return counts


def _get_date_range(session: Session) -> Tuple[Optional[date], Optional[date]]:
    """
    Get the date range for snapshots.
    
    Returns:
        Tuple of (earliest_date, latest_snapshot_date)
    """
    # Find earliest paper creation date
    earliest_query = text("SELECT MIN(DATE(created_at)) FROM papers")
    earliest_result = session.execute(earliest_query).scalar()
    # MySQL DATE() returns a date object, not datetime
    if earliest_result:
        if isinstance(earliest_result, datetime):
            earliest_date = earliest_result.date()
        elif isinstance(earliest_result, date):
            earliest_date = earliest_result
        else:
            # Handle string case
            earliest_date = datetime.strptime(str(earliest_result).split()[0], '%Y-%m-%d').date()
    else:
        earliest_date = None
    
    # Find latest snapshot date
    latest_query = text("SELECT MAX(date) FROM paper_status_history")
    latest_result = session.execute(latest_query).scalar()
    latest_snapshot_date = latest_result if latest_result else None
    
    return earliest_date, latest_snapshot_date


def _snapshot_exists(session: Session, snapshot_date: date) -> bool:
    """
    Check if snapshot already exists for a date.
    
    Args:
        session: Database session
        snapshot_date: Date to check
        
    Returns:
        True if snapshot exists
    """
    existing = session.query(PaperStatusHistory).filter(
        PaperStatusHistory.date == snapshot_date
    ).first()
    return existing is not None


@dag(
    dag_id="daily_paper_status_history",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule="0 1 * * *",  # 1 AM daily
    catchup=False,
    max_active_runs=1,
    tags=["papers", "history", "maintenance"],
    doc_md="""
    ### Daily Paper Status History DAG
    
    Creates daily snapshots of cumulative paper status counts for historical tracking.
    
    **What it does:**
    - Calculates cumulative counts per status (total, failed, processed, not_started, processing) for each date
    - Backfills missing historical dates on first run
    - Runs daily to capture yesterday's snapshot
    - Uses timestamp inference to determine paper status on each historical date
    
    **Status inference logic:**
    - For each date, determines paper status based on created_at, started_at, finished_at timestamps
    - This ensures historical data remains accurate even if papers change status later
    
    **Safety:**
    - Skips dates that already have snapshots (unique constraint prevents overwrites)
    - Processes dates in order from earliest to latest
    """,
)
def daily_paper_status_history():
    """
    Daily DAG to create paper status history snapshots.
    """
    
    @task
    def create_snapshots() -> dict:
        """
        Create snapshots for all missing dates.
        
        Returns:
            Summary of snapshots created
        """
        with database_session() as session:
            earliest_date, latest_snapshot_date = _get_date_range(session)
            
            if earliest_date is None:
                print("No papers found in database")
                return {"snapshots_created": 0, "dates_processed": []}
            
            # Determine end date (yesterday, or today if run late)
            end_date = date.today() - timedelta(days=1)
            
            # Start from day after latest snapshot, or from earliest date if no snapshots exist
            if latest_snapshot_date:
                start_date = latest_snapshot_date + timedelta(days=1)
            else:
                start_date = earliest_date
            
            if start_date > end_date:
                print(f"No new dates to process. Latest snapshot: {latest_snapshot_date}")
                return {"snapshots_created": 0, "dates_processed": []}
            
            print(f"Processing dates from {start_date} to {end_date}")
            
            snapshots_created = 0
            dates_processed = []
            current_date = start_date
            
            while current_date <= end_date:
                # Skip if snapshot already exists (shouldn't happen, but safety check)
                if _snapshot_exists(session, current_date):
                    print(f"Skipping {current_date} - snapshot already exists")
                    current_date += timedelta(days=1)
                    continue
                
                # Calculate snapshot for this date
                counts = _calculate_daily_snapshot(session, current_date)
                
                if counts is None:
                    print(f"No papers found for {current_date}, skipping")
                    current_date += timedelta(days=1)
                    continue
                
                # Create snapshot record
                snapshot = PaperStatusHistory(
                    date=current_date,
                    total_count=counts['total_count'],
                    failed_count=counts['failed_count'],
                    processed_count=counts['processed_count'],
                    not_started_count=counts['not_started_count'],
                    processing_count=counts['processing_count'],
                    snapshot_at=datetime.utcnow()
                )
                
                session.add(snapshot)
                session.flush()  # Flush to check for unique constraint violations
                
                snapshots_created += 1
                dates_processed.append(str(current_date))
                
                print(f"Created snapshot for {current_date}: total={counts['total_count']}, "
                      f"failed={counts['failed_count']}, processed={counts['processed_count']}, "
                      f"not_started={counts['not_started_count']}, processing={counts['processing_count']}")
                
                current_date += timedelta(days=1)
            
            session.commit()
            
            print(f"Created {snapshots_created} snapshots")
            return {
                "snapshots_created": snapshots_created,
                "dates_processed": dates_processed
            }
    
    # Run the task
    create_snapshots()


# Instantiate the DAG
daily_paper_status_history_dag = daily_paper_status_history()

