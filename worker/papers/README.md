# Papers Module

This module handles paper storage, retrieval, and management. It provides a clean DTO-based module for working with papers.

## models.py

Contains all Data Transfer Objects (DTOs) built with Pydantic for automatic validation and ORM conversion:

- **Paper** - Main paper DTO containing metadata and full content (pages, sections)
- **Page** - Simple page model with image data
- **Section** - Document section with rewritten content  
- **PaperSlug** - URL-safe paper slug for routing

See [models.py](./models.py) for complete DTO definitions and field details.

### DTO ↔ Database Model Conversion

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

**Bidirectional Conversion:**
```python
# SQLAlchemy → DTO (automatic field mapping)
record = get_paper_record(db, paper_uuid)
paper = Paper.model_validate(record)

# DTO → SQLAlchemy (for database writes)
paper = Paper(paper_uuid="123", arxiv_id="456", title="Test")
record = paper.to_orm()
db.add(record)
```

## client.py

Main API functions for paper operations:

- `save_paper(db: Session, processed_content: ProcessedDocument) -> Paper` - Save processed document to database and JSON
- `get_paper(db: Session, paper_uuid: str) -> Paper` - Get complete paper with metadata and content loaded from JSON
- `get_paper_metadata(db: Session, paper_uuid: str) -> Paper` - Get paper metadata only (fast, no JSON loading)
- `list_papers(db: Session, statuses: Optional[List[str]], limit: int) -> List[Paper]` - List papers with optional status filtering
- `delete_paper(db: Session, paper_uuid: str) -> bool` - Delete paper and associated files
- `build_paper_slug(title: Optional[str], authors: Optional[str]) -> str` - Generate URL-safe slug from paper metadata
- `create_paper_slug(db: Session, paper: Paper) -> PaperSlug` - Create unique slug for paper with collision checking
- `find_existing_paper_slug(db: Session, paper_uuid: str) -> Optional[PaperSlug]` - Find existing slug for paper

## db/

Database layer responsible for SQLAlchemy operations and transaction management.

- **models.py** - SQLAlchemy models (PaperRecord, PaperSlugRecord)
- **client.py** - Database operations (create, update, get records)

**Transaction Responsibility:** The `db/client.py` layer handles all database commits and transaction management.
