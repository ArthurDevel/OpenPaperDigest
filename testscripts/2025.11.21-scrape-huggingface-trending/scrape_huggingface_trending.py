#!/usr/bin/env python3
"""
Test script to scrape papers from Hugging Face trending papers page.
This script uses requests + BeautifulSoup since the content is server-rendered.
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from typing import List, Dict, Any, Optional


### CONSTANTS ###

HUGGINGFACE_TRENDING_URL = "https://huggingface.co/papers/trending"
MAX_PAPERS_TO_PROCESS = 50


### HELPER FUNCTIONS ###

def extract_arxiv_id_from_url(url: str) -> Optional[str]:
    """
    Extract arXiv ID from URL.
    
    Args:
        url: URL that may contain an arXiv ID
        
    Returns:
        Optional[str]: Extracted arXiv ID or None if not found
    """
    arxiv_match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+)', url, re.I)
    if arxiv_match:
        return arxiv_match.group(1)
    return None


def extract_arxiv_id_from_path(path: str) -> Optional[str]:
    """
    Extract arXiv ID from Hugging Face paper path like /papers/2511.16624.
    
    Args:
        path: Path like /papers/2511.16624
        
    Returns:
        Optional[str]: Extracted arXiv ID or None if not found
    """
    match = re.search(r'/papers/(\d{4}\.\d{4,5})', path)
    if match:
        return match.group(1)
    return None


def scrape_trending_page(url: str = HUGGINGFACE_TRENDING_URL) -> Dict[str, Any]:
    """
    Scrape Hugging Face trending papers page and extract paper information.
    
    Args:
        url: URL of the trending papers page
        
    Returns:
        Dict containing list of papers with information
    """
    print(f"Fetching trending papers page: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        print(f"✓ Status Code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to fetch trending page: {e}")
    
    # Parse HTML
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find all article elements (each represents a paper)
    articles = soup.find_all('article', class_=lambda x: x and 'rounded-xl' in x)
    print(f"Found {len(articles)} paper articles")
    
    result = {
        "url": url,
        "papers": []
    }
    
    papers_to_process = articles[:MAX_PAPERS_TO_PROCESS]
    print(f"\nProcessing {len(papers_to_process)} papers...\n")
    
    for idx, article in enumerate(papers_to_process, 1):
        try:
            paper_data = {
                "index": idx,
                "title": None,
                "arxiv_id": None,
                "arxiv_url": None,
                "paper_url": None,
                "upvotes": None,
                "github_stars": None,
            }
            
            # Extract title from h3 > a
            title_elem = article.find('h3')
            if title_elem:
                title_link = title_elem.find('a')
                if title_link:
                    paper_data["title"] = title_link.get_text(strip=True)
                    href = title_link.get('href', '')
                    if href:
                        # Extract ArXiv ID from path like /papers/2511.16624
                        arxiv_id = extract_arxiv_id_from_path(href)
                        if arxiv_id:
                            paper_data["arxiv_id"] = arxiv_id
                            paper_data["paper_url"] = f"https://huggingface.co{href}"
                            paper_data["arxiv_url"] = f"https://arxiv.org/abs/{arxiv_id}"
            
            # Look for ArXiv link directly
            if not paper_data["arxiv_id"]:
                arxiv_links = article.find_all('a', href=lambda x: x and 'arxiv.org' in x if x else False)
                for link in arxiv_links:
                    arxiv_id = extract_arxiv_id_from_url(link.get('href', ''))
                    if arxiv_id:
                        paper_data["arxiv_id"] = arxiv_id
                        paper_data["arxiv_url"] = link.get('href')
                        if not paper_data["paper_url"]:
                            # Try to find the HF paper link
                            hf_link = article.find('a', href=lambda x: x and '/papers/' in x if x else False)
                            if hf_link:
                                paper_data["paper_url"] = f"https://huggingface.co{hf_link.get('href')}"
                        break
            
            # Extract ArXiv ID from paper path if still not found
            if not paper_data["arxiv_id"]:
                hf_links = article.find_all('a', href=lambda x: x and '/papers/' in x if x else False)
                for link in hf_links:
                    arxiv_id = extract_arxiv_id_from_path(link.get('href', ''))
                    if arxiv_id:
                        paper_data["arxiv_id"] = arxiv_id
                        paper_data["arxiv_url"] = f"https://arxiv.org/abs/{arxiv_id}"
                        paper_data["paper_url"] = f"https://huggingface.co{link.get('href')}"
                        break
            
            # Extract upvotes from the div with class "font-semibold text-orange-500"
            upvote_div = article.find('div', class_=lambda x: x and 'text-orange-500' in x if x else False)
            if upvote_div:
                upvote_text = upvote_div.get_text(strip=True)
                try:
                    paper_data["upvotes"] = int(upvote_text)
                except ValueError:
                    pass
            
            # Extract GitHub stars from the GitHub link span
            github_link = article.find('a', href=lambda x: x and 'github.com' in x if x else False)
            if github_link:
                # Look for span with star count (usually has "k" notation like "2.61k")
                star_spans = github_link.find_all('span')
                for span in star_spans:
                    star_text = span.get_text(strip=True)
                    # Check if it looks like a star count (contains numbers and possibly 'k')
                    if re.match(r'^\d+\.?\d*k?$', star_text.lower()):
                        try:
                            # Handle "k" notation (e.g., "2.61k" = 2610)
                            if 'k' in star_text.lower():
                                star_value = float(star_text.lower().replace('k', ''))
                                paper_data["github_stars"] = int(star_value * 1000)
                            else:
                                paper_data["github_stars"] = int(star_text)
                            break
                        except ValueError:
                            pass
            
            # Print summary
            print(f"  Paper #{idx}:")
            print(f"    Title: {paper_data['title'] or 'Unknown'}")
            if paper_data['arxiv_id']:
                print(f"    ArXiv ID: {paper_data['arxiv_id']}")
                print(f"    ArXiv URL: {paper_data['arxiv_url']}")
            if paper_data['paper_url']:
                print(f"    HF Paper URL: {paper_data['paper_url']}")
            if paper_data['upvotes'] is not None:
                print(f"    Upvotes: {paper_data['upvotes']}")
            if paper_data['github_stars'] is not None:
                print(f"    GitHub Stars: {paper_data['github_stars']}")
            
            result["papers"].append(paper_data)
            
        except Exception as e:
            print(f"  Error processing paper #{idx}: {e}")
            continue
    
    return result


### MAIN ENTRYPOINT ###

def main():
    """Main function to run the scraper test."""
    import os
    
    print("=" * 80)
    print("Hugging Face Trending Papers Scraper Test (Requests + BeautifulSoup)")
    print("=" * 80)
    print()
    
    # Scrape trending page
    result = scrape_trending_page()
    
    # Save results to file in output folder
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, "output")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "huggingface_trending_scrape_results.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'=' * 80}")
    print(f"Results saved to: {output_file}")
    print(f"Total papers processed: {len(result.get('papers', []))}")
    
    # Print summary
    all_papers = result.get('papers', [])
    papers_with_arxiv = [p for p in all_papers if p.get('arxiv_id')]
    papers_with_url = [p for p in all_papers if p.get('paper_url')]
    papers_without_url = [p for p in all_papers if not p.get('paper_url')]
    
    print(f"Papers with ArXiv ID: {len(papers_with_arxiv)}")
    print(f"Papers with any paper URL: {len(papers_with_url)}")
    print(f"Papers without paper URL: {len(papers_without_url)}")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
