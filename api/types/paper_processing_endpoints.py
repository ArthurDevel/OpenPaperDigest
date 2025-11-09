from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class JobDbStatus(BaseModel):
    paper_uuid: str
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    arxiv_id: str | None = None
    arxiv_version: str | None = None
    arxiv_url: str | None = None
    title: str | None = None
    authors: str | None = None
    num_pages: int | None = None
    thumbnail_data_url: str | None = None
    processing_time_seconds: float | None = None
    total_cost: float | None = None
    avg_cost_per_page: float | None = None


