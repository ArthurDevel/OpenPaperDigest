from __future__ import annotations

import json
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260304_000025'
down_revision = '20250120_000024'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add summaries JSON column to papers table.
    Stores extracted summaries (e.g. five_minute_summary) separately from
    the large processed_content blob for fast reads.

    Backfill is handled separately by testscripts/2026.03.04-homepage-performance/backfill_summaries.py
    """
    connection = op.get_bind()
    connection.execute(sa.text("SET statement_timeout = '300s'"))
    op.add_column('papers', sa.Column('summaries', sa.JSON(), nullable=True))


def downgrade() -> None:
    """
    Remove summaries column from papers table.
    """
    op.drop_column('papers', 'summaries')
