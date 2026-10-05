"""
Wiki-dle Tests - Puzzle Generator

This module contains unit tests for the PuzzleGenerator class, verifying
graph transposition, reversed BFS distance calculations, puzzle selection,
and daily schedule generation.
"""

import pytest
from data_pipeline.puzzle_generator import PuzzleGenerator


@pytest.fixture
def sample_graph():
    """
    A simple directed mock graph for testing:
    A ➔ B ➔ C ➔ D ➔ E
    B ➔ E (shortcut)
    F (unreachable component)
    Cycles: D ➔ B
    """
    return {
        "A": ["B"],
        "B": ["C", "E"],
        "C": ["D"],
        "D": ["B", "E"],
        "E": [],
        "F": []
    }


def test_graph_transposition(sample_graph):
    """
    Verify that G^T constructs correctly by reversing every edge in the graph.
    """
    generator = PuzzleGenerator(sample_graph)
    transpose = generator.transpose_graph
    
    # original: A ➔ B  =>  transpose: B ➔ A
    assert "A" in transpose["B"]
    
    # original: B ➔ C  =>  transpose: C ➔ B
    assert "B" in transpose["C"]
    
    # original: B ➔ E  =>  transpose: E ➔ B
    assert "B" in transpose["E"]
    
    # original: D ➔ E  =>  transpose: E ➔ D
    assert "D" in transpose["E"]
    
    # E has out-degree 0 in G, so in G^T it should have no incoming edges (it only points to things)
    # A has in-degree 0 in G, so in G^T it should have no outgoing edges (nothing points to A)
    assert transpose["A"] == []
    assert sorted(transpose["E"]) == ["B", "D"]
    assert transpose["F"] == []


def test_compute_distances_from_target(sample_graph):
    """
    Verify that reversed BFS calculates the correct shortest click-distances
    from all nodes to a single target node.
    """
    generator = PuzzleGenerator(sample_graph)
    
    # Target: E
    # Paths to E:
    # E: 0 clicks
    # B ➔ E: 1 click (B ➔ C ➔ D ➔ E is 3 clicks, but B ➔ E is 1)
    # D ➔ E: 1 click
    # A ➔ B ➔ E: 2 clicks
    # C ➔ D ➔ E: 2 clicks
    # F: unreachable (should not be in distances dictionary)
    distances = generator.compute_distances_from_target("E")
    
    assert distances["E"] == 0
    assert distances["B"] == 1
    assert distances["D"] == 1
    assert distances["A"] == 2
    assert distances["C"] == 2
    assert "F" not in distances  # Unreachable node F excluded


def test_select_puzzle_path_constraints(sample_graph):
    """
    Verify that select_puzzle only selects start/target pairs that satisfy
    the path length limits (min_clicks and max_clicks).
    """
    generator = PuzzleGenerator(sample_graph)
    
    # In our sample graph, the only pairs with distance >= 2 are:
    # dist(A, E) = 2, dist(C, E) = 2, dist(A, C) = 2, dist(A, D) = 3
    # If we request min_clicks = 3, max_clicks = 3:
    # The only valid start is A and target is D (A ➔ B ➔ C ➔ D is 3 clicks, or A ➔ B ➔ E ➔ ? wait, D doesn't go through E.
    # Let's check path A to D: A ➔ B ➔ C ➔ D is indeed 3 clicks. A ➔ B ➔ E (dead end).
    # So dist(A, D) = 3.
    selection = generator.select_puzzle(min_clicks=3, max_clicks=3)
    
    assert selection is not None
    start, target, distances = selection
    assert start == "A"
    assert target == "D"
    assert distances[start] == 3


def test_generate_daily_puzzles(sample_graph):
    """
    Verify that generate_daily_puzzles generates a sequence of puzzles with consecutive dates.
    """
    generator = PuzzleGenerator(sample_graph)
    
    # Generate 3 puzzles starting from '2026-06-26'
    # We set min_clicks=2 to ensure we have valid puzzles in this small graph
    puzzles = generator.generate_daily_puzzles(start_date_str="2026-06-26", num_days=3)
    
    assert len(puzzles) == 3
    assert puzzles[0]["date"] == "2026-06-26"
    assert puzzles[1]["date"] == "2026-06-27"
    assert puzzles[2]["date"] == "2026-06-28"
    
    for puzzle in puzzles:
        assert "startNode" in puzzle
        assert "targetNode" in puzzle
        assert "distances" in puzzle
        assert "shortestPathLength" in puzzle
        
        start = puzzle["startNode"]
        target = puzzle["targetNode"]
        distances = puzzle["distances"]
        
        # The start node must have a distance equal to shortestPathLength in the distances map
        assert distances[start] == puzzle["shortestPathLength"]
        # The target node must have a distance of 0
        assert distances[target] == 0
