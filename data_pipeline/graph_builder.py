"""
Wiki-dle Data Pipeline - Closed-Universe Graph Builder

This module processes the cached Wikipedia page data to construct a clean,
closed-universe directed graph. It filters outgoing links so that they strictly
point to pages within our set of crawled pages (our "universe").

DSA Interview Prep - Graph Representation & Filtering Complexity:
1. Graph Representation:
   - We use an **Adjacency List** represented as a Python dictionary: Dict[str, List[str]].
   - **Why not an Adjacency Matrix?** 
     - An Adjacency Matrix requires O(V^2) space. For V = 3,000, this would require 9,000,000 entries,
       most of which would be 0 (since the graph is extremely sparse, with an average degree of ~50-100).
     - An Adjacency List requires O(V + E) space, where E is the number of edges. This is highly efficient 
       for sparse graphs and integrates naturally with BFS traversal.
2. Filtering Complexity:
   - For each page, we have a list of outgoing links. We must filter them to keep only those in our universe.
   - **Naive Approach**: If we check if each link is in the universe list using a linear search, the time 
     complexity is O(V) per link. For E total links, the overall filtering time is O(E * V).
     With V = 3,000 and E = 150,000, this would take 450,000,000 operations!
   - **Optimal Approach**: By converting our universe list into a **HashSet (Python set)**, lookup time 
     is reduced to O(1) average. The overall filtering time complexity becomes **O(V + E)**, which runs in 
     less than a tenth of a second for our dataset size.
- Space Complexity: O(V + E) to store the filtered graph in memory and write to disk.
"""

import os
import json
import hashlib
import logging
from typing import List, Dict, Set

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class GraphBuilder:
    """
    Constructs a closed-universe directed graph from cached Wikipedia page data.
    """

    def __init__(self, cache_dir: str = ".cache"):
        """
        Initialize the GraphBuilder.
        
        :param cache_dir: Path to the scraper's cache directory.
        """
        self.cache_dir = cache_dir

    def _get_cache_path(self, title: str) -> str:
        """
        Helper to get the cached file path for a title using its MD5 hash.
        Identical to the scraper's hashing method.
        """
        hashed_title = hashlib.md5(title.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{hashed_title}.json")

    def build_graph(self, crawled_pages_file: str, output_graph_file: str) -> Dict[str, List[str]]:
        """
        Reads the crawled pages index, loads their outgoing links from the cache,
        filters them to form a closed universe (no outgoing links outside the set,
        and no self-loops), and writes the resulting adjacency list to a JSON file.
        
        :param crawled_pages_file: Path to the JSON file containing the list of crawled pages.
        :param output_graph_file: Path to save the final adjacency list graph.
        :return: The constructed adjacency list dictionary.
        """
        # 1. Load the closed-universe nodes (V)
        if not os.path.exists(crawled_pages_file):
            raise FileNotFoundError(f"Crawled pages file not found: {crawled_pages_file}")
            
        with open(crawled_pages_file, "r", encoding="utf-8") as f:
            universe_list = json.load(f)
            
        # Convert list to a Set for O(1) average-time lookups (Crucial DSA Optimization!)
        universe_set: Set[str] = set(universe_list)
        logger.info("Loaded closed universe with V = %d nodes", len(universe_set))
        
        graph: Dict[str, List[str]] = {}
        total_edges_before = 0
        total_edges_after = 0

        # 2. Iterate through each page in our universe: O(V) iterations
        for node in universe_list:
            cache_path = self._get_cache_path(node)
            
            if not os.path.exists(cache_path):
                logger.warning("Cache file not found for page: '%s'. Initializing with 0 edges.", node)
                graph[node] = []
                continue
                
            with open(cache_path, "r", encoding="utf-8") as f:
                page_data = json.load(f)
                
            raw_links = page_data.get("links", [])
            total_edges_before += len(raw_links)
            
            # 3. Filter links: O(L) operation per page, where L is the number of outgoing links
            # We enforce:
            # - link in universe_set: Closed-universe constraint
            # - link != node: No self-loops constraint
            filtered_links = [
                link for link in raw_links 
                if link in universe_set and link != node
            ]
            
            graph[node] = filtered_links
            total_edges_after += len(filtered_links)

        logger.info("Graph construction complete.")
        logger.info("Total edges in raw scrape: %d", total_edges_before)
        logger.info("Total edges in closed universe: %d (Filtered out %d external/self links)", 
                    total_edges_after, total_edges_before - total_edges_after)

        # 4. Save the constructed graph to disk
        # Ensure target directory exists
        output_dir = os.path.dirname(output_graph_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            
        try:
            with open(output_graph_file, "w", encoding="utf-8") as f:
                json.dump(graph, f, ensure_ascii=False, separators=(",", ":"))
            logger.info("Saved adjacency list graph to: %s", output_graph_file)
        except Exception as e:
            logger.error("Failed to write graph file: %s", e)
            raise

        return graph


if __name__ == "__main__":
    # Get absolute paths relative to this script's directory to ensure working-directory independence
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
    
    crawled_file = os.path.join(PROJECT_ROOT, "crawled_pages.json")
    output_file = os.path.join(PROJECT_ROOT, "backend", "data", "graph.json")
    
    builder = GraphBuilder(cache_dir=os.path.join(PROJECT_ROOT, ".cache"))
    try:
        builder.build_graph(crawled_pages_file=crawled_file, output_graph_file=output_file)
    except Exception as e:
        logger.error("Error building graph: %s", e)
