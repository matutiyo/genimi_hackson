import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchConfig, requestProposal, ValidationError } from './api'
import { ClosetUploader } from './components/ClosetUploader'
import { EventSection } from './components/EventSection'
import { PARALLEL_STEPS, ProgressView, type ProgressState } from './components/ProgressView'
import { ResultView } from './components/ResultView'
import type { ClientConfig, ClosetPhoto, EventForm, ProposalResult, StreamMessage } from './types'

type Phase = 'input' | 'running' | 'result'

const EMPTY_FORM: EventForm = { event_url: '', artist_name: '', genre: '', event_date: '', venue: '', mv_url: '' }

/** 結果受信後に「できました」を見せてから結果画面に切り替えるまでの時間 */
const DONE_PAUSE_MS = 900

const PHASES: { id: Phase; label: string }[] = [
  { id: 'input', label: '入力' },
  { id: 'running', label: 'AIが考え中' },
  { id: 'result', label: '提案' },
]

function checklist(form: EventForm, photos: ClosetPhoto[], consent: boolean) {
  return [
    { ok: !!(form.event_url.trim() || form.artist_name.trim()), label: '公演URL or アーティスト名', error: '公演URLまたはアーティスト名のどちらかを入力してください。' },
    { ok: photos.length > 0, label: `服の写真${photos.length ? `(${photos.length}枚)` : ''}`, error: '手持ち服の画像を1枚以上追加してください。' },
    { ok: consent, label: '画像利用への同意', error: '画像の利用について同意してください。' },
  ]
}

function initialProgress(): ProgressState {
  const now = Date.now()
  return { status: 'sending', steps: [], retries: 0, startedAt: now, lastUpdateAt: now }
}

/** 進捗メッセージを進捗表示の状態に反映する */
function applyProgress(
  p: ProgressState,
  msg: Extract<StreamMessage, { type: 'start' | 'step' }>,
  now: number,
): ProgressState {
  if (msg.type === 'start') {
    return { ...p, status: 'running', lastUpdateAt: now, steps: msg.steps.map((s) => ({ ...s, done: false })) }
  }
  if (msg.step === 'critic' && msg.passed === false) {
    // 不合格 → LoopAgent で再生成するので、生成・評価を未完了に戻す
    const reopened = p.steps.map((s) =>
      s.step === 'outfit_generator' || s.step === 'critic' ? { ...s, done: false } : s,
    )
    return { ...p, steps: reopened, retries: p.retries + 1, lastUpdateAt: now }
  }
  // 直列の段階が完了したら、それより前のステップもすべて完了扱いにする
  // (再生成上限で Critic 不合格のまま画像生成に進んだ場合など)
  const index = p.steps.findIndex((s) => s.step === msg.step)
  const sequential = !PARALLEL_STEPS.includes(msg.step)
  return {
    ...p,
    lastUpdateAt: now,
    steps: p.steps.map((s, i) => (i === index || (sequential && i < index) ? { ...s, done: true } : s)),
  }
}

export default function App() {
  const [config, setConfig] = useState<ClientConfig | null>(null)
  const [phase, setPhase] = useState<Phase>('input')
  const [form, setForm] = useState<EventForm>(EMPTY_FORM)
  const [photos, setPhotos] = useState<ClosetPhoto[]>([])
  const [consent, setConsent] = useState(false)
  /** サーバー・通信のエラー(入力チェックのエラーは checklist から都度計算する) */
  const [errors, setErrors] = useState<string[]>([])
  /** 一度送信を試みたら、未入力項目をリアルタイムに表示する */
  const [attempted, setAttempted] = useState(false)
  const [errorFocus, setErrorFocus] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)
  const [progress, setProgress] = useState<ProgressState>(initialProgress)
  const [result, setResult] = useState<ProposalResult | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const errorRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchConfig().then(setConfig).catch(() => setConfig(null))
  }, [])

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [phase])

  useEffect(() => {
    if (errorFocus) errorRef.current?.focus()
  }, [errorFocus])

  const updatePhotos = useCallback((updater: (prev: ClosetPhoto[]) => ClosetPhoto[]) => setPhotos(updater), [])

  const handleMessage = (msg: StreamMessage) => {
    switch (msg.type) {
      case 'start':
      case 'step':
        setProgress((p) => applyProgress(p, msg, Date.now()))
        break
      case 'result':
        setProgress((p) => ({ ...p, status: 'done', steps: p.steps.map((s) => ({ ...s, done: true })) }))
        window.setTimeout(() => {
          setResult(msg.result)
          setPhase('result')
        }, DONE_PAUSE_MS)
        break
      case 'error':
        setErrors([msg.message])
        setErrorFocus((n) => n + 1)
        setPhase('input')
        break
    }
  }

  const items = checklist(form, photos, consent)
  const ready = items.every((c) => c.ok)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setNotice(null)
    setAttempted(true)
    setErrors([])
    if (!ready) {
      setErrorFocus((n) => n + 1)
      return
    }

    setProgress(initialProgress())
    setPhase('running')
    abortRef.current = new AbortController()
    try {
      await requestProposal(
        form,
        photos.map((p) => p.file),
        consent,
        handleMessage,
        abortRef.current.signal,
      )
    } catch (err) {
      if ((err as Error).name === 'AbortError') return
      setErrors(
        err instanceof ValidationError
          ? err.errors
          : ['サーバーと通信できませんでした。ネットワーク接続を確認して、もう一度お試しください。'],
      )
      setErrorFocus((n) => n + 1)
      setPhase('input')
    }
  }

  const cancel = () => {
    abortRef.current?.abort()
    setNotice('提案をキャンセルしました。入力内容はそのまま残っています。')
    setPhase('input')
  }

  const shownErrors = [...(attempted ? items.filter((c) => !c.ok).map((c) => c.error) : []), ...errors]
  const phaseIndex = PHASES.findIndex((p) => p.id === phase)

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden>
            ♪
          </span>
          <div>
            <h1>はじめてのライブ服</h1>
            <p>行くライブと手持ちの服から、会場で浮かないコーディネートを提案します。</p>
          </div>
        </div>
        {config?.mock && <span className="mock-badge">モックモード(Gemini未接続)</span>}
        <ol className="phase-steps" aria-label="進み具合">
          {PHASES.map((p, i) => (
            <li
              key={p.id}
              className={i < phaseIndex ? 'is-done' : i === phaseIndex ? 'is-current' : ''}
              aria-current={i === phaseIndex ? 'step' : undefined}
            >
              <span>{i + 1}</span>
              {p.label}
            </li>
          ))}
        </ol>
      </header>

      <main>
        {phase === 'input' && (
          <form onSubmit={submit} noValidate>
            {notice && (
              <div className="notice-box" role="status">
                {notice}
              </div>
            )}
            {shownErrors.length > 0 && (
              <div className="error-box" role="alert" tabIndex={-1} ref={errorRef}>
                <strong>入力内容を確認してください</strong>
                <ul>
                  {shownErrors.map((m) => (
                    <li key={m}>{m}</li>
                  ))}
                </ul>
              </div>
            )}
            <EventSection value={form} onChange={setForm} />
            <ClosetUploader
              photos={photos}
              onChange={updatePhotos}
              config={config}
              consent={consent}
              onConsentChange={setConsent}
              active={phase === 'input'}
            />
            <div className="submit-bar">
              <ul className="checklist" aria-label="送信前チェック">
                {items.map((c) => (
                  <li key={c.label} className={c.ok ? 'is-ok' : ''}>
                    <span aria-hidden>{c.ok ? '✓' : ''}</span>
                    {c.label}
                    <span className="visually-hidden">{c.ok ? '(OK)' : '(未入力)'}</span>
                  </li>
                ))}
              </ul>
              <button type="submit" className={`primary ${ready ? '' : 'is-waiting'}`}>
                コーディネートを提案してもらう
              </button>
            </div>
          </form>
        )}

        {phase === 'running' && (
          <>
            <ProgressView progress={progress} photos={photos} />
            {progress.status !== 'done' && (
              <div className="actions">
                <button type="button" className="secondary" onClick={cancel}>
                  キャンセルして入力に戻る
                </button>
              </div>
            )}
          </>
        )}

        {phase === 'result' && result && (
          <ResultView
            result={result}
            photos={photos}
            onRestart={() => {
              setErrors([])
              setNotice(null)
              setPhase('input')
            }}
          />
        )}
      </main>
    </div>
  )
}
