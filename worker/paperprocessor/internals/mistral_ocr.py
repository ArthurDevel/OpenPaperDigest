import logging
import base64
import os
from typing import Any, Dict

from mistralai import Mistral
from paperprocessor.models import ProcessedDocument, ProcessedImage

logger = logging.getLogger(__name__)

### CONSTANTS ###
MODEL = "mistral-ocr-latest"


### HELPER FUNCTIONS ###
def create_mistral_client() -> Mistral:
    """Create Mistral client with API key from environment."""
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is not set in environment variables")
    return Mistral(api_key=api_key)


def create_document_spec(pdf_base64: str) -> Dict[str, str]:
    """Create document specification for Mistral OCR API."""
    return {
        "type": "document_url", 
        "document_url": f"data:application/pdf;base64,{pdf_base64}"
    }


def extract_base64_from_data_url(data_url: str) -> str:
    """Extract base64 data from data URL format."""
    if data_url.startswith("data:"):
        _, base64_data = data_url.split(",", 1)
        return base64_data
    return data_url


async def extract_markdown_from_pages(document: ProcessedDocument) -> None:
    """
    Step 1: Use Mistral OCR to get the markdown of each page.
    Insert <<page>> tags. For the images, convert to base64 and insert reference tags.
    Uses the PDF base64 from ProcessedDocument.
    Modifies the document pages in place.
    """
    logger.info("Extracting markdown from pages using Mistral OCR...")
    
    # Step 1: Setup Mistral client
    client = create_mistral_client()
    document_spec = create_document_spec(document.pdf_base64)
    
    # Step 2: Call Mistral OCR API
    logger.info("Calling Mistral OCR API...")
    ocr_response = client.ocr.process(
        model=MODEL,
        document=document_spec,
        include_image_base64=True
    )
    
    # Step 3: Process each page from OCR response
    logger.info(f"Processing {len(ocr_response.pages)} pages from OCR response")
    
    for ocr_page in ocr_response.pages:
        page_index = ocr_page.index
        page_markdown = ocr_page.markdown
        
        # Find corresponding ProcessedPage (page_index is 0-based, page_number is 1-based)
        matching_page = None
        for page in document.pages:
            if page.page_number == page_index + 1:
                matching_page = page
                break
        
        if not matching_page:
            logger.warning(f"No matching ProcessedPage found for OCR page {page_index}")
            raise
        
        # Step 4: Set OCR markdown (clean, no page tags needed)
        matching_page.ocr_markdown = page_markdown
        
        # Step 5: Extract images from OCR response
        ocr_images = getattr(ocr_page, "images", []) or []
        
        # Get original page dimensions from OCR response for coordinate transformation
        page_dimensions = getattr(ocr_page, "dimensions", None)
        if page_dimensions:
            original_width = getattr(page_dimensions, "width", None)
            original_height = getattr(page_dimensions, "height", None)
        else:
            original_width = None
            original_height = None
        
        # Get resized page dimensions from our stored page
        resized_width = matching_page.width
        resized_height = matching_page.height
        
        # Calculate scale factors for coordinate transformation
        if original_width and original_height and resized_width and resized_height:
            scale_x = resized_width / original_width  
            scale_y = resized_height / original_height
            logger.info(f"Page {page_index + 1}: original={original_width}x{original_height}, resized={resized_width}x{resized_height}, scale=({scale_x:.3f}, {scale_y:.3f})")
        else:
            scale_x = 1.0
            scale_y = 1.0
            logger.warning(f"Page {page_index + 1}: Could not determine scale factors for coordinate transformation - using 1.0")
        
        for ocr_image in ocr_images:
            # Extract bounding box coordinates (in original page coordinate system)
            orig_top_left_x = ocr_image.top_left_x
            orig_top_left_y = ocr_image.top_left_y
            orig_bottom_right_x = ocr_image.bottom_right_x
            orig_bottom_right_y = ocr_image.bottom_right_y
            
            # Transform coordinates to resized image coordinate system
            top_left_x = int(orig_top_left_x * scale_x)
            top_left_y = int(orig_top_left_y * scale_y)
            bottom_right_x = int(orig_bottom_right_x * scale_x) 
            bottom_right_y = int(orig_bottom_right_y * scale_y)
            
            # Extract base64 image data
            image_data_url = ocr_image.image_base64
            if not image_data_url:
                logger.warning(f"No image data for image on page {page_index + 1}")
                raise
            
            image_base64 = extract_base64_from_data_url(image_data_url)
            
            # Create ProcessedImage with transformed coordinates
            processed_image = ProcessedImage(
                img_base64=image_base64,
                page_number=page_index + 1,
                top_left_x=top_left_x,
                top_left_y=top_left_y,
                bottom_right_x=bottom_right_x,
                bottom_right_y=bottom_right_y
            )
            matching_page.images.append(processed_image)
        
        logger.info(f"Page {page_index + 1}: OCR complete, found {len(ocr_images)} images")
    
    logger.info(f"Mistral OCR processing complete for {len(document.pages)} pages")
