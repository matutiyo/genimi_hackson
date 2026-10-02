"""パイプライン内でやり取りするデータ構造。

ADK のセッション state には JSON 化できる値しか置かないため、
各エージェントは `model_dump()` した dict を state に書き込み、
読み出す側で `model_validate()` して使う。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 入力(P01 / P02)
# ---------------------------------------------------------------------------
class EventInput(BaseModel):
    """P01 公演情報の入力値(キーワード検索の結果 または手動入力)。

    URL の直接入力は受け付けない。公式MVのURLはキーワード検索(P04)で見つかったものだけを使う。
    """

    keyword: str | None = Field(default=None, description="検索キーワード(アーティスト名・公演名など)")
    artist_name: str | None = Field(default=None, description="アーティスト名")
    event_title: str | None = Field(default=None, description="公演名(任意)")
    genre: str | None = Field(default=None, description="ジャンル(任意)")
    event_date: str | None = Field(default=None, description="公演日 YYYY-MM-DD")
    venue: str | None = Field(default=None, description="会場名")
    mv_url: str | None = Field(default=None, description="キーワード検索で見つかった公式MVのYouTube URL")


class ClosetImage(BaseModel):
    """P02 でアップロードされた服画像(バイト列はリクエスト内でのみ保持)。"""

    index: int
    filename: str
    mime_type: str
    data: bytes


# ---------------------------------------------------------------------------
# P04 公演情報解析
# ---------------------------------------------------------------------------
class EventInfo(BaseModel):
    artist_name: str
    event_title: str | None = None
    event_date: str | None = None
    venue: str | None = None
    genre_hint: str | None = None
    mv_url: str | None = None
    source: Literal["search", "manual", "search+manual"] = "manual"


class EventCandidate(BaseModel):
    """キーワード検索で見つかった公演の候補(ユーザーが選ぶ)。"""

    artist_name: str
    event_title: str | None = None
    event_date: str | None = Field(default=None, description="YYYY-MM-DD")
    venue: str | None = None
    genre_hint: str | None = None
    mv_url: str | None = Field(default=None, description="公式チャンネルで公開されているMVのURL(確認済みのもののみ)")
    mv_title: str | None = None


class SearchSource(BaseModel):
    title: str
    url: str


class EventSearchResult(BaseModel):
    candidates: list[EventCandidate] = Field(default_factory=list)
    sources: list[SearchSource] = Field(default_factory=list, description="検索で参照したページ(出典表示用)")


# ---------------------------------------------------------------------------
# P05 カルチャー情報
# ---------------------------------------------------------------------------
class GenreMatch(BaseModel):
    genre_id: str | None = Field(description="候補リスト内のID。該当なしなら null")
    reason: str = ""


class CultureInfo(BaseModel):
    genre_id: str | None = None
    genre_name: str | None = None
    explanation: str | None = Field(default=None, description="ユーザー向けカルチャー解説")
    keywords: list[str] = Field(default_factory=list, description="内部利用のスタイル特徴キーワード")
    source_url: str | None = None
    source_title: str | None = None
    covered: bool = False


class CultureSummary(BaseModel):
    """Gemini に要約させる部分だけの出力スキーマ。"""

    explanation: str
    keywords: list[str]


# ---------------------------------------------------------------------------
# P06 MV解析
# ---------------------------------------------------------------------------
class MvStyle(BaseModel):
    color_palette: list[str] = Field(default_factory=list, description="主な色調")
    lighting_mood: str = ""
    fashion_items: list[str] = Field(default_factory=list, description="出演者が着ている代表的なアイテム")
    silhouettes: list[str] = Field(default_factory=list)
    overall_vibe: str = ""
    analyzed_from: Literal["video", "thumbnail", "none"] = "none"


# ---------------------------------------------------------------------------
# P07 会場・天気(交通は対象外)
# ---------------------------------------------------------------------------
class VenueInfo(BaseModel):
    venue_type: Literal["standing", "seated", "outdoor", "mixed", "unknown"] = "unknown"
    capacity_note: str = ""
    notes: list[str] = Field(default_factory=list)


class VenueWeather(BaseModel):
    venue: VenueInfo = Field(default_factory=VenueInfo)
    season: str | None = None
    weather_note: str = ""
    weather_source: Literal["season_fixed", "none"] = "none"


# ---------------------------------------------------------------------------
# P08 手持ち服解析
# ---------------------------------------------------------------------------
ClothingCategory = Literal[
    "tops", "outer", "bottoms", "onepiece", "shoes", "bag", "accessory", "headwear", "other"
]


class ClosetItemRaw(BaseModel):
    """Gemini の構造化出力スキーマ(1枚の画像に複数アイテムが写る可能性あり)。"""

    category: ClothingCategory
    name: str = Field(description="例: 黒のレザーライダースジャケット")
    colors: list[str]
    material: str | None = None
    pattern: str | None = None
    silhouette: str | None = None
    style_tags: list[str] = Field(default_factory=list)


class ClosetAnalysis(BaseModel):
    items: list[ClosetItemRaw]


class ClosetItem(ClosetItemRaw):
    item_id: str
    image_index: int


# ---------------------------------------------------------------------------
# P09 スタイル統合
# ---------------------------------------------------------------------------
class StyleProfile(BaseModel):
    summary: str = Field(description="目指すスタイルの一文要約")
    key_colors: list[str]
    key_items: list[str]
    silhouettes: list[str]
    avoid: list[str] = Field(default_factory=list, description="浮く/危険などで避けたい要素")
    practical_notes: list[str] = Field(default_factory=list, description="会場・天気由来の実用的注意")
    confidence_notes: list[str] = Field(
        default_factory=list, description="MVとジャンル定番の一致/不一致など確信度に関するメモ"
    )


# ---------------------------------------------------------------------------
# P10 コーデ生成 / P11 Critic
# ---------------------------------------------------------------------------
class OutfitCandidate(BaseModel):
    title: str
    item_ids: list[str] = Field(description="手持ち服の item_id のみを使う")
    styling_tips: list[str] = Field(default_factory=list)
    reason: str = Field(description="選定理由")
    missing_suggestions: list[str] = Field(
        default_factory=list, description="手持ちに無いが足すと良いアイテム(任意)"
    )


class CriticScores(BaseModel):
    color_match: int = Field(ge=1, le=5, description="色調一致度")
    silhouette_match: int = Field(ge=1, le=5, description="シルエット近似度")
    practicality: int = Field(ge=1, le=5, description="会場・天候への適合度")
    blend_in: int = Field(ge=1, le=5, description="浮かず埋もれない度合い")


class CriticLlmOutput(BaseModel):
    scores: CriticScores
    issues: list[str] = Field(default_factory=list)
    revision_instruction: str = ""


class CriticResult(CriticLlmOutput):
    passed: bool
    rule_violations: list[str] = Field(default_factory=list)
    iteration: int


# ---------------------------------------------------------------------------
# P14 最終結果
# ---------------------------------------------------------------------------
class ProposalItem(BaseModel):
    item_id: str
    name: str
    category: str
    image_index: int


class ProposalResult(BaseModel):
    event: EventInfo | None
    outfit_title: str | None
    items: list[ProposalItem]
    styling_tips: list[str]
    reason: str | None
    missing_suggestions: list[str]
    culture: CultureInfo | None
    mv_style: MvStyle | None
    venue_weather: VenueWeather | None
    critic: CriticResult | None
    image_base64: str | None
    image_mime_type: str | None
    notes: list[str]
