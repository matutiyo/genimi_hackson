# はじめてのライブ服(初ジャンルのライブ用 服装エージェント)

行くライブ(公演・アーティスト情報)と手持ちの服の写真から、会場で浮かないコーディネートを提案する Web アプリです。
Google ADK でエージェントの処理フローを組み、Gemini API で解析・生成を行います。

> 現在の実装範囲: **入力は「ライブ/アーティスト情報」と「服の画像」のみ**。希望条件入力(P03 / F07)は未実装です。

## 処理フロー

```
[Web] P01 公演情報(URL or 手入力 + MV URL) / P02 服画像(複数)
   ↓ POST /api/proposals(進捗を NDJSON でストリーミング)
[ADK SequentialAgent]
  P04 公演情報解析 ............ Gemini URL Context(失敗時は手入力にフォールバック)
  [ParallelAgent]
    P05 カルチャー情報 ......... 事前収集データ(app/data/culture_genres.json)+ Gemini 要約
    P06 MV解析 ................. Gemini 動画理解(YouTube URL)→ 失敗時サムネイル解析
    P07 会場・天気 ............. 会場形態を Gemini で推定 / 天気は季節の固定文言(交通は対象外)
    P08 手持ち服解析 ........... Gemini マルチモーダル + 構造化 JSON 出力
  P09 スタイル統合 ............. MV × ジャンル定番のクロスチェック
  [LoopAgent 最大 1+MAX_REGENERATIONS 回]
    P10 コーデ候補生成(Generator)
    P11 Critic 評価 + P12 修正指示(MVP は1処理に統合、合格で escalate して抜ける)
  P13 コーデ画像生成 ........... Gemini 画像生成・編集(Nano Banana 系)
[Web] P14 結果表示(画像・選定理由・カルチャー解説+出典リンク・注意事項)
```

各ステップは失敗しても設計資料「異常時の処理」のフォールバックに切り替わり、全体は止まりません(F30)。
アーティスト名が確定できない/服が1点も読み取れない場合のみエラーとして入力画面に戻します。

## ディレクトリ

```
backend/
  app/
    main.py            FastAPI(入力バリデーション・ストリーミング応答・静的配信)
    service.py         ADK Runner 実行と表示データ統合(P14)
    agents/pipeline.py 処理フローの組み立て(Sequential / Parallel / Loop)
    agents/steps.py    P04〜P13 の各エージェント(フォールバック込み)
    gemini.py          Gemini API 呼び出し
    mock_gemini.py     APIキー無しで動かすためのモック
    prompts.py         プロンプト
    schemas.py         データ構造(Pydantic)
    data/culture_genres.json  カルチャー情報の事前収集データ(要見直し)
  tests/               pytest(モックで全フロー・フォールバックを検証)
frontend/              React + Vite + TypeScript
Dockerfile             フロント + バックエンドを1コンテナにまとめる(Cloud Run 用)
```

## ローカル起動

### 1. バックエンド

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# APIキー無しで試す場合
USE_MOCK_GEMINI=true uvicorn app.main:app --reload --port 8080

# Gemini を使う場合(有料ティアのキーを使うこと / T05)
GOOGLE_API_KEY=xxxx uvicorn app.main:app --reload --port 8080
```

設定値は `.env.example` を参照してください。

### 2. フロントエンド

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173 (/api は 8080 にプロキシ)
```

### テスト

```bash
cd backend && pytest
```

## Cloud Run へのデプロイ

```bash
gcloud run deploy live-outfit-agent   --source .   --region asia-northeast1   --allow-unauthenticated   --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=<プロジェクトID>,GOOGLE_CLOUD_LOCATION=global   --timeout 300
```

- 現在は **Vertex AI 経由**で運用しています(GCP の請求先アカウント/クーポンのクレジットで課金される)。
  事前に `aiplatform.googleapis.com` を有効化し、Cloud Run のサービスアカウントに `roles/aiplatform.user` を付与します(T08)。
- `GOOGLE_CLOUD_LOCATION=global` にする理由: 画像生成モデル(`gemini-3.1-flash-image`)は asia-northeast1 では提供されていないため。
- Gemini API(AI Studio のキー)を使う場合は `--set-secrets GOOGLE_API_KEY=gemini-api-key:latest` を指定します(F33)。
  ただし AI Studio は前払い制で、新規ユーザーは `gemini-2.5-flash` を利用できません(`GEMINI_*_MODEL` で新しいモデルに変更が必要)。
- 画像はリクエスト中のメモリでのみ扱い、保存しません(永続保存は MVP 対象外)。

## 未対応・要確認

- **P03 希望条件入力**(同行者・天候考慮など)は未実装。
- **手動タグ入力**(服画像の解析失敗時): 現状はスキップして注意事項に表示するのみ。
- **天気**: 季節の固定文言で代替(Weather API の日本国内提供可否 T11 が未確認のため)。
- **F27 生成画像のガイドライン適合チェック**: プロンプトでの制約のみ。自動チェックは未実装。
- **モデルID**: `GEMINI_*_MODEL` で差し替え可能。Vertex AI(global)で既定値の `gemini-2.5-flash` / `gemini-3.1-flash-image` の動作を確認済み(T03)。新規プロジェクトは画像生成のクォータが小さく 429 になりやすい(その場合は画像なしで結果を返す)。
- **ADK**: 2.x では Sequential/Parallel/LoopAgent が非推奨(Workflow 推奨)。現時点では動作するため設計資料どおり使用。
- **カルチャー情報データ**: 対象ジャンル・キーワードはデモ前にチームで見直し(T13 / T16)。
