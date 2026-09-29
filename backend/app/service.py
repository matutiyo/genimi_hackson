"""ADK Runner でパイプラインを実行し、進捗イベントと最終結果(P14)を返す。"""

from __future__ import annotations

import logging
import uuid
from typing import Any, AsyncIterator

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agents.pipeline import STEP_LABELS, build_pipeline
from .agents.steps import PipelineDeps
from .config import Settings
from .gemini import GeminiGateway
from .schemas import (
    ClosetImage,
    ClosetItem,
    CriticResult,
    CultureInfo,
    EventInfo,
    EventInput,
    MvStyle,
    OutfitCandidate,
    ProposalItem,
    ProposalResult,
    VenueWeather,
)

logger = logging.getLogger(__name__)

APP_NAME = "live_outfit_agent"

# 注意事項の表示順
_NOTE_ORDER = list(STEP_LABELS)


def build_result(state: dict[str, Any]) -> ProposalResult:
    """P14: セッション state から表示用の統合データを作る(F28)。"""

    def load(key: str, model):
        return model.model_validate(state[key]) if state.get(key) else None

    closet = {i["item_id"]: ClosetItem.model_validate(i) for i in state.get("closet_items", [])}
    candidate: OutfitCandidate | None = load("candidate", OutfitCandidate)
    critic: CriticResult | None = load("critic", CriticResult)

    notes: list[str] = []
    for name in _NOTE_ORDER:
        for note in state.get(f"notes:{name}", []):
            if note not in notes:
                notes.append(note)
    if critic and not critic.passed:
        notes.append("再生成の上限に達したため、評価基準を一部満たしていない候補をそのまま提示しています。")

    image = state.get("image")
    return ProposalResult(
        event=load("event", EventInfo),
        outfit_title=candidate.title if candidate else None,
        items=[
            ProposalItem(item_id=i, name=closet[i].name, category=closet[i].category, image_index=closet[i].image_index)
            for i in (candidate.item_ids if candidate else [])
            if i in closet
        ],
        styling_tips=candidate.styling_tips if candidate else [],
        reason=candidate.reason if candidate else None,
        missing_suggestions=candidate.missing_suggestions if candidate else [],
        culture=load("culture", CultureInfo),
        mv_style=load("mv_style", MvStyle),
        venue_weather=load("venue_weather", VenueWeather),
        critic=critic,
        image_base64=image["base64"] if image else None,
        image_mime_type=image["mime_type"] if image else None,
        notes=notes,
    )


async def run_proposal(
    event_input: EventInput,
    images: list[ClosetImage],
    settings: Settings,
    gateway: GeminiGateway,
) -> AsyncIterator[dict[str, Any]]:
    """進捗イベント → 最終結果(またはエラー)の順に dict を yield する。"""
    deps = PipelineDeps(settings=settings, gateway=gateway, images=images)
    session_service = InMemorySessionService()  # セッション内のみ保持(永続保存しない)
    user_id = "anonymous"
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=str(uuid.uuid4()),
        state={"input": event_input.model_dump()},
    )
    runner = Runner(app_name=APP_NAME, agent=build_pipeline(deps), session_service=session_service)

    yield {"type": "start", "steps": [{"step": k, "label": v} for k, v in STEP_LABELS.items()]}
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text="コーディネートを提案してください")]),
        ):
            delta = event.actions.state_delta if event.actions else {}
            if event.author in STEP_LABELS:
                progress: dict[str, Any] = {"type": "step", "step": event.author, "label": STEP_LABELS[event.author]}
                if event.author == "critic" and delta.get("critic"):
                    progress["passed"] = delta["critic"]["passed"]
                    progress["iteration"] = delta["critic"]["iteration"]
                yield progress
    except Exception:  # noqa: BLE001
        logger.exception("パイプライン実行中にエラー")
        yield {"type": "error", "message": "処理中にエラーが発生しました。時間をおいて再度お試しください。"}
        return

    final = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session.id)
    state = dict(final.state) if final else {}
    if state.get("fatal_error"):
        yield {"type": "error", "message": state["fatal_error"]}
        return
    yield {"type": "result", "result": build_result(state).model_dump()}
