import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import 'models.dart';

/// API の接続先。web は同一オリジン(FastAPI から配信)、
/// それ以外・別ポートの開発サーバーは `--dart-define=API_BASE_URL=http://localhost:8080` で指定する。
const _apiBase = String.fromEnvironment('API_BASE_URL', defaultValue: kIsWeb ? '' : 'http://localhost:8080');

Uri _uri(String path, [Map<String, String>? query]) {
  final base = _apiBase.isEmpty ? Uri.base : Uri.parse(_apiBase);
  return base.replace(path: path, queryParameters: query, fragment: null);
}

/// 入力内容の誤り(422)。メッセージは画面のエラー枠にそのまま出す
class ValidationException implements Exception {
  ValidationException(this.errors);
  final List<String> errors;
}

/// 通信できなかった・サーバーエラー
class ApiException implements Exception {
  ApiException(this.message);
  final String message;
}

List<String> _errors(String body, String fallback) {
  try {
    final errors = (jsonDecode(body) as Map<String, dynamic>)['errors'] as List?;
    if (errors != null && errors.isNotEmpty) return errors.cast<String>();
  } catch (_) {}
  return [fallback];
}

class Api {
  Future<ClientConfig> fetchConfig() async {
    final res = await http.get(_uri('/api/config'));
    if (res.statusCode != 200) throw ApiException('設定の取得に失敗しました');
    return ClientConfig.fromJson(jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>);
  }

  /// キーワード(アーティスト名・公演名など)と詳細検索の条件から公演の候補を探す。
  /// [conditions] のキーは API のクエリ名(artist_name / event_title / genre / venue / event_date)
  Future<EventSearchResult> searchEvents(String keyword, {Map<String, String> conditions = const {}}) async {
    final query = {
      'q': keyword,
      for (final MapEntry(:key, :value) in conditions.entries)
        if (value.trim().isNotEmpty) key: value.trim(),
    };
    final http.Response res;
    try {
      res = await http.get(_uri('/api/events/search', query));
    } catch (_) {
      throw ApiException('サーバーと通信できませんでした。ネットワーク接続を確認してください。');
    }
    final body = utf8.decode(res.bodyBytes);
    if (res.statusCode == 422) throw ValidationException(_errors(body, '検索キーワードを確認してください。'));
    if (res.statusCode != 200) {
      throw ApiException(_errors(body, '公演を検索できませんでした(${res.statusCode})').first);
    }
    return EventSearchResult.fromJson(jsonDecode(body) as Map<String, dynamic>);
  }

  /// 提案 API を呼び出し、NDJSON のメッセージを1行ずつ返す。
  /// [client] を close するとリクエストを中断できる(キャンセル用)。
  Stream<StreamMessage> requestProposal(
    http.Client client,
    EventForm form,
    List<ClosetPhoto> photos,
    bool consent,
  ) async* {
    final req = http.MultipartRequest('POST', _uri('/api/proposals'));
    form.toFields().forEach((key, value) {
      if (value.trim().isNotEmpty) req.fields[key] = value.trim();
    });
    req.fields['consent'] = '$consent';
    for (final p in photos) {
      req.files.add(
        http.MultipartFile.fromBytes('images', p.bytes, filename: p.name, contentType: MediaType.parse(p.mimeType)),
      );
    }

    final res = await client.send(req);
    if (res.statusCode == 422) {
      throw ValidationException(_errors(await res.stream.bytesToString(), '入力内容を確認してください。'));
    }
    if (res.statusCode != 200) throw ApiException('サーバーエラーが発生しました(${res.statusCode})');

    final lines = res.stream.transform(utf8.decoder).transform(const LineSplitter());
    await for (final line in lines) {
      if (line.trim().isEmpty) continue;
      yield StreamMessage.fromJson(jsonDecode(line) as Map<String, dynamic>);
    }
  }
}
