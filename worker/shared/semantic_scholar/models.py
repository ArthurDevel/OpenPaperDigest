"""
Data models for Semantic Scholar API responses.

Responsibilities:
- Define S2Author with Semantic Scholar author stats
- Define S2PaperAuthors linking arxiv papers to their S2 author IDs
- Define S2PaperMetadata with comprehensive paper metadata (IDs, metrics, venue, etc.)
- Define S2PaperReference for citation graph edges (source -> cited)
- Define supporting dataclasses: S2FieldOfStudy, S2PublicationVenue, S2Journal, S2OpenAccessPdf
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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


@dataclass
class S2PaperReference:
    """A single citation edge: source paper references cited paper."""
    source_s2_id: str
    cited_s2_id: str
    is_influential: Optional[bool] = None


# ============================================================================
# PAPER METADATA MODELS
# ============================================================================


@dataclass
class S2FieldOfStudy:
    """A field of study classification from S2."""
    category: str
    source: str


@dataclass
class S2PublicationVenue:
    """Publication venue metadata from S2."""
    id: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    alternate_names: Optional[List[str]] = None
    url: Optional[str] = None


@dataclass
class S2Journal:
    """Journal metadata from S2."""
    name: Optional[str] = None
    volume: Optional[str] = None
    pages: Optional[str] = None


@dataclass
class S2OpenAccessPdf:
    """Open access PDF info from S2."""
    url: Optional[str] = None
    status: Optional[str] = None


@dataclass
class S2PaperMetadata:
    """Comprehensive paper metadata from S2, used for enrichment."""
    paper_id: str
    arxiv_id: Optional[str] = None
    corpus_id: Optional[int] = None
    external_ids: Optional[Dict[str, Any]] = None
    citation_count: Optional[int] = None
    reference_count: Optional[int] = None
    influential_citation_count: Optional[int] = None
    s2_fields_of_study: Optional[List[S2FieldOfStudy]] = None
    publication_types: Optional[List[str]] = None
    venue: Optional[str] = None
    publication_venue: Optional[S2PublicationVenue] = None
    journal: Optional[S2Journal] = None
    year: Optional[int] = None
    publication_date: Optional[str] = None
    tldr: Optional[str] = None
    is_open_access: Optional[bool] = None
    open_access_pdf: Optional[S2OpenAccessPdf] = None
    embedding: Optional[List[float]] = None

    def to_s2_ids_dict(self) -> Dict[str, Any]:
        """
        Build the s2_ids JSONB dict. Maps S2 identifiers to lowercase keys.
        Omits keys with no value.

        @returns Dict with s2_paper_id, s2_corpus_id, doi, pmid, pmcid, dblp, mag, acl
        """
        result = {}

        if self.paper_id:
            result['s2_paper_id'] = self.paper_id
        if self.corpus_id is not None:
            result['s2_corpus_id'] = self.corpus_id

        # Map PascalCase external_ids keys to lowercase JSONB keys
        if self.external_ids:
            key_mapping = {
                'DOI': 'doi',
                'PMID': 'pmid',
                'PMCID': 'pmcid',
                'DBLP': 'dblp',
                'MAG': 'mag',
                'ACL': 'acl',
            }
            for s2_key, json_key in key_mapping.items():
                value = self.external_ids.get(s2_key)
                if value is not None:
                    result[json_key] = value

        return result

    def to_s2_metrics_dict(self) -> Dict[str, Any]:
        """
        Build the s2_metrics JSONB dict from citation/reference counts.
        Omits keys with no value.

        @returns Dict with citation_count, reference_count, influential_citation_count
        """
        result = {}

        if self.citation_count is not None:
            result['citation_count'] = self.citation_count
        if self.reference_count is not None:
            result['reference_count'] = self.reference_count
        if self.influential_citation_count is not None:
            result['influential_citation_count'] = self.influential_citation_count

        return result

    def to_publication_info_dict(self) -> Dict[str, Any]:
        """
        Build the publication_info JSONB dict from venue, journal, dates, open access.
        Omits keys with no value. Nested dataclasses are converted to dicts (also omitting None).

        @returns Dict with venue, publication_venue, journal, year, publication_date, is_open_access, open_access_pdf
        """
        result = {}

        if self.venue:
            result['venue'] = self.venue

        if self.publication_venue:
            venue_dict = {k: v for k, v in {
                'id': self.publication_venue.id,
                'name': self.publication_venue.name,
                'type': self.publication_venue.type,
                'alternate_names': self.publication_venue.alternate_names,
                'url': self.publication_venue.url,
            }.items() if v is not None}
            if venue_dict:
                result['publication_venue'] = venue_dict

        if self.journal:
            journal_dict = {k: v for k, v in {
                'name': self.journal.name,
                'volume': self.journal.volume,
                'pages': self.journal.pages,
            }.items() if v is not None}
            if journal_dict:
                result['journal'] = journal_dict

        if self.year is not None:
            result['year'] = self.year
        if self.publication_date is not None:
            result['publication_date'] = self.publication_date
        if self.is_open_access is not None:
            result['is_open_access'] = self.is_open_access

        if self.open_access_pdf:
            oa_dict = {k: v for k, v in {
                'url': self.open_access_pdf.url,
                'status': self.open_access_pdf.status,
            }.items() if v is not None}
            if oa_dict:
                result['open_access_pdf'] = oa_dict

        return result
