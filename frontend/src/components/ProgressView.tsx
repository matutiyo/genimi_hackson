export interface StepState {
  step: string
  label: string
  done: boolean
  detail?: string
}

/** F04 進捗表示 */
export function ProgressView({ steps }: { steps: StepState[] }) {
  const doneCount = steps.filter((s) => s.done).length
  const current = steps.find((s) => !s.done)
  return (
    <section className="card progress" aria-live="polite">
      <h2>コーディネートを考えています</h2>
      <div className="progress-bar">
        <div style={{ width: `${steps.length ? (doneCount / steps.length) * 100 : 0}%` }} />
      </div>
      <ol className="steps">
        {steps.map((s) => (
          <li key={s.step} className={s.done ? 'done' : s === current ? 'active' : ''}>
            <span className="dot" aria-hidden />
            <span>{s.label}</span>
            {s.detail && <small>{s.detail}</small>}
          </li>
        ))}
      </ol>
      <p className="hint">MVや画像の解析があるため、1〜2分ほどかかることがあります。</p>
    </section>
  )
}
