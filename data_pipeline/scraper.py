"""
Wiki-dle Data Pipeline - MediaWiki API Scraper

This module implements a robust, rate-limited MediaWiki API client with a local
file-based caching layer. It is designed to perform a Breadth-First Search (BFS)
crawl starting from highly connected seed articles to collect Wikipedia pages
and their outgoing links, building the foundation for our closed-universe graph.

DSA Interview Prep - Crawling Complexity:
- Time Complexity:
  - Fetching a page's links: O(L) where L is the number of outgoing links. The
    MediaWiki API limits pllimit to 500, requiring O(L / 500) HTTP requests.
  - Crawling V vertices: O(V * L_avg) where L_avg is the average number of outgoing links.
- Space Complexity:
  - Cache Storage: O(V * L_avg) on disk to store the adjacency list.
  - Crawling Queue & Visited Set: O(V) in-memory space complexity. The visited set
    takes O(V) space, and the BFS queue takes O(W) where W is the maximum width of the
    BFS tree (at most V).
"""

import os
import time
import json
import hashlib
import logging
from typing import List, Dict, Set, Optional, Tuple
import requests

# Set up logging for visibility during offline execution
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class WikiScraper:
    """
    A polite, rate-limited scraper for the MediaWiki API with a local file cache.
    Resolves redirects and filters links to the main article namespace (NS 0).
    """

    API_URL = "https://en.wikipedia.org/w/api.php"
    
    def __init__(self, cache_dir: str = ".cache", delay: float = 0.05):
        """
        Initialize the scraper.
        
        :param cache_dir: Directory to store cached page link files.
        :param delay: Time delay (seconds) between non-cached API requests to respect rate limits.
        """
        self.cache_dir = cache_dir
        self.delay = delay
        self.session = requests.Session()
        
        # Identify our crawler uniquely according to MediaWiki API guidelines
        self.headers = {
            "User-Agent": "WikiIdleBot/1.0 (contact@example.com; Portfolio Project)"
        }
        
        # Ensure cache directory exists
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_cache_path(self, title: str) -> str:
        """
        Generate a safe, unique cache filename for a given Wikipedia page title.
        
        Design Note: Page titles can contain characters like '/' (e.g., "AC/DC") 
        or ':' that are reserved or invalid in Unix/Windows filesystems.
        We use the MD5 hash of the title to guarantee safe, flat filenames.
        
        :param title: The Wikipedia page title.
        :return: Absolute path to the cached JSON file.
        """
        hashed_title = hashlib.md5(title.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{hashed_title}.json")

    def _load_from_cache(self, title: str) -> Optional[Dict]:
        """
        Load page data from the local cache if it exists.
        
        :param title: The Wikipedia page title.
        :return: Processed page dictionary if cached, else None.
        """
        cache_path = self._get_cache_path(title)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to read cache for '%s': %s", title, e)
        return None

    def _save_to_cache(self, title: str, data: Dict) -> None:
        """
        Save page data to the local cache.
        
        :param title: The Wikipedia page title.
        :param data: The processed page dictionary.
        """
        cache_path = self._get_cache_path(title)
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to write cache for '%s': %s", title, e)

    def fetch_page_links(self, title: str) -> Dict:
        """
        Fetch the canonical title and all mainspace outgoing links for a given page.
        Checks the cache first. If not found, queries the MediaWiki API.
        
        MediaWiki API features used:
        - redirects=1: Resolves redirect pages to their canonical targets.
        - plnamespace=0: Filters links to namespace 0 (Main/Article namespace).
        - pllimit=max: Gets the maximum allowed links per request (500).
        
        :param title: The page title to fetch.
        :return: A dictionary containing:
                 - 'requested_title': original requested title
                 - 'canonical_title': resolved canonical title (None if missing)
                 - 'links': list of outgoing mainspace page titles
                 - 'missing': boolean indicating if the page does not exist
        """
        # 1. Check cache first
        cached_data = self._load_from_cache(title)
        if cached_data is not None:
            return cached_data

        # 2. Fetch from MediaWiki API (handling continuation/pagination)
        links: List[str] = []
        canonical_title: Optional[str] = None
        is_missing = False
        plcontinue: Optional[str] = None
        
        logger.info("Fetching '%s' from MediaWiki API...", title)
        
        while True:
            params = {
                "action": "query",
                "titles": title,
                "prop": "links",
                "pllimit": "max",
                "plnamespace": 0,
                "format": "json",
                "redirects": 1
            }
            if plcontinue:
                params["plcontinue"] = plcontinue
            
            # Rate limiting delay before HTTP requests to be a good web citizen
            time.sleep(self.delay)
            
            # Robust retry loop with exponential backoff for network resilience and 429 handling
            max_retries = 5
            backoff_delay = 1.0
            data = None
            
            for attempt in range(max_retries):
                try:
                    response = self.session.get(self.API_URL, params=params, headers=self.headers)
                    
                    # Explicitly handle 429 Too Many Requests
                    if response.status_code == 429:
                        logger.warning("Rate limited (429) on '%s'. Backing off for %.1fs (attempt %d/%d)...",
                                       title, backoff_delay, attempt + 1, max_retries)
                        time.sleep(backoff_delay)
                        backoff_delay *= 2.0  # Exponential backoff
                        continue
                        
                    response.raise_for_status()
                    data = response.json()
                    break  # Success, exit the retry loop
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error("HTTP request failed for '%s' after %d attempts: %s", title, max_retries, e)
                        return {
                            "requested_title": title,
                            "canonical_title": None,
                            "links": [],
                            "missing": True,
                            "error": str(e)
                        }
                    logger.warning("Request failed on '%s' (%s). Retrying in %.1fs...", title, e, backoff_delay)
                    time.sleep(backoff_delay)
                    backoff_delay *= 2.0
            else:
                logger.error("Failed to fetch '%s' due to persistent rate limiting (429).", title)
                return {
                    "requested_title": title,
                    "canonical_title": None,
                    "links": [],
                    "missing": True,
                    "error": "Exhausted retries due to rate limiting."
                }

            query = data.get("query", {})
            pages = query.get("pages", {})
            
            # MediaWiki returns pages as a dictionary keyed by page ID (or "-1" if missing)
            for page_id, page_info in pages.items():
                if "missing" in page_info or int(page_id) < 0:
                    is_missing = True
                    break
                
                # Capture the canonical title (resolves redirects and normalization)
                canonical_title = page_info.get("title")
                
                # Accumulate links
                page_links = page_info.get("links", [])
                for link in page_links:
                    links.append(link.get("title"))
            
            if is_missing:
                break
                
            # Check if there are more links to fetch (MediaWiki pagination)
            if "continue" in data and "plcontinue" in data["continue"]:
                plcontinue = data["continue"]["plcontinue"]
            else:
                break

        # 3. Process and cache the result
        result = {
            "requested_title": title,
            "canonical_title": canonical_title,
            "links": sorted(list(set(links))),  # Deduplicate and sort links alphabetically
            "missing": is_missing
        }
        
        # Cache the result to avoid future network hits
        self._save_to_cache(title, result)
        
        # If the canonical title differs, cache it under the canonical title as well
        if canonical_title and canonical_title != title:
            self._save_to_cache(canonical_title, result)
            
        return result

    def crawl_graph(self, seeds: List[str], max_pages: int = 3000) -> List[str]:
        """
        Perform a Breadth-First Search (BFS) crawl starting from seed pages
        to discover and cache up to max_pages valid Wikipedia articles.
        
        DSA Queue & BFS Mechanics:
        - BFS uses a Queue (FIFO - First In, First Out) to explore nodes level-by-level.
        - This ensures we crawl highly connected hubs near the seeds first.
        - A 'visited' set is critical to avoid infinite loops in a cyclic directed graph.
        - In Python, we use a list as a queue (using pop(0)) or collections.deque for O(1) pops.
          Since this is an offline script run once, deque is preferred for O(1) performance.
        
        :param seeds: List of starting Wikipedia page titles.
        :param max_pages: Number of valid pages to scrape and cache.
        :return: List of canonical page titles that form our universe.
        """
        from collections import deque

        # Queue stores pages to visit. Initialized with seeds.
        queue: deque = deque(seeds)
        
        # Set of pages we have successfully crawled and cached (our universe nodes)
        crawled_set: Set[str] = set()
        
        # Set of pages we have added to the queue to avoid duplicate queue entries
        enqueued_set: Set[str] = set(seeds)
        
        logger.info("Starting BFS crawl for %d pages. Seeds: %s", max_pages, seeds)

        # Standard BFS Queue Loop
        # Time Complexity: O(V + E) where V = max_pages, E = total links processed
        while queue and len(crawled_set) < max_pages:
            current_title = queue.popleft()  # FIFO Pop: O(1)
            
            # Fetch links (automatically uses cache if available)
            page_data = self.fetch_page_links(current_title)
            
            # If the page is missing or an error occurred, skip it
            if page_data.get("missing") or not page_data.get("canonical_title"):
                continue
                
            canonical_title = page_data["canonical_title"]
            
            # If we haven't already marked this canonical title as crawled:
            if canonical_title not in crawled_set:
                crawled_set.add(canonical_title)
                
                # Print progress updates
                if len(crawled_set) % 100 == 0 or len(crawled_set) == max_pages:
                    logger.info("Progress: Crawled and cached %d / %d pages", len(crawled_set), max_pages)
                
                # Traverse outgoing links (BFS neighbors)
                for link in page_data["links"]:
                    # BFS Expansion Rule:
                    # Only enqueue if the node hasn't been queued/visited yet
                    # Visited checks in sets are O(1) average time complexity
                    if link not in enqueued_set:
                        enqueued_set.add(link)
                        queue.append(link)
                        
        logger.info("Crawl complete! Crawled %d pages.", len(crawled_set))
        return sorted(list(crawled_set))


if __name__ == "__main__":
    # Get absolute paths relative to this script's directory to ensure working-directory independence
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

    # Define seeds representing highly-connected general topics
    seeds = [
        "Earth",
        "Science",
        "History",
        "United States",
        "Albert Einstein",
        "Mathematics",
        "Technology",
        "Philosophy",
        "Art",
        "Music",
        "Literature",
        "Biology",
        "Chemistry",
        "Physics",
        "Geography",
        "Internet",
        "Europe",
        "Asia",
        "World War II",
        "Human"
    ]
    
    cache_dir = os.path.join(PROJECT_ROOT, ".cache")
    scraper = WikiScraper(cache_dir=cache_dir, delay=0.25)
    
    # Run the production crawl of 3,000 pages
    logger.info("Running production crawl of 3,000 pages...")
    crawled_pages = scraper.crawl_graph(seeds, max_pages=3000)
    
    # Save the crawled list in the project root
    output_path = os.path.join(PROJECT_ROOT, "crawled_pages.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(crawled_pages, f, ensure_ascii=False, indent=2)
        
    logger.info("Saved crawled pages index to %s", output_path)
