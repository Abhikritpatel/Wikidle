"""
Wiki-dle Tests - MediaWiki API Scraper

This module contains unit tests for the WikiScraper class to verify caching,
API request handling, and crawling logic. It uses pytest and unittest.mock
to avoid hitting the live MediaWiki API during testing.
"""

import os
import json
import hashlib
from unittest.mock import MagicMock, patch
import pytest
from data_pipeline.scraper import WikiScraper


def test_cache_filename_generation(tmp_path):
    """
    Verify that cache filenames are flat, safe, and generated via MD5 hashing.
    Special characters should be resolved to a flat hex string.
    """
    scraper = WikiScraper(cache_dir=str(tmp_path))
    
    # Test a simple title
    title1 = "Earth"
    expected_hash1 = hashlib.md5(title1.encode("utf-8")).hexdigest()
    assert scraper._get_cache_path(title1) == os.path.join(str(tmp_path), f"{expected_hash1}.json")
    
    # Test a title containing slashes (traditionally invalid in filenames)
    title2 = "AC/DC"
    expected_hash2 = hashlib.md5(title2.encode("utf-8")).hexdigest()
    assert scraper._get_cache_path(title2) == os.path.join(str(tmp_path), f"{expected_hash2}.json")


def test_cache_read_write(tmp_path):
    """
    Verify that data is correctly written to and read from the local cache.
    """
    scraper = WikiScraper(cache_dir=str(tmp_path))
    test_title = "Test Article"
    test_data = {
        "requested_title": test_title,
        "canonical_title": test_title,
        "links": ["Link A", "Link B"],
        "missing": False
    }
    
    # Cache should be empty initially
    assert scraper._load_from_cache(test_title) is None
    
    # Save to cache
    scraper._save_to_cache(test_title, test_data)
    
    # Retrieve from cache
    cached = scraper._load_from_cache(test_title)
    assert cached == test_data


@patch("data_pipeline.scraper.requests.Session.get")
def test_fetch_page_links_api_call(mock_get, tmp_path):
    """
    Verify fetch_page_links queries the API correctly and parses the response
    when there is no cached data.
    """
    scraper = WikiScraper(cache_dir=str(tmp_path))
    test_title = "Physics"
    
    # Mock MediaWiki API JSON response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "query": {
            "pages": {
                "12345": {
                    "pageid": 12345,
                    "ns": 0,
                    "title": "Physics",
                    "links": [
                        {"ns": 0, "title": "Quantum Mechanics"},
                        {"ns": 0, "title": "Isaac Newton"}
                    ]
                }
            }
        }
    }
    mock_get.return_value = mock_response
    
    # Fetch links (should hit mock API)
    result = scraper.fetch_page_links(test_title)
    
    # Assertions
    assert result["requested_title"] == test_title
    assert result["canonical_title"] == "Physics"
    assert result["links"] == ["Isaac Newton", "Quantum Mechanics"]  # Sorted alphabetically
    assert result["missing"] is False
    
    # Verify it was saved to the cache
    cached = scraper._load_from_cache(test_title)
    assert cached == result
    
    # Verify the mock get was called once
    mock_get.assert_called_once()


@patch("data_pipeline.scraper.requests.Session.get")
def test_fetch_page_links_pagination(mock_get, tmp_path):
    """
    Verify fetch_page_links handles pagination/continuation (plcontinue)
    correctly when a page has many links.
    """
    scraper = WikiScraper(cache_dir=str(tmp_path), delay=0.0)
    test_title = "Large Article"
    
    # First response contains continue block and first link
    response_1 = MagicMock()
    response_1.json.return_value = {
        "continue": {
            "plcontinue": "12345|0|NextLink",
            "continue": "||"
        },
        "query": {
            "pages": {
                "12345": {
                    "pageid": 12345,
                    "ns": 0,
                    "title": "Large Article",
                    "links": [{"ns": 0, "title": "Link 1"}]
                }
            }
        }
    }
    
    # Second response contains final link and no continue block
    response_2 = MagicMock()
    response_2.json.return_value = {
        "query": {
            "pages": {
                "12345": {
                    "pageid": 12345,
                    "ns": 0,
                    "title": "Large Article",
                    "links": [{"ns": 0, "title": "Link 2"}]
                }
            }
        }
    }
    
    # Set the side effect to return response_1 then response_2
    mock_get.side_effect = [response_1, response_2]
    
    result = scraper.fetch_page_links(test_title)
    
    # Assertions
    assert result["links"] == ["Link 1", "Link 2"]
    assert mock_get.call_count == 2
    
    # Verify second call included the plcontinue parameter
    first_call_args, first_call_kwargs = mock_get.call_args_list[0]
    second_call_args, second_call_kwargs = mock_get.call_args_list[1]
    
    assert "plcontinue" not in first_call_kwargs["params"]
    assert second_call_kwargs["params"]["plcontinue"] == "12345|0|NextLink"


@patch("data_pipeline.scraper.WikiScraper.fetch_page_links")
def test_crawl_graph_bfs(mock_fetch, tmp_path):
    """
    Verify the BFS crawler crawls the graph in the correct order,
    handles missing articles, and stops at max_pages.
    """
    scraper = WikiScraper(cache_dir=str(tmp_path))
    
    # Mocking graph connectivity:
    # A -> B, C
    # B -> D
    # C -> E (missing)
    # D -> A (cycle)
    
    def fetch_side_effect(title):
        if title == "A":
            return {"requested_title": "A", "canonical_title": "A", "links": ["B", "C"], "missing": False}
        elif title == "B":
            return {"requested_title": "B", "canonical_title": "B", "links": ["D"], "missing": False}
        elif title == "C":
            return {"requested_title": "C", "canonical_title": "C", "links": ["E"], "missing": False}
        elif title == "D":
            return {"requested_title": "D", "canonical_title": "D", "links": ["A"], "missing": False}
        elif title == "E":
            return {"requested_title": "E", "canonical_title": None, "links": [], "missing": True}
        return {"requested_title": title, "canonical_title": None, "links": [], "missing": True}
        
    mock_fetch.side_effect = fetch_side_effect
    
    # Crawl with max_pages = 3 starting from "A"
    crawled = scraper.crawl_graph(seeds=["A"], max_pages=3)
    
    # The BFS should visit "A", then "B", then "C".
    # E is missing, so it doesn't count.
    # D is valid but we capped at max_pages=3, so the crawl should stop after B and C.
    # Therefore, the crawled pages should be A, B, C.
    assert crawled == ["A", "B", "C"]
    
    # Verify fetch calls
    # Should fetch A, B, C. Depending on BFS implementation, B's neighbors may have been enqueued,
    # but the loop terminates once len(crawled_set) == max_pages.
    # A is popped, crawled. len=1. Enqueue B, C.
    # B is popped, crawled. len=2. Enqueue D.
    # C is popped, crawled. len=3. Enqueue E. Loop terminates because len == 3.
    # Thus, only A, B, C are fetched.
    assert mock_fetch.call_count == 3
    mock_fetch.assert_any_call("A")
    mock_fetch.assert_any_call("B")
    mock_fetch.assert_any_call("C")
