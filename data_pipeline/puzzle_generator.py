"""
Wiki-dle Data Pipeline - Reversed BFS & Daily Puzzle Generator

This module implements a pure Python Breadth-First Search (BFS) on the transpose
(reversed) graph of our Wikipedia closed universe. It pre-computes shortest path
distances from all nodes to a target node, selecting engaging, solvable daily puzzles.

DSA Interview Prep - Graph Transposition & Reversed BFS:
1. Why Graph Transposition?
   - In the game, a player navigates from a start node S to a target node T. At any node u,
     we want to provide O(1) proximity feedback: "How many clicks is u from T?"
   - **Naive Forward BFS**: Running BFS from the player's current node u to T on the fly 
     would require O(V + E) time in the browser on every single click, which is highly inefficient.
   - **Reversed BFS (Single-Source Destination Shortest Path)**: 
     By reversing all edges of the directed graph G = (V, E) to create the transpose graph G^T = (V, E^T),
     we can run a single BFS starting *from* the target node T.
     - In G^T, an edge v -> u exists if and only if the edge u -> v exists in G.
     - Running BFS from T in G^T traverses edges backward, finding the shortest path distance 
       from *every* reachable node u to T in a single pass!
     - This computes the entire `distances` dictionary in **O(V + E) time** and **O(V) space**.
2. BFS Algorithm Mechanics:
   - Uses a Queue (FIFO) to explore nodes level-by-level, guaranteeing that the first time we
     encounter a node, we have found its shortest path (minimum edge count) in an unweighted graph.
   - A `distances` dictionary acts as both the visited tracker (preventing cycles) and the distance map.
"""

import os
import json
import random
import logging
from datetime import datetime, timedelta
from collections import deque
from typing import List, Dict, Set, Tuple, Optional

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class PuzzleGenerator:
    """
    Generates daily Wiki-dle puzzles using Graph Transposition and Reversed BFS.
    """

    def __init__(self, graph: Dict[str, List[str]]):
        """
        Initialize the generator with a directed graph (adjacency list).
        
        :param graph: Adjacency list representation of the directed graph.
        """
        self.graph = graph
        # Pre-compute the transpose graph for reversed BFS
        self.transpose_graph = self._transpose_graph()

    def _transpose_graph(self) -> Dict[str, List[str]]:
        """
        Constructs the transpose graph G^T by reversing all directed edges.
        G^T has edge v -> u if and only if G has edge u -> v.
        
        Time Complexity: O(V + E) where V is vertices, E is edges.
        Space Complexity: O(V + E) to store the transposed adjacency list.
        
        :return: Transposed adjacency list.
        """
        transpose: Dict[str, List[str]] = {node: [] for node in self.graph}
        
        for u, neighbors in self.graph.items():
            for v in neighbors:
                # Since it's a closed universe, v is guaranteed to be a key in the graph.
                if v in transpose:
                    transpose[v].append(u)
                    
        return transpose

    def compute_distances_from_target(self, target: str) -> Dict[str, int]:
        """
        Runs a Breadth-First Search (BFS) on the transpose graph starting at the target.
        Calculates the shortest click-distance from every reachable page to the target.
        
        Time Complexity: O(V + E)
        Space Complexity: O(V) for the queue and distances dictionary.
        
        :param target: The target Wikipedia page title (BFS source in G^T).
        :return: A dictionary mapping canonical page titles to their click-distance to target.
        """
        if target not in self.transpose_graph:
            return {}

        # BFS initialization
        # distances maps: node -> shortest path distance to target
        # Also serves as our "visited" set to prevent infinite loops in cyclic graphs (O(1) lookups)
        distances: Dict[str, int] = {target: 0}
        queue: deque = deque([target])  # FIFO Queue

        # Standard BFS Loop
        while queue:
            current = queue.popleft()  # O(1) FIFO pop
            current_dist = distances[current]

            # In the transpose graph, neighbors of 'current' are nodes that link TO 'current' in G
            for incoming_node in self.transpose_graph[current]:
                if incoming_node not in distances:
                    # First encounter is guaranteed to be the shortest path
                    distances[incoming_node] = current_dist + 1
                    queue.append(incoming_node)

        return distances

    def select_puzzle(self, min_clicks: int = 3, max_clicks: int = 5,
                      rng: Optional[random.Random] = None) -> Optional[Tuple[str, str, Dict[str, int]]]:
        """
        Selects a start and target node that form an engaging daily puzzle.
        Enforces that the shortest path is between min_clicks and max_clicks.
        
        :param min_clicks: Minimum click-distance for the puzzle path.
        :param max_clicks: Maximum click-distance for the puzzle path.
        :return: A tuple of (start_node, target_node, distances_dict) or None if no puzzle could be found.
        """
        rng = rng or random
        nodes = list(self.graph.keys())
        if len(nodes) < 2:
            return None

        # Shuffle target candidates to ensure random distribution
        target_candidates = nodes.copy()
        rng.shuffle(target_candidates)

        for target in target_candidates:
            # 1. Run reversed BFS from the target candidate
            distances = self.compute_distances_from_target(target)
            
            # 2. Find all start nodes S that satisfy: min_clicks <= dist(S, target) <= max_clicks
            start_candidates = [
                node for node, dist in distances.items()
                if min_clicks <= dist <= max_clicks
            ]
            
            # 3. If we find valid start candidates, choose one randomly and return the puzzle
            if start_candidates:
                start = rng.choice(sorted(start_candidates))
                logger.info("Selected puzzle: Start = '%s', Target = '%s' (Shortest path = %d clicks)", 
                            start, target, distances[start])
                return start, target, distances

        return None

    def puzzle_for_date(self, date_str: str) -> Optional[Dict]:
        """
        Deterministically builds the puzzle for a date (YYYY-MM-DD). The date seeds
        the RNG, so every player and every server instance gets the same puzzle,
        and puzzles never run out.
        """
        selection = self.select_puzzle(rng=random.Random(f"wikidle-{date_str}"))
        if not selection:
            return None
        start, target, distances = selection
        return {
            "date": date_str,
            "startNode": start,
            "targetNode": target,
            "shortestPathLength": distances[start],
            "distances": distances,
        }

    def generate_daily_puzzles(self, start_date_str: str, num_days: int) -> List[Dict]:
        """
        Generates a sequence of daily puzzles starting from a given date.
        
        :param start_date_str: Date string in 'YYYY-MM-DD' format.
        :param num_days: Number of daily puzzles to generate.
        :return: List of daily puzzle dictionaries.
        """
        puzzles = []
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        
        logger.info("Generating %d daily puzzles starting from %s...", num_days, start_date_str)
        
        # Keep track of recently used target nodes to avoid duplicate targets in consecutive days
        used_targets: Set[str] = set()
        
        for i in range(num_days):
            current_date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            
            # Attempt to select a unique puzzle
            puzzle_data = None
            for attempt in range(10):  # Retry loop to find a unique target if possible
                selection = self.select_puzzle()
                if not selection:
                    break
                
                start, target, distances = selection
                if target not in used_targets or len(used_targets) >= len(self.graph) // 2:
                    puzzle_data = (start, target, distances)
                    used_targets.add(target)
                    break
            
            # Fallback if we couldn't get a unique target
            if not puzzle_data and selection:
                start, target, distances = selection
                puzzle_data = (start, target, distances)
                
            if puzzle_data:
                start, target, distances = puzzle_data
                puzzles.append({
                    "date": current_date,
                    "startNode": start,
                    "targetNode": target,
                    "shortestPathLength": distances[start],
                    "distances": distances
                })
            else:
                logger.error("Failed to generate puzzle for date: %s", current_date)
                
        return puzzles


if __name__ == "__main__":
    # Preview the puzzles the server will serve (they are generated on demand from the date).
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    graph_path = os.path.join(os.path.dirname(SCRIPT_DIR), "backend", "data", "graph.json")
    with open(graph_path, "r", encoding="utf-8") as f:
        generator = PuzzleGenerator(json.load(f))
    for i in range(7):
        d = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
        p = generator.puzzle_for_date(d)
        print(f"{d}: {p['startNode']} -> {p['targetNode']} ({p['shortestPathLength']} clicks)")
