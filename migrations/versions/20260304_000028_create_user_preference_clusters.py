from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260304_000028'
down_revision = '20260304_000027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create user_preference_clusters table for storing per-user interest clusters.

    - Each user has 1-5 clusters, each with a 1536-dim embedding centroid.
    - weight and interaction_count track cluster strength.
    - RLS policy restricts users to their own rows.
    """
    connection = op.get_bind()

    # Create user_preference_clusters table
    connection.execute(sa.text("""
        CREATE TABLE user_preference_clusters (
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            cluster_index SMALLINT NOT NULL,
            embedding vector(1536) NOT NULL,
            weight FLOAT NOT NULL DEFAULT 1.0,
            interaction_count INT NOT NULL DEFAULT 1,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, cluster_index)
        )
    """))

    # Create index on user_id for efficient lookups
    connection.execute(sa.text(
        "CREATE INDEX ix_user_pref_clusters_user_id ON user_preference_clusters (user_id)"
    ))

    # Enable RLS and create policy
    connection.execute(sa.text(
        "ALTER TABLE user_preference_clusters ENABLE ROW LEVEL SECURITY"
    ))
    connection.execute(sa.text("""
        CREATE POLICY user_pref_clusters_self ON user_preference_clusters
            FOR ALL TO authenticated
            USING (auth.uid()::text = user_id)
            WITH CHECK (auth.uid()::text = user_id)
    """))


def downgrade() -> None:
    """
    Drop user_preference_clusters table and its indexes/policies.
    """
    connection = op.get_bind()
    connection.execute(sa.text("DROP TABLE IF EXISTS user_preference_clusters CASCADE"))
