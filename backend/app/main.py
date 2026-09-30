"""FastAPI エントリポイント。

- POST /api/proposals : 公演情報 + 服画像を受け取り、進捗と結果を NDJSON でストリーミング返却
- GET  /api/config    : フロントエンド用のアップロード制限値
- フロントエンドのビルド成果物(STATIC_DIR)があれば / で配信
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import ALLOWED_IMAGE_TYPES, get_settings
from .gemini import build_gateway, youtube_video_id
from .schemas import ClosetImage, EventInput
from .service import run_proposal

logging.basicConfig(level=logging.INFO)

settings = get_settings()
gateway = build_gateway(settings)
app = FastAPI(title="Live Outfit Agent", version="0.1.0")

_URL = re.compile(r"^https?://", re.I)


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def validate_event_input(inp: EventInput) -> list[str]:
    """F31 入力バリデーション(公演情報)。"""
    errors: list[str] = []
    if not inp.event_url and not inp.artist_name:
        errors.append("公演URLまたはアーティスト名のどちらかを入力してください。")
    if inp.event_url and not _URL.match(inp.event_url):
        errors.append("公演URLは http:// または https:// から始まるURLを入力してください。")
    if inp.mv_url and not youtube_video_id(inp.mv_url):
        errors.append("公式MVのURLはYouTubeの動画URLを入力してください。")
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


@app.post("/api/proposals")
async def create_proposal(
    images: Annotated[list[UploadFile], File(description="手持ち服の画像(複数可)")],
    consent: Annotated[bool, Form(description="画像利用への同意")] = False,
    event_url: Annotated[str | None, Form()] = None,
    artist_name: Annotated[str | None, Form()] = None,
    genre: Annotated[str | None, Form()] = None,
    event_date: Annotated[str | None, Form()] = None,
    venue: Annotated[str | None, Form()] = None,
    mv_url: Annotated[str | None, Form()] = None,
):
    event_input = EventInput(
        event_url=_clean(event_url),
        artist_name=_clean(artist_name),
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
