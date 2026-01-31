from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250822_000013'
down_revision = '20250820_000012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'new_paper_notifications',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('arxiv_id', sa.String(length=255), nullable=False),
        sa.Column('requested_at', sa.DateTime(), nullable=False),
        sa.Column('notified', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_table('new_paper_notifications')
