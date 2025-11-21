#!/usr/bin/env python3
"""
Simple test to check if we can access the Hugging Face trending page with requests.
This helps determine if we need Selenium (for JavaScript) or if simple HTTP requests work.
"""

import requests
from bs4 import BeautifulSoup


### CONSTANTS ###

HUGGINGFACE_TRENDING_URL = "https://huggingface.co/papers/trending"


### HELPER FUNCTIONS ###

def test_simple_request():
    """
    Test if we can get content with a simple HTTP request.
    """
    print("=" * 80)
    print("Testing Simple HTTP Request to Hugging Face Trending Page")
    print("=" * 80)
    print()
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        print(f"Fetching: {HUGGINGFACE_TRENDING_URL}")
        response = requests.get(HUGGINGFACE_TRENDING_URL, headers=headers, timeout=30)
        response.raise_for_status()
        
        print(f"✓ Status Code: {response.status_code}")
        print(f"✓ Content Length: {len(response.content)} bytes")
        print(f"✓ Content Type: {response.headers.get('Content-Type', 'Unknown')}")
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Check for paper-related content
        print("\n--- Checking for paper-related content ---")
        
        # Look for paper links
        paper_links = soup.find_all('a', href=lambda x: x and '/papers/' in x)
        print(f"Found {len(paper_links)} links containing '/papers/'")
        
        # Look for arXiv links
        arxiv_links = soup.find_all('a', href=lambda x: x and 'arxiv' in x.lower() if x else False)
        print(f"Found {len(arxiv_links)} links containing 'arxiv'")
        
        # Look for article tags
        articles = soup.find_all('article')
        print(f"Found {len(articles)} <article> tags")
        
        # Check if content seems to be JavaScript-rendered
        print("\n--- Checking if content is JavaScript-rendered ---")
        page_text = soup.get_text()
        
        # Common indicators of JS-rendered content
        js_indicators = [
            'react',
            'vue',
            'angular',
            'next.js',
            'nuxt',
            'loading',
            'hydrate',
        ]
        
        found_indicators = []
        for indicator in js_indicators:
            if indicator.lower() in page_text.lower() or indicator.lower() in response.text.lower():
                found_indicators.append(indicator)
        
        if found_indicators:
            print(f"⚠ Found JavaScript framework indicators: {', '.join(found_indicators)}")
            print("  This suggests the page might be JavaScript-rendered")
        else:
            print("  No obvious JavaScript framework indicators found")
        
        # Check if there's actual paper content or just a shell
        if len(paper_links) == 0 and len(articles) == 0:
            print("\n⚠ WARNING: No paper links or articles found in HTML")
            print("  This likely means the page is JavaScript-rendered")
            print("  You will need Selenium to scrape this page")
        else:
            print("\n✓ Found some content in HTML")
            print("  Simple HTTP requests might work, but Selenium is safer")
        
        # Save HTML for inspection in output folder
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(script_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "huggingface_trending_response.html")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"\n✓ HTML saved to: {output_file}")
        
    except requests.exceptions.RequestException as e:
        print(f"\n✗ Error making request: {e}")
        print("  This might indicate the page requires JavaScript or has anti-scraping measures")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")


### MAIN ENTRYPOINT ###

if __name__ == "__main__":
    test_simple_request()

