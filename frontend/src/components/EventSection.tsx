import type { EventForm } from '../types'

interface Props {
  value: EventForm
  onChange: (value: EventForm) => void
}

/** P01 公演情報の入力(URL または手動入力) */
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
        <em className="field-note">公開されている動画のみ解析できます。世界観の読み取りに使います。</em>
      </label>
    </section>
  )
}
