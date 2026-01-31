from dataclasses import dataclass, field
from typing import List, Optional
import uuid

from shared.openrouter.models import ApiCallCost


@dataclass
class ProcessedImage:
    img_base64: str            # base64 string of the image
    page_number: int           # on which page it occurs
    top_left_x: int            # bounding box top-left x coordinate
    top_left_y: int            # bounding box top-left y coordinate
    bottom_right_x: int        # bounding box bottom-right x coordinate
    bottom_right_y: int        # bounding box bottom-right y coordinate
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))  # uuid4 field, used to reference the image
    short_id: Optional[str] = None  # 8-character Base36 ID for markdown references


@dataclass
class Header:
    text: str                  # header text
    level: int                 # header level (1, 2, 3, etc.)
    page_number: int           # which page it appears on
    element_type: str          # type of header (document_section, document_subsection, etc.)
    markdown_line_number: Optional[int] = None  # which line in the OCR markdown (0-based)


@dataclass
class ProcessedPage:
    page_number: int
    img_base64: str             # Base64 encoded page image, max width 1080px
    width: int                  # Page image width in pixels
    height: int                 # Page image height in pixels
    ocr_markdown: Optional[str] = None      # Raw OCR markdown
    structured_markdown: Optional[str] = None    # With << tags >>
    images: List[ProcessedImage] = field(default_factory=list)     # Images on this page


@dataclass
class ApiCallCostForStep:
    """Application-level wrapper that adds step context to pure cost info."""
    step_name: str
    model: str                        # Model used for this step
    cost_info: ApiCallCost


@dataclass
class ProcessedDocument:
    pdf_base64: str            # base64 encoded version of the pdf
    paper_uuid: Optional[str] = None    # If set, overwrite existing paper
    arxiv_id: Optional[str] = None      # ArXiv ID for duplicate checking
    title: Optional[str] = None
    authors: Optional[str] = None
    pages: List[ProcessedPage] = field(default_factory=list)
    headers: List[Header] = field(default_factory=list)       # Document headers
    final_markdown: Optional[str] = None    # Fully processed output
    # Rewriting structure
    # Sections are derived from final_markdown with <<section>> tags
    # and hold rewritten content in a simple flat list in document order
    # Section class is defined below
    sections: List["Section"] = field(default_factory=list)
    rewritten_final_markdown: Optional[str] = None
    # Summary generation
    five_minute_summary: Optional[str] = None    # Accessible 5-minute summary
    # Cost tracking
    step_costs: List[ApiCallCostForStep] = field(default_factory=list)


@dataclass
class Section:
    """
    Represents a document section detected from tagged markdown.

    order_index: Position in document order starting at 0
    original_content: Original markdown content for this section (between tags)
    rewritten_content: Rewritten markdown content for this section
    start_page: First page number where this section appears (only set if header found)
    end_page: Last page number where this section appears (only set if header found)
    level: Header level (1, 2, 3, etc.) (only set if header found)
    section_title: Title text of the section header (only set if header found)
    """
    order_index: int
    original_content: str
    rewritten_content: Optional[str] = None
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    level: Optional[int] = None
    section_title: Optional[str] = None
 