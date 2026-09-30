import { useState } from 'react'
import type { ClosetPhoto, ProposalResult } from '../types'

interface Props {
  result: ProposalResult
  photos: ClosetPhoto[]
  onRestart: () => void
}

const CATEGORY_LABEL: Record<string, string> = {
  tops: 'トップス',
  outer: 'アウター',
  bottoms: 'ボトムス',
  onepiece: 'ワンピース',
  shoes: '靴',
  bag: 'バッグ',
  accessory: 'アクセサリー',
  headwear: '帽子',
  other: 'その他',
}

const VENUE_LABEL: Record<string, string> = {
  standing: 'オールスタンディング',
  seated: '着席',
  outdoor: '野外',
  mixed: 'スタンディング/着席混在',
  unknown: '不明',
}

const SCORE_LABEL: Record<string, string> = {
  color_match: '色調の一致',
  silhouette_match: 'シルエット',
  practicality: '会場・天候への適合',
  blend_in: '浮かず埋もれない',
}

/** P14 最終結果の表示(コーデ画像・選定理由・カルチャー解説・注意事項) */
export function ResultView({ result, photos, onRestart }: Props) {
  const [zoomed, setZoomed] = useState(false)

  const { event, culture, mv_style: mv, venue_weather: vw, critic } = result
  const imageSrc =
    result.image_base64 && result.image_mime_type
      ? `data:${result.image_mime_type};base64,${result.image_base64}`
      : null

  return (
    <div className="result">
      <section className="card hero">
        <p className="eyebrow">
          {event?.artist_name}
          {event?.event_title && ` / ${event.event_title}`}
          {event?.event_date && ` ・ ${event.event_date}`}
          {event?.venue && ` ・ ${event.venue}`}
        </p>
        <h2 className="outfit-title">{result.outfit_title ?? 'コーディネート提案'}</h2>

        <div className="hero-body">
          <div className="hero-image">
            {imageSrc ? (
              <>
                {/* img を button で包むと iOS で長押し保存できないため、画像そのものをクリック対象にする */}
                <div className={`hero-zoom ${zoomed ? 'is-zoomed' : ''}`} onClick={() => setZoomed((z) => !z)}>
                  <img src={imageSrc} alt="提案コーディネートのイメージ画像" />
                </div>
                <a className="save-link" href={imageSrc} download={`live-outfit.${result.image_mime_type?.split('/')[1] ?? 'png'}`}>
                  画像を保存
                </a>
                <button type="button" className="ghost zoom-button" onClick={() => setZoomed(true)}>
                  拡大して見る
                </button>
                <p className="hint save-hint">スマホは画像を長押しすると写真に保存できます</p>
              </>
            ) : (
              <div className="no-image">画像は生成できませんでした</div>
            )}
          </div>
          <div>
            <h3>使うアイテム</h3>
            <ul className="items">
              {result.items.map((item) => (
                <li key={item.item_id}>
                  {photos[item.image_index]?.previewUrl ? (
                    <img src={photos[item.image_index].previewUrl!} alt="" />
                  ) : (
                    <span className="item-no" aria-hidden>
                      {item.image_index + 1}
                    </span>
                  )}
                  <div>
                    <small>{CATEGORY_LABEL[item.category] ?? item.category}</small>
                    <span>{item.name}</span>
                  </div>
                </li>
              ))}
            </ul>
            {result.missing_suggestions.length > 0 && (
              <p className="suggest">
                <strong>足すならこれ:</strong> {result.missing_suggestions.join('、')}
              </p>
            )}
          </div>
        </div>
      </section>

      <section className="card">
        <h3>このコーデを選んだ理由</h3>
        <p>{result.reason}</p>
        {result.styling_tips.length > 0 && (
          <>
            <h4>着こなしのコツ</h4>
            <ul className="bullets">
              {result.styling_tips.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </>
        )}
      </section>

      <div className="grid-2 gap">
        {culture?.covered && (
          <section className="card">
            <h3>{culture.genre_name}系ライブのファッション文化</h3>
            <p>{culture.explanation}</p>
            {culture.source_url && (
              <p className="source">
                出典:{' '}
                <a href={culture.source_url} target="_blank" rel="noreferrer">
                  {culture.source_title ?? culture.source_url}
                </a>
              </p>
            )}
          </section>
        )}

        {mv && mv.analyzed_from !== 'none' && (
          <section className="card">
            <h3>公式MVから読み取った世界観</h3>
            <p>{mv.overall_vibe}</p>
            <div className="chips">
              {mv.color_palette.map((c) => (
                <span key={c} className="chip">
                  {c}
                </span>
              ))}
            </div>
            {mv.analyzed_from === 'thumbnail' && <p className="hint">※サムネイル画像からの推定です</p>}
          </section>
        )}

        {vw && (
          <section className="card">
            <h3>会場・季節のポイント</h3>
            <dl className="facts">
              <dt>会場形態</dt>
              <dd>{VENUE_LABEL[vw.venue.venue_type] ?? vw.venue.venue_type}</dd>
              {vw.season && (
                <>
                  <dt>季節</dt>
                  <dd>{vw.season}</dd>
                </>
              )}
            </dl>
            {vw.weather_note && <p>{vw.weather_note}</p>}
            {vw.venue.notes.length > 0 && (
              <ul className="bullets">
                {vw.venue.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            )}
          </section>
        )}

        {critic && (
          <section className="card">
            <h3>
              AIセルフチェック{' '}
              <span className={`badge ${critic.passed ? 'ok' : 'ng'}`}>{critic.passed ? '合格' : '要注意'}</span>
            </h3>
            <ul className="scores">
              {Object.entries(critic.scores).map(([k, v]) => (
                <li key={k}>
                  <span>{SCORE_LABEL[k] ?? k}</span>
                  <meter min={1} max={5} low={2.9} high={3.9} optimum={5} value={v} />
                  <b>{v}</b>
                </li>
              ))}
            </ul>
            {critic.iteration > 1 && <p className="hint">1回目の評価を受けて、組み合わせを見直しています。</p>}
          </section>
        )}
      </div>

      {result.notes.length > 0 && (
        <section className="card notes">
          <h3>注意事項</h3>
          <ul className="bullets">
            {result.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </section>
      )}

      <div className="actions">
        <button type="button" className="secondary" onClick={onRestart}>
          条件を変えてもう一度
        </button>
      </div>
    </div>
  )
}
