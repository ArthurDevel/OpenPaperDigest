#!/usr/bin/env python3
"""
Test script to scrape papers from Google Research blog.
This script uses Selenium to handle JavaScript-rendered content.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import json
import re
import time
from typing import List, Dict, Any, Optional


GOOGLE_RESEARCH_BLOG_URL = "https://research.google/blog/"
MAX_POSTS_TO_PROCESS = 10


def setup_driver():
    """Set up Selenium Chrome driver with headless options."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    return driver


def scrape_blog_page(url: str = GOOGLE_RESEARCH_BLOG_URL) -> Dict[str, Any]:
    """
    Scrape blog listing page and get URLs to individual posts.

    Args:
        url: URL of the blog page to scrape

    Returns:
        Dict containing list of blog post URLs
    """
    print(f"Fetching blog listing: {url}")
    print("Initializing Selenium Chrome driver...")

    driver = setup_driver()

    try:
        driver.get(url)
        print("Page loaded, waiting for content to render...")

        # Wait for blog posts to load
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/blog/']"))
            )
            print("Blog posts detected!")
        except Exception as e:
            print(f"Warning: Timeout waiting for blog posts: {e}")

        # Give extra time for JavaScript to fully render
        time.sleep(2)

        # Find all blog post links
        print("\n--- Extracting blog post URLs ---\n")

        blog_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/blog/']")

        # Filter for actual blog post URLs (not RSS, labels, or the main page)
        seen_urls = set()
        blog_post_urls = []

        for link in blog_links:
            href = link.get_attribute('href')
            if (href and
                href != url and
                href not in seen_urls and
                '/blog/' in href and
                '/label/' not in href and  # Skip category pages
                '/rss' not in href and     # Skip RSS
                href.count('/') > 4):      # Actual posts have more path segments

                seen_urls.add(href)
                blog_post_urls.append(href)

        print(f"Found {len(blog_post_urls)} unique blog post URLs")

        # Now visit each blog post and extract arXiv/PDF links
        result = {
            "url": url,
            "posts": []
        }

        # Process limited number of blog posts
        posts_to_process = blog_post_urls[:MAX_POSTS_TO_PROCESS]
        print(f"\nProcessing {len(posts_to_process)} blog posts (out of {len(blog_post_urls)} found)...\n")
        for idx, post_url in enumerate(posts_to_process, 1):
            print(f"\n--- Processing post #{idx}/{len(posts_to_process)}: {post_url} ---")
            post_data = scrape_individual_post(driver, post_url, idx)
            if post_data:
                result["posts"].append(post_data)
            time.sleep(1)  # Be nice to the server

        return result

    finally:
        driver.quit()
        print("\nBrowser closed")


def scrape_individual_post(driver, post_url: str, index: int) -> Optional[Dict[str, Any]]:
    """
    Visit an individual blog post and extract paper links.

    Args:
        driver: Selenium WebDriver instance
        post_url: URL of the blog post
        index: Index number for display

    Returns:
        Dict containing post data and paper links
    """
    try:
        driver.get(post_url)
        time.sleep(2)  # Wait for page to render

        # Extract title
        title = None
        try:
            title_element = driver.find_element(By.CSS_SELECTOR, "h1")
            title = title_element.text.strip()
        except:
            title = driver.title

        # First, look for the "Paper" link in quicklinks (the primary paper link)
        paper_url = None
        arxiv_id = None

        try:
            # Find quicklinks items with text "Paper"
            quicklink_items = driver.find_elements(By.CSS_SELECTOR, ".quicklinks__item")
            for item in quicklink_items:
                link = item.find_element(By.TAG_NAME, "a")
                link_text = item.text.strip()

                if link_text.lower() == "paper":
                    href = link.get_attribute('href')
                    paper_url = href

                    # Extract arxiv_id if it's an arxiv link (both /abs/ and /pdf/ formats)
                    arxiv_match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+)', href, re.I)
                    if arxiv_match:
                        arxiv_id = arxiv_match.group(1)

                    break
        except:
            pass

        # Also collect any other arXiv links mentioned in the blog post content
        additional_arxiv_links = []
        all_links = driver.find_elements(By.TAG_NAME, "a")

        for link in all_links:
            href = link.get_attribute('href')
            if not href:
                continue

            # Check for arXiv links (both /abs/ and /pdf/ formats)
            arxiv_match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+)', href, re.I)
            if arxiv_match:
                link_arxiv_id = arxiv_match.group(1)
                # Skip if this is the main paper link we already captured
                if link_arxiv_id != arxiv_id:
                    additional_arxiv_links.append({
                        "arxiv_id": link_arxiv_id,
                        "url": href,
                        "link_text": link.text.strip()
                    })

        post_data = {
            "index": index,
            "title": title,
            "url": post_url,
            "paper_url": paper_url,
            "arxiv_id": arxiv_id,
            "additional_arxiv_links": additional_arxiv_links
        }

        # Print summary
        print(f"  Title: {title}")
        if paper_url:
            print(f"  Paper URL: {paper_url}")
            if arxiv_id:
                print(f"  ArXiv ID: {arxiv_id}")
        else:
            print(f"  Paper URL: None")

        if additional_arxiv_links:
            print(f"  Additional arXiv links: {len(additional_arxiv_links)}")
            for arxiv in additional_arxiv_links[:3]:  # Show first 3
                print(f"    - {arxiv['arxiv_id']}: {arxiv['link_text'][:60]}")

        return post_data

    except Exception as e:
        print(f"  Error scraping post: {e}")
        return None


def main():
    """Main function to run the scraper test."""
    import os

    print("=" * 80)
    print("Google Research Blog Scraper Test (Selenium)")
    print("=" * 80)
    print()

    # Scrape first page
    result = scrape_blog_page()

    # Save results to file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, "google_research_blog_scrape_results.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 80}")
    print(f"Results saved to: {output_file}")
    print(f"Total posts found: {len(result.get('posts', []))}")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
