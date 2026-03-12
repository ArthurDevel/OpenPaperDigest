from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional, Dict, Any, Union

from pydantic import BaseModel, Field, field_validator


class Page(BaseModel):
    """Simple page model for papers."""
    page_number: int
    img_base64: str


class Section(BaseModel):
    """Simple section model for papers."""
    order_index: int
    rewritten_content: str
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    level: Optional[int] = None
    section_title: Optional[str] = None
    summary: Optional[str] = None
    subsections: List["Section"] = Field(default_factory=list)


class PaperSlug(BaseModel):
    """Paper slug DTO with automatic ORM conversion."""
    slug: str
    paper_uuid: Optional[str] = None
    created_at: Optional[datetime] = None
    tombstone: bool = False
    deleted_at: Optional[datetime] = None
    
    def to_orm(self):
        """Convert PaperSlug DTO to SQLAlchemy PaperSlugRecord."""
        from papers.db.models import PaperSlugRecord
        return PaperSlugRecord(
            slug=self.slug,
            paper_uuid=self.paper_uuid,
            created_at=self.created_at or datetime.utcnow(),
            tombstone=self.tombstone,
            deleted_at=self.deleted_at
        )
    
    class Config:
        from_attributes = True


class Paper(BaseModel):
    """
    Complete Paper DTO containing both metadata and full processing results.

    Automatically converts from SQLAlchemy PaperRecord using model_validate().
    For metadata-only operations, content fields (pages, sections) will be empty.
    For full paper operations, all fields are populated from database + JSON.
    """
    # Database metadata fields
    paper_uuid: str
    arxiv_id: Optional[str] = None
    title: Optional[str] = None
    authors: Optional[str] = None
    status: str = "not_started"
    arxiv_version: Optional[str] = None
    arxiv_url: Optional[str] = None
    error_message: Optional[str] = None
    initiated_by_user_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    num_pages: Optional[int] = None
    processing_time_seconds: Optional[float] = None
    total_cost: Optional[float] = None
    avg_cost_per_page: Optional[float] = None
    thumbnail_url: Optional[str] = None
    content_hash: Optional[str] = None
    pdf_url: Optional[str] = None

    # Full processing content fields (loaded from JSON when needed)
    pages: List[Page] = Field(default_factory=list)
    sections: List[Section] = Field(default_factory=list)

    # Pre-computed scoring signals (e.g. {"max_author_h_index": 42, "hf_upvotes": 10})
    signals: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('signals', mode='before')
    @classmethod
    def _deserialize_signals(cls, value: Union[str, Dict, None]) -> Dict[str, Any]:
        """Handle JSON string deserialization from database."""
        if value is None:
            return {}
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError, TypeError):
                return {}
        if isinstance(value, dict):
            return value
        return {}

    def to_orm(self):
        """Convert Paper DTO to SQLAlchemy PaperRecord."""
        from papers.db.models import PaperRecord

        return PaperRecord(
            paper_uuid=self.paper_uuid,
            arxiv_id=self.arxiv_id,
            title=self.title,
            authors=self.authors,
            status=self.status,
            arxiv_version=self.arxiv_version,
            arxiv_url=self.arxiv_url,
            error_message=self.error_message,
            initiated_by_user_id=self.initiated_by_user_id,
            created_at=self.created_at or datetime.utcnow(),
            updated_at=self.updated_at or datetime.utcnow(),
            started_at=self.started_at,
            finished_at=self.finished_at,
            num_pages=self.num_pages,
            processing_time_seconds=self.processing_time_seconds,
            total_cost=self.total_cost,
            avg_cost_per_page=self.avg_cost_per_page,
            signals=self.signals,
            content_hash=self.content_hash,
            pdf_url=self.pdf_url,
        )
    
    class Config:
        from_attributes = True



