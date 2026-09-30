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

/**
 * 大きな写真を長辺 MAX_EDGE の JPEG に縮小する。
 * 縮小できない形式・失敗時は元のファイルをそのまま返す(送信は止めない)。
 */
export async function shrinkImage(file: File): Promise<File> {
  if (!isPreviewable(file) || file.type === 'image/gif') return file
  let bitmap: ImageBitmap
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  } catch {
    return file
  }
  try {
    const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height))
    if (scale === 1 && file.size <= SKIP_BYTES) return file

    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    const ctx = canvas.getContext('2d')
    if (!ctx) return file
    ctx.fillStyle = '#ffffff' // 透過 PNG の背景を白で埋める
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)

    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY))
    if (!blob || blob.size >= file.size) return file
    const name = file.name.replace(/\.[^.]+$/, '') + '.jpg'
    return new File([blob], name, { type: 'image/jpeg', lastModified: file.lastModified })
  } finally {
    bitmap.close()
  }
}
