"""Gemini API 呼び出しの窓口。

エージェント側はこのクラスのメソッドだけを呼ぶ。`USE_MOCK_GEMINI=true` のときは
`MockGeminiGateway` に差し替わり、APIキー無しでも全フローを動かせる。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import TypeVar

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel

from . import prompts
from .config import Settings
from .schemas import (
    ClosetAnalysis,
    ClosetImage,
    CriticLlmOutput,
    CultureSummary,
    EventCandidate,
    EventSearchResult,
    GenreMatch,
    MvStyle,
    OutfitCandidate,
    SearchSource,
    StyleProfile,
    VenueInfo,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_YOUTUBE_ID = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})")


def youtube_video_id(url: str) -> str | None:
    match = _YOUTUBE_ID.search(url)
    return match.group(1) if match else None


def _extract_json(text: str) -> str:
    """ツール併用時(構造化出力が使えない)にテキストから JSON 部分を取り出す。"""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        return fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"JSONが見つかりません: {text[:200]}")
    return text[start : end + 1]


def _valid_date(value: str | None) -> str | None:
    try:
        return date.fromisoformat(value).isoformat() if value else None
    except ValueError:
        return None


def search_conditions(
    artist_name: str | None = None,
    event_title: str | None = None,
    genre: str | None = None,
    venue: str | None = None,
    event_date: str | None = None,
) -> dict[str, str]:
    """詳細検索の条件(入力のあったものだけ)。キーは Gemini に渡す項目名。"""
    labeled = {"アーティスト名": artist_name, "公演名": event_title, "ジャンル": genre, "会場": venue, "公演日": event_date}
    return {label: value.strip() for label, value in labeled.items() if value and value.strip()}


def _conditions_text(conditions: dict[str, str] | None) -> str:
    lines = [f"  - {label}: {value}" for label, value in (conditions or {}).items() if value]
    if not lines:
        return ""
    return "- 次の詳細条件にすべて合う公演だけを候補にすること(合うものが無ければ \"candidates\": [])。\n" + "\n".join(lines) + "\n"


def _normalize(text: str) -> str:
    return re.sub(r"[\s・._\-]", "", text).lower()


async def _verify_mv(artist: str, url: str | None) -> tuple[str | None, str | None]:
    """検索結果の MV URL が実在し、アーティストの動画であることを YouTube oEmbed で確かめる。

    LLM が存在しない動画IDを返すことがあるため、確認できないものは使わない(None を返す)。
    """
    if not url or not youtube_video_id(url):
        return None, None
    canonical = f"https://www.youtube.com/watch?v={youtube_video_id(url)}"
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get("https://www.youtube.com/oembed", params={"url": canonical, "format": "json"})
            resp.raise_for_status()
            info = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.info("MV URL を確認できませんでした: %s (%s)", canonical, exc)
        return None, None
    title, channel = info.get("title") or "", info.get("author_name") or ""
    if _normalize(artist) not in _normalize(title + channel):
        logger.info("MV がアーティストのものと確認できませんでした: %s / %s", title, channel)
        return None, None
    return canonical, title


class GeminiGateway:
    """実際の Gemini API を呼ぶ実装。"""

    def __init__(self, settings: Settings, client: genai.Client | None = None) -> None:
        self.settings = settings
        # APIキー(GOOGLE_API_KEY)または Vertex AI(GOOGLE_GENAI_USE_VERTEXAI=TRUE 等)の
        # 環境変数を SDK が自動で読み込む。
        self.client = client or genai.Client()

    # ---- 共通 -------------------------------------------------------------
    async def _structured(
        self, model: str, contents: list, schema: type[T], temperature: float = 0.4
    ) -> T:
        response = await self.client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=temperature,
            ),
        )
        if isinstance(response.parsed, schema):
            return response.parsed
        return schema.model_validate_json(response.text or "")

    # ---- P04 公演キーワード検索(Google 検索グラウンディング) -------------
    async def search_events(
        self, keyword: str, limit: int = 5, conditions: dict[str, str] | None = None
    ) -> EventSearchResult:
        """conditions: 詳細検索の条件(項目名 → 値)。候補はこの条件に合うものに絞り込む。"""
        prompt = prompts.EVENT_SEARCH_PROMPT.format(
            keyword=keyword,
            today=date.today().isoformat(),
            limit=limit,
            conditions=_conditions_text(conditions),
        )
        response = await self.client.aio.models.generate_content(
            model=self.settings.text_model,
            contents=[prompt],
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.0,
            ),
        )
        data = json.loads(_extract_json(response.text or ""))
        candidates: list[EventCandidate] = []
        for raw in data.get("candidates") or []:
            if not isinstance(raw, dict) or not raw.get("artist_name"):
                continue
            candidate = EventCandidate(**{k: raw.get(k) for k in EventCandidate.model_fields if k in raw})
            candidate.event_date = _valid_date(candidate.event_date)
            candidate.mv_url, candidate.mv_title = await _verify_mv(candidate.artist_name, candidate.mv_url)
            candidates.append(candidate)

        sources: list[SearchSource] = []
        metadata = response.candidates[0].grounding_metadata if response.candidates else None
        for chunk in (metadata.grounding_chunks if metadata else None) or []:
            if chunk.web and chunk.web.uri and len(sources) < 5:
                sources.append(SearchSource(title=chunk.web.title or chunk.web.uri, url=chunk.web.uri))
        return EventSearchResult(candidates=candidates[:limit], sources=sources)

    # ---- P05 カルチャー情報 ----------------------------------------------
    async def match_genre(self, artist: str, genre: str | None, candidates: list[dict]) -> GenreMatch:
        lines = "\n".join(f"- {c['id']}: {c['name']}" for c in candidates)
        return await self._structured(
            self.settings.text_model,
            [prompts.GENRE_MATCH_PROMPT.format(artist=artist, genre=genre or "未入力", candidates=lines)],
            GenreMatch,
            temperature=0.0,
        )

    async def summarize_culture(self, artist: str, genre_name: str, keywords: list[str]) -> CultureSummary:
        return await self._structured(
            self.settings.text_model,
            [
                prompts.CULTURE_SUMMARY_PROMPT.format(
                    artist=artist,
                    genre_name=genre_name,
                    keywords="、".join(keywords),
                    safety=prompts.SAFETY_NOTE,
                )
            ],
            CultureSummary,
        )

    # ---- P06 MV解析 -------------------------------------------------------
    async def analyze_mv_video(self, artist: str, youtube_url: str) -> MvStyle:
        result = await self._structured(
            self.settings.video_model,
            [
                # Vertex AI は mime_type 必須(Gemini API では省略可)
                types.Part(file_data=types.FileData(file_uri=youtube_url, mime_type="video/mp4")),
                prompts.MV_ANALYSIS_PROMPT.format(source="動画", artist=artist, safety=prompts.SAFETY_NOTE),
            ],
            MvStyle,
        )
        result.analyzed_from = "video"
        return result

    async def analyze_mv_thumbnail(self, artist: str, youtube_url: str) -> MvStyle:
        video_id = youtube_video_id(youtube_url)
        if not video_id:
            raise ValueError("YouTube URLから動画IDを取得できませんでした")
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg")
            resp.raise_for_status()
        result = await self._structured(
            self.settings.vision_model,
            [
                types.Part.from_bytes(data=resp.content, mime_type="image/jpeg"),
                prompts.MV_ANALYSIS_PROMPT.format(source="画像", artist=artist, safety=prompts.SAFETY_NOTE),
            ],
            MvStyle,
        )
        result.analyzed_from = "thumbnail"
        return result

    # ---- P07 会場情報 ------------------------------------------------------
    async def infer_venue(self, venue: str) -> VenueInfo:
        return await self._structured(
            self.settings.text_model,
            [prompts.VENUE_PROMPT.format(venue=venue)],
            VenueInfo,
            temperature=0.0,
        )

    # ---- P08 手持ち服解析 -------------------------------------------------
    async def analyze_closet_image(self, image: ClosetImage) -> ClosetAnalysis:
        return await self._structured(
            self.settings.vision_model,
            [types.Part.from_bytes(data=image.data, mime_type=image.mime_type), prompts.CLOSET_PROMPT],
            ClosetAnalysis,
            temperature=0.1,
        )

    # ---- P09 統合 ----------------------------------------------------------
    async def integrate_profile(self, prompt: str) -> StyleProfile:
        return await self._structured(self.settings.text_model, [prompt], StyleProfile)

    # ---- P10 / P11 --------------------------------------------------------
    async def generate_outfit(self, prompt: str) -> OutfitCandidate:
        return await self._structured(self.settings.text_model, [prompt], OutfitCandidate, temperature=0.7)

    async def critique(self, prompt: str) -> CriticLlmOutput:
        return await self._structured(self.settings.text_model, [prompt], CriticLlmOutput, temperature=0.0)

    # ---- P13 画像生成(Nano Banana 系) -----------------------------------
    async def generate_outfit_image(
        self, prompt: str, reference_images: list[ClosetImage]
    ) -> tuple[bytes, str] | None:
        contents: list = [prompt]
        contents += [types.Part.from_bytes(data=img.data, mime_type=img.mime_type) for img in reference_images]
        response = await self.client.aio.models.generate_content(
            model=self.settings.image_model,
            contents=contents,
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
        for candidate in response.candidates or []:
            for part in (candidate.content.parts if candidate.content else None) or []:
                if part.inline_data and part.inline_data.data:
                    return part.inline_data.data, part.inline_data.mime_type or "image/png"
        return None


def build_gateway(settings: Settings) -> GeminiGateway:
    if settings.use_mock_gemini:
        from .mock_gemini import MockGeminiGateway

        logger.warning("USE_MOCK_GEMINI=true: Gemini API を呼ばずにモック応答を返します")
        return MockGeminiGateway(settings)
    return GeminiGateway(settings)
