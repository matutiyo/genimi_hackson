"""FastAPI エントリポイント。

- POST /api/proposals : 公演情報 + 服画像を受け取り、進捗と結果を NDJSON でストリーミング返却
- GET  /api/events/search : キーワードから公演の候補を検索(URL の直接入力は受け付けない)
- GET  /api/config    : フロントエンド用のアップロード制限値
- フロントエンドのビルド成果物(STATIC_DIR)があれば / で配信
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import ALLOWED_IMAGE_TYPES, get_settings
from .gemini import build_gateway, youtube_video_id
from .schemas import ClosetImage, EventInput
from .service import run_proposal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
gateway = build_gateway(settings)
app = FastAPI(title="Live Outfit Agent", version="0.1.0")
# 開発時に `flutter run -d chrome`(別ポート)から API を呼べるようにする。
# 本番は同一オリジン配信、モバイルアプリは CORS の対象外なので、既定では localhost のみ許可する。
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=settings.cors_origin_regex,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_URL = re.compile(r"^https?://", re.I)


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def validate_event_input(inp: EventInput) -> list[str]:
    """F31 入力バリデーション(公演情報)。"""
    errors: list[str] = []
    if not inp.keyword and not inp.artist_name:
        errors.append("検索キーワードまたはアーティスト名のどちらかを入力してください。")
    for label, value in (("検索キーワード", inp.keyword), ("アーティスト名", inp.artist_name)):
        if value and _URL.match(value):
            errors.append(f"{label}にURLは入力できません。アーティスト名や公演名で検索してください。")
    if inp.mv_url and not youtube_video_id(inp.mv_url):
        errors.append("公式MVのURLが正しくありません。もう一度検索して公演を選び直してください。")
    if inp.event_date:
        try:
            date.fromisoformat(inp.event_date)
        except ValueError:
            errors.append("公演日は YYYY-MM-DD 形式で入力してください。")
    return errors


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "mock": settings.use_mock_gemini}


@app.get("/api/config")
async def client_config() -> dict:
    return {
        "max_images": settings.max_images,
        "max_image_mb": settings.max_image_bytes // (1024 * 1024),
        "allowed_types": sorted(ALLOWED_IMAGE_TYPES),
        "mock": settings.use_mock_gemini,
    }


@app.get("/api/events/search")
async def search_events(q: Annotated[str, Query(max_length=100)] = "") -> JSONResponse:
    """F05: キーワード(アーティスト名・公演名など)から公演の候補を探す。"""
    keyword = q.strip()
    if not keyword:
        return JSONResponse(status_code=422, content={"errors": ["検索キーワードを入力してください。"]})
    if _URL.match(keyword):
        return JSONResponse(
            status_code=422, content={"errors": ["URLでは検索できません。アーティスト名や公演名を入力してください。"]}
        )
    try:
        result = await asyncio.wait_for(gateway.search_events(keyword), timeout=settings.step_timeout_sec)
    except Exception:  # noqa: BLE001 - 検索できなくても手入力で続けられる
        logger.exception("公演検索に失敗")
        return JSONResponse(
            status_code=503,
            content={"errors": ["公演を検索できませんでした。時間をおいて再度お試しいただくか、アーティスト名を手入力してください。"]},
        )
    return JSONResponse(content=result.model_dump())


@app.post("/api/proposals")
async def create_proposal(
    images: Annotated[list[UploadFile], File(description="手持ち服の画像(複数可)")],
    consent: Annotated[bool, Form(description="画像利用への同意")] = False,
    keyword: Annotated[str | None, Form()] = None,
    artist_name: Annotated[str | None, Form()] = None,
    event_title: Annotated[str | None, Form()] = None,
    genre: Annotated[str | None, Form()] = None,
    event_date: Annotated[str | None, Form()] = None,
    venue: Annotated[str | None, Form()] = None,
    mv_url: Annotated[str | None, Form()] = None,
):
    event_input = EventInput(
        keyword=_clean(keyword),
        artist_name=_clean(artist_name),
        event_title=_clean(event_title),
        genre=_clean(genre),
        event_date=_clean(event_date),
        venue=_clean(venue),
        mv_url=_clean(mv_url),
    )
    errors = validate_event_input(event_input)

    # F32: 本人同意済みの画像のみ扱う
    if not consent:
        errors.append("アップロードする画像がご自身で撮影・利用許諾を得たものであることに同意してください。")

    # P02 / F06: 画像の受付(永続保存せずリクエスト内のメモリでのみ保持)
    closet_images: list[ClosetImage] = []
    real_images = [f for f in images if f.filename]
    if not real_images:
        errors.append("手持ち服の画像を1枚以上アップロードしてください。")
    if len(real_images) > settings.max_images:
        errors.append(f"画像は{settings.max_images}枚までアップロードできます。")
    for idx, upload in enumerate(real_images[: settings.max_images]):
        data = await upload.read()
        mime = (upload.content_type or "").lower()
        if mime not in ALLOWED_IMAGE_TYPES:
            errors.append(f"「{upload.filename}」は対応していない形式です(JPEG/PNG/WebP/HEIC)。")
            continue
        if len(data) > settings.max_image_bytes:
            errors.append(f"「{upload.filename}」は{settings.max_image_bytes // (1024 * 1024)}MBを超えています。")
            continue
        closet_images.append(ClosetImage(index=idx, filename=upload.filename or f"image{idx}", mime_type=mime, data=data))

    if errors:
        return JSONResponse(status_code=422, content={"errors": errors})

    async def stream():
        async for message in run_proposal(event_input, closet_images, settings, gateway):
            yield json.dumps(message, ensure_ascii=False) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


# フロントエンド(Vite ビルド成果物)の配信
_static = Path(settings.static_dir)
if _static.is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="static")
