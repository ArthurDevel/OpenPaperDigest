from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal, Union

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


class ExternalPopularitySignal(BaseModel):
    """External popularity metrics from various sources. This will be used in ranking papers."""
    source: Literal["HuggingFace", "HuggingFaceTrending", "AlphaXiv", "GoogleResearch", "MicrosoftResearch", "DeepMindResearch", "NvidiaResearch"]  # Expandable to more sources
    values: Dict[str, Any]  # Flexible values per source
    fetch_info: Dict[str, Any]  # Refetch metadata per source
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        from_attributes = True


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


# ============================================================================
# ARXIV DISCOVERY MODELS
# ============================================================================

class ArxivPaperAuthor(BaseModel):
    """
    Single author with optional Semantic Scholar ID.

    Attributes:
        name: Author's full name as it appears on the paper.
        semantic_scholar_id: S2 author ID, or None if not found in S2.
    """
    name: str
    semantic_scholar_id: Optional[str] = None


class ArxivDiscoveredPaper(BaseModel):
    """
    Discovered arXiv paper DTO with metadata, authors, and credibility scores.

    Automatically converts from SQLAlchemy ArxivPaperRecord using model_validate().
    Use to_orm() to convert back to database model.

    Required fields:
        arxiv_id: ArXiv identifier without version (e.g., "2312.00752").
        title: Paper title.

    Optional fields (nullable in DB):
        version: ArXiv version number (e.g., 1, 2, 3).
        abstract: Paper abstract text.
        published_at: Publication timestamp from arXiv.
        primary_category: Primary arXiv category (e.g., "cs.LG").
        categories: All arXiv categories the paper belongs to.
        authors: List of authors with optional S2 IDs.
        semantic_scholar_id: S2 paper ID (40-char hex string).
        citation_count: Number of citations from S2.
        influential_citation_count: Influential citations from S2.
        embedding_model: Name of embedding model (e.g., "specter_v1").
        embedding_vector: 768-dimensional embedding as float list.
        avg_author_h_index: Average h-index across authors with S2 profiles (unknowns excluded).
        avg_author_citations_per_paper: Average citations per paper across authors with S2 profiles.
        total_author_h_index: Sum of h-indices for authors with S2 profiles.
    """
    arxiv_id: str
    title: str
    version: Optional[int] = None
    abstract: Optional[str] = None
    published_at: Optional[datetime] = None
    primary_category: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    authors: List[ArxivPaperAuthor] = Field(default_factory=list)
    semantic_scholar_id: Optional[str] = None
    citation_count: Optional[int] = None
    influential_citation_count: Optional[int] = None
    embedding_model: Optional[str] = None
    embedding_vector: Optional[List[float]] = None
    avg_author_h_index: Optional[float] = None
    avg_author_citations_per_paper: Optional[float] = None
    total_author_h_index: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator('categories', mode='before')
    @classmethod
    def _deserialize_categories(cls, value: Union[str, List, None]) -> List[str]:
        """Handle JSON string deserialization from database."""
        if value is None:
            return []
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError, TypeError):
                return []
        return value or []

    @field_validator('authors', mode='before')
    @classmethod
    def _deserialize_authors(cls, value: Union[str, List, None]) -> List[ArxivPaperAuthor]:
        """Handle JSON string deserialization from database."""
        if value is None:
            return []
        if isinstance(value, str):
            try:
                authors_data = json.loads(value)
                return [ArxivPaperAuthor.model_validate(a) for a in authors_data]
            except (json.JSONDecodeError, ValueError, TypeError):
                return []
        if isinstance(value, list):
            return [
                ArxivPaperAuthor.model_validate(a) if not isinstance(a, ArxivPaperAuthor) else a
                for a in value
            ]
        return []

    @field_validator('embedding_vector', mode='before')
    @classmethod
    def _deserialize_embedding_vector(cls, value: Union[str, List, None]) -> Optional[List[float]]:
        """Handle JSON string deserialization from database."""
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError, TypeError):
                return None
        return value

    def to_orm(self):
        """Convert ArxivDiscoveredPaper DTO to SQLAlchemy ArxivPaperRecord."""
        from papers.db.models import ArxivPaperRecord

        # Serialize authors to JSON
        authors_json = None
        if self.authors:
            authors_json = json.dumps(
                [author.model_dump() for author in self.authors],
                default=str
            )

        # Serialize categories to JSON
        categories_json = None
        if self.categories:
            categories_json = json.dumps(self.categories)

        # Serialize embedding vector to JSON
        embedding_json = None
        if self.embedding_vector:
            embedding_json = json.dumps(self.embedding_vector)

        return ArxivPaperRecord(
            arxiv_id=self.arxiv_id,
            version=self.version,
            title=self.title,
            abstract=self.abstract,
            published_at=self.published_at,
            primary_category=self.primary_category,
            categories=categories_json,
            authors=authors_json,
            semantic_scholar_id=self.semantic_scholar_id,
            citation_count=self.citation_count,
            influential_citation_count=self.influential_citation_count,
            embedding_model=self.embedding_model,
            embedding_vector=embedding_json,
            avg_author_h_index=self.avg_author_h_index,
            avg_author_citations_per_paper=self.avg_author_citations_per_paper,
            total_author_h_index=self.total_author_h_index,
            created_at=self.created_at or datetime.utcnow(),
            updated_at=self.updated_at or datetime.utcnow(),
        )

    class Config:
        from_attributes = True


class ArxivPaperFilter(BaseModel):
    """
    Filter options for listing arXiv papers.

    Attributes:
        min_avg_h_index: Only return papers where avg_author_h_index >= this value.
        primary_category: Only return papers with this primary category.
        published_after: Only return papers published after this datetime.
        limit: Maximum number of papers to return (default 100).
        offset: Number of papers to skip for pagination (default 0).
    """
    min_avg_h_index: Optional[float] = None
    primary_category: Optional[str] = None
    published_after: Optional[datetime] = None
    limit: int = 100
    offset: int = 0


# ============================================================================
# PAPER PROCESSING MODELS
# ============================================================================

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
    thumbnail_data_url: Optional[str] = None
    content_hash: Optional[str] = None
    pdf_url: Optional[str] = None

    # Full processing content fields (loaded from JSON when needed)
    pages: List[Page] = Field(default_factory=list)
    sections: List[Section] = Field(default_factory=list)

    # External popularity signals from various platforms
    external_popularity_signals: List[ExternalPopularitySignal] = Field(default_factory=list)
    
    @field_validator('external_popularity_signals', mode='before')
    @classmethod
    def _deserialize_external_popularity_signals(cls, value: Union[str, List, None]) -> List[ExternalPopularitySignal]:
        """Handle JSON string deserialization from database."""
        if value is None:
            return []
        
        if isinstance(value, str):
            try:
                # Parse JSON string from database
                signals_data = json.loads(value)
                return [ExternalPopularitySignal.model_validate(signal_data) for signal_data in signals_data]
            except (json.JSONDecodeError, ValueError, TypeError):
                return []
        
        if isinstance(value, list):
            # Already a list - validate each item
            return [
                ExternalPopularitySignal.model_validate(signal) if not isinstance(signal, ExternalPopularitySignal) else signal 
                for signal in value
            ]
        
        return []
    
    def to_orm(self):
        """Convert Paper DTO to SQLAlchemy PaperRecord."""
        from papers.db.models import PaperRecord

        # Serialize external popularity signals to JSON
        signals_json = None
        if self.external_popularity_signals:
            signals_json = json.dumps(
                [signal.model_dump() for signal in self.external_popularity_signals],
                default=str  # Convert datetime objects to strings
            )

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
            thumbnail_data_url=self.thumbnail_data_url,
            external_popularity_signals=signals_json,
            content_hash=self.content_hash,
            pdf_url=self.pdf_url,
        )
    
    class Config:
        from_attributes = True



