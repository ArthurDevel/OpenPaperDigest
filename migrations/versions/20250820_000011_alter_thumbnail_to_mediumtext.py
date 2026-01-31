from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250820_000011'
down_revision = '20250820_000010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL TEXT has no size limit, so this is a no-op on PostgreSQL
    # Keeping for migration history consistency
    pass


def downgrade() -> None:
    # No-op on PostgreSQL
    pass


