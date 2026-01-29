"""drop requested_papers table

Revision ID: 20250827_000020
Revises: 20250826_000019
Create Date: 2025-08-27 00:00:20.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20250827_000020'
down_revision: Union[str, None] = '20250826_000019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    try:
        op.drop_table('requested_papers')
    except Exception:
        # Table may already be absent
        pass


def downgrade() -> None:
    op.create_table(
        'requested_papers',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('arxiv_id', sa.String(length=64), nullable=False, unique=True),
        sa.Column('arxiv_abs_url', sa.String(length=255), nullable=False),
        sa.Column('arxiv_pdf_url', sa.String(length=255), nullable=False),
        sa.Column('request_count', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('first_requested_at', sa.DateTime(), nullable=False),
        sa.Column('last_requested_at', sa.DateTime(), nullable=False),
        sa.Column('processed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('title', sa.String(length=512), nullable=True),
        sa.Column('authors', sa.Text(), nullable=True),
        sa.Column('num_pages', sa.Integer(), nullable=True),
    )


