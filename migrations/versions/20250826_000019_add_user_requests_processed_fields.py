"""add processed fields to user_requests

Revision ID: 20250826_000019
Revises: 20250824_000018
Create Date: 2025-08-26 00:00:19.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20250826_000019'
down_revision: Union[str, None] = '20250824_000018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_requests', sa.Column('is_processed', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('user_requests', sa.Column('processed_slug', sa.String(length=255), nullable=True))
    op.create_index('ix_user_requests_is_processed', 'user_requests', ['is_processed'])
    # Clean up server_default so future inserts rely on ORM default
    with op.batch_alter_table('user_requests') as batch_op:
        batch_op.alter_column('is_processed', server_default=None)


def downgrade() -> None:
    op.drop_index('ix_user_requests_is_processed', table_name='user_requests')
    op.drop_column('user_requests', 'processed_slug')
    op.drop_column('user_requests', 'is_processed')


