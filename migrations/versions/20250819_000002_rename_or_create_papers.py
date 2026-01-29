from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250819_000002'
down_revision = '20250819_000001'
branch_labels = None
depends_on = None


def _table_exists(bind, name: str) -> bool:
    res = bind.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = :name"),
        {"name": name}
    ).fetchone()
    return res is not None


def upgrade() -> None:
    bind = op.get_bind()
    has_paper_jobs = _table_exists(bind, 'paper_jobs')
    has_papers = _table_exists(bind, 'papers')

    if has_paper_jobs and not has_papers:
        # Rename table and indexes
        op.execute("ALTER TABLE paper_jobs RENAME TO papers")
        # Rename composite status index if it exists
        try:
            op.execute("ALTER INDEX ix_paper_jobs_status_created RENAME TO ix_papers_status_created")
        except Exception:
            pass
        # Rename unique index on paper_uuid if it exists
        try:
            op.execute("ALTER INDEX uq_paper_jobs_paper_uuid RENAME TO uq_papers_paper_uuid")
        except Exception:
            pass
        return

    if not has_papers:
        # Create fresh papers table if neither exists
        op.create_table(
            'papers',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('paper_uuid', sa.String(length=36), nullable=False),
            sa.Column('arxiv_id', sa.String(length=64), nullable=False),
            sa.Column('arxiv_version', sa.String(length=10), nullable=True),
            sa.Column('arxiv_url', sa.String(length=255), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('finished_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('paper_uuid', name='uq_papers_paper_uuid'),
        )
        op.create_index('ix_papers_status_created', 'papers', ['status', 'created_at'])


def downgrade() -> None:
    bind = op.get_bind()
    has_papers = _table_exists(bind, 'papers')
    if has_papers:
        # Prefer rename back if original name existed before
        try:
            op.execute("ALTER INDEX ix_papers_status_created RENAME TO ix_paper_jobs_status_created")
        except Exception:
            pass
        try:
            op.execute("ALTER INDEX uq_papers_paper_uuid RENAME TO uq_paper_jobs_paper_uuid")
        except Exception:
            pass
        try:
            op.execute("ALTER TABLE papers RENAME TO paper_jobs")
            return
        except Exception:
            # If rename fails, drop instead
            pass
    try:
        op.drop_index('ix_papers_status_created', table_name='papers')
    except Exception:
        pass
    try:
        op.drop_table('papers')
    except Exception:
        pass


