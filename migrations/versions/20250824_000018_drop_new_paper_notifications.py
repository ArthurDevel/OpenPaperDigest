"""drop new_paper_notifications

Revision ID: 20250824_000018
Revises: 20250823_000017
Create Date: 2025-08-24 00:00:18.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20250824_000018'
down_revision: Union[str, None] = '20250823_000017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    try:
        op.drop_table('new_paper_notifications')
    except Exception:
        # Table may not exist in some environments
        pass


def downgrade() -> None:
    op.create_table(
        'new_paper_notifications',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('arxiv_id', sa.String(length=255), nullable=False),
        sa.Column('requested_at', sa.DateTime(), nullable=False),
        sa.Column('notified', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


