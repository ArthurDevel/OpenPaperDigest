from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250820_000012'
down_revision = '20250820_000011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'paper_slugs',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('slug', sa.String(length=255), nullable=False, unique=True),
        sa.Column('paper_uuid', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('tombstone', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('paper_slugs')


