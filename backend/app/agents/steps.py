"""パイプラインの各処理(P04〜P13)を ADK のカスタムエージェントとして実装する。

各エージェントは Gemini を呼び出して結果を ADK セッション state に書き込む。
LLM に処理順を委ねず、処理フロー(Sequential / Parallel / Loop)は pipeline.py で固定する。

- 各ステップの失敗は「異常時の処理」列のフォールバックに切り替え、全体は止めない(F30)
- ユーザーに伝えるべき事項は `notes:<agent名>` に書き、最終結果の注意事項に集約する
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, AsyncGenerator, Awaitable, TypeVar

from google.adk.agents import BaseAgent, InvocationContext
from google.adk.events import Event, EventActions
from pydantic import ConfigDict

from .. import prompts
from ..config import Settings
from ..gemini import GeminiGateway
from ..schemas import (
    ClosetImage,
    ClosetItem,
    CriticLlmOutput,
    CriticResult,
    CriticScores,
    CultureInfo,
    EventInfo,
    EventInput,
    MvStyle,
    OutfitCandidate,
    StyleProfile,
    VenueInfo,
    VenueWeather,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")

GENRES_PATH = Path(__file__).resolve().parent.parent / "data" / "culture_genres.json"


def load_genres() -> list[dict]:
    return json.loads(GENRES_PATH.read_text(encoding="utf-8"))["genres"]


@dataclass
class PipelineDeps:
    """1リクエスト分の依存物。画像バイト列は state に載せずここで保持する(永続保存しない)。"""

    settings: Settings
    gateway: GeminiGateway
    images: list[ClosetImage]
    genres: list[dict] = field(default_factory=load_genres)


class FatalPipelineError(Exception):
    """これ以上処理を続けられない失敗(ユーザーに入力し直してもらう)。"""


# ---------------------------------------------------------------------------
# 共通基底
# ---------------------------------------------------------------------------
class StepAgent(BaseAgent):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    deps: Any  # PipelineDeps(pydantic の検証対象外にするため Any)
    label: str = ""

    async def call(self, awaitable: Awaitable[T]) -> T:
        return await asyncio.wait_for(awaitable, timeout=self.deps.settings.step_timeout_sec)

    async def run_step(self, state: dict[str, Any], notes: list[str]) -> tuple[dict[str, Any], bool]:
        """state_delta と escalate フラグを返す。notes にユーザー向け注意事項を追記する。"""
        raise NotImplementedError

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = dict(ctx.session.state)
        if state.get("fatal_error"):
            return
        notes_key = f"notes:{self.name}"
        notes: list[str] = list(state.get(notes_key, []))
        escalate = False
        try:
            delta, escalate = await self.run_step(state, notes)
        except FatalPipelineError as exc:
            delta = {"fatal_error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - 想定外エラーでもサービス全体は止めない
            logger.exception("%s で想定外のエラー", self.name)
            delta = {"fatal_error": f"{self.label}で予期しないエラーが発生しました: {exc}"}
        delta[notes_key] = notes
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            actions=EventActions(state_delta=delta, escalate=escalate or None),
        )


# ---------------------------------------------------------------------------
# P04 公演情報解析
# ---------------------------------------------------------------------------
class EventParseAgent(StepAgent):
    async def run_step(self, state, notes):
        inp = EventInput.model_validate(state["input"])
        manual = EventInfo(
            artist_name=inp.artist_name or "",
            event_date=inp.event_date,
            venue=inp.venue,
            genre_hint=inp.genre,
            mv_url=inp.mv_url,
            source="manual",
        )
        event = manual
        if inp.event_url:
            try:
                parsed = await self.call(self.deps.gateway.parse_event_url(inp.event_url))
                # URL 抽出結果を基本とし、手動入力があればそちらを優先して上書きする
                merged = parsed.model_dump()
                for key in ("artist_name", "event_date", "venue", "genre_hint", "mv_url"):
                    manual_value = getattr(manual, key)
                    if manual_value:
                        merged[key] = manual_value
                merged["source"] = "url+manual" if any(
                    getattr(manual, k) for k in ("artist_name", "event_date", "venue")
                ) else "url"
                event = EventInfo.model_validate(merged)
            except Exception as exc:  # noqa: BLE001
                logger.warning("公演URL解析に失敗: %s", exc)
                notes.append("公演URLから情報を読み取れなかったため、手動入力の内容で提案しています。")
        if not event.artist_name:
            raise FatalPipelineError(
                "公演URLからアーティスト名を読み取れませんでした。アーティスト名を手動で入力してください。"
            )
        return {"event": event.model_dump()}, False


# ---------------------------------------------------------------------------
# P05 カルチャー情報(事前収集データ + Gemini 要約)
# ---------------------------------------------------------------------------
class CultureAgent(StepAgent):
    def _match_by_alias(self, text: str) -> dict | None:
        lowered = text.lower()
        for genre in self.deps.genres:
            if any(alias.lower() == lowered or alias.lower() in lowered for alias in genre["aliases"]):
                return genre
        return None

    async def run_step(self, state, notes):
        event = EventInfo.model_validate(state["event"])
        genre = self._match_by_alias(event.genre_hint) if event.genre_hint else None
        if genre is None:
            try:
                match = await self.call(
                    self.deps.gateway.match_genre(event.artist_name, event.genre_hint, self.deps.genres)
                )
                genre = next((g for g in self.deps.genres if g["id"] == match.genre_id), None)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ジャンル判定に失敗: %s", exc)

        if genre is None:
            notes.append("このアーティストのジャンルは現在のカルチャー情報の対象外のため、MV解析の結果を中心に提案しています。")
            return {"culture": CultureInfo(covered=False).model_dump()}, False

        culture = CultureInfo(
            genre_id=genre["id"],
            genre_name=genre["name"],
            keywords=list(genre["keywords"]),
            source_url=genre["source_url"],
            source_title=genre["source_title"],
            covered=True,
        )
        try:
            summary = await self.call(
                self.deps.gateway.summarize_culture(event.artist_name, genre["name"], genre["keywords"])
            )
            culture.explanation = summary.explanation
            culture.keywords = list(dict.fromkeys(summary.keywords + genre["keywords"]))
        except Exception as exc:  # noqa: BLE001
            logger.warning("カルチャー解説の生成に失敗: %s", exc)
            culture.explanation = (
                f"{genre['name']}系のライブでは「{'」「'.join(genre['keywords'][:4])}」などの要素がよく見られます。"
            )
        return {"culture": culture.model_dump()}, False


# ---------------------------------------------------------------------------
# P06 MV解析(動画 → サムネイル → なし)
# ---------------------------------------------------------------------------
class MvAnalysisAgent(StepAgent):
    async def run_step(self, state, notes):
        event = EventInfo.model_validate(state["event"])
        if not event.mv_url:
            notes.append("公式MVのURLが未入力のため、MV解析は行っていません。")
            return {"mv_style": MvStyle(analyzed_from="none").model_dump()}, False
        try:
            mv = await self.call(self.deps.gateway.analyze_mv_video(event.artist_name, event.mv_url))
        except Exception as exc:  # noqa: BLE001
            logger.warning("MV動画解析に失敗、サムネイル解析に切替: %s", exc)
            try:
                mv = await self.call(self.deps.gateway.analyze_mv_thumbnail(event.artist_name, event.mv_url))
                notes.append("MV動画を解析できなかったため、サムネイル画像から雰囲気を読み取りました。")
            except Exception as exc2:  # noqa: BLE001
                logger.warning("サムネイル解析にも失敗: %s", exc2)
                notes.append("MVを解析できなかったため、ジャンル情報を中心に提案しています。")
                mv = MvStyle(analyzed_from="none")
        return {"mv_style": mv.model_dump()}, False


# ---------------------------------------------------------------------------
# P07 会場・天気(天気は季節の固定文言で簡易対応、交通は対象外)
# ---------------------------------------------------------------------------
_SEASON_NOTES = {
    "冬": "冬場は屋外の待機列が冷えます。会場内は暑くなるので、脱いでしまえる羽織りでの温度調整がおすすめです。",
    "春": "春は朝晩の寒暖差があります。薄手の羽織りがあると安心です。",
    "夏": "夏場は熱中症対策を優先し、通気性の良い素材と汗対策を意識しましょう。",
    "秋": "秋は日によって気温差が大きいので、重ね着で調整できる服装が安心です。",
}


def season_of(event_date: str | None) -> str | None:
    if not event_date:
        return None
    try:
        month = date.fromisoformat(event_date[:10]).month
    except ValueError:
        return None
    return {12: "冬", 1: "冬", 2: "冬", 3: "春", 4: "春", 5: "春",
            6: "夏", 7: "夏", 8: "夏", 9: "秋", 10: "秋", 11: "秋"}[month]


class VenueWeatherAgent(StepAgent):
    async def run_step(self, state, notes):
        event = EventInfo.model_validate(state["event"])
        result = VenueWeather()
        season = season_of(event.event_date)
        if season:
            result.season = season
            result.weather_note = _SEASON_NOTES[season]
            result.weather_source = "season_fixed"
        else:
            notes.append("公演日が不明なため、季節・天気は考慮していません。")
        if event.venue:
            try:
                result.venue = await self.call(self.deps.gateway.infer_venue(event.venue))
            except Exception as exc:  # noqa: BLE001
                logger.warning("会場情報の取得に失敗: %s", exc)
                result.venue = VenueInfo(venue_type="unknown")
        notes.append("天気は公演日の季節から一般的な目安を表示しています(当日の予報ではありません)。")
        return {"venue_weather": result.model_dump()}, False


# ---------------------------------------------------------------------------
# P08 手持ち服解析
# ---------------------------------------------------------------------------
class ClosetAnalysisAgent(StepAgent):
    async def run_step(self, state, notes):
        images: list[ClosetImage] = self.deps.images
        results = await asyncio.gather(
            *(self.call(self.deps.gateway.analyze_closet_image(img)) for img in images),
            return_exceptions=True,
        )
        items: list[ClosetItem] = []
        for img, res in zip(images, results):
            if isinstance(res, BaseException):
                logger.warning("画像 %s の解析に失敗: %s", img.filename, res)
                notes.append(f"画像「{img.filename}」は服を読み取れなかったためスキップしました。")
                continue
            for k, raw in enumerate(res.items):
                items.append(ClosetItem(item_id=f"img{img.index}-{k}", image_index=img.index, **raw.model_dump()))
        if not items:
            raise FatalPipelineError("アップロードされた画像から服を読み取れませんでした。服がはっきり写った画像で再度お試しください。")
        return {"closet_items": [i.model_dump() for i in items]}, False


# ---------------------------------------------------------------------------
# P09 スタイル特徴の統合
# ---------------------------------------------------------------------------
def _closet_summary(items: list[ClosetItem]) -> str:
    return "\n".join(f"- {i.category}: {i.name}(色: {'/'.join(i.colors)})" for i in items)


def fallback_profile(culture: CultureInfo | None, mv: MvStyle | None, vw: VenueWeather | None) -> StyleProfile:
    colors = (mv.color_palette if mv else []) or [k for k in (culture.keywords if culture else []) if len(k) <= 3]
    return StyleProfile(
        summary=(mv.overall_vibe if mv and mv.overall_vibe else "") or
        (f"{culture.genre_name}系のライブに馴染むスタイル" if culture and culture.genre_name else "動きやすいライブ向けスタイル"),
        key_colors=colors[:4] or ["黒"],
        key_items=((mv.fashion_items if mv else []) + (culture.keywords if culture else []))[:6],
        silhouettes=mv.silhouettes if mv else [],
        practical_notes=[n for n in [vw.weather_note if vw else "", *(vw.venue.notes if vw else [])] if n],
    )


class IntegrateStyleAgent(StepAgent):
    async def run_step(self, state, notes):
        event = EventInfo.model_validate(state["event"])
        culture = CultureInfo.model_validate(state["culture"]) if state.get("culture") else None
        mv = MvStyle.model_validate(state["mv_style"]) if state.get("mv_style") else None
        vw = VenueWeather.model_validate(state["venue_weather"]) if state.get("venue_weather") else None
        items = [ClosetItem.model_validate(i) for i in state["closet_items"]]
        try:
            profile = await self.call(
                self.deps.gateway.integrate_profile(
                    prompts.integrate_prompt(event.artist_name, culture, mv, vw, _closet_summary(items))
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("スタイル統合に失敗、ルールベースで代替: %s", exc)
            profile = fallback_profile(culture, mv, vw)
        return {"profile": profile.model_dump()}, False


# ---------------------------------------------------------------------------
# P10 コーデ候補生成(Generator)
# ---------------------------------------------------------------------------
_CATEGORY_ORDER = ["tops", "onepiece", "outer", "bottoms", "shoes", "bag", "accessory", "headwear", "other"]


def fallback_outfit(items: list[ClosetItem]) -> OutfitCandidate:
    """最も近い組み合わせとして各カテゴリから1点ずつ選ぶ。"""
    chosen: dict[str, ClosetItem] = {}
    for item in sorted(items, key=lambda i: _CATEGORY_ORDER.index(i.category)):
        chosen.setdefault(item.category, item)
    return OutfitCandidate(
        title="手持ち服からの基本コーデ",
        item_ids=[i.item_id for i in chosen.values()][:5],
        reason="AIによる選定ができなかったため、手持ち服から各カテゴリ1点ずつを組み合わせた基本の提案です。",
    )


class OutfitGeneratorAgent(StepAgent):
    async def run_step(self, state, notes):
        profile = StyleProfile.model_validate(state["profile"])
        items = [ClosetItem.model_validate(i) for i in state["closet_items"]]
        valid_ids = {i.item_id for i in items}
        previous = state.get("critic")
        feedback = None
        if previous and not previous["passed"]:
            feedback = "\n".join([*previous["issues"], *previous["rule_violations"], previous["revision_instruction"]])
        closet_json = json.dumps(
            [i.model_dump(exclude={"image_index"}) for i in items], ensure_ascii=False, indent=1
        )
        try:
            candidate = await self.call(
                self.deps.gateway.generate_outfit(prompts.outfit_prompt(profile, closet_json, feedback))
            )
            unknown = [i for i in candidate.item_ids if i not in valid_ids]
            candidate.item_ids = [i for i in dict.fromkeys(candidate.item_ids) if i in valid_ids]
            if unknown:
                logger.warning("存在しない item_id を除外: %s", unknown)
            if not candidate.item_ids:
                raise ValueError("有効なアイテムが選ばれませんでした")
        except Exception as exc:  # noqa: BLE001
            logger.warning("コーデ生成に失敗: %s", exc)
            if state.get("candidate"):
                candidate = OutfitCandidate.model_validate(state["candidate"])
            else:
                candidate = fallback_outfit(items)
                notes.append("AIによるコーデ選定ができなかったため、手持ち服から基本の組み合わせを提示しています。")
        return {
            "candidate": candidate.model_dump(),
            "generation_count": int(state.get("generation_count", 0)) + 1,
        }, False


# ---------------------------------------------------------------------------
# P11 Critic 評価(MVP では評価と修正指示を1処理に統合 / P12 修正指示もここで生成)
# ---------------------------------------------------------------------------
PASS_MIN_SCORE = 3
PASS_MIN_AVERAGE = 3.5


def rule_violations(candidate: OutfitCandidate, items: list[ClosetItem]) -> list[str]:
    by_id = {i.item_id: i for i in items}
    chosen_cats = {by_id[i].category for i in candidate.item_ids if i in by_id}
    closet_cats = {i.category for i in items}
    violations = []
    if closet_cats & {"tops", "onepiece"} and not chosen_cats & {"tops", "onepiece"}:
        violations.append("トップス(またはワンピース)が含まれていません。")
    if "bottoms" in closet_cats and not chosen_cats & {"bottoms", "onepiece"}:
        violations.append("ボトムスが含まれていません。")
    if "shoes" in closet_cats and "shoes" not in chosen_cats:
        violations.append("靴が含まれていません。")
    return violations


def judge(scores: CriticScores, violations: list[str]) -> bool:
    values = list(scores.model_dump().values())
    return not violations and min(values) >= PASS_MIN_SCORE and sum(values) / len(values) >= PASS_MIN_AVERAGE


class CriticAgent(StepAgent):
    async def run_step(self, state, notes):
        profile = StyleProfile.model_validate(state["profile"])
        items = [ClosetItem.model_validate(i) for i in state["closet_items"]]
        candidate = OutfitCandidate.model_validate(state["candidate"])
        by_id = {i.item_id: i for i in items}
        candidate_json = json.dumps(
            {
                "title": candidate.title,
                "items": [by_id[i].model_dump(exclude={"image_index"}) for i in candidate.item_ids],
                "reason": candidate.reason,
            },
            ensure_ascii=False,
        )
        violations = rule_violations(candidate, items)
        try:
            llm = await self.call(self.deps.gateway.critique(prompts.critic_prompt(profile, candidate_json)))
        except Exception as exc:  # noqa: BLE001
            # 評価が不安定・失敗した場合はルールベースの閾値チェックのみで判定する
            logger.warning("Critic評価に失敗、ルールベースで判定: %s", exc)
            llm = CriticLlmOutput(
                scores=CriticScores(color_match=3, silhouette_match=3, practicality=3, blend_in=3),
                issues=[],
                revision_instruction="、".join(violations),
            )
        result = CriticResult(
            **llm.model_dump(),
            passed=judge(llm.scores, violations),
            rule_violations=violations,
            iteration=int(state.get("generation_count", 1)),
        )
        # 合格なら LoopAgent を抜ける(escalate)。不合格なら次の反復で Generator が修正する
        return {"critic": result.model_dump()}, result.passed


# ---------------------------------------------------------------------------
# P13 コーデ画像生成
# ---------------------------------------------------------------------------
class OutfitImageAgent(StepAgent):
    async def run_step(self, state, notes):
        profile = StyleProfile.model_validate(state["profile"])
        items = {i["item_id"]: ClosetItem.model_validate(i) for i in state["closet_items"]}
        candidate = OutfitCandidate.model_validate(state["candidate"])
        chosen = [items[i] for i in candidate.item_ids if i in items]
        image_indexes = list(dict.fromkeys(i.image_index for i in chosen))[: self.deps.settings.max_reference_images]
        refs = [img for img in self.deps.images if img.index in image_indexes]
        try:
            generated = await self.call(
                self.deps.gateway.generate_outfit_image(
                    prompts.image_prompt(candidate.title, [i.name for i in chosen], profile), refs
                )
            )
            if generated is None:
                raise ValueError("画像が返されませんでした")
        except Exception as exc:  # noqa: BLE001
            logger.warning("コーデ画像生成に失敗: %s", exc)
            notes.append("コーデ画像を生成できなかったため、テキストでの提案のみ表示しています。")
            return {"image": None}, False
        data, mime = generated
        return {"image": {"base64": base64.b64encode(data).decode(), "mime_type": mime}}, False
