from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# --- Vector search payload for arXiv papers (domain-specific) ---

class ArxivPaperVectorPayload(BaseModel):
    paper_uuid: str
    arxiv_id: str
    slug: Optional[str] = None
    title: Optional[str] = None
    # Preferred: list of author names
    authors_json: Optional[List[str]] = None
    # Optional denormalized string (legacy); avoid using in new code
    categories: Optional[List[str]] = None
    published_at: Optional[str] = None
    updated_at: Optional[str] = None
    published_at_ts: Optional[int] = None
    updated_at_ts: Optional[int] = None
    embedding_model: Optional[str] = None
    embedding_dimensions: Optional[int] = None
    abstract_excerpt: Optional[str] = None
    # Additional commonly used fields in search UI
    abs_url: Optional[str] = None
    summary: Optional[str] = None
    has_thumbnail: Optional[bool] = None
    extra: Optional[dict] = None


class ParsedArxivUrl(BaseModel):
    """Result of parsing a user-provided arXiv URL or identifier."""

    uuid: UUID = Field(default_factory=uuid4)
    raw: str
    arxiv_id: str
    version: Optional[str] = None  # e.g., "v2"
    url_type: Literal["abs", "pdf", "id"]


class NormalizedArxivId(BaseModel):
    """Canonicalized arXiv identifier with optional version."""

    uuid: UUID = Field(default_factory=uuid4)
    arxiv_id: str
    version: Optional[str] = None  # e.g., "v2"


class ArxivAuthor(BaseModel):
    name: str
    affiliation: Optional[str] = None


class ArxivVersion(BaseModel):
    version: str  # e.g., "v1"
    updated_at: Optional[datetime] = None


class ArxivMetadata(BaseModel):
    """Subset of arXiv Atom metadata sufficient for our pipeline."""

    uuid: UUID = Field(default_factory=uuid4)
    arxiv_id: str
    latest_version: Optional[str] = None
    title: str
    authors: List[ArxivAuthor] = Field(default_factory=list)
    summary: str
    categories: List[str] = Field(default_factory=list)
    doi: Optional[str] = None
    journal_ref: Optional[str] = None
    submitted_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    all_versions: List[ArxivVersion] = Field(default_factory=list)


class ArxivPdfHead(BaseModel):
    url: str
    filename: Optional[str] = None
    content_type: Optional[str] = None
    content_length: Optional[int] = None


class ArxivPdfResult(BaseModel):
    url: str
    filename: str
    content_type: str
    content_length: Optional[int] = None
    pdf_bytes: bytes


class ArxivPdfForProcessing(BaseModel):
    pdf_bytes: bytes
    filename: str
    metadata: Optional[ArxivMetadata] = None


