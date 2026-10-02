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
    assert any("MV" in e for e in errors)
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


def test_url_input_is_rejected():
    r = client.post("/api/proposals", data={"keyword": "https://example.com/live", "consent": "true"}, files=files(1))
    assert r.status_code == 422
    assert any("URL" in e for e in r.json()["errors"])
    assert client.get("/api/events/search", params={"q": "https://example.com"}).status_code == 422


def test_event_search():
    r = client.get("/api/events/search", params={"q": "モックバンド"})
    assert r.status_code == 200
    body = r.json()
    assert body["candidates"][0]["artist_name"] == "モックバンド"
    assert body["candidates"][0]["mv_url"].startswith("https://www.youtube.com/")
    assert body["sources"]
    assert client.get("/api/events/search", params={"q": " "}).status_code == 422
    assert client.get("/api/events/search", params={"q": "fail"}).status_code == 503
    assert client.get("/api/events/search", params={"q": "nohit"}).json()["candidates"] == []


def test_keyword_only_stream():
    with client.stream("POST", "/api/proposals", data={"keyword": "モックバンド", "consent": "true"}, files=files()) as r:
        lines = [json.loads(l) for l in r.iter_lines() if l]
    assert lines[-1]["result"]["event"]["artist_name"] == "モックバンド"


def test_config():
    assert client.get("/api/config").json()["max_images"] == 10
