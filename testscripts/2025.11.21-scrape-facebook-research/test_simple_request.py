#!/usr/bin/env python3
"""
Test simple HTTP request to Facebook Research publications page.
"""

import requests
from bs4 import BeautifulSoup


def test_simple_request():
    """Test simple HTTP GET request."""
    url = "https://research.facebook.com/publications/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    print(f"Testing simple HTTP request to: {url}")
    print("=" * 80)
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        print(f"Status code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type')}")
        print(f"Content length: {len(response.content)} bytes")
        print()
        
        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        print(f"Page title: {soup.title.string if soup.title else 'No title'}")
        print()
        
        # Check for common elements
        print("Looking for common elements:")
        print(f"  - article tags: {len(soup.find_all('article'))}")
        print(f"  - div tags: {len(soup.find_all('div'))}")
        print(f"  - a tags: {len(soup.find_all('a'))}")
        print()
        
        # Check for keywords in content
        content_lower = response.text.lower()
        keywords = ['publication', 'paper', 'arxiv', 'pdf', 'research', 'blocked', 'freedom']
        print("Keyword occurrences in content:")
        for keyword in keywords:
            count = content_lower.count(keyword)
            print(f"  - '{keyword}': {count}")
        print()
        
        # Save the HTML for inspection
        with open('facebook_research_page.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        print("Full HTML saved to: facebook_research_page.html")
        
        # Show first 1000 characters of body
        print("\nFirst 1000 characters of response:")
        print("=" * 80)
        print(response.text[:1000])
        
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    test_simple_request()
