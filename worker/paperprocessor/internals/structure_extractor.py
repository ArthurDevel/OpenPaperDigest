import asyncio
import logging
import json
import os
import re
from typing import Dict, Any, List, Optional

from shared.openrouter import client as openrouter_client
from paperprocessor.models import ProcessedDocument, Header

logger = logging.getLogger(__name__)

### CONSTANTS ###
STRUCTURE_ANALYSIS_MODEL = "google/gemini-2.5-pro"
HEADER_EXTRACTION_MODEL = "google/gemini-2.5-flash"
MAX_PAGES_FOR_STRUCTURE_ANALYSIS = 20


### HELPER FUNCTIONS ###
def _write_debug_output(data: Dict[str, Any], filename: str) -> None:
    """
    Write debugging data to JSON file in the debugging output directory.
    
    Args:
        data: The data to write to the file
        filename: Name of the output file (should end with .json)
    """
    # Create path relative to this file's location
    debug_dir = os.path.join(os.path.dirname(__file__), '..', 'debugging_output')
    os.makedirs(debug_dir, exist_ok=True)
    
    # Write the data to the specified file
    file_path = os.path.join(debug_dir, filename)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Debug output written to {file_path}")


def _load_structure_analysis_prompt() -> str:
    """Load the document structure analysis prompt."""
    prompts_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts')
    prompt_path = os.path.join(prompts_dir, 'analyze_document_structure.md')
    
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        raise RuntimeError(f"Structure analysis prompt not found: {prompt_path}")


def _load_header_extraction_prompt() -> str:
    """Load the header extraction prompt template."""
    prompts_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts')
    prompt_path = os.path.join(prompts_dir, 'extract_page_headers.md')
    
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        raise RuntimeError(f"Header extraction prompt not found: {prompt_path}")


def _create_structure_analysis_prompt_parts(pages_base64: List[str]) -> List[Dict[str, Any]]:
    """Create multimodal prompt parts for document structure analysis."""
    prompt_parts = [
        {"type": "text", "text": "Analyze the structure of this research paper and identify all structural elements:"}
    ]
    
    # Add each page image
    for page_base64 in pages_base64:
        prompt_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{page_base64}"}
        })
    
    return prompt_parts


def _create_header_extraction_prompt_with_structure(structure_data: Dict[str, Any]) -> str:
    """Create detailed header extraction prompt based on structure analysis."""
    base_prompt = _load_header_extraction_prompt()
    
    # Create structure reference to replace the placeholder
    structure_reference = ""
    
    for element in structure_data.get('elements', []):
        structure_reference += f"\n**{element['element_type']}** (Level {element['level']})"
        structure_reference += f"\n  How to recognize this element: {element['recognition_pattern']}"
        examples = element.get('examples', [])[:2]  # Take first 2 examples
        structure_reference += f"\n  Examples: {', '.join(examples)}"
        structure_reference += "\n"
    
    # Replace the placeholder with the actual structure reference
    return base_prompt.replace("<<document_structure>>", structure_reference.strip())


def _parse_json_with_fallback(content: str, context: str) -> Dict[str, Any]:
    """Parse JSON content with fallback handling for malformed responses."""
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parsing failed for {context}: {e.msg}")
        
        # Try to extract JSON from response if wrapped in other text
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                logger.error(f"Extracted JSON also failed for {context}")
                
        # Return empty fallback
        if context.startswith("structure"):
            return {"document_type": "research_paper", "elements": [], "notes": "JSON parsing failed"}
        else:  # header extraction context
            return {"headers": []}


def _validate_unique_element_types(structure_data: Dict[str, Any]) -> None:
    """
    Validate that each element type appears only once in the structure analysis.
    Raises RuntimeError if duplicate element types are found.
    
    Args:
        structure_data: Structure analysis results to validate
    """
    element_types_seen = set()
    duplicates = set()
    
    for element in structure_data.get('elements', []):
        element_type = element.get('element_type')
        if element_type:
            if element_type in element_types_seen:
                duplicates.add(element_type)
            else:
                element_types_seen.add(element_type)
    
    if duplicates:
        raise RuntimeError(f"Duplicate element types found in structure analysis: {sorted(duplicates)}. Each element type must be unique.")


def _create_element_type_to_level_mapping(structure_data: Dict[str, Any]) -> Dict[str, int]:
    """Create a mapping from element type to hierarchical level from structure analysis."""
    element_type_to_level = {}
    
    for element in structure_data.get('elements', []):
        element_type = element.get('element_type')
        level = element.get('level')
        
        if element_type and level is not None:
            element_type_to_level[element_type] = level
    
    return element_type_to_level


def _normalize_heading_text(text: str) -> str:
    """
    Lowercase and collapse whitespace for robust matching.
    
    Args:
        text: Text to normalize
        
    Returns:
        Normalized text for comparison
    """
    return " ".join((text or "").lower().split())


def _find_header_line_in_markdown(header_text: str, markdown_content: str) -> Optional[int]:
    """
    Find the line number where a header appears in markdown content using RapidFuzz.
    
    Args:
        header_text: The header text to search for
        markdown_content: The markdown content to search in
        
    Returns:
        Line number (0-based) where header appears, or None if not found
    """
    if not markdown_content or not header_text:
        return None
    
    try:
        from rapidfuzz import fuzz
    except ImportError:
        logger.error("rapidfuzz is required for header line matching. Install with: pip install rapidfuzz")
        return None
    
    lines = markdown_content.split('\n')
    query = _normalize_heading_text(header_text)
    
    best_score = -1
    best_line_idx = None
    threshold = 85
    
    for i, line in enumerate(lines):
        # Remove markdown formatting for comparison
        line_no_markdown = line.lstrip('#').strip().replace('**', '').replace('*', '')
        line_normalized = _normalize_heading_text(line_no_markdown)
        
        if not line_normalized:  # Skip empty lines
            continue
        
        score = fuzz.token_set_ratio(query, line_normalized)
        if score > best_score:
            best_score = score
            best_line_idx = i
    
    if best_line_idx is not None and best_score >= threshold:
        logger.debug(f"Found header '{header_text}' at line {best_line_idx} with score {best_score}")
        return best_line_idx
    else:
        logger.debug(f"Header '{header_text}' not found with sufficient similarity (best score: {best_score})")
        return None


def _validate_and_clean_headers(headers_data: List[Dict[str, Any]], page_number: int, element_type_to_level_mapping: Dict[str, int]) -> List[Dict[str, Any]]:
    """Validate and clean headers data from API response."""
    valid_headers = []
    
    for i, header in enumerate(headers_data):
        if not isinstance(header, dict):
            logger.warning(f"Header {i+1} on page {page_number} is not a dict, skipping")
            raise RuntimeError(f"Header {i+1} on page {page_number} is not a dict. Raw response: {header}")
        
        # Check required fields
        required_fields = ["text", "element_type"]
        missing_fields = [field for field in required_fields if field not in header or header[field] is None]
        
        if missing_fields:
            logger.warning(f"Header {i+1} on page {page_number} missing fields {missing_fields}, skipping")
            raise RuntimeError(f"Header {i+1} on page {page_number} missing fields {missing_fields}. Raw response: {header}")
        
        # Clean and validate text
        header_text = str(header["text"]).strip()
        if not header_text:
            logger.warning(f"Header {i+1} on page {page_number} has empty text, skipping")
            raise RuntimeError(f"Header {i+1} on page {page_number} has empty text. Raw response: {header}")
        
        # Get element type and look up its level
        element_type = str(header["element_type"]).strip()
        level = element_type_to_level_mapping.get(element_type)
        
        if level is None:
            logger.warning(f"Header {i+1} on page {page_number} has unknown element_type '{element_type}', skipping")
            raise RuntimeError(f"Header {i+1} on page {page_number} has unknown element_type '{element_type}'. Raw response: {header}")
        
        valid_headers.append({
            "text": header_text,
            "element_type": element_type,
            "level": level,
            "page_number": page_number
        })
    
    return valid_headers


async def _analyze_document_structure(pages_base64: List[str]) -> Dict[str, Any]:
    """
    Step 3a: Analyze document structure from first pages.
    Validates that each element type is unique.
    
    Args:
        pages_base64: List of base64-encoded page images
        
    Returns:
        Document structure analysis results with unique element types
        
    Raises:
        RuntimeError: If duplicate element types are found
    """
    logger.info(f"Analyzing document structure from {len(pages_base64)} pages")
    
    # Step 1: Prepare API call for structure analysis
    system_prompt = _load_structure_analysis_prompt()
    user_prompt_parts = _create_structure_analysis_prompt_parts(pages_base64)
    
    # Step 2: Call OpenRouter API for structure analysis
    response = await openrouter_client.get_multimodal_json_response(
        system_prompt=system_prompt,
        user_prompt_parts=user_prompt_parts,
        model=STRUCTURE_ANALYSIS_MODEL
    )
    
    # Step 3: Parse structure response with error handling
    structure_data = _parse_json_with_fallback(
        response.parsed_json if isinstance(response.parsed_json, str) else json.dumps(response.parsed_json),
        "structure analysis"
    )
    
    # Step 4: Validate that element types are unique
    _validate_unique_element_types(structure_data)
    
    logger.info(f"Found {len(structure_data.get('elements', []))} element types in document")
    return structure_data


async def _extract_headers_from_page(page_base64: str, page_number: int, extraction_prompt: str, element_type_to_level_mapping: Dict[str, int], page_markdown: Optional[str] = None) -> List[Header]:
    """
    Extract headers from a single page.
    
    Args:
        page_base64: Base64-encoded page image
        page_number: Page number (1-based)
        extraction_prompt: Detailed extraction prompt with structure info
        page_markdown: OCR markdown content for line number detection
        
    Returns:
        List of Header objects found on this page
    """
    # Step 1: Create single-page prompt
    user_prompt_parts = [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{page_base64}"}}
    ]
    
    # Step 2: Call OpenRouter API for header extraction
    response = await openrouter_client.get_multimodal_json_response(
        system_prompt=extraction_prompt,
        user_prompt_parts=user_prompt_parts,
        model=HEADER_EXTRACTION_MODEL
    )
    
    # Step 3: Parse and validate response
    page_data = _parse_json_with_fallback(
        response.parsed_json if isinstance(response.parsed_json, str) else json.dumps(response.parsed_json),
        f"page {page_number} header extraction"
    )
    
    # Step 4: Validate and clean headers
    headers_data = page_data.get("headers", [])
    valid_headers_data = _validate_and_clean_headers(headers_data, page_number, element_type_to_level_mapping)
    
    # Step 5: Convert to Header objects
    headers = []
    for header_data in valid_headers_data:
        # Find markdown line number if page markdown is available
        markdown_line_number = None
        if page_markdown:
            markdown_line_number = _find_header_line_in_markdown(header_data["text"], page_markdown)
        
        header = Header(
            text=header_data["text"],
            level=header_data["level"],
            page_number=page_number,
            element_type=header_data["element_type"],
            markdown_line_number=markdown_line_number
        )
        headers.append(header)
    
    logger.info(f"Page {page_number}: found {len(headers)} valid headers")
    return headers


async def extract_structure(document: ProcessedDocument) -> None:
    """
    Step 3: Extract structural elements (headers) from the processed document.
    Uses a two-step approach: analyze structure, then extract headers per page.
    Modifies the document in place.
    """
    logger.info("Starting structural elements extraction...")
    
    if not document.pages:
        logger.warning("No pages available for structure extraction")
        return
    
    # Step 1: Get pages for structure analysis (first MAX_PAGES_FOR_STRUCTURE_ANALYSIS)
    structure_pages = document.pages[:MAX_PAGES_FOR_STRUCTURE_ANALYSIS]
    structure_pages_base64 = []
    
    for page in structure_pages:
        if page.img_base64:
            structure_pages_base64.append(page.img_base64)
        else:
            logger.warning(f"Page {page.page_number} missing img_base64 for structure analysis")
            raise RuntimeError(f"Page {page.page_number} missing img_base64")
    
    logger.info(f"Using first {len(structure_pages_base64)} pages for structure analysis")
    
    # Step 2: Analyze document structure and validate uniqueness
    try:
        structure_data = await _analyze_document_structure(structure_pages_base64)
    except Exception as e:
        logger.error(f"Document structure analysis failed: {e}")
        raise RuntimeError(f"Structure analysis failed: {e}") from e

    logger.info(f"Structure data: {structure_data}")
    
    # Step 2a: Write structure data to debug output
    _write_debug_output(structure_data, "structure_extractor_structure.json")
    
    # Step 3: Create extraction prompt with structure information
    extraction_prompt = _create_header_extraction_prompt_with_structure(structure_data)
    
    # Step 4: Create mapping from element types to levels
    element_type_to_level_mapping = _create_element_type_to_level_mapping(structure_data)
    
    # Step 5: Extract headers from each page (in parallel)
    # Step 5a: Validate all pages have img_base64 before starting parallel processing
    for page in document.pages:
        if not page.img_base64:
            logger.warning(f"Page {page.page_number} missing img_base64 for header extraction")
            raise RuntimeError(f"Page {page.page_number} missing img_base64")
    
    # Step 5b: Create tasks for parallel processing
    page_tasks = []
    for page in document.pages:
        task = _extract_headers_from_page(
            page.img_base64,
            page.page_number,
            extraction_prompt,
            element_type_to_level_mapping,
            page.ocr_markdown
        )
        page_tasks.append(task)
    
    # Step 5c: Execute all page extractions in parallel (maintains page order)
    try:
        page_results = await asyncio.gather(*page_tasks)
    except Exception as e:
        # Find which page failed by checking the exception
        logger.error(f"Header extraction failed during parallel processing: {e}")
        raise RuntimeError(f"Header extraction failed during parallel processing: {e}") from e
    
    # Step 5d: Combine results from all pages
    all_headers = []
    for headers in page_results:
        all_headers.extend(headers)
    
    # Step 6: Write extracted headers to debug output
    headers_debug_data = {
        "total_headers": len(all_headers),
        "headers": [
            {
                "text": header.text,
                "level": header.level,
                "page_number": header.page_number,
                "element_type": header.element_type,
                "markdown_line_number": header.markdown_line_number
            }
            for header in all_headers
        ]
    }
    _write_debug_output(headers_debug_data, "structure_extractor_headers.json")
    
    # Step 7: Update document with extracted headers
    document.headers = all_headers
    
    logger.info(f"Successfully extracted {len(all_headers)} headers from {len(document.pages)} pages")
