"""
Wiki-dle Backend - Flask application.

Puzzles are generated deterministically from the date (see PuzzleGenerator.puzzle_for_date),
so the game never runs out of puzzles. The server keeps the graph and the distance map;
the browser only receives the start/target, the links of the page it is on, and the
distance of each page it moves to.
"""

import os
import re
import sys
import json
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from flask import Flask, jsonify, render_template, request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

from data_pipeline.puzzle_generator import PuzzleGenerator  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    static_folder=os.path.join(SCRIPT_DIR, "static"),
    template_folder=os.path.join(SCRIPT_DIR, "templates"),
)

GRAPH_FILE = os.path.join(SCRIPT_DIR, "data", "graph.json")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _load_generator() -> PuzzleGenerator:
    with open(GRAPH_FILE, "r", encoding="utf-8") as f:
        graph = json.load(f)
    logger.info("Loaded graph: %d nodes", len(graph))
    return PuzzleGenerator(graph)


GENERATOR = _load_generator()


@lru_cache(maxsize=8)
def get_puzzle_for_date(date_str: str) -> dict:
    puzzle = GENERATOR.puzzle_for_date(date_str)
    if puzzle is None:
        raise RuntimeError("Could not generate a puzzle")
    return puzzle


def resolve_date(requested: str = None) -> str:
    """
    Players pass their local date so the puzzle flips at their midnight. Anything
    outside +/-1 day of UTC now (the range covering every real time zone) is ignored,
    which stops people from peeking at far-future puzzles.
    """
    now = datetime.now(timezone.utc).date()
    if requested and DATE_RE.match(requested):
        try:
            req = datetime.strptime(requested, "%Y-%m-%d").date()
            if abs((req - now).days) <= 1:
                return requested
        except ValueError:
            pass
    return now.strftime("%Y-%m-%d")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/healthz")
def healthz():
    return "ok"


@app.route("/api/puzzle")
def api_puzzle():
    date_str = resolve_date(request.args.get("date"))
    p = get_puzzle_for_date(date_str)
    return jsonify({
        "date": p["date"],
        "startNode": p["startNode"],
        "targetNode": p["targetNode"],
        "shortestPathLength": p["shortestPathLength"],
        "startDistance": p["distances"][p["startNode"]],
    })


@app.route("/api/links")
def api_links():
    """Outgoing links of a page (the autocomplete options)."""
    page = request.args.get("page", "")
    if page not in GENERATOR.graph:
        return jsonify({"error": "Unknown page"}), 404
    return jsonify({"page": page, "links": GENERATOR.graph[page]})


@app.route("/api/move")
def api_move():
    """
    Validates a click and returns the click-distance of the destination to the target.
    """
    date_str = resolve_date(request.args.get("date"))
    src, dst = request.args.get("from", ""), request.args.get("to", "")
    if dst not in GENERATOR.graph.get(src, []):
        return jsonify({"error": "Illegal move"}), 400
    distance = get_puzzle_for_date(date_str)["distances"].get(dst, -1)
    return jsonify({"to": dst, "distance": distance})


@app.after_request
def cache_headers(resp):
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=True)
