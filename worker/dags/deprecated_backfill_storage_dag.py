"""
DEPRECATED: This DAG is no longer needed. New papers (pipeline v2) only store
thumbnail + metadata.json. This DAG was used for migrating old papers from
PostgreSQL to Supabase Storage.

Backfill Storage DAG

Migrates existing paper data from PostgreSQL processed_content JSON blob
and thumbnail_data_url column into Supabase Storage. Processes papers one
at a time to avoid statement timeouts on large blobs.

The DAG reads the old columns via raw SQL (they are no longer in the ORM)
and uploads each paper's assets to the private "papers" bucket.
"""

import sys
import json
import base64
import logging
import pendulum

from airflow.decorators import dag, task

sys.path.insert(0, '/opt/airflow')

logger = logging.getLogger(__name__)


def _decode_data_url(data_url):
    """Decode a base64 data URL to raw bytes."""
    _, b64_data = data_url.split(",", 1)
    return base64.b64decode(b64_data)


@dag(
    dag_id="deprecated_backfill_storage",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance", "backfill", "one-time", "storage"],
    doc_md="""
    ### Backfill Storage DAG

    **DEPRECATED**: This DAG is no longer needed. New papers (pipeline v2) only
    store thumbnail + metadata.json. This DAG was used for migrating old papers
    from PostgreSQL to Supabase Storage.

    Migrates existing paper data from PostgreSQL `processed_content` and
    `thumbnail_data_url` columns into Supabase Storage. Safe to re-run —
    skips papers that already exist in storage.
    """,
)
def backfill_storage_dag():

    @task
    def migrate_papers() -> None:
        """Read old columns via raw SQL one at a time and upload to Supabase Storage."""
        from sqlalchemy import text, create_engine
        from sqlalchemy.orm import sessionmaker
        from shared.config import settings
        import papers.storage as storage

        # Use a direct engine with no statement timeout for heavy reads
        engine = create_engine(
            settings.DATABASE_URL,
            connect_args={"options": "-c statement_timeout=0"},
        )
        Session = sessionmaker(bind=engine)
        db = Session()

        try:
            # Step 1: Get list of paper UUIDs to migrate (lightweight query)
            uuid_rows = db.execute(
                text(
                    "SELECT paper_uuid FROM papers "
                    "WHERE status = 'completed' "
                    "AND processed_content IS NOT NULL "
                    "ORDER BY id"
                )
            ).fetchall()

            total = len(uuid_rows)
            logger.info("Found %d papers to migrate", total)

            migrated = 0
            skipped = 0
            failed = 0

            # Step 2: Process each paper individually
            for i, uuid_row in enumerate(uuid_rows):
                paper_uuid = uuid_row[0]

                try:
                    # Check if already migrated
                    try:
                        storage.get_thumbnail_url(paper_uuid)
                        skipped += 1
                        logger.info(
                            "[%d/%d] Skipping %s — already in storage",
                            i + 1, total, paper_uuid
                        )
                        continue
                    except Exception:
                        pass

                    # Fetch this paper's content individually
                    row = db.execute(
                        text(
                            "SELECT processed_content, thumbnail_data_url "
                            "FROM papers WHERE paper_uuid = :uuid"
                        ),
                        {"uuid": paper_uuid}
                    ).fetchone()

                    if not row or not row[0]:
                        logger.warning("[%d/%d] No content for %s", i + 1, total, paper_uuid)
                        failed += 1
                        continue

                    processed_content_raw = row[0]
                    thumbnail_data_url = row[1]

                    # Parse processed_content JSON
                    if isinstance(processed_content_raw, str):
                        content = json.loads(processed_content_raw)
                    else:
                        content = processed_content_raw

                    # Decode thumbnail
                    thumb_url = thumbnail_data_url or content.get("thumbnail_data_url", "")
                    if not thumb_url:
                        logger.warning("[%d/%d] No thumbnail for %s, skipping", i + 1, total, paper_uuid)
                        failed += 1
                        continue
                    thumbnail_bytes = _decode_data_url(thumb_url)

                    # Extract text content
                    final_markdown = content.get("final_markdown", "")
                    sections = content.get("sections", [])

                    # Build figures with decoded image bytes
                    figures = []
                    for fig in content.get("figures", []):
                        image_data_url = fig.get("image_data_url", "")
                        if not image_data_url:
                            continue
                        figures.append({
                            "identifier": fig.get("figure_identifier", fig.get("identifier", "")),
                            "image_bytes": _decode_data_url(image_data_url),
                            "short_id": fig.get("short_id"),
                            "bounding_box": fig.get("bounding_box"),
                            "location_page": fig.get("location_page"),
                            "referenced_on_pages": fig.get("referenced_on_pages"),
                            "explanation": fig.get("explanation"),
                        })

                    # Build metadata
                    metadata = {
                        "usage_summary": content.get("usage_summary", {}),
                        "processing_time_seconds": content.get("processing_time_seconds", 0.0),
                        "num_pages": content.get("num_pages", 0),
                        "total_cost": content.get("total_cost", 0.0),
                        "avg_cost_per_page": content.get("avg_cost_per_page", 0.0),
                    }

                    # Upload to storage
                    storage.upload_paper_assets(
                        paper_uuid=paper_uuid,
                        thumbnail_bytes=thumbnail_bytes,
                        final_markdown=final_markdown,
                        sections=sections,
                        figures=figures,
                        metadata=metadata,
                    )

                    migrated += 1
                    logger.info(
                        "[%d/%d] Migrated %s (%d figures)",
                        i + 1, total, paper_uuid, len(figures)
                    )

                except Exception as e:
                    failed += 1
                    logger.error(
                        "[%d/%d] Failed to migrate %s: %s",
                        i + 1, total, paper_uuid, str(e)
                    )

            logger.info(
                "Backfill complete: %d migrated, %d skipped, %d failed out of %d total",
                migrated, skipped, failed, total
            )

        finally:
            db.close()
            engine.dispose()

    migrate_papers()


backfill_storage_dag()
