"""各ステップで Gemini に渡すプロンプト。"""

from __future__ import annotations

import json

from .schemas import CultureInfo, MvStyle, StyleProfile, VenueWeather

SAFETY_NOTE = (
    "実在の人物(アーティスト本人を含む)の容姿・顔・体型を模倣・描写しないこと。"
    "服装・色調・シルエットなどのスタイル特徴のみを扱うこと。"
)

EVENT_SEARCH_PROMPT = """\
ユーザーがこれから行く音楽ライブ・公演を探しています。検索キーワードは「{keyword}」です。
Google 検索で、このキーワードに該当する公演(今日 {today} 以降に開催されるものを優先)を調べ、
候補を最大{limit}件、次のキーを持つJSONオブジェクトのみで出力してください。説明文やコードブロック記号は付けないでください。
分からない項目は null にしてください。推測で日付や会場を作らないこと。

{{
  "candidates": [
    {{
      "artist_name": "出演アーティスト名(複数ならメインの1組)",
      "event_title": "公演名・ツアー名",
      "event_date": "YYYY-MM-DD 形式の公演日(複数日程なら最も近い日)",
      "venue": "会場名",
      "genre_hint": "音楽ジャンル",
      "mv_url": "アーティストの公式YouTubeチャンネルで公開されている代表曲の公式MVのURL(確実なものが無ければ null)"
    }}
  ]
}}

- 公演が見つからない場合でも、アーティストが特定できれば event_title などを null にして1件返すこと。
- 該当するアーティストが特定できない場合は "candidates": [] を返すこと。
{conditions}"""

GENRE_MATCH_PROMPT = """\
アーティスト「{artist}」(ユーザー入力ジャンル: {genre})のライブに参加します。
このアーティストの音楽ジャンル・ライブ客層のファッション文化に最も近いものを、次の候補IDから1つ選んでください。
確信が持てない、または候補に近いものが無い場合は genre_id を null にしてください。

候補:
{candidates}
"""

CULTURE_SUMMARY_PROMPT = """\
ライブに初めて参加する人向けに、「{genre_name}」系のライブでよく見られるファッション文化を2〜3文で解説してください。
アーティスト: {artist}
参考キーワード(チームが整理した特徴語): {keywords}

- 解説は一般的な傾向として書き、断定的な「ドレスコード」扱いはしないこと。
- keywords には、コーディネートに使える色・素材・アイテムの特徴語を5〜10個挙げること。
- {safety}
"""

MV_ANALYSIS_PROMPT = """\
この{source}は、アーティスト「{artist}」の公式ミュージックビデオ(またはそのサムネイル)です。
ライブ参加者が「会場で浮かず、世界観に合う」服装を考えるための材料として、映像全体の大づかみなビジュアル特徴を抽出してください。

- color_palette: 主な色調(3〜6個、日本語の色名)
- lighting_mood: 照明・雰囲気の一言説明
- fashion_items: 出演者の衣装に見られる代表的なアイテム(一般名詞で)
- silhouettes: シルエットの傾向(例: オーバーサイズ、タイト、Aライン)
- overall_vibe: 世界観を一文で
- 時系列の細かい変化は追わず、全体の傾向だけでよい。
- {safety}
"""

VENUE_PROMPT = """\
ライブ会場「{venue}」について、服装選びに影響する情報を推定してください。
- venue_type: standing(オールスタンディング)/ seated(着席)/ outdoor(野外)/ mixed / unknown
- capacity_note: 規模感の一言(分からなければ空文字)
- notes: 服装に関わる注意(例: 「ロッカーが少ないため荷物は小さく」)を最大3つ
確実な知識が無い場合は venue_type を unknown にし、推測で断定しないこと。
"""

CLOSET_PROMPT = """\
これはユーザーの手持ち服の写真です(1枚に複数アイテムが写っている場合があります)。
写っている衣類・靴・バッグ・アクセサリーをそれぞれ1アイテムとして列挙してください。
- category は tops / outer / bottoms / onepiece / shoes / bag / accessory / headwear / other から選ぶ
- name は「色+素材+アイテム名」の短い日本語(例: 黒のレザーライダースジャケット)
- colors / material / pattern / silhouette / style_tags は見て分かる範囲で。分からなければ null や空配列
- 人物が写っていても、人物の特徴(顔・体型など)には一切触れないこと
"""


def integrate_prompt(
    artist: str,
    culture: CultureInfo | None,
    mv: MvStyle | None,
    venue_weather: VenueWeather | None,
    closet_summary: str,
) -> str:
    return f"""\
アーティスト「{artist}」のライブに初めて参加するユーザーのため、目指すべき服装スタイルを統合してください。

## ジャンル定番要素(事前収集データ由来)
{json.dumps(culture.model_dump() if culture and culture.covered else None, ensure_ascii=False)}

## 公式MV由来の特徴
{json.dumps(mv.model_dump() if mv and mv.analyzed_from != "none" else None, ensure_ascii=False)}

## 会場・天気
{json.dumps(venue_weather.model_dump() if venue_weather else None, ensure_ascii=False)}

## 手持ち服の傾向(参考)
{closet_summary}

指示:
- MVの特徴とジャンル定番要素をクロスチェックし、両方に現れる要素を重視、片方のみの要素は控えめに扱うこと。
  一致/不一致の判断は confidence_notes に書くこと。どちらかが null なら取得できた情報のみで統合すること。
- 会場形態・季節から実用面の注意(動きやすさ・荷物・温度調整など)を practical_notes に入れること。
- 「浮く」要素(過度なコスプレ、アーティスト本人の衣装の完全コピー等)や危険な要素は avoid に入れること。
- {SAFETY_NOTE}
"""


def outfit_prompt(profile: StyleProfile, closet_json: str, feedback: str | None) -> str:
    feedback_block = (
        f"\n## 前回候補への指摘(必ず反映すること)\n{feedback}\n" if feedback else ""
    )
    return f"""\
次の統合スタイルプロファイルに合うコーディネートを、ユーザーの手持ち服だけで1つ組んでください。

## 統合スタイルプロファイル
{profile.model_dump_json()}

## 手持ち服(item_id 付き)
{closet_json}
{feedback_block}
指示:
- item_ids には上の一覧に存在する item_id だけを使うこと。存在しないIDを作らないこと。
- 可能ならトップス(またはワンピース)・ボトムス・靴を含めること。同カテゴリの重複は避ける。
- reason には、なぜこの組み合わせがライブの世界観と会場に合うのかを、初参加者に伝わる言葉で3〜4文で書くこと。
- styling_tips には着こなしのコツを最大3つ。
- 手持ちで足りない要素があれば missing_suggestions に最大3つ(無理に挙げなくてよい)。
"""


def critic_prompt(profile: StyleProfile, candidate_json: str) -> str:
    return f"""\
あなたはライブファッションの批評担当です。次のコーディネート候補を、統合スタイルプロファイルに照らして評価してください。

## 統合スタイルプロファイル
{profile.model_dump_json()}

## コーディネート候補(選ばれたアイテムの詳細付き)
{candidate_json}

評価軸(1〜5の整数、3が「許容範囲」):
- color_match: 色調がプロファイルの key_colors とどれだけ合っているか
- silhouette_match: シルエットがプロファイルとどれだけ近いか
- practicality: 会場形態・天気に対して実用的か
- blend_in: 会場で浮きすぎず、埋もれすぎないか

issues には具体的な問題点を、revision_instruction には「どのアイテムをどう変えるべきか」を1〜2文で書くこと。
問題が無ければ issues は空、revision_instruction は空文字でよい。
"""


def image_prompt(title: str, item_names: list[str], profile: StyleProfile) -> str:
    items = "\n".join(f"- {name}" for name in item_names)
    return f"""\
添付した手持ち服の写真を参考に、次のアイテムを組み合わせたライブ向けコーディネート画像を1枚生成してください。

コーディネート名: {title}
使用アイテム:
{items}

雰囲気: {profile.summary}
キーカラー: {", ".join(profile.key_colors)}

表現ルール:
- 平置き(フラットレイ)または顔の無いトルソー/マネキンに着せた構図にすること。人物の顔は描かない。
- 添付写真の服の色・素材・柄をできるだけ忠実に再現すること。
- 背景はシンプルに、ライブの世界観を感じる色の照明程度に留めること。
- 文字・ロゴ・アーティスト名は入れないこと。
- {SAFETY_NOTE}
"""
