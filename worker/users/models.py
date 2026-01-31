from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String, UniqueConstraint, Boolean

from shared.db import Base


class UserRow(Base):
    __tablename__ = "users"

    # Use the auth provider's user id as our primary key (string)
    id = Column(String(128), primary_key=True)
    email = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class UserListRow(Base):
    __tablename__ = "user_lists"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    paper_id = Column(BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "paper_id", name="uq_user_lists_user_paper"),
        Index("ix_user_lists_user_id", "user_id"),
        Index("ix_user_lists_paper_id", "paper_id"),
    )



class UserRequestRow(Base):
    __tablename__ = "user_requests"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    arxiv_id = Column(String(64), nullable=False)
    title = Column(String(512), nullable=True)
    authors = Column(String(2048), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    # Mark true when a paper for this arXiv id is fully processed and a slug exists
    is_processed = Column(Boolean, nullable=False, default=False)
    processed_slug = Column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "arxiv_id", name="uq_user_requests_user_arxiv"),
        Index("ix_user_requests_user_id", "user_id"),
        Index("ix_user_requests_arxiv_id", "arxiv_id"),
        Index("ix_user_requests_is_processed", "is_processed"),
    )
