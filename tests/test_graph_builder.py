"""
Wiki-dle Tests - Graph Builder

This module contains unit tests for the GraphBuilder class, verifying the
closed-universe adjacency list construction, edge filtering, and self-loop removal.
"""

import os
import json
import hashlib
import pytest
from data_pipeline.graph_builder import GraphBuilder


def write_mock_cache(cache_dir, title, links):
    """
    Helper to write a mock page scrape to the temporary cache directory.
    """
    hashed = hashlib.md5(title.encode("utf-8")).hexdigest()
    cache_path = os.path.join(cache_dir, f"{hashed}.json")
    data = {
        "requested_title": title,
        "canonical_title": title,
        "links": links,
        "missing": False
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_build_graph_filtering_and_self_loops(tmp_path):
    """
    Verify that GraphBuilder correctly:
    1. Removes links pointing to pages outside the closed universe.
    2. Removes self-loops (links pointing to the page itself).
    3. Retains valid, in-universe, non-self links.
    """
    # Define paths
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    
    crawled_file = tmp_path / "crawled.json"
    output_file = tmp_path / "graph.json"
    
    # 1. Define our closed universe: ["A", "B", "C"]
    universe = ["A", "B", "C"]
    with open(crawled_file, "w", encoding="utf-8") as f:
        json.dump(universe, f)
        
    # 2. Setup mock cache files
    # A links to:
    # - "B" (valid, in universe)
    # - "A" (invalid, self-loop)
    # - "D" (invalid, outside universe)
    write_mock_cache(str(cache_dir), "A", ["B", "A", "D"])
    
    # B links to:
    # - "C" (valid, in universe)
    # - "A" (valid, in universe)
    write_mock_cache(str(cache_dir), "B", ["C", "A"])
    
    # C has no cache file (simulating missing page)
    # This should be handled gracefully by initializing C with an empty link list.
    
    # 3. Build the graph
    builder = GraphBuilder(cache_dir=str(cache_dir))
    graph = builder.build_graph(str(crawled_file), str(output_file))
    
    # 4. Assertions
    # A's links should only contain B (A and D filtered out)
    assert graph["A"] == ["B"]
    
    # B's links should contain C and A (both are in universe)
    assert sorted(graph["B"]) == ["A", "C"]
    
    # C should have an empty list of links since it has no cache file
    assert graph["C"] == []
    
    # Verify the output file was created and contains the correct JSON
    assert os.path.exists(str(output_file))
    with open(output_file, "r", encoding="utf-8") as f:
        saved_graph = json.load(f)
        
    assert saved_graph == graph
