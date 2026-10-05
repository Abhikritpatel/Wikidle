import json
from datetime import datetime, timezone

import pytest

from backend import app as app_module


@pytest.fixture()
def client():
    return app_module.app.test_client()


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def test_puzzle_is_deterministic_and_hides_distances(client):
    a = client.get(f"/api/puzzle?date={today()}").get_json()
    b = client.get(f"/api/puzzle?date={today()}").get_json()
    assert a == b
    assert "distances" not in a
    assert 3 <= a["shortestPathLength"] <= 5


def test_far_future_date_is_ignored(client):
    p = client.get("/api/puzzle?date=2099-01-01").get_json()
    assert p["date"] == today()


def test_move_validation_and_distance(client):
    p = client.get(f"/api/puzzle?date={today()}").get_json()
    links = client.get("/api/links", query_string={"page": p["startNode"]}).get_json()["links"]
    assert links
    ok = client.get("/api/move", query_string={"date": p["date"], "from": p["startNode"], "to": links[0]})
    assert ok.status_code == 200
    bad = client.get("/api/move", query_string={"date": p["date"], "from": p["startNode"], "to": "Not a real page"})
    assert bad.status_code == 400


def test_unknown_links_page(client):
    assert client.get("/api/links?page=nope").status_code == 404
