from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RequestedPaperItem(BaseModel):
    arxiv_id: str
    arxiv_abs_url: str
    arxiv_pdf_url: str
    request_count: int
    first_requested_at: datetime
    last_requested_at: datetime
    title: Optional[str] = None
    authors: Optional[str] = None
    num_pages: Optional[int] = None
    processed_slug: Optional[str] = None


class StartProcessingResponse(BaseModel):
    paper_uuid: str
    status: str


class DeleteRequestedResponse(BaseModel):
    deleted: str


class RestartPaperRequest(BaseModel):
    reason: Optional[str] = None


class ImportResult(BaseModel):
    paper_uuid: str
    status: str


class CumulativeDailyPaperItem(BaseModel):
    date: str
    daily_count: int
    cumulative_count: int
    cumulative_failed: int
    cumulative_processed: int
    cumulative_not_started: int
    cumulative_processing: int


