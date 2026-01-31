import logging
import os
import random
import re
import string
from typing import Dict, List, Set

from paperprocessor.models import ProcessedDocument, Header, ProcessedImage

logger = logging.getLogger(__name__)


### HELPER FUNCTIONS ###
def _write_debug_output(content: str, filename: str) -> None:
    """
    Write debugging content to file in the debugging output directory.
    
    Args:
        content: The content to write to the file
        filename: Name of the output file
    """
    # Create path relative to this file's location
    debug_dir = os.path.join(os.path.dirname(__file__), '..', 'debugging_output')
    os.makedirs(debug_dir, exist_ok=True)
    
    # Write the content to the specified file
    file_path = os.path.join(debug_dir, filename)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info(f"Debug output written to {file_path}")


def _format_header_line(header: Header) -> str:
    """
    Format a header with the appropriate number of # symbols.
    
    Args:
        header: Header object with text and level
        
    Returns:
        Properly formatted markdown header line
    """
    # Convert level to # symbols (level 1 = #, level 2 = ##, etc.)
    hash_symbols = "#" * header.level
    return f"{hash_symbols} {header.text.strip()}"


def _get_page_headers(document_headers: List[Header], page_number: int) -> List[Header]:
    """
    Get all headers that belong to a specific page.
    
    Args:
        document_headers: All headers in the document
        page_number: Page number to filter by
        
    Returns:
        List of headers for the specified page
    """
    return [header for header in document_headers if header.page_number == page_number]


def _add_section_tags_to_page_markdown(original_markdown: str, page_headers: List[Header]) -> str:
    """
    Add section tags to markdown by inserting <<section>> before document_section and document_section_references headers.
    
    Args:
        original_markdown: Original OCR markdown content
        page_headers: Headers found on this page
        
    Returns:
        Markdown with section tags added
    """
    if not original_markdown or not page_headers:
        return original_markdown or ""
    
    # Split markdown into lines
    lines = original_markdown.split('\n')
    
    # Find document_section and document_section_references headers that have line numbers
    section_headers_by_line: Dict[int, Header] = {}
    for header in page_headers:
        if (header.markdown_line_number is not None and 
            header.element_type in ['document_section', 'document_section_references']):
            section_headers_by_line[header.markdown_line_number] = header
    
    # Insert section tags before document_section and document_section_references headers
    # Work backwards to avoid line number shifts
    for line_number in sorted(section_headers_by_line.keys(), reverse=True):
        header = section_headers_by_line[line_number]
        if 0 <= line_number < len(lines):
            lines.insert(line_number, "<<section>>")
            logger.debug(f"Added section tag before header on line {line_number}: '{header.text}'")
    
    return '\n'.join(lines)


def _format_page_markdown(original_markdown: str, page_headers: List[Header]) -> str:
    """
    Format markdown by adjusting header levels for lines that already start with # and are confirmed headers.
    Only modifies lines that OCR detected as headers (start with #) AND are in our headers list.
    
    Args:
        original_markdown: Original OCR markdown content
        page_headers: Headers found on this page
        
    Returns:
        Markdown with properly formatted header levels
    """
    if not original_markdown or not page_headers:
        return original_markdown or ""
    
    # Split markdown into lines
    lines = original_markdown.split('\n')
    
    # Create a dictionary of line numbers to format
    headers_by_line: Dict[int, Header] = {}
    for header in page_headers:
        if header.markdown_line_number is not None:
            headers_by_line[header.markdown_line_number] = header
    
    # Replace header lines with formatted versions - but only if line already starts with #
    for line_number, header in headers_by_line.items():
        if 0 <= line_number < len(lines):
            current_line = lines[line_number].strip()
            # Only format if line already starts with # (OCR detected it as header)
            if current_line.startswith('#'):
                formatted_line = _format_header_line(header)
                lines[line_number] = formatted_line
                logger.debug(f"Formatted header on line {line_number}: '{header.text}' -> '{formatted_line}'")
    
    return '\n'.join(lines)


async def format_headers(document: ProcessedDocument) -> None:
    """
    Combine OCR pages into final_markdown document.

    In simplified pipeline (without structure extraction):
    - Simply combines all page OCR markdown into document.final_markdown
    - No header formatting or section tagging since document.headers will be empty

    Legacy behavior (if headers are populated):
    1. Formats header levels (# count) for lines that already start with # and are confirmed headers
    2. Inserts <<section>> tags before document_section and document_section_references headers
    3. Creates document.final_markdown by combining all processed pages

    Preserves original OCR markdown in pages.
    """
    logger.info("Combining pages into final_markdown...")
    
    if not document.headers:
        logger.info("No headers found in document, creating final_markdown from OCR content")
        # Combine all OCR markdown even if no headers
        page_markdowns = []
        for page in document.pages:
            if page.ocr_markdown:
                page_markdowns.append(page.ocr_markdown)
        document.final_markdown = '\n\n'.join(page_markdowns)
        
        # Write final markdown to debug output even if no headers
        if document.final_markdown:
            _write_debug_output(document.final_markdown, "header_formatter_final_markdown.md")
        
        return
    
    # Step 1: Process each page to add section tags
    page_markdowns = []
    total_section_tags_added = 0
    
    for page in document.pages:
        if not page.ocr_markdown:
            logger.warning(f"Page {page.page_number} has no OCR markdown, skipping")
            continue
        
        # Step 2: Get headers for this page
        page_headers = _get_page_headers(document.headers, page.page_number)
        
        # Step 3: Format header levels for lines that already start with #
        page_markdown_formatted = _format_page_markdown(page.ocr_markdown, page_headers)
        
        # Step 4: Add section tags to page markdown
        page_markdown_final = _add_section_tags_to_page_markdown(page_markdown_formatted, page_headers)
        page_markdowns.append(page_markdown_final)
        
        # Count section headers on this page
        section_headers = [h for h in page_headers if h.element_type in ['document_section', 'document_section_references'] and h.markdown_line_number is not None]
        total_section_tags_added += len(section_headers)
        
        if section_headers:
            logger.info(f"Page {page.page_number}: added {len(section_headers)} section tags")
        else:
            logger.debug(f"Page {page.page_number}: no section headers found")
    
    # Step 5: Combine all pages into final_markdown
    document.final_markdown = '\n\n'.join(page_markdowns)
    
    # Step 6: Write final markdown to debug output
    if document.final_markdown:
        _write_debug_output(document.final_markdown, "header_formatter_final_markdown.md")
    
    # Step 7: Log summary
    total_section_headers = [h for h in document.headers if h.element_type in ['document_section', 'document_section_references']]
    section_headers_with_line_numbers = [h for h in total_section_headers if h.markdown_line_number is not None]
    section_headers_without_line_numbers = [h for h in total_section_headers if h.markdown_line_number is None]
    
    logger.info(f"Header processing completed: {total_section_tags_added} section tags added, {len(section_headers_without_line_numbers)} section headers without line numbers")
    
    if section_headers_without_line_numbers:
        logger.warning(f"Section headers without line numbers: {[h.text for h in section_headers_without_line_numbers]}")


### IMAGE FORMATTING FUNCTIONS ###
def _generate_short_id() -> str:
    """
    Generate 8-character Base36 ID (0-9, a-z).
    
    Returns:
        8-character string using lowercase letters and digits
    """
    base36_chars = string.digits + string.ascii_lowercase  # 0-9, a-z
    return ''.join(random.choices(base36_chars, k=8))


def _ensure_unique_image_ids(document: ProcessedDocument) -> None:
    """
    Generate and assign unique short IDs to all images in document.
    
    Args:
        document: ProcessedDocument with images to assign IDs to
    """
    # Collect all images that need IDs
    images_needing_ids = []
    for page in document.pages:
        for image in page.images:
            if image.short_id is None:
                images_needing_ids.append(image)
    
    # Generate unique IDs
    used_ids: Set[str] = set()
    for image in images_needing_ids:
        while True:
            new_id = _generate_short_id()
            if new_id not in used_ids:
                image.short_id = new_id
                used_ids.add(new_id)
                break
    
    logger.info(f"Generated {len(used_ids)} unique short IDs for images")


def _replace_image_references_in_page_markdown(markdown: str, page_images: List[ProcessedImage]) -> str:
    """
    Replace ![img-X.jpeg](img-X.jpeg) with <<img{"id":"shortid"}>>.
    
    Args:
        markdown: Page markdown content with image references
        page_images: Images on this page (must have short_id assigned)
        
    Returns:
        Markdown with image references replaced
        
    Raises:
        RuntimeError: If image reference cannot be correlated to actual image
    """
    if not markdown or not page_images:
        return markdown or ""
    
    # Pattern to match ![img-X.jpeg](img-X.jpeg)
    pattern = r'!\[img-(\d+)\.jpeg\]\(img-\d+\.jpeg\)'
    
    def replace_image_ref(match):
        # Extract the image index from the match
        image_index_str = match.group(1)
        logger.info(f"Found image reference: {match.group(0)}, extracting index: {image_index_str}")
        
        try:
            image_index = int(image_index_str)
        except ValueError:
            logger.error(f"Invalid image index in reference: {match.group(0)}")
            raise RuntimeError(f"Invalid image index in reference: {match.group(0)}")
        
        # Check if index is valid for this page's images
        if image_index >= len(page_images):
            logger.error(f"Image index {image_index} >= available images {len(page_images)}")
            raise RuntimeError(f"Image reference img-{image_index}.jpeg not found on page - only {len(page_images)} images available")
        
        # Get the corresponding image
        image = page_images[image_index]
        logger.debug(f"Found image at index {image_index}: UUID={image.uuid}, short_id={image.short_id}")
        logger.debug(f"Image object details: {vars(image)}")
        
        # Ensure the image has a short_id
        if not image.short_id:
            logger.error(f"Image at index {image_index} has no short_id! UUID={image.uuid}")
            raise RuntimeError(f"Image at index {image_index} does not have a short_id assigned")
        
        # Return the replacement
        replacement = f'<<img{{"id":"{image.short_id}"}}>>'
        logger.info(f"Replacing '{match.group(0)}' with '{replacement}'")
        return replacement
    
    # Replace all matches
    result = re.sub(pattern, replace_image_ref, markdown)
    
    # Count replacements for logging
    original_matches = len(re.findall(pattern, markdown))
    if original_matches > 0:
        logger.debug(f"Replaced {original_matches} image references on page")
    
    return result


def _replace_image_references_in_final_markdown(document: ProcessedDocument) -> None:
    """
    Replace ![img-X.jpeg](img-X.jpeg) with <<img{"id":"shortid"}>> in document.final_markdown.
    
    Uses global image indexing since we can't reliably split final_markdown back into pages.
    img-0.jpeg = first image globally, img-1.jpeg = second image globally, etc.
    
    Args:
        document: ProcessedDocument with final_markdown and pages to process
        
    Raises:
        RuntimeError: If image reference cannot be correlated to actual image
    """
    if not document.final_markdown:
        return
    
    # Collect all images in order across all pages
    all_images = []
    for page in document.pages:
        all_images.extend(page.images)
    
    logger.info(f"Processing final_markdown globally with {len(all_images)} total images")
    
    # Pattern to match ![img-X.jpeg](img-X.jpeg)
    pattern = r'!\[img-(\d+)\.jpeg\]\(img-\d+\.jpeg\)'
    
    def replace_image_ref(match):
        # Extract the image index from the match
        image_index_str = match.group(1)
        logger.info(f"Found global image reference: {match.group(0)}, extracting index: {image_index_str}")
        
        try:
            image_index = int(image_index_str)
        except ValueError:
            logger.error(f"Invalid image index in reference: {match.group(0)}")
            raise RuntimeError(f"Invalid image index in reference: {match.group(0)}")
        
        # Check if index is valid globally
        if image_index >= len(all_images):
            logger.error(f"Global image index {image_index} >= total images {len(all_images)}")
            raise RuntimeError(f"Image reference img-{image_index}.jpeg not found - only {len(all_images)} total images available")
        
        # Get the corresponding image
        image = all_images[image_index]
        logger.info(f"Found global image at index {image_index}: UUID={image.uuid}, short_id={image.short_id}")
        
        # Ensure the image has a short_id
        if not image.short_id:
            logger.error(f"Global image at index {image_index} has no short_id! UUID={image.uuid}")
            raise RuntimeError(f"Image at index {image_index} does not have a short_id assigned")
        
        # Generate proper markdown image syntax for frontend processing
        # Future: Add description support like this:
        # description = _generate_description(image, document)
        # replacement = f'![Figure {image.short_id}](shortid:{image.short_id} "{description}")'
        
        replacement = f'![Figure {image.short_id}](shortid:{image.short_id})'
        logger.info(f"Replacing '{match.group(0)}' with '{replacement}'")
        return replacement
    
    # Replace all matches globally
    document.final_markdown = re.sub(pattern, replace_image_ref, document.final_markdown)
    logger.info("Finished global image reference replacement")


async def format_images(document: ProcessedDocument) -> None:
    """
    Replace inline image references with short ID tags and assign IDs to images.
    
    Process:
    1. Generate unique short IDs for all images in the document
    2. Replace ![img-X.jpeg](img-X.jpeg) with <<img{"id":"shortid"}>> in document.final_markdown
    3. Update document.final_markdown with the replacements
    
    Args:
        document: ProcessedDocument to process (must have final_markdown set)
        
    Raises:
        RuntimeError: If image references cannot be correlated to actual images
    """
    logger.info("Formatting inline image references...")
    
    # Step 1: Generate unique IDs for all images
    logger.info("Step 1: Generating unique IDs for images")
    _ensure_unique_image_ids(document)
    
    # Step 2: Check if we have final_markdown to process
    if not document.final_markdown:
        logger.warning("No final_markdown found, skipping image reference processing")
        return
    
    logger.info(f"Step 2: Processing final_markdown with {len(document.final_markdown)} characters")
    
    # Step 3: Count original references before replacement
    original_pattern = r'!\[img-\d+\.jpeg\]\(img-\d+\.jpeg\)'
    original_matches = re.findall(original_pattern, document.final_markdown)
    original_count = len(original_matches)
    
    logger.info(f"Step 3: Found {original_count} original image references: {original_matches}")
    
    if original_count == 0:
        logger.warning("No image references found in final_markdown")
        return
    
    # Step 4: Replace image references in final_markdown
    logger.info("Step 4: Replacing image references")
    _replace_image_references_in_final_markdown(document)
    
    # Step 5: Verify replacements - fail fast if counts don't match
    new_pattern = r'!\[Figure ([^\]]+)\]\(shortid:([^)]+)\)'
    new_matches = re.findall(new_pattern, document.final_markdown)
    new_image_ids = [match[1] for match in new_matches]  # Extract just the short_ids
    logger.info(f"Step 5: After replacement, found {len(new_matches)} new markdown images with IDs: {new_image_ids}")
    
    # Fail fast if replacement count doesn't match original count
    if len(new_matches) != original_count:
        raise RuntimeError(f"Image replacement failed: expected {original_count} replacements, got {len(new_matches)}")
    
    logger.info(f"Image formatting completed: {original_count} image references replaced with short IDs")
