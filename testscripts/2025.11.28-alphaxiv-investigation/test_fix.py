"""
Test the fix for title extraction issue.

This simulates what happens in the DAG:
1. Papers are scraped from homepage (title might be None)
2. When adding to queue, if title is None, fetch from paper page h1
"""
import requests
import re

def fetch_title_from_h1(arxiv_id: str) -> str:
    """
    Fetch title from h1 tag on paper page.
    
    Args:
        arxiv_id: The arXiv ID
        
    Returns:
        Title string or None if not found
    """
    paper_url = f"https://www.alphaxiv.org/abs/{arxiv_id}"
    
    try:
        response = requests.get(paper_url, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"  Warning: Failed to fetch paper page for {arxiv_id}: {e}")
        return None
    
    # Extract title from h1 tag
    match = re.search(r'<h1[^>]*>(.+?)</h1>', response.text, re.DOTALL | re.IGNORECASE)
    
    if not match:
        return None
    
    # Clean up HTML tags and whitespace
    title = match.group(1)
    title = re.sub(r'<[^>]+>', '', title).strip()
    
    return title if title else None

def simulate_dag_logic():
    """
    Simulate the DAG's add_top_papers_to_queue logic with the fix.
    """
    # Simulate papers that were scraped but have no title (like in the DAG)
    papers_without_titles = [
        {'universal_paper_id': '2511.21631', 'title': None},
        {'universal_paper_id': '2511.21140', 'title': None},
        {'universal_paper_id': '2511.21689', 'title': None},
        {'universal_paper_id': '2511.21395', 'title': None},
        {'universal_paper_id': '2511.21688', 'title': None},
        {'universal_paper_id': '2511.21686', 'title': None},
        {'universal_paper_id': '2511.21691', 'title': None},
        {'universal_paper_id': '2511.21678', 'title': None},
        {'universal_paper_id': '2511.21690', 'title': None},
        {'universal_paper_id': '2511.21622', 'title': None},
    ]
    
    print("=== Simulating DAG Logic with Fix ===\n")
    print(f"Processing {len(papers_without_titles)} papers without titles...\n")
    
    added_count = 0
    skipped_count = 0
    
    for rank, paper in enumerate(papers_without_titles, 1):
        arxiv_id = paper.get('universal_paper_id')
        title = paper.get('title')
        
        print(f"Paper {rank}: {arxiv_id}")
        
        # This is the fix: if title is None, fetch from paper page
        if not title:
            print(f"  Title missing, fetching from paper page...")
            title = fetch_title_from_h1(arxiv_id)
        
        if not title:
            print(f"  ✗ Skipping {arxiv_id} - no title found")
            skipped_count += 1
        else:
            print(f"  ✓ Title found: '{title[:80]}...'")
            print(f"  ✓ Would add {arxiv_id} to queue")
            added_count += 1
        
        print()
    
    print(f"\n=== Processing Queue Summary ===")
    print(f"Added: {added_count} papers")
    print(f"Skipped: {skipped_count} papers")
    print(f"===========================\n")
    
    if added_count == len(papers_without_titles):
        print("✓ SUCCESS: All papers can be processed with the fix!")
        return True
    else:
        print(f"⚠️  {skipped_count} papers still failed")
        return False

if __name__ == "__main__":
    success = simulate_dag_logic()
    exit(0 if success else 1)

