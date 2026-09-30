import { useCallback, useEffect, useRef, useState } from 'react'
import { fileKey, formatBytes, isPreviewable, newId, shrinkImage } from '../imageUtils'
import type { ClientConfig, ClosetPhoto } from '../types'

interface Props {
  photos: ClosetPhoto[]
  onChange: (updater: (prev: ClosetPhoto[]) => ClosetPhoto[]) => void
  config: ClientConfig | null
  consent: boolean
  onConsentChange: (value: boolean) => void
  /** 入力画面が表示されている間だけ、画面全体へのドロップ・貼り付けを受け付ける */
  active: boolean
}

const DEFAULT_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif']

function hasFiles(e: DragEvent): boolean {
  return Array.from(e.dataTransfer?.types ?? []).includes('Files')
}

const EXT_TYPES: Record<string, string> = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
  heic: 'image/heic',
  heif: 'image/heif',
}

/** 拡張子から MIME を補う(Windows などで HEIC の type が空や octet-stream になる対策) */
function normalizeType(file: File, allowed: string[]): File {
  if (allowed.includes(file.type)) return file
  const type = EXT_TYPES[file.name.split('.').pop()?.toLowerCase() ?? '']
  return type ? new File([file], file.name, { type, lastModified: file.lastModified }) : file
}

/** P02 手持ち服・クローゼット画像の登録(複数枚) */
export function ClosetUploader({ photos, onChange, config, consent, onConsentChange, active }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const cameraInputRef = useRef<HTMLInputElement>(null)
  const [pageDragging, setPageDragging] = useState(false)
  const [zoneDragging, setZoneDragging] = useState(false)
  const [preparing, setPreparing] = useState(0)
  const [warnings, setWarnings] = useState<string[]>([])
  const [showTips, setShowTips] = useState(false)

  const maxImages = config?.max_images ?? 10
  const maxMb = config?.max_image_mb ?? 10
  const allowed = config?.allowed_types ?? DEFAULT_TYPES
  const remaining = maxImages - photos.length - preparing
  const full = remaining <= 0

  // 最新の photos を非同期処理から参照する
  const photosRef = useRef(photos)
  useEffect(() => {
    photosRef.current = photos
  }, [photos])
  const preparingRef = useRef(0)
  /** 縮小処理中のファイル(連続で追加されたときの重複判定用) */
  const pendingKeysRef = useRef(new Set<string>())

  const addFiles = useCallback(
    async (incoming: File[]) => {
      if (incoming.length === 0) return
      const rejected: string[] = []
      const known = new Set([...photosRef.current.map((p) => p.sourceKey), ...pendingKeysRef.current])
      const queue: File[] = []
      for (const raw of incoming) {
        const f = normalizeType(raw, allowed)
        if (!allowed.includes(f.type)) {
          rejected.push(`「${f.name}」は対応していない形式です(JPEG/PNG/WebP/HEIC)`)
        } else if (known.has(fileKey(f))) {
          rejected.push(`「${f.name}」はすでに追加されています`)
        } else if (photosRef.current.length + preparingRef.current + queue.length >= maxImages) {
          rejected.push(`${maxImages}枚を超えた分は追加できません`)
          break
        } else {
          known.add(fileKey(f))
          queue.push(f)
        }
      }
      setWarnings(rejected)
      if (queue.length === 0) return

      queue.forEach((f) => pendingKeysRef.current.add(fileKey(f)))
      preparingRef.current += queue.length
      setPreparing(preparingRef.current)
      // スマホで大きな写真を同時にデコードするとメモリ不足になるため1枚ずつ処理し、終わった順に表示する
      const tooLarge: string[] = []
      for (const f of queue) {
        const file = await shrinkImage(f)
        pendingKeysRef.current.delete(fileKey(f))
        preparingRef.current -= 1
        setPreparing(preparingRef.current)
        if (file.size > maxMb * 1024 * 1024) {
          tooLarge.push(`「${f.name}」は${maxMb}MBを超えています(${formatBytes(file.size)})`)
          continue
        }
        const photo: ClosetPhoto = {
          id: newId(),
          file,
          sourceKey: fileKey(f),
          previewUrl: isPreviewable(file) ? URL.createObjectURL(file) : null,
          originalSize: f.size,
        }
        onChange((prev) => [...prev, photo].slice(0, maxImages))
      }
      if (tooLarge.length) setWarnings((w) => [...w, ...tooLarge])
    },
    [allowed, maxImages, maxMb, onChange],
  )

  // 画面のどこにドロップしても追加できるようにする
  useEffect(() => {
    if (!active) return
    let depth = 0
    const onEnter = (e: DragEvent) => {
      if (!hasFiles(e)) return
      depth += 1
      setPageDragging(true)
    }
    const onLeave = (e: DragEvent) => {
      if (!hasFiles(e)) return
      depth = Math.max(0, depth - 1)
      if (depth === 0) setPageDragging(false)
    }
    const onOver = (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault()
    }
    const onDrop = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      depth = 0
      setPageDragging(false)
      setZoneDragging(false)
      void addFiles(Array.from(e.dataTransfer?.files ?? []))
    }
    // スクリーンショット等をクリップボードから貼り付け
    const onPaste = (e: ClipboardEvent) => {
      const target = e.target as HTMLElement | null
      const files = Array.from(e.clipboardData?.files ?? []).filter((f) => f.type.startsWith('image/'))
      if (files.length === 0) return
      if (target?.tagName === 'INPUT' && (target as HTMLInputElement).type !== 'checkbox') return
      e.preventDefault()
      void addFiles(files)
    }
    window.addEventListener('dragenter', onEnter)
    window.addEventListener('dragleave', onLeave)
    window.addEventListener('dragover', onOver)
    window.addEventListener('drop', onDrop)
    window.addEventListener('paste', onPaste)
    return () => {
      window.removeEventListener('dragenter', onEnter)
      window.removeEventListener('dragleave', onLeave)
      window.removeEventListener('dragover', onOver)
      window.removeEventListener('drop', onDrop)
      window.removeEventListener('paste', onPaste)
    }
  }, [active, addFiles])

  const remove = (id: string) => {
    onChange((prev) => {
      const target = prev.find((p) => p.id === id)
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl)
      return prev.filter((p) => p.id !== id)
    })
    setWarnings([])
  }

  const clearAll = () => {
    photos.forEach((p) => p.previewUrl && URL.revokeObjectURL(p.previewUrl))
    onChange(() => [])
    setWarnings([])
  }

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    void addFiles(Array.from(e.target.files ?? []))
    e.target.value = ''
  }

  const openPicker = () => fileInputRef.current?.click()
  const empty = photos.length === 0 && preparing === 0

  return (
    <section className="card" aria-labelledby="closet-heading">
      <h2 id="closet-heading">
        <span className="step-no">2</span>手持ちの服
        <span className={`count-pill ${photos.length > 0 ? 'has' : ''}`}>
          {photos.length} / {maxImages} 枚
        </span>
      </h2>
      <p className="hint">
        持っている服・靴・小物の写真を追加してください。1枚に複数アイテムが写っていても大丈夫です。
        <b>トップス・ボトムス・靴</b>がそろうと提案の精度が上がります。
      </p>

      {empty ? (
        <div
          className={`dropzone ${zoneDragging || pageDragging ? 'is-dragging' : ''}`}
          onClick={openPicker}
          onDragEnter={() => setZoneDragging(true)}
          onDragLeave={() => setZoneDragging(false)}
          role="button"
          tabIndex={0}
          aria-label="服の写真を選ぶ"
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              openPicker()
            }
          }}
        >
          <svg className="dropzone-icon" viewBox="0 0 48 48" aria-hidden>
            <path
              d="M20 13a4 4 0 1 1 4 4v2L6 35h36L24 19"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <strong>写真を選ぶ</strong>
          <span className="dropzone-sub">
            ここにドラッグ&ドロップ ・ <kbd>Ctrl</kbd>+<kbd>V</kbd> で貼り付けもOK
          </span>
          <span className="dropzone-meta">
            JPEG / PNG / WebP / HEIC ・ 1枚{maxMb}MBまで ・ 最大{maxImages}枚(大きい写真は自動で縮小します)
          </span>
        </div>
      ) : (
        <ul className="thumbs" aria-label="追加した写真">
          {photos.map((p, i) => (
            <li key={p.id} className="thumb">
              {p.previewUrl ? (
                <img src={p.previewUrl} alt={`服の写真 ${i + 1}: ${p.file.name}`} />
              ) : (
                <div className="thumb-fallback" title={p.file.name}>
                  <span>{p.file.name.split('.').pop()?.toUpperCase()}</span>
                  <small>プレビュー非対応</small>
                </div>
              )}
              <span className="thumb-no" aria-hidden>
                {i + 1}
              </span>
              <span className="thumb-size">
                {p.file.size < p.originalSize ? `${formatBytes(p.originalSize)}→` : ''}
                {formatBytes(p.file.size)}
              </span>
              <button
                type="button"
                className="thumb-remove"
                aria-label={`${i + 1}枚目(${p.file.name})を削除`}
                onClick={() => remove(p.id)}
              >
                <svg viewBox="0 0 16 16" aria-hidden>
                  <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              </button>
            </li>
          ))}
          {Array.from({ length: preparing }, (_, i) => (
            <li key={`preparing-${i}`} className="thumb is-preparing" aria-label="写真を準備中">
              <span className="spinner" aria-hidden />
              <small>準備中…</small>
            </li>
          ))}
          {!full && (
            <li className="thumb">
              <button
                type="button"
                className={`thumb-add ${pageDragging ? 'is-dragging' : ''}`}
                onClick={openPicker}
              >
                <span aria-hidden>+</span>
                <small>追加(あと{remaining}枚)</small>
              </button>
            </li>
          )}
        </ul>
      )}

      <div className="upload-tools">
        <button type="button" className="ghost camera-only" onClick={() => cameraInputRef.current?.click()} disabled={full}>
          <svg viewBox="0 0 24 24" aria-hidden>
            <path
              d="M4 8h3l2-3h6l2 3h3v11H4z M12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinejoin="round"
            />
          </svg>
          カメラで撮る
        </button>
        <button type="button" className="ghost" onClick={() => setShowTips((v) => !v)} aria-expanded={showTips}>
          上手に撮るコツ {showTips ? '▲' : '▼'}
        </button>
        {photos.length > 0 && (
          <button type="button" className="ghost danger" onClick={clearAll}>
            すべて削除
          </button>
        )}
      </div>

      {showTips && (
        <ul className="photo-tips">
          <li>
            <b>平置き or ハンガー掛け</b>で、服の形がわかるように撮る
          </li>
          <li>
            <b>明るい場所</b>で撮ると色を正しく読み取れます
          </li>
          <li>
            <b>自分が写らない</b>ように撮影してください(人物は解析に使いません)
          </li>
          <li>
            靴やアクセサリーも1枚あると、コーデ全体を組みやすくなります
          </li>
        </ul>
      )}

      {warnings.length > 0 && (
        <ul className="warning" role="status">
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}

      <input ref={fileInputRef} type="file" accept={allowed.join(',')} multiple hidden onChange={onInputChange} />
      <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" hidden onChange={onInputChange} />

      <label className={`consent ${consent ? 'is-checked' : ''}`}>
        <input type="checkbox" checked={consent} onChange={(e) => onConsentChange(e.target.checked)} />
        <span>
          自分で撮影した(または利用許諾を得た)画像です。画像は提案の生成にのみ使われ、保存されません。
        </span>
      </label>

      {pageDragging && (
        <div className="page-drop" aria-hidden>
          <div>
            <strong>ドロップして服の写真を追加</strong>
            <span>あと{Math.max(0, remaining)}枚追加できます</span>
          </div>
        </div>
      )}
    </section>
  )
}
