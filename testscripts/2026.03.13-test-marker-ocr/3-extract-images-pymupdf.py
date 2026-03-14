"""
Test PyMuPDF image extraction from PDF papers.

Extracts all embedded images from a sample PDF using PyMuPDF's
get_images() and get_image_rects() APIs. Saves each image with
its bounding box coordinates for comparison against Mistral OCR.

- Extracts embedded image objects from each page
- Gets bounding box coordinates per image
- Saves images to disk with metadata
"""

import os
import urllib.request

import fitz  # PyMuPDF

# ============================================================================
# CONSTANTS
# ============================================================================

DOCUMENT_URL = "https://arxiv.org/pdf/2508.13149"
IMAGES_SUBDIR = "extracted_images"

# ============================================================================
# MAIN LOGIC
# ============================================================================

script_dir = os.path.dirname(os.path.abspath(__file__))
images_dir = os.path.join(script_dir, IMAGES_SUBDIR)
os.makedirs(images_dir, exist_ok=True)

# Download PDF
pdf_path = os.path.join(script_dir, "temp.pdf")
print(f"Downloading PDF from {DOCUMENT_URL}...")
urllib.request.urlretrieve(DOCUMENT_URL, pdf_path)

doc = fitz.open(pdf_path)
total_images = 0

for page_num in range(len(doc)):
    page = doc.load_page(page_num)
    image_list = page.get_images(full=True)

    if not image_list:
        continue

    print(f"\nPage {page_num + 1}: {len(image_list)} embedded image(s)")

    for img_idx, img_info in enumerate(image_list):
        xref = img_info[0]
        width = img_info[2]
        height = img_info[3]

        # Get bounding box(es) for this image on the page
        rects = page.get_image_rects(xref)

        # Extract the raw image bytes
        base_image = doc.extract_image(xref)
        image_bytes = base_image["image"]
        image_ext = base_image["ext"]

        # Save image
        filename = f"page{page_num + 1}_img{img_idx + 1}.{image_ext}"
        filepath = os.path.join(images_dir, filename)
        with open(filepath, "wb") as f:
            f.write(image_bytes)

        # Print metadata
        for rect in rects:
            print(f"  [{filename}] size={width}x{height}, "
                  f"bbox=({rect.x0:.0f}, {rect.y0:.0f}, {rect.x1:.0f}, {rect.y1:.0f})")

        total_images += 1

# Clean up
os.remove(pdf_path)

print(f"\nTotal images extracted: {total_images}")
print(f"Saved to: {images_dir}/")
