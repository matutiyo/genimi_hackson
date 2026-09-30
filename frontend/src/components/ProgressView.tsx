import { useEffect, useState } from 'react'
import type { ClosetPhoto } from '../types'

export interface StepState {
  step: string
  label: string
  done: boolean
}

export interface ProgressState {
  /** sending: サーバー応答待ち / running: 解析中 / done: 結果受信済み(完成演出中) */
  status: 'sending' | 'running' | 'done'
  steps: StepState[]
  /** Critic 不合格による再生成の回数 */
  retries: number
  startedAt: number
  /** 最後に進捗が動いた時刻(バーを滑らかに進めるのに使う) */
  lastUpdateAt: number
}

/** 処理フロー(pipeline.py)の段階。ParallelAgent 配下は同じ段階にまとめて表示する */
const STAGES: { id: string; title: string; active: string; steps: string[] }[] = [
  { id: 'event', title: '公演情報', active: '公演情報を読み取っています', steps: ['event_parser'] },
  {
    id: 'analyze',
    title: 'ライブの雰囲気と手持ち服を解析',
    active: 'カルチャー・MV・会場・手持ち服を同時に解析しています',
    steps: ['culture', 'mv_analyzer', 'venue_weather', 'closet_analyzer'],
  },
  { id: 'integrate', title: 'スタイルの方向性を決定', active: 'スタイルの方向性をまとめています', steps: ['style_integrator'] },
  {
    id: 'outfit',
    title: 'コーデを組んでセルフチェック',
    active: '手持ち服からコーデを組み、AIがセルフチェックしています',
    steps: ['outfit_generator', 'critic'],
  },
  { id: 'image', title: 'コーデ画像を作成', active: '完成イメージ画像を作っています', steps: ['image_generator'] },
]

/** ParallelAgent 配下のステップ(完了順が前後する) */
export const PARALLEL_STEPS = STAGES[1].steps

const TIPS = [
  'スタンディング公演では、両手が空くショルダーバッグやサコッシュが便利です。',
  '会場内は冬でも暑くなりがち。脱ぎ着しやすい重ね着がおすすめです。',
  '厚底やヒールは長時間立つと疲れやすく、周りの足を踏む心配も。スニーカーが安心です。',
  'グッズのTシャツやタオルを会場で買って、その場で合わせるのも定番の楽しみ方です。',
  'アーティストの公式MVやアー写の色味をひとつ取り入れると、ぐっと「それっぽく」なります。',
  'コインロッカーは開演前に埋まりがち。荷物は少なめにしておくと動きやすいです。',
  '帽子や大きな髪飾りは後ろの人の視界をさえぎることがあるので、会場では外すのがマナーです。',
]

interface Stage {
  id: string
  title: string
  active: string
  steps: StepState[]
}

function buildStages(steps: StepState[]): Stage[] {
  const byId = new Map(steps.map((s) => [s.step, s]))
  const used = new Set<string>()
  const stages: Stage[] = []
  for (const def of STAGES) {
    const found = def.steps.map((id) => byId.get(id)).filter((s): s is StepState => !!s)
    found.forEach((s) => used.add(s.step))
    if (found.length) stages.push({ ...def, steps: found })
  }
  // 未知のステップ(バックエンド側で追加された場合)は単独の段階として末尾に出す
  for (const s of steps) {
    if (!used.has(s.step)) stages.push({ id: s.step, title: s.label, active: `${s.label}中`, steps: [s] })
  }
  return stages
}

function formatElapsed(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return m > 0 ? `${m}分${String(s).padStart(2, '0')}秒` : `${s}秒`
}

function Check() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden className="check">
      <path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** F04 進捗表示(ロード/待機画面) */
export function ProgressView({ progress, photos }: { progress: ProgressState; photos: ClosetPhoto[] }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(t)
  }, [])

  const { status, steps, retries } = progress
  const stages = buildStages(steps)
  const activeIndex = stages.findIndex((st) => st.steps.some((s) => !s.done))
  const activeStage = activeIndex >= 0 ? stages[activeIndex] : null
  const elapsed = Math.max(0, Math.floor((now - progress.startedAt) / 1000))
  const tip = TIPS[Math.floor(elapsed / 8) % TIPS.length]

  // 完了ステップ数 + 処理中ステップの経過時間に応じた「じわじわ進む」分
  const total = steps.length || 1
  const doneCount = steps.filter((s) => s.done).length
  const sinceUpdate = (now - progress.lastUpdateAt) / 1000
  const creep = status === 'running' && activeStage ? 0.85 * (1 - Math.exp(-sinceUpdate / 12)) : 0
  const percent =
    status === 'done' ? 100 : status === 'sending' ? Math.min(4, sinceUpdate) : Math.min(99, ((doneCount + creep) / total) * 100)

  const headline =
    status === 'done'
      ? 'コーディネートができました!'
      : status === 'sending'
        ? '写真と公演情報を送信しています'
        : retries > 0 && activeStage?.id === 'outfit'
          ? 'セルフチェックの結果を受けて、組み合わせを見直しています'
          : (activeStage?.active ?? '仕上げをしています')

  const closet = steps.find((s) => s.step === 'closet_analyzer')
  const scanning = status !== 'done' && !closet?.done

  return (
    <section className={`card progress is-${status}`} aria-labelledby="progress-heading">
      <div className="progress-visual" aria-hidden>
        {status === 'done' ? (
          <div className="done-mark">
            <Check />
          </div>
        ) : (
          <div className="equalizer">
            {Array.from({ length: 7 }, (_, i) => (
              <span key={i} style={{ animationDelay: `${(i * 137) % 700}ms` }} />
            ))}
          </div>
        )}
      </div>

      <h2 id="progress-heading" className="progress-headline" aria-live="polite">
        {headline}
        {status !== 'done' && <span className="dots" aria-hidden />}
      </h2>

      <div className="progress-meter">
        <div
          className="progress-bar"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(percent)}
          aria-label="全体の進み具合"
        >
          <div style={{ width: `${percent}%` }} />
        </div>
        <div className="progress-numbers">
          <b>{Math.round(percent)}%</b>
          <span>
            経過 {formatElapsed(elapsed)}
            {status !== 'done' && ' ・ 目安 1〜2分'}
          </span>
        </div>
      </div>

      {status !== 'done' && <p className="keep-open">完了まで、この画面を開いたままお待ちください</p>}

      {elapsed >= 150 && status !== 'done' && (
        <p className="slow-note" role="status">
          いつもより時間がかかっています。画面を閉じずにそのままお待ちください。
        </p>
      )}

      {photos.length > 0 && (
        <div className={`scan-strip ${scanning ? 'is-scanning' : 'is-scanned'}`}>
          <p className="scan-label">
            {closet?.done ? (
              <>
                <Check /> 手持ち服 {photos.length}枚の解析が完了
              </>
            ) : (
              `手持ち服 ${photos.length}枚を読み取り中`
            )}
          </p>
          <ul>
            {photos.map((p, i) => (
              <li key={p.id} style={{ animationDelay: `${i * 180}ms` }}>
                {p.previewUrl ? <img src={p.previewUrl} alt="" /> : <span className="thumb-fallback mini">{i + 1}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <ol className="stages">
        {status === 'sending' && (
          <li className="stage is-active">
            <span className="stage-icon">
              <span className="spinner" />
            </span>
            <div className="stage-body">
              <span className="stage-title">送信・準備</span>
            </div>
          </li>
        )}
        {stages.map((st, i) => {
          const done = st.steps.every((s) => s.done)
          const isActive = status === 'running' && i === activeIndex
          const state = done ? 'is-done' : isActive ? 'is-active' : 'is-pending'
          return (
            <li key={st.id} className={`stage ${state}`}>
              <span className="stage-icon">{done ? <Check /> : isActive ? <span className="spinner" /> : i + 1}</span>
              <div className="stage-body">
                <span className="stage-title">
                  {st.title}
                  {st.id === 'outfit' && retries > 0 && <em className="retry-badge">見直し {retries}回</em>}
                </span>
                {st.steps.length > 1 && (
                  <ul className="substeps">
                    {st.steps.map((s) => (
                      <li key={s.step} className={s.done ? 'is-done' : isActive ? 'is-active' : ''}>
                        {s.done ? <Check /> : isActive ? <span className="spinner small" /> : <span className="dot" />}
                        {s.label}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </li>
          )
        })}
      </ol>

      {status !== 'done' && (
        <aside className="tip" aria-label="待ち時間の豆知識">
          <span className="tip-label">ライブ服の豆知識</span>
          <p key={tip}>{tip}</p>
        </aside>
      )}
    </section>
  )
}
