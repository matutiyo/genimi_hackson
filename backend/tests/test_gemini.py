import httpx
import pytest

from app import gemini


@pytest.fixture
def oembed(monkeypatch):
    """YouTube oEmbed への通信を差し替える(実在する動画IDは abcdefghijk のみ)。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if "abcdefghijk" in request.url.params["url"]:
            return httpx.Response(200, json={"title": "Test Band - Song (Official MV)", "author_name": "TestBandOfficial"})
        return httpx.Response(404)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(gemini.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))


@pytest.mark.asyncio
async def test_verify_mv_accepts_only_existing_video_of_the_artist(oembed):
    url, title = await gemini._verify_mv("Test Band", "https://youtu.be/abcdefghijk")
    assert url == "https://www.youtube.com/watch?v=abcdefghijk"
    assert title == "Test Band - Song (Official MV)"
    # アーティスト名が一致しない / 存在しない動画 / YouTube 以外は使わない
    assert await gemini._verify_mv("Other Artist", "https://youtu.be/abcdefghijk") == (None, None)
    assert await gemini._verify_mv("Test Band", "https://youtu.be/zzzzzzzzzzz") == (None, None)
    assert await gemini._verify_mv("Test Band", "https://example.com/video") == (None, None)
    assert await gemini._verify_mv("Test Band", None) == (None, None)


def test_valid_date():
    assert gemini._valid_date("2026-12-05") == "2026-12-05"
    assert gemini._valid_date("12/5") is None
    assert gemini._valid_date(None) is None


@pytest.mark.asyncio
async def test_search_events_parses_grounded_response(oembed):
    from types import SimpleNamespace

    from app.config import Settings

    text = """```json
{"candidates": [
  {"artist_name": "Test Band", "event_title": "TOUR", "event_date": "2026-12-05", "venue": "Zepp Haneda",
   "genre_hint": "パンク", "mv_url": "https://www.youtube.com/watch?v=abcdefghijk"},
  {"artist_name": "Test Band", "event_date": "未定", "mv_url": "https://www.youtube.com/watch?v=zzzzzzzzzzz"},
  {"artist_name": ""}
]}
```"""
    chunk = SimpleNamespace(web=SimpleNamespace(uri="https://example.com/tour", title="公式サイト"))
    response = SimpleNamespace(
        text=text, candidates=[SimpleNamespace(grounding_metadata=SimpleNamespace(grounding_chunks=[chunk]))]
    )

    async def generate_content(**kwargs):
        assert kwargs["config"].tools[0].google_search is not None
        assert "会場: Zepp Haneda" in kwargs["contents"][0]
        return response

    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    result = await gemini.GeminiGateway(Settings(), client=client).search_events(
        "Test Band", conditions=gemini.search_conditions(venue="Zepp Haneda")
    )

    assert [c.event_title for c in result.candidates] == ["TOUR", None]
    assert result.candidates[0].mv_url == "https://www.youtube.com/watch?v=abcdefghijk"
    assert result.candidates[1].event_date is None  # 日付として不正な値は捨てる
    assert result.candidates[1].mv_url is None  # 確認できない MV は使わない
    assert result.sources[0].title == "公式サイト"
