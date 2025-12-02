### 1. High-Level Goal

The primary objective is to create a backend service that accepts a PDF paper, processes it through a multi-step pipeline, and returns a comprehensive JSON object containing a structured, simplified, and summarized version of the original document.

### 2. Processing Pipeline & Data Flow

The backend will execute the following steps in sequence. Each step's output serves as the input for a subsequent step.

1.  **PDF to Image Conversion**
    *   **Description:** Convert each page of the uploaded PDF into a high-resolution, non-annotated PNG image.
    *   **Input:** A single PDF file.
    *   **Output:** An ordered list of file paths to the generated page images, stored temporarily.
        *   *Example:* `['/tmp/datasheet_xyz/page_1.png', '/tmp/datasheet_xyz/page_2.png', ...]`

2.  **Initial Content Extraction (Gemini 2.5 Flash)**
    *   **Description:** Process each page image to identify all headers, where assets (tables/figures) are located, and where they are mentioned in the text.
    *   **Input:** The list of page image paths from Step 1.
    *   **Output:** A JSON object with three lists: `headers`, `asset_locations`, and `asset_mentions`.
        *   `headers`: Flat list of all found headers.
            *   *Example:* `[{ "text": "1. Introduction", "page": 1 }, { "text": "1.1. Overview", "page": 1 }]`
        *   `asset_locations`: List of where each unique asset physically appears.
            *   *Example:* `[{ "type": "figure", "identifier": "Figure 3", "page": 6 }]`
        *   `asset_mentions`: List of every time an asset is referenced in the text.
            *   *Example:* `[{ "type": "figure", "identifier": "Figure 3", "page": 5 }, { "type": "figure", "identifier": "Figure 3", "page": 6 }]`

3.  **Table of Contents Generation (Gemini 2.5 Flash)**
    *   **Description:** Consolidate the flat list of `headers` into a hierarchical table of contents, calculating the start and end pages for each section.
    *   **Input:** The `headers` list from Step 2.
    *   **Output:** A hierarchical list of section objects. This structure forms the basis of the final `sections` array in the output. `rewritten_content` and `summary` are `null` at this stage.
        *   *Example:* `[{ "level": 1, "section_title": "1. Introduction", "start_page": 1, "end_page": 3, "subsections": [...] }, ...]`

4.  **Asset Explanation (Gemini 2.5 Pro)**
    *   **Description:** For each asset, generate a detailed explanation. The context provided to the LLM includes the full page image where the asset is located, plus all page images from the section(s) in which the asset is mentioned.
    *   **Input:** `asset_locations` and `asset_mentions` (from Step 2), the ToC (from Step 3), and all page images (from Step 1).
    *   **Output:** Two lists, `tables` and `figures`, containing objects with the identifier, a generated explanation, and paths to the relevant page images.
        *   *Example:* `[{ "table_identifier": "Table 1", "location_page": 2, "explanation": "This table details...", "referenced_on_pages": [2, 4], "image_path": "/tmp/datasheet_xyz/page_2.png" }]`

5.  **Section Processing (Gemini 2.5 Pro)**
    *   **Description:** This step runs two separate processes for each **top-level section** identified in the Table of Contents.
    *   **Input:** The ToC (from Step 3) and the page images (from Step 1).
    *   **5a. Rewrite Section:** For a given section, make an LLM call with all of that section's page images to generate a rewritten, simplified version of the text.
    *   **5b. Summarize Section:** For the same section, make a *separate* LLM call with all of that section's page images to generate a concise summary.
    *   **Output:** The hierarchical ToC data structure from Step 3, now with the `rewritten_content` and `summary` fields populated for all top-level sections from the results of these calls.

### 3. API Endpoint

We will use a single, synchronous API endpoint. The client will upload the PDF and wait for the full JSON response.

*   **Endpoint:** `POST /api/papers/process`
*   **Request:** `multipart/form-data` containing the PDF file.
*   **Response:** A single JSON object with the structure defined below.

### 4. Final JSON Output Structure

The API will return the following JSON object. Note the recursive structure for `sections` to capture the full hierarchy.

```json
{
  "paper_id": "string",
  "title": "string",
  "sections": [
    {
      "level": "integer",
      "section_title": "string",
      "start_page": "integer",
      "end_page": "integer",
      "rewritten_content": "string | null",
      "summary": "string | null",
      "subsections": [
        
      ]
    }
  ],
  "tables": [
    {
      "table_identifier": "string",
      "location_page": "integer",
      "explanation": "string",
      "image_path": "string",
      "referenced_on_pages": ["integer"]
    }
  ],
  "figures": [
    {
      "figure_identifier": "string",
      "location_page": "integer",
      "explanation": "string",
      "image_path": "string",
      "referenced_on_pages": ["integer"]
    }
  ]
}
```

### 5. Proposed File Structure

To implement this, we will add the following new files to the existing structure.

```
api/
|-- endpoints/
|   |-- paper_processing_endpoints.py  # <-- NEW: API endpoint logic
|-- types/
|   |-- paper_processing_api_models.py # <-- NEW: Pydantic models for JSON
paperprocessor/
|-- client.py                          # <-- MODIFIED: Orchestrates the pipeline
|-- prompts/                           # <-- EXISTING
|   |-- 1_extract_content.md           # <-- EXISTING
|   |-- 2_generate_toc.md              # <-- EXISTING
|   |-- 3_explain_asset.md             # <-- EXISTING
|   |-- 4_rewrite_section.md           # <-- EXISTING
|   |-- 5_summarize_section.md         # <-- EXISTING
```

### 6. LLM Integration

*   **Configuration:** API keys and model names for OpenRouter will be managed via environment variables.
*   **Prompts:** Each distinct call to an LLM will have its prompt defined in a dedicated markdown file within `paperprocessor/prompts/`. This keeps prompts separate from the core application logic and makes them easy to manage and version.
*   **Models:**
    *   `gemini-2.5-flash`: Used for the high-volume, lower-complexity tasks of content extraction and table of contents generation.
    *   `gemini-2.5-pro`: Used for the high-quality generation tasks of rewriting, summarizing, and explaining.

### 7. Frontend Plan [not started]

The frontend will provide a new, separate page for testing the paper processing service. This will not affect any existing frontend pages or components.

#### 7.1. User Interface & Flow [not started]

1.  **New Page:** A new page will be created at the `/quicktest` route.
2.  **Upload View:** This page (`/quicktest`) will feature a file upload input.
3.  **Processing State:** Upon submitting a PDF, the UI will show a loading indicator.
4.  **Results Display:** Once the API returns the final JSON, the frontend will display the raw JSON response in a readable, pretty-printed format directly on the page.

#### 7.2. File Structure [not started]

To implement this, we will add a new `quicktest` directory and page. All existing files at `frontend/app/` will remain unchanged.

```
frontend/
|-- app/
    |-- page.tsx           # <-- EXISTING, UNCHANGED
    |-- layout.tsx         # <-- EXISTING, UNCHANGED
    |-- quicktest/         # <-- NEW Route group [not started]
        |-- page.tsx       # <-- NEW file for upload and display [not started]
|-- components/            # <-- EXISTING, UNCHANGED
```

This ensures the new test page is completely isolated from the current application.

