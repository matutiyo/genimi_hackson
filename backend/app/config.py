"""環境変数から読み込む設定値。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Gemini 呼び出しをモックに差し替える(APIキー無しでの画面確認・テスト用)
    use_mock_gemini: bool = field(default_factory=lambda: _bool("USE_MOCK_GEMINI", False))
    # モックの各呼び出しに入れる待ち時間(秒)。ロード画面の確認用で、テストでは 0
    mock_delay_sec: float = field(default_factory=lambda: float(os.getenv("MOCK_DELAY_SEC", "0")))

    # モデルID(公開状況で変わるため環境変数で差し替え可能にしている)
    text_model: str = field(default_factory=lambda: os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash"))
    vision_model: str = field(default_factory=lambda: os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash"))
    video_model: str = field(default_factory=lambda: os.getenv("GEMINI_VIDEO_MODEL", "gemini-2.5-flash"))
    image_model: str = field(
        default_factory=lambda: os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
    )

    # 1ステップあたりのタイムアウト(秒)
    step_timeout_sec: float = field(default_factory=lambda: float(os.getenv("STEP_TIMEOUT_SEC", "90")))
    # Critic 不合格時の再生成上限(MVP は1回)
    max_regenerations: int = field(default_factory=lambda: int(os.getenv("MAX_REGENERATIONS", "1")))

    # アップロード制限
    max_images: int = field(default_factory=lambda: int(os.getenv("MAX_IMAGES", "10")))
    max_image_bytes: int = field(
        default_factory=lambda: int(os.getenv("MAX_IMAGE_MB", "10")) * 1024 * 1024
    )
    # 画像生成に参照画像として渡す最大枚数
    max_reference_images: int = field(
        default_factory=lambda: int(os.getenv("MAX_REFERENCE_IMAGES", "6"))
    )

    # CORS を許可するオリジン(正規表現)。既定は localhost の任意ポート(Flutter の開発サーバー用)
    cors_origin_regex: str = field(
        default_factory=lambda: os.getenv("CORS_ORIGIN_REGEX", r"https?://(localhost|127\.0\.0\.1)(:\d+)?")
    )

    # フロントエンドのビルド成果物(存在すれば FastAPI から配信)
    static_dir: str = field(default_factory=lambda: os.getenv("STATIC_DIR", "static"))


ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}


def get_settings() -> Settings:
    return Settings()
