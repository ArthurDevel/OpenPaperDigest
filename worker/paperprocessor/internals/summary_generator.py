"""
Summary generation for processed papers.

Generates two types of summaries from research papers:
- Five-minute summary: comprehensive accessible summary from the full PDF via file content type
- Abstract summary: short 2-3 sentence summary from the paper's abstract or first page images

Responsibilities:
- Send PDF URL to LLM via OpenRouter file content type for full summaries
- Generate short abstract summaries from abstract text or page images as fallback
- Track API call costs for each generation step
"""

import asyncio
import logging
import os
from typing import Optional

from shared.openrouter import client as openrouter_client
from paperprocessor.models import ProcessedDocument, ApiCallCostForStep

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

SUMMARY_MODEL = "google/gemini-3-flash-preview"
ABSTRACT_SUMMARY_MODEL = "google/gemini-3.1-flash-lite-preview"
PDF_FILE_PLUGINS = [{"id": "file-parser", "pdf": {"engine": "native"}}]
ABSTRACT_SUMMARY_TIMEOUT_SECONDS = 30


# ============================================================================
# MAIN FUNCTIONS
# ============================================================================

async def generate_five_minute_summary(document: ProcessedDocument, pdf_url: str) -> None:
    """
    Generate a 5-minute accessible summary by sending the PDF URL directly to the LLM.

    Sends the PDF via OpenRouter file content type with native PDF engine plugin.
    Modifies the document in place by setting the five_minute_summary field.

    Args:
        document: ProcessedDocument to store the summary on.
        pdf_url: Public URL of the PDF to summarize.

    Raises:
        RuntimeError: If pdf_url is missing or empty.
        RuntimeError: If LLM response is empty.
    """
    logger.info("Generating 5-minute summary from PDF URL...")

    # Step 1: Validate input
    if not pdf_url or pdf_url.strip() == "":
        raise RuntimeError("Cannot generate summary: pdf_url is missing or empty")

    # Step 2: Load summary generation prompt
    prompts_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts')
    prompt_path = os.path.join(prompts_dir, 'generate_5min_summary.md')

    with open(prompt_path, 'r', encoding='utf-8') as f:
        system_prompt = f.read()

    # Step 3: Build messages with PDF file content type
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [
            {"type": "text", "text": "Please summarize this research paper."},
            {"type": "file", "file": {"filename": "paper.pdf", "file_data": pdf_url}},
        ]},
    ]

    # Step 4: Generate summary using LLM with native PDF engine
    result = await openrouter_client.get_llm_response_with_file(
        messages=messages,
        model=SUMMARY_MODEL,
        plugins=PDF_FILE_PLUGINS,
    )

    # Step 5: Validate response
    summary_text = getattr(result, "response_text", None)
    if not summary_text or summary_text.strip() == "":
        raise RuntimeError("Summary generation failed: LLM returned empty response")

    # Step 6: Track costs
    step_cost = ApiCallCostForStep(
        step_name="generate_summary",
        model=result.model,
        cost_info=result.cost_info
    )
    document.step_costs.append(step_cost)

    # Step 7: Store summary on document
    document.five_minute_summary = summary_text.strip()

    logger.info("5-minute summary generation completed.")


async def generate_abstract_summary(document: ProcessedDocument) -> None:
    """
    Generate a short 2-3 sentence summary from the paper's abstract.

    If no abstract is available, falls back to sending the first 3 page images
    to the LLM to extract and summarize the abstract.
    Modifies the document in place by setting the abstract_summary field.

    Args:
        document: ProcessedDocument with abstract text or page images.

    Raises:
        RuntimeError: If neither abstract nor page images are available.
        RuntimeError: If LLM response is empty.
    """
    logger.info("Generating abstract summary...")

    # Step 1: Load prompt
    prompts_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts')
    prompt_path = os.path.join(prompts_dir, 'generate_abstract_summary.md')

    with open(prompt_path, 'r', encoding='utf-8') as f:
        system_prompt = f.read()

    # Step 2: Determine input (abstract text preferred, fallback to page images)
    input_text = document.abstract
    if input_text and input_text.strip() != "":
        # Use abstract text directly
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": input_text},
        ]
        try:
            result = await asyncio.wait_for(
                openrouter_client.get_llm_response(messages=messages, model=ABSTRACT_SUMMARY_MODEL),
                timeout=ABSTRACT_SUMMARY_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(f"Abstract summary generation timed out after {ABSTRACT_SUMMARY_TIMEOUT_SECONDS}s")
    else:
        # Fallback: send first 3 page images to extract abstract
        if not document.pages:
            raise RuntimeError("Cannot generate abstract summary: no abstract and no page images available")

        user_content = [{"type": "text", "text": "Extract and summarize the abstract from these paper pages."}]
        for page in document.pages[:3]:
            user_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{page.img_base64}"}})

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        try:
            result = await asyncio.wait_for(
                openrouter_client.get_llm_response(messages=messages, model=ABSTRACT_SUMMARY_MODEL),
                timeout=ABSTRACT_SUMMARY_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(f"Abstract summary generation timed out after {ABSTRACT_SUMMARY_TIMEOUT_SECONDS}s")

    # Step 3: Validate response
    summary_text = getattr(result, "response_text", None)
    if not summary_text or summary_text.strip() == "":
        raise RuntimeError("Abstract summary generation failed: LLM returned empty response")

    # Step 4: Track costs
    step_cost = ApiCallCostForStep(
        step_name="generate_abstract_summary",
        model=result.model,
        cost_info=result.cost_info
    )
    document.step_costs.append(step_cost)

    # Step 5: Store on document
    document.abstract_summary = summary_text.strip()

    logger.info("Abstract summary generation completed.")
