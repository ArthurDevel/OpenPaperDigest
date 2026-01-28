from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel


class VectorPoint(BaseModel):
    """Domain-agnostic wrapper for a Qdrant point for reads."""

    id: str
    score: Optional[float] = None
    payload: Dict[str, Any] = {}


