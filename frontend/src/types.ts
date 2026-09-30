// backend/app/schemas.py の ProposalResult などに対応する型

export interface EventInfo {
  artist_name: string
  event_title: string | null
  event_date: string | null
  venue: string | null
  genre_hint: string | null
  mv_url: string | null
  source: 'url' | 'manual' | 'url+manual'
}

export interface CultureInfo {
  genre_id: string | null
  genre_name: string | null
  explanation: string | null
  keywords: string[]
  source_url: string | null
  source_title: string | null
  covered: boolean
}

export interface MvStyle {
  color_palette: string[]
  lighting_mood: string
  fashion_items: string[]
  silhouettes: string[]
  overall_vibe: string
  analyzed_from: 'video' | 'thumbnail' | 'none'
}

export interface VenueWeather {
  venue: { venue_type: string; capacity_note: string; notes: string[] }
  season: string | null
  weather_note: string
  weather_source: string
}

export interface CriticResult {
  scores: { color_match: number; silhouette_match: number; practicality: number; blend_in: number }
  issues: string[]
  revision_instruction: string
  passed: boolean
  rule_violations: string[]
  iteration: number
}

export interface ProposalItem {
  item_id: string
  name: string
  category: string
  image_index: number
}

export interface ProposalResult {
  event: EventInfo | null
  outfit_title: string | null
  items: ProposalItem[]
  styling_tips: string[]
  reason: string | null
  missing_suggestions: string[]
  culture: CultureInfo | null
  mv_style: MvStyle | null
  venue_weather: VenueWeather | null
  critic: CriticResult | null
  image_base64: string | null
  image_mime_type: string | null
  notes: string[]
}

export type StreamMessage =
  | { type: 'start'; steps: { step: string; label: string }[] }
  | { type: 'step'; step: string; label: string; passed?: boolean; iteration?: number }
  | { type: 'result'; result: ProposalResult }
  | { type: 'error'; message: string }

export interface EventForm {
  event_url: string
  artist_name: string
  genre: string
  event_date: string
  venue: string
  mv_url: string
}

export interface ClientConfig {
  max_images: number
  max_image_mb: number
  allowed_types: string[]
  mock: boolean
}

// ---- フロントエンド専用の型(バックエンドとは同期不要) ----

/** 入力画面で追加した手持ち服の写真(file は縮小済みで、そのまま送信する) */
export interface ClosetPhoto {
  id: string
  file: File
  /** 重複追加の判定用(縮小前のファイル名・サイズ) */
  sourceKey: string
  /** ブラウザで表示できない形式(HEIC など)は null */
  previewUrl: string | null
  originalSize: number
}
