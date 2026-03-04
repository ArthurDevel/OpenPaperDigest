"""
Generates semantic embeddings for paper content via OpenRouter.

Uses the text-embedding-3-small model (1536 dimensions) through the existing
OpenRouter integration. No local model needed.

Responsibilities:
- Combine title and summary into a single embedding input text
- Call the OpenRouter embeddings endpoint
- Return a single embedding vector for the paper
"""

import asyncio
import logging
from typing import Optional

from shared.openrouter.client import get_embeddings

logger = logging.getLogger(__name__)


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================


def generate_embedding(title: str, summary: Optional[str] = None) -> list[float]:
    """
    Generate a 1536-dimensional embedding for a paper from its title and summary.

    Combines title + summary into a single text and calls OpenRouter's
    text-embedding-3-small model. Falls back to title-only if summary is None.

    Args:
        title: Paper title (required).
        summary: Optional paper summary text (e.g. five_minute_summary).

    Returns:
        list[float]: 1536-dimensional embedding vector.
    """
    # Build the input text from title and optional summary
    if summary:
        text = f"{title}\n\n{summary}"
    else:
        text = title

    # Call the OpenRouter embeddings endpoint (async -> sync bridge)
    embeddings = asyncio.run(get_embeddings([text]))

    return embeddings[0]
