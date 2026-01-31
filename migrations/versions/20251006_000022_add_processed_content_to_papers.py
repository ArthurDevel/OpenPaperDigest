from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251006_000022'
down_revision = '20250919_000021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add processed_content column to papers table to store complete paper JSON.
    This eliminates the need for shared file system storage.
    """
    with op.batch_alter_table('papers') as batch_op:
        batch_op.add_column(
            sa.Column(
                'processed_content',
                sa.Text(),
                nullable=True
            )
        )


def downgrade() -> None:
    """
    Remove processed_content column from papers table.
    """
    with op.batch_alter_table('papers') as batch_op:
        batch_op.drop_column('processed_content')
