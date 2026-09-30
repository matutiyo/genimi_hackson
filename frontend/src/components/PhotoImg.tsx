import { useEffect, useState } from 'react'
import type { ClosetPhoto } from '../types'

/** 表示に失敗したときに URL を作り直して再読み込みする回数 */
const MAX_RETRIES = 2

/**
 * 手持ち服の写真を表示する。
 * WebKit では作成直後の blob URL の読み込みがまれに失敗し、同じ URL では以降も失敗し続けるため、
 * 失敗したら新しい blob URL を作って読み直す。
 */
export function PhotoImg({ photo, alt }: { photo: ClosetPhoto; alt: string }) {
  const [retryUrl, setRetryUrl] = useState<string | null>(null)
  const [retries, setRetries] = useState(0)

  // 作り直した URL は、次に作り直したとき・画面から消えたときに解放する
  useEffect(() => () => {
    if (retryUrl) URL.revokeObjectURL(retryUrl)
  }, [retryUrl])

  const src = retryUrl ?? photo.previewUrl
  if (!src) return null
  return (
    <img
      src={src}
      alt={alt}
      onError={() => {
        if (retries >= MAX_RETRIES) return
        setRetries((n) => n + 1)
        setRetryUrl(URL.createObjectURL(photo.file))
      }}
    />
  )
}
