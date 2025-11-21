# Hugging Face Trending Papers Scraper Tests

This folder contains test scripts to explore and scrape the Hugging Face trending papers page: https://huggingface.co/papers/trending

## Scripts

### 1. `test_simple_request.py`
**Purpose**: Test if the page can be accessed with simple HTTP requests (no JavaScript).

**Usage**:
```bash
python test_simple_request.py
```

**What it does**:
- Makes a simple HTTP GET request to the trending page
- Checks if content is available in the HTML (vs JavaScript-rendered)
- Saves the HTML response for inspection
- Helps determine if Selenium is needed

### 2. `debug_page_structure.py`
**Purpose**: Inspect the structure of the trending page to understand how papers are displayed.

**Usage**:
```bash
python debug_page_structure.py
```

**What it does**:
- Opens the page in a browser (non-headless for visibility)
- Identifies paper card elements and their selectors
- Finds all links on the page
- Checks for pagination or infinite scroll
- Saves page source HTML for manual inspection

**Note**: This script opens a visible browser window. Press Enter to close it when done.

### 3. `test_pagination_simple.py`
**Purpose**: Test if the page uses pagination (URL-based) or infinite scroll.

**Usage**:
```bash
python test_pagination_simple.py
```

**What it does**:
- Tests infinite scroll by scrolling the page
- Tests URL-based pagination by trying different URL parameters
- Reports which pagination method is used

### 4. `scrape_huggingface_trending.py`
**Purpose**: Main scraper to extract paper information from the trending page.

**Usage**:
```bash
python scrape_huggingface_trending.py
```

**What it does**:
- Loads the trending page with Selenium
- Scrolls to load more papers (if infinite scroll)
- Extracts paper information from each card:
  - Title
  - ArXiv ID and URL
  - Upvotes
  - GitHub stars
  - Authors (if available)
- Saves results to `huggingface_trending_scrape_results.json`

## Configuration

Edit constants at the top of each script:
- `HUGGINGFACE_TRENDING_URL`: The URL to scrape
- `MAX_PAPERS_TO_PROCESS`: Maximum number of papers to process (in main scraper)

## Dependencies

Required Python packages:
- `selenium` - For browser automation
- `requests` - For HTTP requests
- `beautifulsoup4` - For HTML parsing (in test_simple_request.py)

Install with:
```bash
pip install selenium requests beautifulsoup4
```

You also need ChromeDriver installed and in your PATH.

## Expected Output

After running the main scraper, you should get:
- `huggingface_trending_scrape_results.json` - JSON file with scraped paper data
- Console output showing progress and summary statistics

## Notes

- The trending page likely uses JavaScript rendering, so Selenium is probably required
- The page might use infinite scroll rather than traditional pagination
- Paper cards may need different selectors depending on Hugging Face's current page structure

