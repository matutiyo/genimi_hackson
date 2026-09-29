import { useEffect, useRef, useState } from 'react'
import { fetchConfig, requestProposal, ValidationError } from './api'
import { ClosetUploader } from './components/ClosetUploader'
import { EventSection } from './components/EventSection'
import { ProgressView, type StepState } from './components/ProgressView'
import { ResultView } from './components/ResultView'
import type { ClientConfig, EventForm, ProposalResult, StreamMessage } from './types'

type Phase = 'input' | 'running' | 'result'

const EMPTY_FORM: EventForm = { event_url: '', artist_name: '', genre: '', event_date: '', venue: '', mv_url: '' }

function validate(form: EventForm, files: File[], consent: boolean): string[] {
  const errors: string[] = []
  if (!form.event_url.trim() && !form.artist_name.trim())
    errors.push('公演URLまたはアーティスト名のどちらかを入力してください。')
  if (files.length === 0) errors.push('手持ち服の画像を1枚以上追加してください。')
  if (!consent) errors.push('画像の利用について同意してください。')
  return errors
}

export default function App() {
  const [config, setConfig] = useState<ClientConfig | null>(null)
  const [phase, setPhase] = useState<Phase>('input')
  const [form, setForm] = useState<EventForm>(EMPTY_FORM)
  const [files, setFiles] = useState<File[]>([])
  const [consent, setConsent] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const [steps, setSteps] = useState<StepState[]>([])
  const [result, setResult] = useState<ProposalResult | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    fetchConfig().then(setConfig).catch(() => setConfig(null))
  }, [])

  const handleMessage = (msg: StreamMessage) => {
    switch (msg.type) {
      case 'start':
        setSteps(msg.steps.map((s) => ({ ...s, done: false })))
        break
      case 'step':
        setSteps((prev) =>
          prev.map((s) => {
            if (msg.step === 'critic' && msg.passed === false && (s.step === 'outfit_generator' || s.step === 'critic')) {
              // 不合格 → 再生成ループに入るので生成・評価を未完了に戻す
              return { ...s, done: s.step === 'critic' ? false : s.done, detail: '見直し中…' }
            }
            if (s.step !== msg.step) return s
            return { ...s, done: true, detail: msg.step === 'critic' ? (msg.passed ? '合格' : '上限到達') : undefined }
          }),
        )
        break
      case 'result':
        setResult(msg.result)
        setPhase('result')
        break
      case 'error':
        setErrors([msg.message])
        setPhase('input')
        break
    }
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const clientErrors = validate(form, files, consent)
    setErrors(clientErrors)
    if (clientErrors.length) return

    setPhase('running')
    setSteps([])
    abortRef.current = new AbortController()
    try {
      await requestProposal(form, files, consent, handleMessage, abortRef.current.signal)
    } catch (err) {
      if ((err as Error).name === 'AbortError') return
      setErrors(err instanceof ValidationError ? err.errors : [(err as Error).message || '通信に失敗しました。'])
      setPhase('input')
    }
  }

  const cancel = () => {
    abortRef.current?.abort()
    setPhase('input')
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>はじめてのライブ服</h1>
        <p>行くライブと手持ちの服から、会場で浮かないコーディネートを提案します。</p>
        {config?.mock && <span className="mock-badge">モックモード(Gemini未接続)</span>}
      </header>

      <main>
        {phase === 'input' && (
          <form onSubmit={submit} noValidate>
            {errors.length > 0 && (
              <div className="error-box" role="alert">
                <ul>
                  {errors.map((m) => (
                    <li key={m}>{m}</li>
                  ))}
                </ul>
              </div>
            )}
            <EventSection value={form} onChange={setForm} />
            <ClosetUploader
              files={files}
              onChange={setFiles}
              config={config}
              consent={consent}
              onConsentChange={setConsent}
            />
            <div className="actions">
              <button type="submit" className="primary">
                コーディネートを提案してもらう
              </button>
            </div>
          </form>
        )}

        {phase === 'running' && (
          <>
            <ProgressView steps={steps} />
            <div className="actions">
              <button type="button" className="secondary" onClick={cancel}>
                キャンセル
              </button>
            </div>
          </>
        )}

        {phase === 'result' && result && (
          <ResultView result={result} files={files} onRestart={() => setPhase('input')} />
        )}
      </main>
    </div>
  )
}
