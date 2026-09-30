"""処理フロー(P04〜P13)を ADK の Sequential / Parallel / Loop エージェントで組み立てる。

    P04 公演情報解析
      └─ 並列: P05 カルチャー / P06 MV / P07 会場・天気 / P08 手持ち服
    P09 スタイル統合
      └─ ループ(最大 1 + MAX_REGENERATIONS 回): P10 コーデ生成 → P11 Critic(合格で抜ける)
    P13 コーデ画像生成
    (P14 表示データ統合は service.py)

NOTE: ADK 2.x では Sequential/Parallel/LoopAgent は Workflow への移行が推奨され
非推奨警告が出る。現時点では動作するため設計資料(T06)どおりこれらを使う。
"""

from __future__ import annotations

import warnings

from google.adk.agents import BaseAgent, LoopAgent, ParallelAgent, SequentialAgent

from .steps import (
    ClosetAnalysisAgent,
    CriticAgent,
    CultureAgent,
    EventParseAgent,
    IntegrateStyleAgent,
    MvAnalysisAgent,
    OutfitGeneratorAgent,
    OutfitImageAgent,
    PipelineDeps,
    VenueWeatherAgent,
)

# UI の進捗表示に使うステップ名とラベル(順序どおり)
STEP_LABELS: dict[str, str] = {
    "event_parser": "公演情報を解析",
    "culture": "ジャンルのカルチャー情報を取得",
    "mv_analyzer": "公式MVを解析",
    "venue_weather": "会場・天気情報を取得",
    "closet_analyzer": "手持ち服を解析",
    "style_integrator": "スタイル特徴を統合",
    "outfit_generator": "コーディネート候補を生成",
    "critic": "コーディネートを評価",
    "image_generator": "コーデ画像を生成",
}


def build_pipeline(deps: PipelineDeps) -> BaseAgent:
    def step(cls, name: str):
        return cls(name=name, label=STEP_LABELS[name], deps=deps)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return SequentialAgent(
            name="live_outfit_pipeline",
            sub_agents=[
                step(EventParseAgent, "event_parser"),
                ParallelAgent(
                    name="parallel_analysis",
                    sub_agents=[
                        step(CultureAgent, "culture"),
                        step(MvAnalysisAgent, "mv_analyzer"),
                        step(VenueWeatherAgent, "venue_weather"),
                        step(ClosetAnalysisAgent, "closet_analyzer"),
                    ],
                ),
                step(IntegrateStyleAgent, "style_integrator"),
                LoopAgent(
                    name="generate_and_critique",
                    max_iterations=1 + deps.settings.max_regenerations,
                    sub_agents=[
                        step(OutfitGeneratorAgent, "outfit_generator"),
                        step(CriticAgent, "critic"),
                    ],
                ),
                step(OutfitImageAgent, "image_generator"),
            ],
        )
