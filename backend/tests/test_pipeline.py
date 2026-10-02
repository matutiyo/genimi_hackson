import pytest

from app.config import Settings
from app.gemini import GeminiGateway
from app.mock_gemini import MockGeminiGateway
from app.schemas import ClosetImage, EventInput
from app.service import run_proposal

PNG = b"\x89PNG\r\n\x1a\nfake"


def images(*names: str) -> list[ClosetImage]:
    return [ClosetImage(index=i, filename=n, mime_type="image/png", data=PNG) for i, n in enumerate(names)]


def settings() -> Settings:
    return Settings(use_mock_gemini=True, step_timeout_sec=5)


async def collect(inp: EventInput, imgs: list[ClosetImage], gateway=None) -> list[dict]:
    s = settings()
    return [m async for m in run_proposal(inp, imgs, s, gateway or MockGeminiGateway(s))]


MANUAL = EventInput(artist_name="テストバンド", genre="パンク", event_date="2026-12-05", venue="Zepp Haneda",
                    mv_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")


@pytest.mark.asyncio
async def test_full_flow_runs_critic_loop_and_returns_result():
    msgs = await collect(MANUAL, images("a.png", "b.png", "c.png", "d.png"))
    steps = [m["step"] for m in msgs if m["type"] == "step"]
    # 1回目は Critic 不合格 → 再生成 → 合格
    assert steps.count("outfit_generator") == 2
    critic_events = [m for m in msgs if m.get("step") == "critic"]
    assert [c["passed"] for c in critic_events] == [False, True]

    result = msgs[-1]["result"]
    assert msgs[-1]["type"] == "result"
    assert result["culture"]["genre_id"] == "punk"
    assert result["culture"]["source_url"].startswith("https://ja.wikipedia.org/")
    assert result["mv_style"]["analyzed_from"] == "video"
    assert result["venue_weather"]["season"] == "冬"
    assert {i["category"] for i in result["items"]} >= {"tops", "bottoms", "shoes"}
    assert result["image_base64"]
    assert result["critic"]["passed"] is True


@pytest.mark.asyncio
async def test_selected_candidate_is_used_without_searching_again():
    inp = MANUAL.model_copy(update={"keyword": "fail", "event_title": "TEST TOUR"})
    msgs = await collect(inp, images("a.png", "b.png", "c.png"))
    result = msgs[-1]["result"]
    assert result["event"]["artist_name"] == "テストバンド"
    assert result["event"]["event_title"] == "TEST TOUR"
    assert result["event"]["source"] == "manual"
    assert not any("検索" in n for n in result["notes"])


@pytest.mark.asyncio
async def test_keyword_only_uses_top_search_result():
    msgs = await collect(EventInput(keyword="モックバンド"), images("a.png", "b.png", "c.png"))
    result = msgs[-1]["result"]
    assert result["event"]["source"] == "search"
    assert result["event"]["venue"] == "Zepp Haneda"
    assert result["mv_style"]["analyzed_from"] == "video"
    assert any("検索結果" in n for n in result["notes"])


@pytest.mark.asyncio
async def test_keyword_with_detail_conditions_narrows_search():
    msgs = await collect(EventInput(keyword="モックバンド", venue="幕張メッセ"), images("a.png", "b.png", "c.png"))
    event = msgs[-1]["result"]["event"]
    assert event["source"] == "search+manual"
    assert event["event_title"] == "MOCK FES 2027"
    assert event["venue"] == "幕張メッセ"


@pytest.mark.asyncio
async def test_search_failure_falls_back_to_keyword_as_artist():
    for keyword in ("fail-band", "nohit-band"):
        msgs = await collect(EventInput(keyword=keyword), images("a.png", "b.png", "c.png"))
        result = msgs[-1]["result"]
        assert result["event"]["artist_name"] == keyword
        assert any("検索できなかった" in n for n in result["notes"])


@pytest.mark.asyncio
async def test_missing_artist_is_fatal():
    msgs = await collect(EventInput(), images("a.png"))
    assert msgs[-1]["type"] == "error"
    assert "アーティスト名" in msgs[-1]["message"]


@pytest.mark.asyncio
async def test_mv_failure_uses_thumbnail_and_missing_mv_is_noted():
    msgs = await collect(MANUAL.model_copy(update={"mv_url": "https://youtu.be/fail0000000"}), images("a.png", "b.png", "c.png"))
    assert msgs[-1]["result"]["mv_style"]["analyzed_from"] == "thumbnail"
    msgs = await collect(MANUAL.model_copy(update={"mv_url": None}), images("a.png", "b.png", "c.png"))
    assert any("MV" in n for n in msgs[-1]["result"]["notes"])


@pytest.mark.asyncio
async def test_closet_partial_and_total_failure():
    msgs = await collect(MANUAL, images("a.png", "fail.png", "c.png", "d.png"))
    assert any("fail.png" in n for n in msgs[-1]["result"]["notes"])
    msgs = await collect(MANUAL, images("fail1.png", "fail2.png"))
    assert msgs[-1]["type"] == "error"



@pytest.mark.asyncio
async def test_image_without_clothes_is_skipped_with_note():
    msgs = await collect(MANUAL, images("a.png", "empty.png", "c.png"))
    result = msgs[-1]["result"]
    assert any("empty.png" in n and "服が写っていない" in n for n in result["notes"])
    assert all(i["image_index"] != 1 for i in result["items"])
    msgs = await collect(MANUAL, images("empty1.png", "empty2.png"))
    assert msgs[-1]["type"] == "error"


class NoGenreGateway(MockGeminiGateway):
    """ジャンル判定だけ失敗する(カルチャー情報の対象外になる)ケース。"""

    async def match_genre(self, *a, **k):
        raise RuntimeError("no genre")


@pytest.mark.asyncio
async def test_notes_match_the_given_input():
    # MV・公演日なし: 「MV解析の結果を中心に」「天気は公演日の季節から」は出さない
    inp = EventInput(artist_name="テストバンド", genre="謎ジャンル")
    msgs = await collect(inp, images("a.png", "b.png", "c.png"), NoGenreGateway(settings()))
    notes = msgs[-1]["result"]["notes"]
    assert any("手持ち服を中心に" in n and "会場" not in n and "季節" not in n for n in notes)
    assert not any("MV解析の結果を中心に" in n for n in notes)
    assert not any("天気は公演日の季節から" in n for n in notes)
    assert any("公演日が不明" in n for n in notes)

    # MV・公演日あり: MV を中心にした旨と天気の目安を出す
    msgs = await collect(MANUAL.model_copy(update={"genre": "謎ジャンル"}), images("a.png", "b.png", "c.png"),
                         NoGenreGateway(settings()))
    notes = msgs[-1]["result"]["notes"]
    assert any("MV解析の結果を中心に" in n for n in notes)
    assert any("天気は公演日の季節から" in n for n in notes)

    # MV なし・会場と公演日あり: 入力された情報だけを挙げる
    inp = EventInput(artist_name="テストバンド", genre="謎ジャンル", venue="Zepp Haneda", event_date="2026-12-05")
    msgs = await collect(inp, images("a.png", "b.png", "c.png"), NoGenreGateway(settings()))
    assert any("会場・季節と手持ち服を中心に" in n for n in msgs[-1]["result"]["notes"])


class BrokenGateway(MockGeminiGateway):
    """P08 以外のすべての Gemini 呼び出しが失敗するケース。"""

    async def _boom(self, *a, **k):
        raise RuntimeError("API down")

    match_genre = summarize_culture = analyze_mv_video = analyze_mv_thumbnail = _boom
    infer_venue = integrate_profile = generate_outfit = critique = generate_outfit_image = _boom


@pytest.mark.asyncio
async def test_all_fallbacks_keep_service_running():
    s = settings()
    msgs = await collect(MANUAL.model_copy(update={"genre": "謎ジャンル"}), images("a.png", "b.png", "c.png"), BrokenGateway(s))
    assert msgs[-1]["type"] == "result"
    result = msgs[-1]["result"]
    assert result["items"]  # ルールベースの基本コーデ
    assert result["image_base64"] is None
    assert any("テキスト" in n for n in result["notes"])
    assert result["culture"]["covered"] is False


def test_gateway_is_real_class_when_not_mocked(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy")
    from app.gemini import build_gateway

    gw = build_gateway(Settings(use_mock_gemini=False))
    assert type(gw) is GeminiGateway
