from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from shared.config import settings

# SQLAlchemy base for ORM models
Base = declarative_base()


def _get_database_url() -> str:
    """Get DATABASE_URL and ensure it has the correct SQLAlchemy driver prefix."""
    url = settings.DATABASE_URL
    # SQLAlchemy needs postgresql+psycopg2://, but Prisma uses postgresql://
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


# Global engine and session factory
engine = create_engine(
    _get_database_url(),
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


