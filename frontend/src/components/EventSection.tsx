import type { EventForm } from '../types'

interface Props {
  value: EventForm
  onChange: (value: EventForm) => void
}

/** P01 公演情報の入力(URL または手動入力) */
// backend/app/gemini.py の _YOUTUBE_ID と同じ判定
const YOUTUBE = /(?:v=|youtu\.be\/|shorts\/|embed\/)([A-Za-z0-9_-]{11})/

function urlStatus(value: string, kind: 'event' | 'mv'): { ok: boolean; text: string } | null {
  const v = value.trim()
  if (!v) return null
  if (!/^https?:\/\//i.test(v)) return { ok: false, text: 'http:// または https:// から始まるURLを入力してください' }
  if (kind === 'mv' && !YOUTUBE.test(v)) return { ok: false, text: 'YouTube の動画URLを入力してください' }
  return { ok: true, text: kind === 'mv' ? 'YouTube の動画URLを認識しました' : 'このページから公演情報を読み取ります' }
}

function Status({ status }: { status: { ok: boolean; text: string } | null }) {
  if (!status) return null
  return (
    <em className={`field-status ${status.ok ? 'ok' : 'ng'}`} role={status.ok ? undefined : 'alert'}>
      {status.ok ? '✓ ' : '! '}
      {status.text}
    </em>
  )
}

export function EventSection({ value, onChange }: Props) {
  const set = (key: keyof EventForm) => (e: React.ChangeEvent<HTMLInputElement>) =>
    onChange({ ...value, [key]: e.target.value })

  return (
    <section className="card">
      <h2>
        <span className="step-no">1</span>行くライブの情報
      </h2>
      <p className="hint">公演ページのURLか、アーティスト名のどちらかは必須です。両方入れた場合は手入力の内容を優先します。</p>

      <label className="field">
        <span>公演告知ページのURL</span>
        <input type="url" inputMode="url" placeholder="https://..." value={value.event_url} onChange={set('event_url')} />
        <Status status={urlStatus(value.event_url, 'event')} />
      </label>

      <div className="divider">または手入力</div>

      <div className="grid-2">
        <label className="field">
          <span>アーティスト名</span>
          <input type="text" placeholder="例: ○○○○" value={value.artist_name} onChange={set('artist_name')} />
        </label>
        <label className="field">
          <span>
            ジャンル <small>任意</small>
          </span>
          <input type="text" placeholder="例: パンク、ヒップホップ、V系" value={value.genre} onChange={set('genre')} />
        </label>
        <label className="field">
          <span>
            公演日 <small>任意</small>
          </span>
          <input type="date" value={value.event_date} onChange={set('event_date')} />
        </label>
        <label className="field">
          <span>
            会場 <small>任意</small>
          </span>
          <input type="text" placeholder="例: Zepp Haneda" value={value.venue} onChange={set('venue')} />
        </label>
      </div>

      <label className="field">
        <span>
          公式MVのYouTube URL <small>任意・おすすめ</small>
        </span>
        <input
          type="url"
          inputMode="url"
          placeholder="https://www.youtube.com/watch?v=..."
          value={value.mv_url}
          onChange={set('mv_url')}
        />
        <Status status={urlStatus(value.mv_url, 'mv')} />
        <em className="field-note">公開されている動画のみ解析できます。世界観の読み取りに使います。</em>
      </label>
    </section>
  )
}
