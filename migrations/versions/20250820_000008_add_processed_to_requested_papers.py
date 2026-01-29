from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250820_000008'
down_revision = '20250820_000007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('requested_papers') as batch_op:
        batch_op.add_column(sa.Column('processed', sa.Boolean(), nullable=False, server_default=sa.false()))
        # Drop server_default after set
    op.execute("UPDATE requested_papers SET processed = FALSE WHERE processed IS NULL")
    with op.batch_alter_table('requested_papers') as batch_op:
        batch_op.alter_column('processed', server_default=None)


def downgrade() -> None:
    with op.batch_alter_table('requested_papers') as batch_op:
        batch_op.drop_column('processed')



