# CLAUDE.md

初ジャンルのライブ用 服装エージェント(「はじめてのライブ服」)。ライブ/アーティスト情報と手持ち服の画像から、
会場で浮かないコーディネートを提案する Web アプリ。ハッカソン(5週間)の MVP。

## 構成

- `backend/` Python 3.11+ / FastAPI / Google ADK / google-genai
  - `app/agents/pipeline.py` 処理フロー(Sequential → Parallel → Loop)。処理ID(P04〜P13)は設計資料の「処理・入出力一覧」に対応
  - `app/agents/steps.py` 各処理のカスタムエージェント。**失敗時は必ずフォールバックして全体を止めない**(設計資料「異常時の処理」列)
  - `app/gemini.py` Gemini 呼び出しはすべてここを経由する。新しい呼び出しを足したら `app/mock_gemini.py` にもモックを追加する
  - `app/prompts.py` プロンプト。人物の容姿を模倣しない制約(`SAFETY_NOTE`)を画像・MV系プロンプトに必ず含める
  - `app/schemas.py` Pydantic モデル。ADK の state には `model_dump()` した dict のみ置く(画像バイト列は `PipelineDeps` で保持)
- `frontend/` React 19 + Vite + TypeScript。`src/types.ts` は `backend/app/schemas.py` と手で同期する
- `Dockerfile` フロントをビルドして FastAPI から配信する1コンテナ構成(Cloud Run)

## コマンド

```bash
# バックエンド
cd backend && pip install -r requirements-dev.txt
USE_MOCK_GEMINI=true uvicorn app.main:app --reload --port 8080   # APIキー無しで動作確認
USE_MOCK_GEMINI=true MOCK_DELAY_SEC=1.5 uvicorn app.main:app --port 8080  # ロード画面の確認用に各処理を遅らせる
pytest                                                            # テスト(モックで全フロー)

# フロントエンド(/api は 8080 にプロキシ)
cd frontend && npm install && npm run dev
npm run build      # 型チェック込み
npm run lint
```

## 開発ルール

- 変更後は `pytest` と `npm run build` が通ることを確認する
- 実 Gemini API を使う検証は有料ティアのキー(`GOOGLE_API_KEY`)で行う。キーをコミットしない(`.env` は gitignore 済み)
- UI 文言・ユーザー向けメッセージ・注意事項は日本語。注意事項は各エージェントの `notes` に追記すると結果画面に集約される
- MVP スコープ外: 希望条件入力(P03)、交通情報、YouCam API、データ永続化、複数回の再生成
- ADK 2.x で Sequential/Parallel/LoopAgent は非推奨警告が出るが、設計資料(T06)どおり現状維持。Workflow 移行は別タスク
- ブランチは `feature/<内容>` で切り、`main` へは PR でマージする
