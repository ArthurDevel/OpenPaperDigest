import logging
import os
from typing import Optional

from shared.openrouter import client as openrouter_client
from paperprocessor.models import ProcessedDocument, ApiCallCostForStep

logger = logging.getLogger(__name__)


### CONSTANTS ###
SUMMARY_MODEL = "google/gemini-2.5-pro"


### PUBLIC API ###
async def generate_five_minute_summary(document: ProcessedDocument) -> None:
    """
    Generate a 5-minute accessible summary from original OCR content.

    Takes the final_markdown (original OCR content) and creates a concise, accessible summary
    suitable for general audiences. Modifies the document in place by setting
    the five_minute_summary field.

    Args:
        document: ProcessedDocument with final_markdown content

    Raises:
        RuntimeError: If final_markdown is missing or empty
        RuntimeError: If LLM response is empty
    """
    logger.info("Generating 5-minute summary from original OCR content...")

    # Step 1: Validate input
    if not document.final_markdown:
        raise RuntimeError("Cannot generate summary: final_markdown is missing or empty")

    if document.final_markdown.strip() == "":
        raise RuntimeError("Cannot generate summary: final_markdown is empty")

    # Step 2: Load summary generation prompt
    prompts_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts')
    prompt_path = os.path.join(prompts_dir, 'generate_5min_summary.md')

    with open(prompt_path, 'r', encoding='utf-8') as f:
        system_prompt = f.read()

    # Step 3: Generate summary using LLM
    result = await openrouter_client.get_llm_response(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": document.final_markdown},
        ],
        model=SUMMARY_MODEL,
    )

    # Step 4: Validate response
    summary_text = getattr(result, "response_text", None)
    if not summary_text or summary_text.strip() == "":
        raise RuntimeError("Summary generation failed: LLM returned empty response")

    # Step 5: Track costs
    step_cost = ApiCallCostForStep(
        step_name="generate_summary",
        model=result.model,
        cost_info=result.cost_info
    )
    document.step_costs.append(step_cost)

    # Step 6: Store summary on document
    document.five_minute_summary = summary_text.strip()

    logger.info("5-minute summary generation completed.")
