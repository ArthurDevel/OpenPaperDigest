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
        print(f"  Warning: Could not find h1 tag for {arxiv_id}")
        return None
    
    # Clean up HTML tags and whitespace
    title = match.group(1)
    title = re.sub(r'<[^>]+>', '', title).strip()
    
    return title if title else None

def test_failing_papers():
    """
    Test title extraction for the papers that are failing in the DAG.
    """
    # These are the papers from the error log
    failing_papers = [
        "2511.21631",
        "2511.21140",
        "2511.21689",
        "2511.21395",
        "2511.21688",
        "2511.21686",
        "2511.21691",
        "2511.21678",
        "2511.21690",
        "2511.21622"
    ]
    
    print("Testing title extraction from h1 tag for failing papers:\n")
    
    success_count = 0
    fail_count = 0
    
    for arxiv_id in failing_papers:
        print(f"Testing {arxiv_id}...")
        title = fetch_title_from_h1(arxiv_id)
        
        if title:
            print(f"  ✓ SUCCESS: '{title[:100]}...'")
            success_count += 1
        else:
            print(f"  ✗ FAILED: Could not extract title")
            fail_count += 1
        print()
    
    print(f"\n=== SUMMARY ===")
    print(f"Success: {success_count}/{len(failing_papers)}")
    print(f"Failed: {fail_count}/{len(failing_papers)}")
    
    if success_count == len(failing_papers):
        print("\n✓ All papers can have titles extracted from h1!")
        return True
    else:
        print(f"\n⚠️  {fail_count} papers still failed")
        return False

if __name__ == "__main__":
    test_failing_papers()

