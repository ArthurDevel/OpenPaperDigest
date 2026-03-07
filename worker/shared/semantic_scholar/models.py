"""
Data models for Semantic Scholar API responses.

Responsibilities:
- Define S2Author with Semantic Scholar author stats
- Define S2PaperAuthors linking arxiv papers to their S2 author IDs
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class S2Author:
    """A single author with Semantic Scholar metadata."""
    s2_author_id: str
    name: str
    affiliations: Optional[List[str]] = None
    homepage: Optional[str] = None
    paper_count: Optional[int] = None
    citation_count: Optional[int] = None
    h_index: Optional[int] = None


@dataclass
class S2PaperAuthors:
    """Authors for a single paper, as returned by Semantic Scholar."""
    s2_paper_id: str
    arxiv_id: Optional[str] = None
    authors: List[S2Author] = field(default_factory=list)
