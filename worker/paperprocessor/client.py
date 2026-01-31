import logging
import base64
import io
import time
import os
import json
from typing import Optional, Dict, Any, List

from paperprocessor.models import ProcessedDocument, ProcessedPage, ApiCallCostForStep
from paperprocessor.internals.pdf_to_image import convert_pdf_to_images
from paperprocessor.internals.mistral_ocr import extract_markdown_from_pages
from paperprocessor.internals.metadata_extractor import extract_metadata
from paperprocessor.internals.header_formatter import format_headers, format_images
from paperprocessor.internals.summary_generator import generate_five_minute_summary
from shared.db import SessionLocal
from papers.client import get_paper_metadata

logger = logging.getLogger(__name__)


### HELPER FUNCTIONS ###
def _calculate_usage_summary(step_costs: List[ApiCallCostForStep]) -> Dict[str, Any]:
    """
    Aggregate ApiCallCostForStep objects into UsageSummary format.
    Business logic for cost aggregation - belongs in client.py, not models.py.
    """
    if not step_costs:
        return {}
    
    total_cost = 0.0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    by_model: Dict[str, Dict[str, Any]] = {}
    
    for step_cost in step_costs:
        cost = step_cost.cost_info
        
        # Aggregate totals
        if cost.total_cost:
            total_cost += cost.total_cost
        if cost.prompt_tokens:
            total_prompt_tokens += cost.prompt_tokens
        if cost.completion_tokens:
            total_completion_tokens += cost.completion_tokens
        if cost.total_tokens:
            total_tokens += cost.total_tokens
            
        # Aggregate by model
        model = step_cost.model
        if model not in by_model:
            by_model[model] = {
                "num_calls": 0,
                "total_cost": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        
        by_model[model]["num_calls"] += 1
        if cost.total_cost:
            by_model[model]["total_cost"] += cost.total_cost
        if cost.prompt_tokens:
            by_model[model]["prompt_tokens"] += cost.prompt_tokens
        if cost.completion_tokens:
            by_model[model]["completion_tokens"] += cost.completion_tokens
        if cost.total_tokens:
            by_model[model]["total_tokens"] += cost.total_tokens
    
    return {
        "currency": "USD",
        "total_cost": total_cost if total_cost > 0 else None,
        "total_prompt_tokens": total_prompt_tokens if total_prompt_tokens > 0 else None,
        "total_completion_tokens": total_completion_tokens if total_completion_tokens > 0 else None,
        "total_tokens": total_tokens if total_tokens > 0 else None,
        "by_model": by_model
    }




def _load_usage_summary_from_json(paper_uuid: str) -> Optional[Dict[str, Any]]:
    """
    Load usage summary data from database processed_content field.
    
    Args:
        paper_uuid: UUID of paper to load usage summary for
        
    Returns:
        Optional[Dict]: Usage summary dict or None if not found
    """
    try:
        from papers.db.client import get_paper_record
        session = SessionLocal()
        try:
            record = get_paper_record(session, paper_uuid, load_content=True)
            if not record or not record.processed_content:
                return None
            data = json.loads(record.processed_content)
            us = data.get('usage_summary')
            return us if isinstance(us, dict) else None
        finally:
            session.close()
    except Exception:
        return None


def get_processing_metrics_for_user(paper_uuid: str, auth_provider_id: str) -> Dict[str, Any]:
    """
    Return processing metrics for a completed paper to the initiating user only.
    Raises PermissionError if caller is not the initiator.
    """
    session = SessionLocal()
    try:
        paper = get_paper_metadata(session, paper_uuid)
        if paper.status != 'completed':
            raise RuntimeError("Paper not completed")
        if not paper.initiated_by_user_id or paper.initiated_by_user_id != auth_provider_id:
            raise PermissionError("Not authorized to view metrics for this paper")
        usage_summary = _load_usage_summary_from_json(paper.paper_uuid)
        return {
            "paper_uuid": paper.paper_uuid,
            "status": paper.status,
            "created_at": paper.created_at,
            "started_at": paper.started_at,
            "finished_at": paper.finished_at,
            "num_pages": paper.num_pages,
            "processing_time_seconds": paper.processing_time_seconds,
            "total_cost": paper.total_cost,
            "avg_cost_per_page": paper.avg_cost_per_page,
            "usage_summary": usage_summary,
        }
    finally:
        session.close()


def get_processing_metrics_for_admin(paper_uuid: str) -> Dict[str, Any]:
    """
    Return processing metrics for a completed paper for admin usage. No initiator check.
    """
    session = SessionLocal()
    try:
        paper = get_paper_metadata(session, paper_uuid)
        if paper.status != 'completed':
            raise RuntimeError("Paper not completed")
        usage_summary = _load_usage_summary_from_json(paper.paper_uuid)
        return {
            "paper_uuid": paper.paper_uuid,
            "status": paper.status,
            "created_at": paper.created_at,
            "started_at": paper.started_at,
            "finished_at": paper.finished_at,
            "num_pages": paper.num_pages,
            "processing_time_seconds": paper.processing_time_seconds,
            "total_cost": paper.total_cost,
            "avg_cost_per_page": paper.avg_cost_per_page,
            "usage_summary": usage_summary,
            "initiated_by_user_id": paper.initiated_by_user_id,
        }
    finally:
        session.close()


async def process_paper_pdf(pdf_contents: bytes, paper_id: Optional[str] = None) -> ProcessedDocument:
        """
        Simplified 4-step pipeline:
        1. OCR → markdown per page
        2. Extract metadata
        3. Format headers and images
        4. Generate summary from original content
        """
        logger.info("Paper processing pipeline v2 started (simplified).")

        # Create ProcessedDocument DTO with PDF base64
        pdf_base64 = base64.b64encode(pdf_contents).decode('utf-8')

        logger.info("Converting PDF to images for page image storage...")
        images = await convert_pdf_to_images(pdf_contents)

        # Create ProcessedPages with base64 encoded images
        pages = []
        for i, image in enumerate(images):
            page_num = i + 1

            # Convert PIL Image to base64
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            page = ProcessedPage(
                page_number=page_num,
                img_base64=img_base64,
                width=image.width,
                height=image.height
            )
            pages.append(page)

        document = ProcessedDocument(
            pdf_base64=pdf_base64,
            pages=pages
        )

        # Step 1: OCR pages to markdown - populates ocr_markdown
        logger.info("Step 1: OCR pages to markdown.")
        await extract_markdown_from_pages(document)

        # Step 2: Extract metadata (title, authors) - modifies document in place
        logger.info("Step 2: Extracting metadata.")
        await extract_metadata(document)

        # Step 3: Format headers and combine pages - modifies document in place
        # Note: Without structure extraction, this only combines OCR markdown into final_markdown
        logger.info("Step 3: Formatting document (combining pages).")
        await format_headers(document)

        # Step 3b: Format inline image references - modifies document in place
        logger.info("Step 3b: Formatting inline image references.")
        await format_images(document)

        # Step 4: Generate 5-minute summary from original OCR content - modifies document in place
        logger.info("Step 4: Generating 5-minute summary.")
        await generate_five_minute_summary(document)

        logger.info("Paper processing pipeline v2 finished (simplified).")
        return document
