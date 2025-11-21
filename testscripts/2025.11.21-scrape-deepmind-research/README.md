# DeepMind Research Publications Scraper Test

Test scripts for scraping papers from https://deepmind.google/research/publications/

## Directory Structure

```
2025.11.21-scrape-deepmind-research/
├── README.md                              # This file
├── debug_page_structure.py                # Debug individual publication pages
├── scrape_deepmind_research.py            # Single page scraper (10 pubs)
├── scrape_deepmind_multipage.py           # Multi-page scraper (configurable)
├── test_pagination.py                     # Test pagination detection
├── test_pagination_navigation.py          # Test URL-based pagination
├── deepmind_research_scrape_results.json  # Single page results
└── deepmind_research_multipage_results.json  # Multi-page results
```

## Test Results Summary

### Page Structure
- **Publications per page**: ~30
- **Pagination**: URL-based pattern `/page/1/`, `/page/2/`, etc.
- **Total pages**: 8+ (verified up to page 5)
- **Paper link formats**: arXiv (majority), direct PDF links

### Multi-Page Test Results (3 pages)
- **Total publications**: 90
- **Publications with paper links**: 58 (64%)
  - arXiv papers: 50
  - PDF papers: 8
- **Publications without links**: 32 (36%)

### Paper Link Distribution
Most DeepMind publications link to arXiv. The scraper successfully:
- ✅ Extracts arXiv IDs from publication pages
- ✅ Finds direct PDF links to other sources
- ✅ Handles publications without paper links

## Scripts

### 1. `debug_page_structure.py`
Inspect individual publication pages to understand structure and find paper links.

**Usage:**
```bash
python3 debug_page_structure.py
```

**Features:**
- Opens browser in non-headless mode
- Lists all links on the page
- Highlights PDF and arXiv links
- Waits for user input before closing

### 2. `scrape_deepmind_research.py`
Single-page scraper that processes the first 10 publications.

**Usage:**
```bash
python3 scrape_deepmind_research.py
```

**Output:** `deepmind_research_scrape_results.json`

### 3. `scrape_deepmind_multipage.py` ⭐ RECOMMENDED
Multi-page scraper with pagination support.

**Usage:**
```bash
python3 scrape_deepmind_multipage.py
```

**Configuration:**
```python
MAX_PAGES_TO_SCRAPE = 3  # Adjust number of pages
```

**Output:** `deepmind_research_multipage_results.json`

**Features:**
- Scrapes multiple pages using URL pattern
- Tracks page number for each publication
- Provides detailed statistics by page

### 4. `test_pagination.py`
Tests pagination detection on the main listing page.

**Usage:**
```bash
python3 test_pagination.py
```

**Findings:**
- Pagination container detected
- 8 pages total
- No infinite scroll
- 30 publications per page

### 5. `test_pagination_navigation.py`
Tests URL-based pagination navigation.

**Usage:**
```bash
python3 test_pagination_navigation.py
```

**Features:**
- Tests direct URL access pattern
- Validates pagination across multiple pages
- Confirms unique publications per page

## Key Findings

### URL Pattern
```
Page 1: https://deepmind.google/research/publications/
Page 2: https://deepmind.google/research/publications/page/2/
Page 3: https://deepmind.google/research/publications/page/3/
...
```

### Publication Page Structure
Individual publication pages contain:
- Title (h1 element)
- Publication date (optional)
- Paper links (arXiv or PDF) - typically with "View publication" or "Download" text
- Not all publications have paper links available

### Scraped Data Structure
```json
{
  "base_url": "https://deepmind.google/research/publications",
  "pages_scraped": 3,
  "publications": [
    {
      "index": 1,
      "title": "Paper Title",
      "url": "https://deepmind.google/research/publications/...",
      "paper_url": "https://arxiv.org/abs/...",
      "arxiv_id": "2510.26396",
      "pdf_hash": null,
      "publication_date": null,
      "page_number": 1
    }
  ]
}
```

## Requirements

- Python 3.x
- Selenium
- Chrome WebDriver
- requests

## Comparison with Microsoft Research Scraper

| Feature | Microsoft Research | DeepMind |
|---------|-------------------|----------|
| Pagination | URL-based | URL-based |
| Pubs per page | ~varies | ~30 |
| Paper links | Mixed (arXiv, PDF) | Mostly arXiv |
| Link location | "Related resources" sidebar | Main content area |
| Success rate | ~varies | ~64% |

## Next Steps

For production scraper integration:
1. Adjust `MAX_PAGES_TO_SCRAPE` based on needs
2. Enable PDF hash computation for non-arXiv papers (currently disabled for speed)
3. Add retry logic for failed downloads
4. Implement incremental scraping (track last scraped date)
5. Add duplicate detection across runs
