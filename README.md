# はじめてのライブ服(初ジャンルのライブ用 服装エージェント)

行くライブ(公演・アーティスト情報)と手持ちの服の写真から、会場で浮かないコーディネートを提案するアプリです。
画面は Flutter(web / Android / iOS)で実装し、公演はキーワード検索で探します(URL の直接入力は受け付けません)。
Google ADK でエージェントの処理フローを組み、Gemini(Vertex AI 経由)で解析・生成を行います。

---

## 機能一覧(F01〜F07: 画面・入力受付)の実装状況

| ID | 区分 | 機能 | 状態 | 入力 → 出力 | 実装場所 |
| --- | --- | --- | --- | --- | --- |
| F01 | 画面 | 入力受付画面UI | ✅ 実装済み | ユーザー操作 → 入力データ(公演情報) | `frontend/lib/main.dart`, `widgets/event_search_section.dart` |
| F02 | 画面 | クローゼット画像アップロードUI | ✅ 実装済み | ユーザー操作 → 画像ファイル(複数) | `widgets/closet_section.dart` |
| F03 | 画面 | 結果表示画面UI | ✅ 実装済み | F28 の表示用統合データ → 画面表示 | `screens/result_view.dart`(データは `backend/app/service.py` の `build_result`) |
| F04 | 画面 | 進捗表示・ローディングUI | ✅ 実装済み | 処理ステータス → 進捗表示 | `screens/progress_view.dart`, `api.dart` |
| F05 | 入力 | 公演情報入力受付 | ✅ 実装済み | キーワード検索 またはテキスト → 公演情報 | 画面: `widgets/event_search_section.dart` / API: `backend/app/main.py` の `search_events`・`validate_event_input` |
| F06 | 入力 | クローゼット画像登録受付 | ⚠️ 一部(保存しない) | 画像ファイル → 画像への参照 | 画面: `widgets/closet_section.dart` / API: `backend/app/main.py` の `create_proposal` |
| F07 | 入力 | 希望条件入力受付 | ❌ 未実装 | 選択項目 → 希望条件データ | —(MVP 対象外) |

**設計資料との差分**

- **F06**: 設計では「ストレージ等に保持」だが、MVP では **Cloud Storage 等に保存せず、1回のリクエストの処理中だけメモリで保持**する。
  個人の服の写真を残さないため(データ永続化は MVP 対象外)。画像は `ClosetImage` として ADK の state ではなく `PipelineDeps` で持つ。
- **F05**: 設計では「URL またはテキスト」だったが、公演ページや MV の **URL を利用者が直接入力する方式は著作権への配慮から廃止**し、
  キーワード検索(Gemini + Google 検索グラウンディング)で公演を探して選ぶ方式に変更した。
- **F07**: MVP 対象外のため未実装。F01 の入力フォームにも希望条件の項目はない(追加する場合の手順は[後述](#f07-希望条件入力受付未実装))。

画面の文言・エラーメッセージはすべて日本語。動作確認は Flutter web(Chromium、スマホ幅 390px)とウィジェットテストで実施している。

---

## F01〜F07 の詳細

### F01 入力受付画面UI

入力画面は「① 行くライブを検索(F05)」「② 手持ちの服(F02)」の2つのカードと、画面下に固定した送信バーで構成する。

- **進み具合の表示**: 画面上部に「1 入力 → 2 AIが考え中 → 3 提案」の3段階を表示
- **送信前チェックリスト**: 送信バーに次の3つの充足状況を ✓ で表示
  1. 検索キーワード またはアーティスト名
  2. 服の写真(枚数も表示)
  3. 画像利用への同意
- **エラー表示**: 一度送信を試みた後は、未入力の項目をリアルタイムに表示し、入力すると消える。サーバーのエラー(F05・F06 の 422 など)も同じ枠に表示し、画面の先頭へスクロールする
- **キャンセル**: 処理中にキャンセルすると入力画面に戻り、入力内容・写真はそのまま残る
- **スマホ対応**: 入力欄の文字は 16px、主要ボタン 48px、ホームバーに送信バーが重ならないよう SafeArea を考慮。幅 880px を上限に中央寄せ

### F02 クローゼット画像アップロードUI

| 項目 | 内容 |
| --- | --- |
| 追加方法 | 「写真を選ぶ」(複数選択)/「カメラで撮る」(Android・iOS のみ表示)。`image_picker` を使用 |
| 制限 | 最大10枚・1枚10MB まで、JPEG / PNG / WebP / HEIC(値は `GET /api/config` から取得) |
| 自動縮小 | 選択時に `image_picker` で長辺 1600px・JPEG 品質 85 に縮小してから送信 |
| HEIC | 表示できない環境(ブラウザなど)では「プレビュー非対応」のタイルで表示し、そのまま送信 |
| 重複・不正 | 同じ写真(ファイル名+サイズ)の重複、非対応形式、枚数超過は追加せず、理由を警告表示 |
| 表示 | サムネイルに番号・サイズ・削除ボタン。読み込み中は「準備中」タイル |
| その他 | 「上手に撮るコツ」の表示、すべて削除、画像利用への同意チェック |

旧 Web 版(React)にあったドラッグ&ドロップ・貼り付けは、Flutter 版では未対応。

### F03 結果表示画面UI

F28(`service.py` の `build_result` が作る `ProposalResult`)を受け取り、次を1画面にまとめて表示する。

- 公演情報(アーティスト・公演名・日付・会場)とコーデのタイトル
- **コーデ画像**: タップで拡大(ピンチで拡大縮小)、web は「画像を保存」でダウンロード(Android・iOS アプリの保存は未対応)
- **使うアイテム**: カテゴリ・名前と、ユーザーが追加した写真のサムネイル。「足すならこれ」の提案
- **選定理由**と着こなしのコツ
- **カルチャー解説**(出典リンク付き)、**MV から読み取った世界観**(色のチップ)、**会場・季節のポイント**
- **AI セルフチェック**の評価(4項目のスコアと合否)
- **注意事項**(各処理のフォールバック内容を集約)
- 「条件を変えてもう一度」で入力画面に戻る(入力内容は保持)

### F04 進捗表示・ローディングUI

`POST /api/proposals` の応答を NDJSON で1行ずつ受け取り(`api.dart`。web でも `package:http` が fetch のストリームで逐次受信する)、処理の段階を表示する。

- **段階表示**: 公演情報 → ライブの雰囲気と手持ち服を解析(並列の4処理をそれぞれ表示)→ スタイルの方向性 → コーデ作成とセルフチェック → コーデ画像作成
- **見出し**: 今の処理内容を文章で表示(例: 「カルチャー・MV・会場・手持ち服を同時に解析しています」)
- **進捗率・経過時間**: 完了したステップ数に加え、処理中のステップの経過時間に応じて少しずつ進む。「目安 1〜2分」を併記し、150秒を超えたら案内を表示
- **手持ち服のスキャン表示**: 追加した写真を並べ、解析中は読み取り中の演出、完了で ✓
- **見直しの表示**: セルフチェックが不合格で作り直すと「見直し n回」を表示
- **待ち時間の豆知識**: 8秒ごとに切り替え
- **完成演出**: 結果を受け取ったら「コーディネートができました!」を 0.9 秒表示してから結果画面へ
- **スマホ対策**: 処理中は画面のスリープを防ぐ(`wakelock_plus`。web は HTTPS のみ)。「この画面を開いたままお待ちください」を表示し、画面切替で通信が切れた場合は専用のエラーメッセージを出す

### F05 公演情報入力受付

公演ページや MV の URL は入力させず、**キーワード検索で公演を探して選ぶ**(著作権への配慮)。

1. 「検索キーワード」(アーティスト名・ツアー名など)を入れて「検索」→ `GET /api/events/search?q=...`。
   日付・会場などで絞り込みたいときは「**詳細検索(任意)**」を押すと下に入力欄が開く(最初は閉じている。閉じていても「n件入力中」と表示)
2. バックエンドが Gemini の **Google 検索グラウンディング**で公演を調べ、候補(アーティスト・公演名・日付・会場・ジャンル)を最大5件返す。
   参照したページは「参照した情報源」としてリンク表示する
3. 候補を選ぶと詳細検索の欄に反映される(開けば修正可)。候補に公式MVがあれば「公式MVの雰囲気も参考にする」スイッチを表示(オフにすると MV 解析しない)
4. 見つからない場合は、詳細検索の欄(アーティスト名・公演名・ジャンル・会場・公演日)に入れた内容だけで送信できる

**詳細検索(任意項目)**: アーティスト名・公演名・ジャンル・会場・公演日。

- 検索時は絞り込み条件として API に渡し(`artist_name` / `event_title` / `genre` / `venue` / `event_date`)、Gemini に「すべての条件に合う公演だけ」を候補にさせる。キーワードが空でもアーティスト名か公演名があれば検索できる
- 送信時は検索結果より優先する値として使う
- 検索を実行すると詳細検索は閉じる(結果が検索欄のすぐ下に見えるように。条件は残る)
- 候補を選んだ後に検索し直すと、候補から入っただけの値は条件から外す(手で直した値は残す)

**公式MV の扱い**: 検索結果の MV URL は LLM が誤った動画IDを返すことがあるため、YouTube oEmbed で **実在し、タイトルかチャンネル名にアーティスト名を含む** ことを確かめたものだけを返す(`gemini.py` の `_verify_mv`)。利用者が URL を入力・編集する手段はない。

| 項目 | 必須 | API でのチェック(`validate_event_input`) |
| --- | --- | --- |
| 検索キーワード | キーワードかアーティスト名のどちらか | どちらも空ならエラー。URL は不可 |
| アーティスト名 | 同上 | URL は不可 |
| 公演名・ジャンル・会場 | 任意 | — |
| 公演日 | 任意(日付選択) | `YYYY-MM-DD` 形式か |
| 公式MV(検索結果のもの) | 任意 | YouTube の動画 ID を含むか |

- 候補を選んで送信した場合は、その内容(+手入力)をそのまま使う
- **キーワードだけで送信した場合**は、P04 でキーワード検索して1件目の公演を使い、注意事項に「〇〇の検索結果から…として提案しています」と表示する。手入力した項目があればそちらを優先する
- 検索に失敗・該当なしの場合はキーワードをアーティスト名として続行し、注意事項に表示する。アーティスト名が得られない場合のみエラーで入力画面に戻る

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
3. `frontend/lib/models.dart` の `EventForm`(`schemas.py` と手で同期)と、F01 の入力フォームに選択項目を追加
4. `backend/app/prompts.py` のコーデ生成・評価のプロンプトに希望条件を反映

### F04・F05・F06 で使う API

| メソッド・パス | 用途 |
| --- | --- |
| `GET /api/events/search?q=キーワード&venue=...` | 公演の候補を検索(F05)。詳細条件 `artist_name` / `event_title` / `genre` / `venue` / `event_date` は任意。`{"candidates": [...], "sources": [{"title", "url"}]}`。空・URL は `422`、検索失敗は `503` |
| `GET /api/config` | アップロード制限(`max_images`, `max_image_mb`, `allowed_types`)とモックモードかどうか |
| `POST /api/proposals` | 公演情報と画像を受け取り、進捗と結果を NDJSON で返す |

`POST /api/proposals` のリクエスト(`multipart/form-data`):
`keyword`, `artist_name`, `event_title`, `genre`, `event_date`, `venue`, `mv_url`(検索結果の公式MV。いずれも任意の文字列)、`consent`(`true`)、`images`(画像ファイル、複数可)

レスポンス:

- 入力エラー: `422` `{"errors": ["検索キーワードまたはアーティスト名のどちらかを入力してください。", ...]}`
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
[Flutter] F05 キーワード検索(GET /api/events/search: Gemini + Google 検索)→ 候補を選ぶ or 手入力
[Flutter] F01/F05 公演情報(+ 検索で確認済みの公式MV) / F02/F06 服画像(複数)
   ↓ POST /api/proposals(進捗を NDJSON でストリーミング → F04)
[ADK SequentialAgent]
  P04 公演情報解析 ............ 選んだ候補・手入力をそのまま使用。キーワードのみなら詳細条件つきで Google 検索し1件目を採用
                                (失敗時はキーワードをアーティスト名としてフォールバック)
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
[Flutter] P14 / F03 結果表示(画像・選定理由・カルチャー解説+出典リンク・注意事項)
```

各ステップは失敗しても設計資料「異常時の処理」のフォールバックに切り替わり、全体は止まらない(F30)。
アーティスト名が確定できない/服が1点も読み取れない場合のみエラーとして入力画面に戻す。

## ディレクトリ

```
frontend/              Flutter(web / Android / iOS)。F01〜F05 の画面
  lib/main.dart        画面全体・状態管理・送信(F01 / F04)
  lib/api.dart         API 呼び出し・キーワード検索・NDJSON の受信(F04 / F05)
  lib/models.dart      backend/app/schemas.py と手で同期するデータ型
  lib/widgets/         event_search_section(F05)/ closet_section(F02)
  lib/screens/         progress_view(F04)/ result_view(F03)
  test/                ウィジェットテスト
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

# フロントエンド(別ターミナル。Flutter 3.47 系)
cd frontend
flutter pub get
flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8080
# Android エミュレータ: --dart-define=API_BASE_URL=http://10.0.2.2:8080
# 実機: PC の LAN の IP を指定(例: http://192.168.0.10:8080)

# 本番と同じく FastAPI から配信する場合
flutter build web --release --no-web-resources-cdn
cd ../backend && USE_MOCK_GEMINI=true STATIC_DIR=../frontend/build/web uvicorn app.main:app --port 8080
```

- web の API 接続先は既定で同一オリジン、Android・iOS は `http://localhost:8080`。`API_BASE_URL` で変更する
- バックエンドは開発用に `localhost` の任意ポートからの CORS を許可している(`CORS_ORIGIN_REGEX` で変更可)
- モックでの検索は、キーワードに `fail` を含むと検索失敗、`nohit` を含むと該当なしを返す。詳細条件は候補の項目に含まれるかで絞り込む(例: 会場「幕張」)

実際の Gemini を使う場合は、Vertex AI の環境変数(下記)か `GOOGLE_API_KEY` を設定する。設定値は `.env.example` を参照。

### テスト

```bash
cd backend && pytest                            # モックで全フロー
cd frontend && flutter analyze && flutter test  # 静的解析・ウィジェットテスト
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

- **Google 検索グラウンディングの表示要件**: Gemini の Google 検索グラウンディングは、利用規約上「検索候補(Search Suggestions)」の表示が求められる。
  現状は参照ページ(出典)のリンクのみ表示しているため、公開前に `grounding_metadata.search_entry_point` の表示方法を確認・対応する。
- **Flutter 版で未対応**: 写真のドラッグ&ドロップ・貼り付け、Android・iOS アプリでのコーデ画像の保存。

- **F07 / P03 希望条件入力**(同行者・天候考慮など)は未実装。
- **F06 の永続保存**: 画像は保存しない(上記)。保存が必要になった場合は Cloud Storage と削除ポリシーの設計が必要。
- **手動タグ入力**(服画像の解析失敗時): 現状はスキップして注意事項に表示するのみ。
- **天気**: 季節の固定文言で代替(Weather API の日本国内提供可否 T11 が未確認のため)。
- **F27 生成画像のガイドライン適合チェック**: プロンプトでの制約のみ。自動チェックは未実装。
- **モデルID**: `GEMINI_*_MODEL` で差し替え可能。Vertex AI(global)で既定値の `gemini-2.5-flash` / `gemini-3.1-flash-image` の動作を確認済み(T03)。
  新規プロジェクトは画像生成のクォータが小さく 429 になりやすい(その場合は画像なしで結果を返す)。
- **ADK**: 2.x では Sequential/Parallel/LoopAgent が非推奨(Workflow 推奨)。現時点では動作するため設計資料どおり使用。
- **カルチャー情報データ**: 対象ジャンル・キーワードはデモ前にチームで見直し(T13 / T16)。
