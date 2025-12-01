import requests
import re

def inspect_page(arxiv_id: str):
    """
    Inspect the actual page structure to see what's available.
    """
    paper_url = f"https://www.alphaxiv.org/abs/{arxiv_id}"
    
    print(f"Inspecting page for {arxiv_id}")
    print(f"URL: {paper_url}\n")
    
    try:
        response = requests.get(paper_url, timeout=10)
        response.raise_for_status()
        print(f"Status: {response.status_code}\n")
        
        # Check if page exists
        if response.status_code == 404:
            print("⚠️  Page returns 404 - paper may not exist on AlphaXiv")
            return
        
        # Look for JSON-LD
        jsonld_patterns = [
            r'<script[^>]*data-alphaxiv-id="json-ld-paper-detail-view"[^>]*>(.+?)</script>',
            r'<script[^>]*type="application/ld\+json"[^>]*>(.+?)</script>',
        ]
        
        print("=== Looking for JSON-LD ===")
        found_jsonld = False
        for pattern in jsonld_patterns:
            matches = re.findall(pattern, response.text, re.DOTALL)
            if matches:
                print(f"Found JSON-LD with pattern: {pattern[:50]}...")
                print(f"Number of matches: {len(matches)}")
                # Show first match (truncated)
                if matches:
                    jsonld_text = matches[0][:500]
                    print(f"First match (truncated):\n{jsonld_text}...")
                    found_jsonld = True
                    break
        
        if not found_jsonld:
            print("✗ No JSON-LD found")
        
        # Look for title in HTML
        print("\n=== Looking for title in HTML ===")
        title_patterns = [
            r'<h1[^>]*>(.+?)</h1>',
            r'<title>(.+?)</title>',
            r'<h2[^>]*>(.+?)</h2>',
            r'property="og:title"[^>]*content="([^"]+)"',
        ]
        
        for pattern in title_patterns:
            matches = re.findall(pattern, response.text, re.DOTALL | re.IGNORECASE)
            if matches:
                print(f"Found title with pattern: {pattern[:50]}...")
                for match in matches[:3]:  # Show first 3 matches
                    title = re.sub(r'<[^>]+>', '', match).strip()[:100]
                    if title:
                        print(f"  - '{title}...'")
        
        # Check page title
        print("\n=== Page title ===")
        title_match = re.search(r'<title>(.+?)</title>', response.text, re.IGNORECASE)
        if title_match:
            print(f"HTML title: {title_match.group(1)}")
        
        # Save a sample of the HTML for inspection
        print("\n=== Saving HTML sample ===")
        with open(f'/tmp/alphaxiv_{arxiv_id}_sample.html', 'w') as f:
            f.write(response.text[:5000])
        print(f"Saved first 5000 chars to /tmp/alphaxiv_{arxiv_id}_sample.html")
        
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Test with one of the failing papers
    inspect_page("2511.21631")
    print("\n" + "="*50 + "\n")
    # Also test with a recent paper that should exist
    inspect_page("2511.20000")

