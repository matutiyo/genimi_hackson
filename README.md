# はじめてのライブ服(初ジャンルのライブ用 服装エージェント)

行くライブ(公演・アーティスト情報)と手持ちの服の写真から、会場で浮かないコーディネートを提案する Web アプリです。
Google ADK でエージェントの処理フローを組み、Gemini(Vertex AI 経由)で解析・生成を行います。

---

## 機能一覧(F01〜F07: 画面・入力受付)の実装状況

| ID | 区分 | 機能 | 状態 | 入力 → 出力 | 実装場所 |
| --- | --- | --- | --- | --- | --- |
| F01 | 画面 | 入力受付画面UI | ✅ 実装済み | ユーザー操作 → 入力データ(公演情報) | `frontend/src/App.tsx`, `components/EventSection.tsx` |
| F02 | 画面 | クローゼット画像アップロードUI | ✅ 実装済み | ユーザー操作 → 画像ファイル(複数) | `components/ClosetUploader.tsx`, `imageUtils.ts` |
| F03 | 画面 | 結果表示画面UI | ✅ 実装済み | F28 の表示用統合データ → 画面表示 | `components/ResultView.tsx`(データは `backend/app/service.py` の `build_result`) |
| F04 | 画面 | 進捗表示・ローディングUI | ✅ 実装済み | 処理ステータス → 進捗表示 | `components/ProgressView.tsx`, `api.ts` |
| F05 | 入力 | 公演情報入力受付 | ✅ 実装済み | URL またはテキスト → 公演情報 | 画面: `components/EventSection.tsx` / API: `backend/app/main.py` の `validate_event_input` |
| F06 | 入力 | クローゼット画像登録受付 | ⚠️ 一部(保存しない) | 画像ファイル → 画像への参照 | 画面: `components/ClosetUploader.tsx` / API: `backend/app/main.py` の `create_proposal` |
| F07 | 入力 | 希望条件入力受付 | ❌ 未実装 | 選択項目 → 希望条件データ | —(MVP 対象外) |

**設計資料との差分**

- **F06**: 設計では「ストレージ等に保持」だが、MVP では **Cloud Storage 等に保存せず、1回のリクエストの処理中だけメモリで保持**する。
  個人の服の写真を残さないため(データ永続化は MVP 対象外)。画像は `ClosetImage` として ADK の state ではなく `PipelineDeps` で持つ。
- **F07**: MVP 対象外のため未実装。F01 の入力フォームにも希望条件の項目はない(追加する場合の手順は[後述](#f07-希望条件入力受付未実装))。

画面の文言・エラーメッセージはすべて日本語。動作確認は Chrome(Windows)と WebKit(iPhone 13 相当)、スマホ幅 390px で実施している。

---

## F01〜F07 の詳細

### F01 入力受付画面UI

入力画面は「① 行くライブの情報(F05)」「② 手持ちの服(F02)」の2つのカードと、画面下に固定した送信バーで構成する。

- **進み具合の表示**: 画面上部に「1 入力 → 2 AIが考え中 → 3 提案」の3段階を表示
- **送信前チェックリスト**: 送信バーに次の3つの充足状況を ✓ で表示
  1. 公演URL またはアーティスト名
  2. 服の写真(枚数も表示)
  3. 画像利用への同意
- **エラー表示**: 一度送信を試みた後は、未入力の項目をリアルタイムに表示し、入力すると消える。サーバーのエラー(F05・F06 の 422 など)も同じ枠に表示し、枠にフォーカスを移す
- **キャンセル**: 処理中にキャンセルすると入力画面に戻り、入力内容・写真はそのまま残る
- **スマホ対応**: 入力欄の文字は 16px(iOS の自動ズーム防止)、入力欄の高さ 44px・主要ボタン 48px、ホームバーに送信バーが重ならないよう safe-area を考慮

### F02 クローゼット画像アップロードUI

| 項目 | 内容 |
| --- | --- |
| 追加方法 | ファイル選択 / 画面のどこへでもドラッグ&ドロップ / Ctrl+V で貼り付け / 「カメラで撮る」(タッチ端末のみ表示) |
| 制限 | 最大10枚・1枚10MB まで、JPEG / PNG / WebP / HEIC(値は `GET /api/config` から取得) |
| 自動縮小 | 長辺 1600px 超または 1.5MB 超の写真は、ブラウザ内で長辺 1600px の JPEG(品質 0.85)に縮小してから送信。写真の向き(EXIF)も反映 |
| HEIC | デコードできるブラウザ(iOS Safari など)では JPEG に変換してプレビュー表示。できない場合は「HEIC プレビュー非対応」のタイルで表示し、そのまま送信 |
| 重複・不正 | 同じ写真(ファイル名+サイズ)の重複、非対応形式、枚数超過は追加せず、理由を警告表示 |
| 表示 | サムネイルに番号・サイズ(縮小時は「7.5MB→828KB」)・削除ボタン。縮小処理中は「準備中」タイル |
| その他 | 「上手に撮るコツ」の表示、すべて削除、画像利用への同意チェック |

スマホでのメモリ不足を避けるため、写真は1枚ずつ順に処理し、終わったものから表示する。

### F03 結果表示画面UI

F28(`service.py` の `build_result` が作る `ProposalResult`)を受け取り、次を1画面にまとめて表示する。

- 公演情報(アーティスト・公演名・日付・会場)とコーデのタイトル
- **コーデ画像**: タップで拡大、「画像を保存」リンク、スマホは長押しで写真に保存
- **使うアイテム**: カテゴリ・名前と、ユーザーが追加した写真のサムネイル。「足すならこれ」の提案
- **選定理由**と着こなしのコツ
- **カルチャー解説**(出典リンク付き)、**MV から読み取った世界観**(色のチップ)、**会場・季節のポイント**
- **AI セルフチェック**の評価(4項目のスコアと合否)
- **注意事項**(各処理のフォールバック内容を集約)
- 「条件を変えてもう一度」で入力画面に戻る(入力内容は保持)

### F04 進捗表示・ローディングUI

`POST /api/proposals` の応答を NDJSON で1行ずつ受け取り(`api.ts`)、処理の段階を表示する。

- **段階表示**: 公演情報 → ライブの雰囲気と手持ち服を解析(並列の4処理をそれぞれ表示)→ スタイルの方向性 → コーデ作成とセルフチェック → コーデ画像作成
- **見出し**: 今の処理内容を文章で表示(例: 「カルチャー・MV・会場・手持ち服を同時に解析しています」)
- **進捗率・経過時間**: 完了したステップ数に加え、処理中のステップの経過時間に応じて少しずつ進む。「目安 1〜2分」を併記し、150秒を超えたら案内を表示
- **手持ち服のスキャン表示**: 追加した写真を並べ、解析中は読み取り中の演出、完了で ✓
- **見直しの表示**: セルフチェックが不合格で作り直すと「見直し n回」を表示
- **待ち時間の豆知識**: 8秒ごとに切り替え
- **完成演出**: 結果を受け取ったら「コーディネートができました!」を 0.9 秒表示してから結果画面へ
- **スマホ対策**: 処理中は画面のスリープを防ぐ(Wake Lock。HTTPS のみ)。「この画面を開いたままお待ちください」を表示し、画面切替で通信が切れた場合は専用のエラーメッセージを出す
- **動きを減らす設定**: OS の「視差効果を減らす」等が有効でも、ゆっくりした回転と明滅は残し、処理中だと分かるようにする

### F05 公演情報入力受付

入力項目(`EventSection.tsx`):

| 項目 | 必須 | 画面でのチェック | API でのチェック(`validate_event_input`) |
| --- | --- | --- | --- |
| 公演告知ページの URL | URL かアーティスト名のどちらか | `http(s)://` で始まるか | `http(s)://` で始まるか |
| アーティスト名 | 同上 | — | URL とどちらも空ならエラー |
| ジャンル | 任意 | — | — |
| 公演日 | 任意 | 日付入力欄 | `YYYY-MM-DD` 形式か |
| 会場 | 任意 | — | — |
| 公式 MV の YouTube URL | 任意(推奨) | YouTube の動画 URL か(入力中に ✓ / ! を表示) | YouTube の動画 ID を含むか |

- URL と手入力の両方がある場合、URL から読み取った内容を基本に、**手入力した項目で上書き**する(`steps.py` の P04)
- URL から読み取れなかった場合は手入力の内容で続行し、注意事項に表示する。アーティスト名がどちらからも得られない場合のみエラーで入力画面に戻る

### F06 クローゼット画像登録受付

`POST /api/proposals` の `create_proposal` で、F05 の公演情報のチェックとあわせて、画像について次を確認して受け付ける(問題はまとめて返す)。

1. 画像利用への同意(`consent=true`)があるか(F32)
2. 1枚以上あるか、`MAX_IMAGES`(既定 10)以下か
3. 形式が JPEG / PNG / WebP / HEIC / HEIF か
4. 1枚あたり `MAX_IMAGE_MB`(既定 10MB)以下か

問題があれば 422 とエラーメッセージの一覧を返す(F01 のエラー枠に表示)。
受け付けた画像は `ClosetImage`(番号・ファイル名・形式・バイト列)としてメモリにだけ保持し、処理が終われば破棄する。

### F07 希望条件入力受付(未実装)

同行者の有無・天候考慮などの希望条件は、MVP の対象外のため未実装。追加する場合に手を入れる場所:

1. `backend/app/schemas.py` の `EventInput`(または新しいモデル)に項目を追加
2. `backend/app/main.py` の `create_proposal` に Form 項目とバリデーションを追加
3. `frontend/src/types.ts` の `EventForm`(`schemas.py` と手で同期)と、F01 の入力フォームに選択項目を追加
4. `backend/app/prompts.py` のコーデ生成・評価のプロンプトに希望条件を反映

### F04・F05・F06 で使う API

| メソッド・パス | 用途 |
| --- | --- |
| `GET /api/config` | アップロード制限(`max_images`, `max_image_mb`, `allowed_types`)とモックモードかどうか |
| `POST /api/proposals` | 公演情報と画像を受け取り、進捗と結果を NDJSON で返す |

`POST /api/proposals` のリクエスト(`multipart/form-data`):
`event_url`, `artist_name`, `genre`, `event_date`, `venue`, `mv_url`(いずれも任意の文字列)、`consent`(`true`)、`images`(画像ファイル、複数可)

レスポンス:

- 入力エラー: `422` `{"errors": ["公演URLまたはアーティスト名のどちらかを入力してください。", ...]}`
- 正常: `200` `application/x-ndjson`。1行ずつ次の JSON が届く

```jsonc
{"type": "start", "steps": [{"step": "event_parser", "label": "公演情報を解析"}, ...]}
{"type": "step", "step": "closet_analyzer", "label": "手持ち服を解析"}
{"type": "step", "step": "critic", "label": "コーディネートを評価", "passed": false, "iteration": 1}
{"type": "result", "result": { /* ProposalResult(F28) */ }}
// または
{"type": "error", "message": "アップロードされた画像から服を読み取れませんでした。…"}
```

### テスト用の入力データ

`samples/closet/` に服の写真 12 枚と服以外の写真 1 枚、`samples/README.md` にテストシナリオ(一式そろう場合・最小入力・服が読み取れない場合・枚数上限など)がある。

---

## 処理フロー(F08 以降・参考)

```
[Web] F01/F05 公演情報(URL or 手入力 + MV URL) / F02/F06 服画像(複数)
   ↓ POST /api/proposals(進捗を NDJSON でストリーミング → F04)
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
  P13 コーデ画像生成 ........... Gemini 画像生成(Nano Banana 系)
[Web] P14 / F03 結果表示(画像・選定理由・カルチャー解説+出典リンク・注意事項)
```

各ステップは失敗しても設計資料「異常時の処理」のフォールバックに切り替わり、全体は止まらない(F30)。
アーティスト名が確定できない/服が1点も読み取れない場合のみエラーとして入力画面に戻す。

## ディレクトリ

```
frontend/              React 19 + Vite + TypeScript(F01〜F05 の画面)
  src/App.tsx          画面全体・状態管理・送信(F01 / F04)
  src/api.ts           API 呼び出しと NDJSON の受信(F04)
  src/imageUtils.ts    写真の縮小・HEIC 変換(F02)
  src/components/      EventSection(F05)/ ClosetUploader(F02)/ ProgressView(F04)/ ResultView(F03)
backend/
  app/
    main.py            FastAPI(F05・F06 の入力受付・ストリーミング応答・静的配信)
    service.py         ADK Runner 実行と表示データ統合(P14 / F28)
    agents/pipeline.py 処理フローの組み立て(Sequential / Parallel / Loop)
    agents/steps.py    P04〜P13 の各エージェント(フォールバック込み)
    gemini.py          Gemini 呼び出し / mock_gemini.py  APIキー無しで動かすモック
    prompts.py         プロンプト / schemas.py  データ構造(Pydantic)
    data/culture_genres.json  カルチャー情報の事前収集データ
  tests/               pytest(モックで全フロー・フォールバックを検証)
samples/               テスト用の服の写真とテストシナリオ
Dockerfile             フロント + バックエンドを1コンテナにまとめる(Cloud Run 用)
```

## ローカル起動

```bash
# バックエンド(APIキー無しのモックで起動)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
USE_MOCK_GEMINI=true uvicorn app.main:app --reload --port 8080
# ロード画面(F04)をじっくり確認したい場合は各処理を遅らせる
USE_MOCK_GEMINI=true MOCK_DELAY_SEC=1.5 uvicorn app.main:app --port 8080

# フロントエンド(別ターミナル)
cd frontend
npm install
npm run dev   # http://localhost:5173(/api は 8080 にプロキシ)
```

実際の Gemini を使う場合は、Vertex AI の環境変数(下記)か `GOOGLE_API_KEY` を設定する。設定値は `.env.example` を参照。

### テスト

```bash
cd backend && pytest                            # モックで全フロー
cd frontend && npm run build && npm run lint    # 型チェック・lint
```

## Cloud Run へのデプロイ

```bash
gcloud run deploy live-outfit-agent \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=<プロジェクトID>,GOOGLE_CLOUD_LOCATION=global \
  --timeout 300
```

- **Vertex AI 経由**で運用する(GCP の請求先アカウントで課金)。事前に `aiplatform.googleapis.com` を有効化し、
  Cloud Run のサービスアカウントに `roles/aiplatform.user` を付与する(T08)。
- `GOOGLE_CLOUD_LOCATION=global` にする理由: 画像生成モデル(`gemini-3.1-flash-image`)は asia-northeast1 では提供されていないため。
- Gemini API(AI Studio のキー)を使う場合は `--set-secrets GOOGLE_API_KEY=gemini-api-key:latest` を指定する(F33)。
  ただし AI Studio は前払い制で、新規ユーザーは `gemini-2.5-flash` を利用できない(`GEMINI_*_MODEL` で新しいモデルに変更が必要)。

## 未対応・要確認

- **F07 / P03 希望条件入力**(同行者・天候考慮など)は未実装。
- **F06 の永続保存**: 画像は保存しない(上記)。保存が必要になった場合は Cloud Storage と削除ポリシーの設計が必要。
- **手動タグ入力**(服画像の解析失敗時): 現状はスキップして注意事項に表示するのみ。
- **天気**: 季節の固定文言で代替(Weather API の日本国内提供可否 T11 が未確認のため)。
- **F27 生成画像のガイドライン適合チェック**: プロンプトでの制約のみ。自動チェックは未実装。
- **モデルID**: `GEMINI_*_MODEL` で差し替え可能。Vertex AI(global)で既定値の `gemini-2.5-flash` / `gemini-3.1-flash-image` の動作を確認済み(T03)。
  新規プロジェクトは画像生成のクォータが小さく 429 になりやすい(その場合は画像なしで結果を返す)。
- **ADK**: 2.x では Sequential/Parallel/LoopAgent が非推奨(Workflow 推奨)。現時点では動作するため設計資料どおり使用。
- **カルチャー情報データ**: 対象ジャンル・キーワードはデモ前にチームで見直し(T13 / T16)。
