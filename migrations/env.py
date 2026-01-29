from logging.config import fileConfig
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, MetaData
from sqlalchemy import pool
from dotenv import load_dotenv

from alembic import context

# Add worker directory to path for model imports
worker_path = Path(__file__).parent.parent / "worker"
sys.path.insert(0, str(worker_path))

# Load environment from worker/.env
env_path = worker_path / ".env"
load_dotenv(env_path)

# Import Base and models for autogenerate
from shared.db import Base
# Import all models so they register with Base.metadata
from papers.db.models import PaperRecord, PaperSlugRecord, PaperStatusHistory

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def get_database_url() -> str:
    """Get DATABASE_URL and ensure it has the correct SQLAlchemy driver prefix."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL environment variable is required")
    # SQLAlchemy needs postgresql+psycopg2://, but Prisma uses postgresql://
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(
        get_database_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online() 