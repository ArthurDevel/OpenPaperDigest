"""
Remove processed_content and thumbnail_data_url columns from papers table.

These columns previously stored the full paper JSON blob (~2 MB) and a base64
thumbnail image directly in the database. Both have been migrated to Supabase
Storage (bucket: papers) and are no longer needed.

Responsibilities:
- upgrade: Drop processed_content and thumbnail_data_url columns
- downgrade: Re-add both columns as nullable Text
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260305_000029'
down_revision = '20260304_000028'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop processed_content and thumbnail_data_url columns from papers."""
    with op.batch_alter_table('papers') as batch_op:
        batch_op.drop_column('processed_content')
        batch_op.drop_column('thumbnail_data_url')


def downgrade() -> None:
    """Re-add processed_content and thumbnail_data_url as nullable Text columns."""
    with op.batch_alter_table('papers') as batch_op:
        batch_op.add_column(
            sa.Column('processed_content', sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('thumbnail_data_url', sa.Text(), nullable=True)
        )
