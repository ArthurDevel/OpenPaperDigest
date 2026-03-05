"""
Supabase Storage client wrapper for paper assets.

Handles uploading, downloading, and deleting paper files (thumbnails, markdown,
sections, figures, metadata) in a private Supabase Storage bucket.

Responsibilities:
- Upload all paper assets after processing (thumbnail, markdown, sections, figures, metadata)
- Download paper content for reading (markdown, sections, figures metadata, metadata)
- Generate signed URLs for thumbnails and figures (private bucket)
- Delete all assets for a paper
- Lazy-initialize the Supabase client from config

NOTE: The "papers" bucket must be created manually in the Supabase dashboard.
      It should be private with no file size restrictions beyond plan limits.
"""

import json
from dataclasses import dataclass
from typing import Dict, List, Optional

from supabase import create_client, Client

from shared.config import settings


# ============================================================================
# CONSTANTS
# ============================================================================

BUCKET_NAME = "papers"
SIGNED_URL_EXPIRY_SECONDS = 3600


# ============================================================================
# TYPES
# ============================================================================

@dataclass
class StoredPaperContent:
    """Content downloaded from storage for a single paper."""

    final_markdown: str
    sections: List[Dict]
    figures: List[Dict]
    metadata: dict


# ============================================================================
# CLIENT INITIALIZATION
# ============================================================================

_client: Optional[Client] = None


def _get_client() -> Client:
    """Return the lazily-initialized Supabase client.

    Returns:
        Supabase client instance configured with service key.

    Raises:
        RuntimeError: If SUPABASE_URL or SUPABASE_SERVICE_KEY are not set.
    """
    global _client
    if _client is None:
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment"
            )
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    return _client


def _bucket():
    """Return the storage bucket handle.

    Returns:
        Supabase storage bucket reference for the papers bucket.
    """
    return _get_client().storage.from_(BUCKET_NAME)


# ============================================================================
# MAIN FUNCTIONS
# ============================================================================

def upload_paper_assets(
    paper_uuid: str,
    thumbnail_bytes: bytes,
    final_markdown: str,
    sections: List[Dict],
    figures: List[Dict],
    metadata: dict,
) -> None:
    """Upload all processed paper assets to Supabase Storage.

    Uploads the following files under {paper_uuid}/:
      - thumbnail.png (raw PNG bytes)
      - content.md (final markdown text)
      - sections.json (rewritten sections array)
      - figures.json (figure metadata WITHOUT image_bytes)
      - metadata.json (usage summary, processing stats)
      - figures/{identifier}.png for each figure with image_bytes

    Args:
        paper_uuid: Unique identifier for the paper.
        thumbnail_bytes: Raw PNG bytes for the thumbnail (NOT base64).
        final_markdown: The OCR/processed markdown content.
        sections: List of section dicts (rewritten content).
        figures: List of figure dicts, each with at least "identifier" (str)
                 and "image_bytes" (bytes). Additional metadata keys are preserved
                 in figures.json without the image_bytes field.
        metadata: Dict of usage summary, processing stats, cost info.
    """
    bucket = _bucket()
    prefix = paper_uuid

    # Upload thumbnail
    bucket.upload(
        f"{prefix}/thumbnail.png",
        thumbnail_bytes,
        {"content-type": "image/png", "upsert": "true"},
    )

    # Upload markdown content
    bucket.upload(
        f"{prefix}/content.md",
        final_markdown.encode("utf-8"),
        {"content-type": "text/markdown", "upsert": "true"},
    )

    # Upload sections JSON
    bucket.upload(
        f"{prefix}/sections.json",
        json.dumps(sections, ensure_ascii=False).encode("utf-8"),
        {"content-type": "application/json", "upsert": "true"},
    )

    # Build figures metadata (strip image_bytes from each figure)
    figures_metadata = []
    for fig in figures:
        fig_meta = {k: v for k, v in fig.items() if k != "image_bytes"}
        figures_metadata.append(fig_meta)

    # Upload figures metadata JSON
    bucket.upload(
        f"{prefix}/figures.json",
        json.dumps(figures_metadata, ensure_ascii=False).encode("utf-8"),
        {"content-type": "application/json", "upsert": "true"},
    )

    # Upload metadata JSON
    bucket.upload(
        f"{prefix}/metadata.json",
        json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
        {"content-type": "application/json", "upsert": "true"},
    )

    # Upload each figure image
    for fig in figures:
        identifier = fig["identifier"]
        image_bytes = fig["image_bytes"]
        bucket.upload(
            f"{prefix}/figures/{identifier}.png",
            image_bytes,
            {"content-type": "image/png", "upsert": "true"},
        )


def download_paper_content(paper_uuid: str) -> StoredPaperContent:
    """Download all text/JSON content for a paper from storage.

    Downloads content.md, sections.json, figures.json, and metadata.json.
    Does NOT download figure images (those are served by public URL).

    Args:
        paper_uuid: Unique identifier for the paper.

    Returns:
        StoredPaperContent with all text content fields populated.
    """
    bucket = _bucket()
    prefix = paper_uuid

    markdown_bytes = bucket.download(f"{prefix}/content.md")
    sections_bytes = bucket.download(f"{prefix}/sections.json")
    figures_bytes = bucket.download(f"{prefix}/figures.json")
    metadata_bytes = bucket.download(f"{prefix}/metadata.json")

    return StoredPaperContent(
        final_markdown=markdown_bytes.decode("utf-8"),
        sections=json.loads(sections_bytes.decode("utf-8")),
        figures=json.loads(figures_bytes.decode("utf-8")),
        metadata=json.loads(metadata_bytes.decode("utf-8")),
    )


def download_markdown(paper_uuid: str) -> str:
    """Download only the markdown content for a paper.

    Args:
        paper_uuid: Unique identifier for the paper.

    Returns:
        The raw markdown string from content.md.
    """
    bucket = _bucket()
    markdown_bytes = bucket.download(f"{paper_uuid}/content.md")
    return markdown_bytes.decode("utf-8")


def get_thumbnail_url(paper_uuid: str) -> str:
    """Generate a signed URL for a paper's thumbnail.

    Uses the service role key to create a time-limited signed URL
    for the private storage bucket.

    Args:
        paper_uuid: Unique identifier for the paper.

    Returns:
        Signed HTTPS URL for thumbnail.png (valid for 1 hour).

    Raises:
        RuntimeError: If signed URL generation fails.
    """
    path = f"{paper_uuid}/thumbnail.png"
    response = _bucket().create_signed_url(path, SIGNED_URL_EXPIRY_SECONDS)
    signed_url = response.get("signedURL")
    if not signed_url:
        raise RuntimeError(
            f"Failed to generate signed URL for {path}: {response}"
        )
    return signed_url


def get_figure_url(paper_uuid: str, figure_id: str) -> str:
    """Generate a signed URL for a specific figure image.

    Uses the service role key to create a time-limited signed URL
    for the private storage bucket.

    Args:
        paper_uuid: Unique identifier for the paper.
        figure_id: The figure identifier (used as filename without extension).

    Returns:
        Signed HTTPS URL for the figure PNG (valid for 1 hour).

    Raises:
        RuntimeError: If signed URL generation fails.
    """
    path = f"{paper_uuid}/figures/{figure_id}.png"
    response = _bucket().create_signed_url(path, SIGNED_URL_EXPIRY_SECONDS)
    signed_url = response.get("signedURL")
    if not signed_url:
        raise RuntimeError(
            f"Failed to generate signed URL for {path}: {response}"
        )
    return signed_url


def delete_paper_assets(paper_uuid: str) -> None:
    """Delete all storage files for a paper.

    Removes all known file paths under {paper_uuid}/ including any figure images
    listed in figures.json.

    Args:
        paper_uuid: Unique identifier for the paper.
    """
    bucket = _bucket()
    prefix = paper_uuid

    # Collect known top-level paths
    paths_to_delete = [
        f"{prefix}/thumbnail.png",
        f"{prefix}/content.md",
        f"{prefix}/sections.json",
        f"{prefix}/figures.json",
        f"{prefix}/metadata.json",
    ]

    # Try to read figures.json to find individual figure files
    try:
        figures_bytes = bucket.download(f"{prefix}/figures.json")
        figures_list = json.loads(figures_bytes.decode("utf-8"))
        for fig in figures_list:
            identifier = fig.get("identifier")
            if identifier:
                paths_to_delete.append(f"{prefix}/figures/{identifier}.png")
    except Exception:
        # If figures.json doesn't exist or is malformed, skip figure deletion.
        # The top-level files will still be cleaned up.
        pass

    bucket.remove(paths_to_delete)
