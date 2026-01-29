from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250819_000005'
down_revision = '20250819_000004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure no duplicates before adding constraint (best-effort: keep earliest)
    conn = op.get_bind()
    # Delete newer duplicates by arxiv_id, keeping min(id)
    conn.execute(sa.text(
        """
        DELETE FROM papers
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM papers
            GROUP BY arxiv_id
        )
        """
    ))
    # Add unique constraint
    try:
        op.create_unique_constraint('uq_papers_arxiv_id', 'papers', ['arxiv_id'])
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_constraint('uq_papers_arxiv_id', 'papers', type_='unique')
    except Exception:
        pass


