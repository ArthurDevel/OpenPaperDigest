from typing import List
from PIL import Image
import fitz  # PyMuPDF
import io
import asyncio
import logging

logger = logging.getLogger(__name__)


def _resize_to_max(image: Image.Image, max_width: int, max_height: int) -> Image.Image:
    """
    Downscale the image to fit within (max_width x max_height) while preserving
    aspect ratio. If the image already fits, return it unchanged.
    """
    width, height = image.size
    if width <= max_width and height <= max_height:
        return image

    scale_w = max_width / float(width)
    scale_h = max_height / float(height)
    scale = min(scale_w, scale_h)

    new_width = max(1, int(width * scale))
    new_height = max(1, int(height * scale))

    try:
        resample = Image.Resampling.LANCZOS  # Pillow >= 9.1.0
    except AttributeError:  # Pillow < 9.1.0
        resample = Image.LANCZOS

    return image.resize((new_width, new_height), resample=resample)


async def convert_pdf_to_images(pdf_bytes: bytes, max_pages: int = 3) -> List[Image.Image]:
    """
    Converts the first pages of a PDF document into PIL Image objects.

    Only the first max_pages are converted, since the pipeline only needs them
    for metadata extraction (first 3 pages) and thumbnail (first page).

    Args:
        pdf_bytes: The byte content of the PDF file.
        max_pages: Maximum number of pages to convert (default: 3).

    Returns:
        A list of PIL Image objects, one for each converted page.
    """
    logger.info("Converting PDF to images...")

    try:
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_to_convert = min(len(pdf_document), max_pages)
        images = []
        for page_num in range(pages_to_convert):
            page = pdf_document.load_page(page_num)
            
            # Render page to a pixmap (an image)
            # The higher the dpi, the higher the resolution
            pix = page.get_pixmap(dpi=300)
            
            # Convert pixmap to a PIL Image
            img_bytes = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_bytes))

            # Downscale to fit within 1080x1920 if larger
            orig_width, orig_height = image.size
            resized_image = _resize_to_max(image, max_width=1080, max_height=1920)

            images.append(resized_image)
            
            # Log page image details
            logger.info(
                f"PDF->Image page {page_num + 1}: original={orig_width}x{orig_height} px, "
                f"resized={resized_image.width}x{resized_image.height} px"
            )
            
        logger.info(f"Converted {len(images)} of {len(pdf_document)} PDF pages to images.")
        return images
        
    except Exception as e:
        logger.error(f"Failed to convert PDF to images: {e}")
        raise
