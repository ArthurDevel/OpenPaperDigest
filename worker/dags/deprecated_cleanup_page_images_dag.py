"""
DEPRECATED: Page image cleanup is no longer needed.

This DAG previously removed page image data from the processed_content JSON
column and normalized bounding box coordinates. Since processed_content has
been migrated to Supabase Storage (Phase 5), page images are no longer stored
anywhere -- they are discarded during processing. Bounding box normalization
is now performed at save time in save_paper().

This file is kept as a no-op to avoid Airflow import errors for existing
DAG references.
"""

import sys
import pendulum

from airflow.decorators import dag, task

sys.path.insert(0, '/opt/airflow')


@dag(
    dag_id='deprecated_cleanup_page_images',
    start_date=pendulum.datetime(2025, 1, 1, tz='UTC'),
    schedule=None,
    catchup=False,
    tags=['maintenance', 'cleanup', 'storage', 'deprecated'],
    description='DEPRECATED - Page images are no longer stored in the database',
)
def cleanup_page_images_workflow():
    """
    Deprecated DAG. Page images are no longer stored in the database.
    This is a no-op kept for backward compatibility with Airflow.
    """

    @task
    def noop() -> None:
        """No-op task. This DAG is deprecated."""
        print("This DAG is deprecated. Page images are no longer stored in the database.")
        print("processed_content has been migrated to Supabase Storage.")
        print("No action required.")

    noop()


cleanup_page_images_dag = cleanup_page_images_workflow()
