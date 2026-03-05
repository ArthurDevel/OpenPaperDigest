from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260304_000027'
down_revision = '20260304_000026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create user_interactions table for tracking expand/read/save signals.

    - Stores interactions for all users (anonymous and authenticated via Supabase Auth).
    - Indexes on user_id and (user_id, paper_uuid) for efficient lookups.
    - RLS policy restricts users to their own rows.
    """
    connection = op.get_bind()

    # Create user_interactions table
    connection.execute(sa.text("""
        CREATE TABLE user_interactions (
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            paper_uuid TEXT NOT NULL,
            interaction_type TEXT NOT NULL,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))

    # Create indexes
    connection.execute(sa.text(
        "CREATE INDEX ix_user_interactions_user_id ON user_interactions (user_id)"
    ))
    connection.execute(sa.text(
        "CREATE INDEX ix_user_interactions_user_paper ON user_interactions (user_id, paper_uuid)"
    ))

    # Enable RLS and create policy
    connection.execute(sa.text(
        "ALTER TABLE user_interactions ENABLE ROW LEVEL SECURITY"
    ))
    connection.execute(sa.text("""
        CREATE POLICY user_interactions_self ON user_interactions
            FOR ALL TO authenticated
            USING (auth.uid()::text = user_id)
            WITH CHECK (auth.uid()::text = user_id)
    """))


def downgrade() -> None:
    """
    Drop user_interactions table and its indexes/policies.
    """
    connection = op.get_bind()
    connection.execute(sa.text("DROP TABLE IF EXISTS user_interactions CASCADE"))
