// backend/app/schemas.py の ProposalResult などに対応する型(手で同期する)

import 'dart:typed_data';

List<String> _strings(Object? value) => [for (final v in (value as List?) ?? const []) v as String];

class EventInfo {
  EventInfo.fromJson(Map<String, dynamic> j)
    : artistName = j['artist_name'] as String,
      eventTitle = j['event_title'] as String?,
      eventDate = j['event_date'] as String?,
      venue = j['venue'] as String?,
      genreHint = j['genre_hint'] as String?,
      mvUrl = j['mv_url'] as String?,
      source = j['source'] as String;

  final String artistName;
  final String? eventTitle;
  final String? eventDate;
  final String? venue;
  final String? genreHint;
  final String? mvUrl;

  /// search / manual / search+manual
  final String source;
}

/// キーワード検索で見つかった公演の候補(`EventCandidate`)
class EventCandidate {
  EventCandidate.fromJson(Map<String, dynamic> j)
    : artistName = j['artist_name'] as String,
      eventTitle = j['event_title'] as String?,
      eventDate = j['event_date'] as String?,
      venue = j['venue'] as String?,
      genreHint = j['genre_hint'] as String?,
      mvUrl = j['mv_url'] as String?,
      mvTitle = j['mv_title'] as String?;

  final String artistName;
  final String? eventTitle;
  final String? eventDate;
  final String? venue;
  final String? genreHint;
  final String? mvUrl;
  final String? mvTitle;
}

class SearchSource {
  SearchSource.fromJson(Map<String, dynamic> j) : title = j['title'] as String, url = j['url'] as String;

  final String title;
  final String url;
}

class EventSearchResult {
  EventSearchResult.fromJson(Map<String, dynamic> j)
    : candidates = [for (final c in j['candidates'] as List) EventCandidate.fromJson(c as Map<String, dynamic>)],
      sources = [for (final s in j['sources'] as List) SearchSource.fromJson(s as Map<String, dynamic>)];

  final List<EventCandidate> candidates;
  final List<SearchSource> sources;
}

class CultureInfo {
  CultureInfo.fromJson(Map<String, dynamic> j)
    : genreName = j['genre_name'] as String?,
      explanation = j['explanation'] as String?,
      sourceUrl = j['source_url'] as String?,
      sourceTitle = j['source_title'] as String?,
      covered = j['covered'] as bool;

  final String? genreName;
  final String? explanation;
  final String? sourceUrl;
  final String? sourceTitle;
  final bool covered;
}

class MvStyle {
  MvStyle.fromJson(Map<String, dynamic> j)
    : colorPalette = _strings(j['color_palette']),
      overallVibe = j['overall_vibe'] as String,
      analyzedFrom = j['analyzed_from'] as String;

  final List<String> colorPalette;
  final String overallVibe;

  /// video / thumbnail / none
  final String analyzedFrom;
}

class VenueWeather {
  VenueWeather.fromJson(Map<String, dynamic> j)
    : venueType = (j['venue'] as Map<String, dynamic>)['venue_type'] as String,
      venueNotes = _strings((j['venue'] as Map<String, dynamic>)['notes']),
      season = j['season'] as String?,
      weatherNote = j['weather_note'] as String;

  final String venueType;
  final List<String> venueNotes;
  final String? season;
  final String weatherNote;
}

class CriticResult {
  CriticResult.fromJson(Map<String, dynamic> j)
    : scores = (j['scores'] as Map<String, dynamic>).map((k, v) => MapEntry(k, v as int)),
      passed = j['passed'] as bool,
      iteration = j['iteration'] as int;

  final Map<String, int> scores;
  final bool passed;
  final int iteration;
}

class ProposalItem {
  ProposalItem.fromJson(Map<String, dynamic> j)
    : itemId = j['item_id'] as String,
      name = j['name'] as String,
      category = j['category'] as String,
      imageIndex = j['image_index'] as int;

  final String itemId;
  final String name;
  final String category;
  final int imageIndex;
}

class ProposalResult {
  ProposalResult.fromJson(Map<String, dynamic> j)
    : event = j['event'] == null ? null : EventInfo.fromJson(j['event'] as Map<String, dynamic>),
      outfitTitle = j['outfit_title'] as String?,
      items = [for (final i in j['items'] as List) ProposalItem.fromJson(i as Map<String, dynamic>)],
      stylingTips = _strings(j['styling_tips']),
      reason = j['reason'] as String?,
      missingSuggestions = _strings(j['missing_suggestions']),
      culture = j['culture'] == null ? null : CultureInfo.fromJson(j['culture'] as Map<String, dynamic>),
      mvStyle = j['mv_style'] == null ? null : MvStyle.fromJson(j['mv_style'] as Map<String, dynamic>),
      venueWeather = j['venue_weather'] == null
          ? null
          : VenueWeather.fromJson(j['venue_weather'] as Map<String, dynamic>),
      critic = j['critic'] == null ? null : CriticResult.fromJson(j['critic'] as Map<String, dynamic>),
      imageBase64 = j['image_base64'] as String?,
      imageMimeType = j['image_mime_type'] as String?,
      notes = _strings(j['notes']);

  final EventInfo? event;
  final String? outfitTitle;
  final List<ProposalItem> items;
  final List<String> stylingTips;
  final String? reason;
  final List<String> missingSuggestions;
  final CultureInfo? culture;
  final MvStyle? mvStyle;
  final VenueWeather? venueWeather;
  final CriticResult? critic;
  final String? imageBase64;
  final String? imageMimeType;
  final List<String> notes;
}

/// POST /api/proposals の NDJSON 1行分
sealed class StreamMessage {
  static StreamMessage fromJson(Map<String, dynamic> j) => switch (j['type']) {
    'start' => StartMessage([
      for (final s in j['steps'] as List) (step: s['step'] as String, label: s['label'] as String),
    ]),
    'step' => StepMessage(j['step'] as String, j['label'] as String, passed: j['passed'] as bool?),
    'result' => ResultMessage(ProposalResult.fromJson(j['result'] as Map<String, dynamic>)),
    _ => ErrorMessage(j['message'] as String? ?? '処理中にエラーが発生しました。'),
  };
}

class StartMessage extends StreamMessage {
  StartMessage(this.steps);
  final List<({String step, String label})> steps;
}

class StepMessage extends StreamMessage {
  StepMessage(this.step, this.label, {this.passed});
  final String step;
  final String label;
  final bool? passed;
}

class ResultMessage extends StreamMessage {
  ResultMessage(this.result);
  final ProposalResult result;
}

class ErrorMessage extends StreamMessage {
  ErrorMessage(this.message);
  final String message;
}

class ClientConfig {
  ClientConfig.fromJson(Map<String, dynamic> j)
    : maxImages = j['max_images'] as int,
      maxImageMb = j['max_image_mb'] as int,
      allowedTypes = _strings(j['allowed_types']),
      mock = j['mock'] as bool;

  const ClientConfig.fallback()
    : maxImages = 10,
      maxImageMb = 10,
      allowedTypes = const ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'],
      mock = false;

  final int maxImages;
  final int maxImageMb;
  final List<String> allowedTypes;
  final bool mock;
}

// ---- フロントエンド専用の型(バックエンドとは同期不要) ----

/// 公演情報の入力内容(送信時の Form 項目)
class EventForm {
  String keyword = '';
  String artistName = '';
  String eventTitle = '';
  String genre = '';
  String eventDate = '';
  String venue = '';

  /// 検索結果で選んだ公演の公式MV(URL はユーザーが入力しない)
  String? mvUrl;
  String? mvTitle;
  bool useMv = true;

  bool get hasEvent => keyword.trim().isNotEmpty || artistName.trim().isNotEmpty;

  /// 詳細検索の条件(GET /api/events/search のクエリ)
  Map<String, String> get searchConditions => {
    'artist_name': artistName,
    'event_title': eventTitle,
    'genre': genre,
    'venue': venue,
    'event_date': eventDate,
  };

  /// 詳細検索に入力済みの項目数
  int get detailCount => searchConditions.values.where((v) => v.trim().isNotEmpty).length;

  Map<String, String> toFields() => {
    'keyword': keyword,
    'artist_name': artistName,
    'event_title': eventTitle,
    'genre': genre,
    'event_date': eventDate,
    'venue': venue,
    if (useMv && mvUrl != null) 'mv_url': mvUrl!,
  };
}

/// 入力画面で追加した手持ち服の写真(縮小済みで、そのまま送信する)
class ClosetPhoto {
  ClosetPhoto({required this.id, required this.name, required this.mimeType, required this.bytes});

  final String id;
  final String name;
  final String mimeType;
  final Uint8List bytes;

  /// 重複追加の判定用
  String get key => '$name:${bytes.length}';
}
