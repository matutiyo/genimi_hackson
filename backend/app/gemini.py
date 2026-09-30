"""Gemini API 呼び出しの窓口。

エージェント側はこのクラスのメソッドだけを呼ぶ。`USE_MOCK_GEMINI=true` のときは
`MockGeminiGateway` に差し替わり、APIキー無しでも全フローを動かせる。
"""

from __future__ import annotations

import json
import logging
import re
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
    EventInfo,
    GenreMatch,
    MvStyle,
    OutfitCandidate,
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

    # ---- P04 公演URL解析(URL Context ツール) -----------------------------
    async def parse_event_url(self, url: str) -> EventInfo:
        response = await self.client.aio.models.generate_content(
            model=self.settings.text_model,
            contents=[prompts.EVENT_URL_PROMPT.format(url=url)],
            config=types.GenerateContentConfig(
                tools=[types.Tool(url_context=types.UrlContext())],
                temperature=0.0,
            ),
        )
        data = json.loads(_extract_json(response.text or ""))
        if not data.get("artist_name"):
            raise ValueError("URLからアーティスト名を抽出できませんでした")
        return EventInfo(**{k: data.get(k) for k in EventInfo.model_fields if k in data}, source="url")

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
