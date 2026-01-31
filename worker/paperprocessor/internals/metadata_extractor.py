import logging
import os
from typing import Dict, Any, List

from shared.openrouter import client as openrouter_client
from paperprocessor.models import ProcessedDocument, ApiCallCostForStep

logger = logging.getLogger(__name__)

### CONSTANTS ###
MODEL = "google/gemini-2.5-pro"
MAX_PAGES_FOR_METADATA = 3


### HELPER FUNCTIONS ###
def load_metadata_prompt() -> str:
    """Load the metadata extraction prompt from the prompts directory."""
    prompts_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts')
    prompt_path = os.path.join(prompts_dir, 'extract_metadata.md')
    
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        raise RuntimeError(f"Metadata extraction prompt not found: {prompt_path}")


def create_multimodal_user_prompt(pages_base64: List[str]) -> List[Dict[str, Any]]:
    """
    Create multimodal user prompt with page images.
    
    Args:
        pages_base64: List of base64-encoded page images
        
    Returns:
        List of prompt parts for multimodal API call
    """
    prompt_parts = [
        {"type": "text", "text": "Extract the title and authors from these document pages:"}
    ]
    
    # Add each page image
    for i, page_base64 in enumerate(pages_base64, 1):
        prompt_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{page_base64}"}
        })
    
    return prompt_parts


async def extract_metadata(document: ProcessedDocument) -> None:
    """
    Step 2: Extract metadata (title, authors) from the processed document.
    Uses the first 3 pages and calls OpenRouter API for extraction.
    Modifies the document in place.
    """
    logger.info("Extracting document metadata...")
    
    # Step 1: Get first few pages for metadata extraction
    pages_to_analyze = document.pages[:MAX_PAGES_FOR_METADATA]
    if not pages_to_analyze:
        logger.warning("No pages available for metadata extraction")
        return
    
    logger.info(f"Analyzing first {len(pages_to_analyze)} pages for metadata")
    
    # Step 2: Prepare page images for multimodal API call
    pages_base64 = []
    for page in pages_to_analyze:
        if page.img_base64:
            pages_base64.append(page.img_base64)
        else:
            logger.warning(f"Page {page.page_number} missing img_base64, raising")
            raise
    
    if not pages_base64:
        logger.warning("No page images available for metadata extraction")
        raise
    
    # Step 3: Load prompt and create API request
    system_prompt = load_metadata_prompt()
    user_prompt_parts = create_multimodal_user_prompt(pages_base64)
    
    # Step 4: Call OpenRouter API for metadata extraction
    logger.info(f"Calling OpenRouter API to extract metadata from {len(pages_base64)} pages")
    
    try:
        response = await openrouter_client.get_multimodal_json_response(
            system_prompt=system_prompt,
            user_prompt_parts=user_prompt_parts,
            model=MODEL
        )
        
        # Step 5: Track cost for this API call
        step_cost = ApiCallCostForStep(
            step_name="extract_metadata",
            model=response.model,
            cost_info=response.cost_info
        )
        document.step_costs.append(step_cost)
        
        # Step 6: Parse response and update document
        metadata = response.parsed_json
        
        document.title = metadata.get("title")
        document.authors = metadata.get("authors")
        
        logger.info(f"Successfully extracted metadata - Title: '{document.title}', Authors: '{document.authors}'")
        
    except Exception as e:
        logger.error(f"Failed to extract metadata: {e}")
        raise RuntimeError(f"Metadata extraction failed: {e}") from e
