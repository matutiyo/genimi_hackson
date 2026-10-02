# ---- フロントエンド(Flutter web)のビルド ----
FROM debian:bookworm-slim AS frontend
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git unzip xz-utils \
    && rm -rf /var/lib/apt/lists/*
# 公式の安定版アーカイブ(frontend/pubspec.lock を作ったバージョンに合わせる)
ARG FLUTTER_VERSION=3.47.6
RUN curl -fsSL "https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_${FLUTTER_VERSION}-stable.tar.xz" \
    | tar -xJ -C /opt \
    && git config --global --add safe.directory /opt/flutter
ENV PATH=/opt/flutter/bin:$PATH
RUN flutter --disable-analytics && flutter config --no-cli-animations
WORKDIR /frontend
COPY frontend/pubspec.yaml frontend/pubspec.lock ./
RUN flutter pub get
COPY frontend/ ./
# CanvasKit を CDN から読まずに同梱する(外部 CDN に依存しない)
RUN flutter build web --release --no-web-resources-cdn

# ---- バックエンド(Cloud Run) ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 STATIC_DIR=/app/static
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /frontend/build/web ./static
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
