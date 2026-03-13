"""
Generates semantic embeddings for paper content via OpenRouter.

Uses the text-embedding-3-small model (1536 dimensions) through the existing
OpenRouter integration. No local model needed.

Responsibilities:
- Combine title and abstract into a single embedding input text
- Call the OpenRouter embeddings endpoint
- Return a single embedding vector for the paper
"""

import logging
from typing import List, Optional

from shared.openrouter.client import get_embeddings

logger = logging.getLogger(__name__)


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================


async def generate_embedding(title: str, abstract: Optional[str] = None) -> List[float]:
    """
    Generate a 1536-dimensional embedding for a paper from its title and abstract.

    Combines title + abstract into a single text and calls OpenRouter's
    text-embedding-3-small model. Falls back to title-only if abstract is None.

    Args:
        title: Paper title (required).
        abstract: Optional paper abstract text.

    Returns:
        list[float]: 1536-dimensional embedding vector.
    """
    # Build the input text from title and optional abstract
    if abstract:
        text = f"{title}\n\n{abstract}"
    else:
        text = title

    embeddings = await get_embeddings([text])

    if not embeddings:
        raise ValueError(f"OpenRouter returned no embeddings for text: {text[:100]}...")

    return embeddings[0]
