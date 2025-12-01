import requests
import re
import json

def fetch_title_from_jsonld(arxiv_id: str) -> str:
    """
    Fetch title from JSON-LD on paper page.
    
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
    
    # Extract JSON-LD data from the page
    match = re.search(
        r'<script data-alphaxiv-id="json-ld-paper-detail-view" type="application/ld\+json">(.+?)</script>',
        response.text,
        re.DOTALL
    )
    
    if not match:
        print(f"  Warning: Could not find JSON-LD data for {arxiv_id}")
        return None
    
    try:
        json_ld = json.loads(match.group(1))
        # JSON-LD typically has 'name' or 'headline' for title
        title = json_ld.get('name') or json_ld.get('headline')
        return title
    except json.JSONDecodeError as e:
        print(f"  Warning: Failed to parse JSON-LD for {arxiv_id}: {e}")
        return None

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
    
    print("Testing title extraction from JSON-LD for failing papers:\n")
    
    success_count = 0
    fail_count = 0
    
    for arxiv_id in failing_papers:
        print(f"Testing {arxiv_id}...")
        title = fetch_title_from_jsonld(arxiv_id)
        
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
        print("\n✓ All papers can have titles extracted from JSON-LD!")
        return True
    else:
        print(f"\n⚠️  {fail_count} papers still failed")
        return False

if __name__ == "__main__":
    test_failing_papers()

