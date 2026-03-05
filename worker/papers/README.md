# Papers Module

This module handles paper storage, retrieval, and management. It provides a clean DTO-based module for working with papers.

Paper content (markdown, sections, figures, thumbnails, metadata) is stored in Supabase Storage. The database stores only relational metadata and small fields.

## models.py

Contains all Data Transfer Objects (DTOs) built with Pydantic for automatic validation and ORM conversion:

- **Paper** - Main paper DTO containing metadata and full content (pages, sections)
- **Page** - Simple page model with image data (used only during processing pipeline)
- **Section** - Document section with rewritten content
- **PaperSlug** - URL-safe paper slug for routing

See [models.py](./models.py) for complete DTO definitions and field details.

### DTO <-> Database Model Conversion

**Database Models:** SQLAlchemy models are separate in [db/models.py](./db/models.py) - these handle database persistence while DTOs handle business logic.

**Automatic Conversion:** Pydantic DTOs automatically convert from SQLAlchemy models using `model_validate()`:

```python
# Convert SQLAlchemy record to DTO (automatic field mapping)
record = get_paper_record(db, paper_uuid)
paper = Paper.model_validate(record)

# Convert list of records to DTOs
records = list_paper_records(db, statuses=['completed'], limit=10)
papers = [Paper.model_validate(record) for record in records]
```

**Built-in Functions:**
- `Paper.model_validate(record)` - Convert from SQLAlchemy model or dict
- `paper.to_orm()` - Convert to SQLAlchemy model for database operations
- `paper.model_dump()` - Convert to dict for JSON serialization
- `paper.model_dump_json()` - Convert directly to JSON string
- Automatic validation and type coercion on all field assignments

## storage.py

Supabase Storage client wrapper for paper assets. All heavy content lives in a `papers` bucket.

**Storage layout per paper:**
```
{paper_uuid}/
  thumbnail.png      -- first-page thumbnail
  content.md         -- final_markdown (raw OCR output)
  sections.json      -- rewritten sections array
  figures.json       -- figure metadata
  metadata.json      -- usage_summary, processing stats
  figures/
    {identifier}.png -- extracted figure images
```

**Key functions:**
- `upload_paper_assets()` - Upload all paper files after processing
- `download_paper_content()` - Download content.md, sections.json, figures.json, metadata.json
- `download_markdown()` - Download only content.md
- `get_thumbnail_url()` - Public URL for thumbnail
- `get_figure_url()` - Public URL for a figure image
- `delete_paper_assets()` - Delete all files for a paper

## client.py

Main API functions for paper operations:

- `save_paper(db, processed_content)` - Upload assets to Supabase Storage, then save metadata to database
- `get_paper(db, paper_uuid)` - Get paper metadata from DB + full content from storage
- `get_paper_metadata(db, paper_uuid)` - Get paper metadata only (fast, no storage call)
- `list_papers(db, statuses, limit)` - List papers with optional status filtering
- `list_minimal_papers(db, page, limit)` - List completed papers with thumbnail URLs for overview page
- `delete_paper(db, paper_uuid)` - Delete storage assets and database record
- `create_paper(db, ...)` - Create a new paper queued for processing
- `build_paper_slug(title, authors)` - Generate URL-safe slug from paper metadata
- `create_paper_slug(db, paper)` - Create unique slug for paper with collision checking
- `find_existing_paper_slug(db, paper_uuid)` - Find existing slug for paper

## db/

Database layer responsible for SQLAlchemy operations and transaction management.

- **models.py** - SQLAlchemy models (PaperRecord, PaperSlugRecord)
- **client.py** - Database operations (create, update, get records)

**Transaction Responsibility:** The `db/client.py` layer handles all database commits and transaction management.
