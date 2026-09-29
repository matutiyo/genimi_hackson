import { useEffect, useMemo, useRef, useState } from 'react'
import type { ClientConfig } from '../types'

interface Props {
  files: File[]
  onChange: (files: File[]) => void
  config: ClientConfig | null
  consent: boolean
  onConsentChange: (value: boolean) => void
}

/** P02 手持ち服・クローゼット画像の登録(複数枚) */
export function ClosetUploader({ files, onChange, config, consent, onConsentChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [warning, setWarning] = useState<string | null>(null)
  const maxImages = config?.max_images ?? 10
  const maxBytes = (config?.max_image_mb ?? 10) * 1024 * 1024

  const previews = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files])
  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews])

  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return
    const accepted: File[] = []
    const rejected: string[] = []
    for (const f of Array.from(incoming)) {
      if (!f.type.startsWith('image/')) rejected.push(`${f.name}(画像ではありません)`)
      else if (f.size > maxBytes) rejected.push(`${f.name}(${config?.max_image_mb ?? 10}MB超)`)
      else accepted.push(f)
    }
    const next = [...files, ...accepted].slice(0, maxImages)
    if (files.length + accepted.length > maxImages) rejected.push(`${maxImages}枚を超えた分`)
    setWarning(rejected.length ? `追加できなかった画像: ${rejected.join('、')}` : null)
    onChange(next)
  }

  return (
    <section className="card">
      <h2>
        <span className="step-no">2</span>手持ちの服
      </h2>
      <p className="hint">
        持っている服・靴・小物の写真を追加してください(最大{maxImages}枚)。1枚に複数アイテムが写っていても大丈夫です。
      </p>

      <div
        className={`dropzone ${dragging ? 'is-dragging' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          addFiles(e.dataTransfer.files)
        }}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && inputRef.current?.click()}
      >
        <strong>写真を選ぶ</strong>
        <span>またはここにドラッグ&ドロップ</span>
        <input
          ref={inputRef}
          type="file"
          accept={config?.allowed_types.join(',') ?? 'image/*'}
          multiple
          hidden
          onChange={(e) => {
            addFiles(e.target.files)
            e.target.value = ''
          }}
        />
      </div>
      {warning && <p className="warning">{warning}</p>}

      {files.length > 0 && (
        <ul className="thumbs">
          {files.map((f, i) => (
            <li key={`${f.name}-${i}`}>
              <img src={previews[i]} alt={f.name} />
              <button
                type="button"
                className="thumb-remove"
                aria-label={`${f.name}を削除`}
                onClick={() => onChange(files.filter((_, j) => j !== i))}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="counter">
        {files.length} / {maxImages} 枚
      </p>

      <label className="consent">
        <input type="checkbox" checked={consent} onChange={(e) => onConsentChange(e.target.checked)} />
        <span>
          自分で撮影した(または利用許諾を得た)画像です。画像は提案の生成にのみ使われ、保存されません。
        </span>
      </label>
    </section>
  )
}
