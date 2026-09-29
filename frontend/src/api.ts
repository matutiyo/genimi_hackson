import type { ClientConfig, EventForm, StreamMessage } from './types'

export class ValidationError extends Error {
  errors: string[]
  constructor(errors: string[]) {
    super(errors.join('\n'))
    this.errors = errors
  }
}

export async function fetchConfig(): Promise<ClientConfig> {
  const res = await fetch('/api/config')
  if (!res.ok) throw new Error('設定の取得に失敗しました')
  return res.json()
}

/** 提案APIを呼び出し、NDJSON のメッセージを1行ずつ onMessage に渡す */
export async function requestProposal(
  form: EventForm,
  files: File[],
  consent: boolean,
  onMessage: (msg: StreamMessage) => void,
  signal?: AbortSignal,
): Promise<void> {
  const body = new FormData()
  for (const [key, value] of Object.entries(form)) {
    if (value.trim()) body.append(key, value.trim())
  }
  body.append('consent', String(consent))
  files.forEach((f) => body.append('images', f, f.name))

  const res = await fetch('/api/proposals', { method: 'POST', body, signal })
  if (res.status === 422) {
    const data = await res.json()
    throw new ValidationError(data.errors ?? ['入力内容を確認してください。'])
  }
  if (!res.ok || !res.body) throw new Error(`サーバーエラーが発生しました(${res.status})`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (line.trim()) onMessage(JSON.parse(line) as StreamMessage)
    }
  }
  if (buffer.trim()) onMessage(JSON.parse(buffer) as StreamMessage)
}
