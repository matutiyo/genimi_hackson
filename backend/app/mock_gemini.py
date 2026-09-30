"""Gemini API を呼ばないモック実装(ローカル画面確認・テスト用)。

- 手持ち服は画像の並び順に応じて擬似的な属性を割り当てる
- Critic は 1 回目を不合格、再生成後を合格にして自己批評ループを必ず通す
"""

from __future__ import annotations

import asyncio
import html
import json
import re

from .config import Settings
from .gemini import GeminiGateway
from .schemas import (
    ClosetAnalysis,
    ClosetImage,
    ClosetItemRaw,
    CriticLlmOutput,
    CriticScores,
    CultureSummary,
    EventInfo,
    GenreMatch,
    MvStyle,
    OutfitCandidate,
    StyleProfile,
    VenueInfo,
)

_MOCK_ITEMS: list[ClosetItemRaw] = [
    ClosetItemRaw(category="tops", name="黒のバンドTシャツ", colors=["黒", "白"], material="コットン",
                  pattern="プリント", silhouette="レギュラー", style_tags=["ロック", "カジュアル"]),
    ClosetItemRaw(category="bottoms", name="ブラックデニムのスキニーパンツ", colors=["黒"], material="デニム",
                  pattern="無地", silhouette="タイト", style_tags=["ロック"]),
    ClosetItemRaw(category="shoes", name="黒のレザーブーツ", colors=["黒"], material="レザー",
                  pattern="無地", silhouette=None, style_tags=["ハード"]),
    ClosetItemRaw(category="outer", name="赤のタータンチェックシャツ", colors=["赤", "黒"], material="ネル",
                  pattern="タータンチェック", silhouette="オーバーサイズ", style_tags=["グランジ"]),
    ClosetItemRaw(category="tops", name="白の無地Tシャツ", colors=["白"], material="コットン",
                  pattern="無地", silhouette="レギュラー", style_tags=["ベーシック"]),
    ClosetItemRaw(category="bottoms", name="ベージュのチノパンツ", colors=["ベージュ"], material="コットン",
                  pattern="無地", silhouette="ストレート", style_tags=["きれいめ"]),
    ClosetItemRaw(category="shoes", name="白のキャンバススニーカー", colors=["白"], material="キャンバス",
                  pattern="無地", silhouette=None, style_tags=["カジュアル"]),
    ClosetItemRaw(category="accessory", name="シルバーのチェーンネックレス", colors=["シルバー"], material="金属",
                  pattern=None, silhouette=None, style_tags=["ロック"]),
]


class MockGeminiGateway(GeminiGateway):
    def __init__(self, settings: Settings) -> None:  # noqa: D107 - client は作らない
        self.settings = settings
        self.client = None  # type: ignore[assignment]

    async def _delay(self, factor: float = 1.0) -> None:
        if self.settings.mock_delay_sec > 0:
            await asyncio.sleep(self.settings.mock_delay_sec * factor)

    async def parse_event_url(self, url: str) -> EventInfo:
        await self._delay()
        if "fail" in url:
            raise ValueError("モック: URL解析失敗")
        return EventInfo(artist_name="モックバンド", event_title="MOCK TOUR 2026",
                         event_date="2026-12-05", venue="Zepp Haneda", genre_hint="パンク", source="url")

    async def match_genre(self, artist: str, genre: str | None, candidates: list[dict]) -> GenreMatch:
        await self._delay()
        text = f"{artist} {genre or ''}".lower()
        for c in candidates:
            if any(alias.lower() in text for alias in c.get("aliases", [])):
                return GenreMatch(genre_id=c["id"], reason="モック: 別名一致")
        return GenreMatch(genre_id="jrock", reason="モック: 既定値")

    async def summarize_culture(self, artist: str, genre_name: str, keywords: list[str]) -> CultureSummary:
        await self._delay()
        return CultureSummary(
            explanation=f"{genre_name}系のライブでは、{('・'.join(keywords[:3]))}といった要素を取り入れた服装がよく見られます。"
                        "必ずしも決まりではないので、動きやすさを優先しつつ一部に取り入れるのがおすすめです。(モック)",
            keywords=keywords[:6],
        )

    async def analyze_mv_video(self, artist: str, youtube_url: str) -> MvStyle:
        await self._delay()
        if "fail" in youtube_url:
            raise ValueError("モック: 動画解析失敗")
        return MvStyle(color_palette=["黒", "赤", "モノクロ"], lighting_mood="強いコントラストのスポットライト",
                       fashion_items=["レザージャケット", "チェックシャツ", "ブーツ"],
                       silhouettes=["タイトなボトムス", "ゆるめのトップス"],
                       overall_vibe="荒々しく疾走感のあるライブハウスの空気", analyzed_from="video")

    async def analyze_mv_thumbnail(self, artist: str, youtube_url: str) -> MvStyle:
        await self._delay()
        return MvStyle(color_palette=["黒", "赤"], lighting_mood="暗めの照明", fashion_items=["Tシャツ"],
                       silhouettes=["レギュラー"], overall_vibe="ラフでエネルギッシュ", analyzed_from="thumbnail")

    async def infer_venue(self, venue: str) -> VenueInfo:
        await self._delay()
        return VenueInfo(venue_type="standing", capacity_note="数千人規模のライブハウス",
                         notes=["オールスタンディングのため動きやすい靴が安心", "ロッカーが混むので荷物は最小限に"])

    async def analyze_closet_image(self, image: ClosetImage) -> ClosetAnalysis:
        await self._delay()
        if "fail" in image.filename:
            raise ValueError("モック: 画像解析失敗")
        if "empty" in image.filename:  # 服が写っていない画像
            return ClosetAnalysis(items=[])
        return ClosetAnalysis(items=[_MOCK_ITEMS[image.index % len(_MOCK_ITEMS)]])

    async def integrate_profile(self, prompt: str) -> StyleProfile:
        await self._delay()
        return StyleProfile(
            summary="黒と赤を軸にしたラフなパンク/ロックスタイル",
            key_colors=["黒", "赤"],
            key_items=["バンドTシャツ", "チェックシャツ", "ブーツ"],
            silhouettes=["トップスはゆるめ", "ボトムスはタイト"],
            avoid=["アーティスト衣装の完全コピー", "ヒールの高い靴"],
            practical_notes=["オールスタンディングなので動きやすさ重視", "冬場は脱ぎ着しやすい羽織りを"],
            confidence_notes=["MVの黒・赤とジャンル定番の黒・赤が一致(確信度高)"],
        )

    async def generate_outfit(self, prompt: str) -> OutfitCandidate:
        await self._delay()
        closet = [json.loads(block) for block in re.findall(r"\{[^{}]*\"item_id\"[^{}]*\}", prompt)]
        chosen: list[str] = []
        seen: set[str] = set()
        for item in closet:
            if item["category"] not in seen:
                chosen.append(item["item_id"])
                seen.add(item["category"])
        revised = "前回候補への指摘" in prompt
        return OutfitCandidate(
            title="黒赤ラフロック" + ("(修正版)" if revised else ""),
            item_ids=chosen[:5] if revised else chosen[:2],
            styling_tips=["チェックシャツは腰巻きにして温度調整", "アクセサリーはシルバーで統一"],
            reason="MVとジャンル定番の両方に現れる黒と赤を軸にしました。スタンディング会場なので"
                   "足元はしっかりしたブーツにし、動きやすさと世界観を両立しています。(モック)",
            missing_suggestions=["スタッズ付きのベルト"],
        )

    async def critique(self, prompt: str) -> CriticLlmOutput:
        await self._delay()
        # item 数が少ない1回目の候補は不合格にしてループを通す
        n_items = len(json.loads(prompt.split("## コーディネート候補(選ばれたアイテムの詳細付き)")[1]
                                 .split("評価軸")[0]).get("items", []))
        if n_items < 3:
            return CriticLlmOutput(
                scores=CriticScores(color_match=4, silhouette_match=3, practicality=2, blend_in=3),
                issues=["靴が含まれておらず、スタンディング会場での実用性が判断できない"],
                revision_instruction="ブーツなど歩きやすい靴と、温度調整できる羽織りを追加してください。",
            )
        return CriticLlmOutput(
            scores=CriticScores(color_match=4, silhouette_match=4, practicality=4, blend_in=4),
            issues=[], revision_instruction="",
        )

    async def generate_outfit_image(self, prompt: str, reference_images: list[ClosetImage]) -> tuple[bytes, str] | None:
        await self._delay(2)
        names = re.findall(r"^- (.+)$", prompt.split("使用アイテム:")[1].split("雰囲気:")[0], re.M)
        rows = "".join(
            f'<rect x="40" y="{70 + i * 56}" width="320" height="44" rx="8" fill="#{"222222" if i % 2 == 0 else "8b1a1a"}"/>'
            f'<text x="200" y="{98 + i * 56}" font-size="16" fill="#fff" text-anchor="middle">{html.escape(n)}</text>'
            for i, n in enumerate(names)
        )
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="480" viewBox="0 0 400 480">'
            '<rect width="400" height="480" fill="#f3efe9"/>'
            '<text x="200" y="42" font-size="18" text-anchor="middle" fill="#333">MOCK コーデ画像</text>'
            f"{rows}</svg>"
        )
        return svg.encode("utf-8"), "image/svg+xml"

