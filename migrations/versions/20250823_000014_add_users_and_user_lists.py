from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250823_000014'
down_revision = '20250822_000013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users table: auth provider id as PK
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=128), primary_key=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # user_lists table
    op.create_table(
        'user_lists',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.String(length=128), nullable=False),
        sa.Column('paper_id', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_user_lists_user', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], name='fk_user_lists_paper', ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'paper_id', name='uq_user_lists_user_paper'),
    )

    op.create_index('ix_user_lists_user_id', 'user_lists', ['user_id'])
    op.create_index('ix_user_lists_paper_id', 'user_lists', ['paper_id'])


def downgrade() -> None:
    op.drop_index('ix_user_lists_paper_id', table_name='user_lists')
    op.drop_index('ix_user_lists_user_id', table_name='user_lists')
    op.drop_table('user_lists')
    op.drop_table('users')


