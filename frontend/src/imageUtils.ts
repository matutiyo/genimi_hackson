// 手持ち服画像の前処理(ブラウザ内で完結。サーバーには縮小後の画像だけを送る)

/** 長辺がこれを超える写真は縮小する(Gemini の解析にはこれで十分) */
const MAX_EDGE = 1600
/** これより小さく、かつ長辺が MAX_EDGE 以下なら元ファイルのまま送る */
const SKIP_BYTES = 1.5 * 1024 * 1024
const JPEG_QUALITY = 0.85

/** ブラウザでプレビュー・縮小できる形式か(HEIC は Safari 以外で表示できない) */
export function isPreviewable(file: File): boolean {
  return ['image/jpeg', 'image/png', 'image/webp', 'image/gif'].includes(file.type)
}

/** 重複追加の判定キー(lastModified は取得経路で変わることがあるので使わない) */
export function fileKey(file: File): string {
  return `${file.name}:${file.size}`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
}

/** EXIF の向きを反映してデコードする(オプション非対応のブラウザでは付けずに再試行) */
async function decode(file: File): Promise<ImageBitmap | null> {
  try {
    return await createImageBitmap(file, { imageOrientation: 'from-image' })
  } catch {
    try {
      return await createImageBitmap(file)
    } catch {
      return null
    }
  }
}

/**
 * 大きな写真を長辺 MAX_EDGE の JPEG に縮小する。
 * HEIC などはデコードできるブラウザ(iOS Safari など)なら JPEG に変換してプレビュー可能にする。
 * 縮小できない形式・失敗時は元のファイルをそのまま返す(送信は止めない)。
 */
export async function shrinkImage(file: File): Promise<File> {
  if (file.type === 'image/gif') return file
  const convert = !isPreviewable(file)
  const bitmap = await decode(file)
  if (!bitmap) return file
  try {
    const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height))
    if (!convert && scale === 1 && file.size <= SKIP_BYTES) return file

    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    const ctx = canvas.getContext('2d')
    if (!ctx) return file
    ctx.fillStyle = '#ffffff' // 透過 PNG の背景を白で埋める
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)

    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY))
    // iOS Safari はキャンバスのメモリを GC まで保持するので明示的に解放する
    canvas.width = 0
    canvas.height = 0
    if (!blob || (!convert && blob.size >= file.size)) return file
    const name = file.name.replace(/\.[^.]+$/, '') + '.jpg'
    return new File([blob], name, { type: 'image/jpeg', lastModified: file.lastModified })
  } finally {
    bitmap.close()
  }
}

/** crypto.randomUUID は HTTPS / localhost でしか使えないため、LAN 経由の実機確認用に代替する */
let idSeq = 0
export function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function' && window.isSecureContext) {
    return crypto.randomUUID()
  }
  idSeq += 1
  return `photo-${Date.now()}-${idSeq}`
}
