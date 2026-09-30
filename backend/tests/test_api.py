import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
PNG = b"\x89PNG\r\n\x1a\nfake"


def files(n=3, mime="image/png"):
    return [("images", (f"item{i}.png", PNG, mime)) for i in range(n)]


def test_validation_errors():
    r = client.post("/api/proposals", data={"mv_url": "https://example.com", "event_date": "12/5"},
                    files=files(1, "text/plain"))
    assert r.status_code == 422
    errors = r.json()["errors"]
    assert any("アーティスト名" in e for e in errors)
    assert any("YouTube" in e for e in errors)
    assert any("YYYY-MM-DD" in e for e in errors)
    assert any("同意" in e for e in errors)
    assert any("形式" in e for e in errors)


def test_stream_success():
    data = {"artist_name": "テストバンド", "genre": "ヒップホップ", "event_date": "2026-08-01",
            "venue": "日本武道館", "consent": "true"}
    with client.stream("POST", "/api/proposals", data=data, files=files()) as r:
        assert r.status_code == 200
        lines = [json.loads(l) for l in r.iter_lines() if l]
    assert lines[0]["type"] == "start"
    assert lines[-1]["type"] == "result"
    assert lines[-1]["result"]["culture"]["genre_id"] == "hiphop"
    assert lines[-1]["result"]["venue_weather"]["season"] == "夏"


def test_config():
    assert client.get("/api/config").json()["max_images"] == 10
