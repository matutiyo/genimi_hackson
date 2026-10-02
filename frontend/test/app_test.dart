import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:live_outfit/api.dart';
import 'package:live_outfit/main.dart';
import 'package:live_outfit/models.dart';
import 'package:live_outfit/screens/progress_view.dart';

/// API を呼ばずに固定の応答を返す
class FakeApi extends Api {
  final searched = <String>[];
  EventForm? submitted;

  @override
  Future<ClientConfig> fetchConfig() async => const ClientConfig.fallback();

  @override
  Future<EventSearchResult> searchEvents(String keyword) async {
    searched.add(keyword);
    return EventSearchResult.fromJson({
      'candidates': [
        {
          'artist_name': 'モックバンド',
          'event_title': 'MOCK TOUR 2026',
          'event_date': '2026-12-05',
          'venue': 'Zepp Haneda',
          'genre_hint': 'パンク',
          'mv_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
          'mv_title': 'モックバンド - Official MV',
        },
      ],
      'sources': [
        {'title': '公式サイト', 'url': 'https://example.com'},
      ],
    });
  }

  @override
  Stream<StreamMessage> requestProposal(http.Client client, EventForm form, List<ClosetPhoto> photos, bool consent) {
    submitted = form;
    return const Stream.empty();
  }
}

Future<FakeApi> _pumpApp(WidgetTester tester) async {
  tester.view.physicalSize = const Size(400, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final api = FakeApi();
  await tester.pumpWidget(LiveOutfitApp(api: api));
  await tester.pumpAndSettle();
  return api;
}

void main() {
  testWidgets('キーワード検索で候補を選ぶと公演情報が入る', (tester) async {
    final api = await _pumpApp(tester);

    // URL の入力欄は無い
    expect(find.textContaining('URL'), findsNothing);

    await tester.enterText(find.widgetWithText(TextField, '検索キーワード'), 'モックバンド');
    await tester.tap(find.widgetWithText(FilledButton, '検索'));
    await tester.pumpAndSettle();
    expect(api.searched, ['モックバンド']);
    expect(find.textContaining('見つかった公演(1件)'), findsOneWidget);

    await tester.tap(find.text('モックバンド / MOCK TOUR 2026'));
    await tester.pumpAndSettle();
    expect(find.text('公式MVの雰囲気も参考にする'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Zepp Haneda'), findsOneWidget);
    expect(find.widgetWithText(TextField, '2026-12-05'), findsOneWidget);
  });

  testWidgets('未入力で送信すると不足項目を表示する', (tester) async {
    final api = await _pumpApp(tester);

    await tester.tap(find.text('コーディネートを提案してもらう'));
    await tester.pumpAndSettle();
    expect(find.text('入力内容を確認してください'), findsOneWidget);
    expect(find.textContaining('検索キーワードまたはアーティスト名'), findsOneWidget);
    expect(find.textContaining('画像を1枚以上'), findsOneWidget);
    expect(api.submitted, isNull);

    // 入力すると該当のエラーは消える
    await tester.enterText(find.widgetWithText(TextField, '検索キーワード'), 'モックバンド');
    await tester.pumpAndSettle();
    expect(find.textContaining('検索キーワードまたはアーティスト名'), findsNothing);
  });

  test('送信内容: MV は検索結果のものだけ、使わない設定なら送らない', () {
    final form = EventForm()
      ..keyword = 'モックバンド'
      ..mvUrl = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ';
    expect(form.toFields()['mv_url'], isNotNull);
    form.useMv = false;
    expect(form.toFields().containsKey('mv_url'), isFalse);
    expect(form.toFields().containsKey('event_url'), isFalse);
  });

  test('進捗: Critic 不合格で生成・評価を未完了に戻し、直列ステップは前を完了扱いにする', () {
    var p = ProgressState().apply(
      StartMessage([
        (step: 'event_parser', label: 'a'),
        (step: 'culture', label: 'b'),
        (step: 'closet_analyzer', label: 'c'),
        (step: 'style_integrator', label: 'd'),
        (step: 'outfit_generator', label: 'e'),
        (step: 'critic', label: 'f'),
        (step: 'image_generator', label: 'g'),
      ]),
    );
    expect(p.status, ProgressStatus.running);
    p = p.apply(StepMessage('culture', 'b'));
    expect(p.steps.where((s) => s.done).map((s) => s.step), ['culture']);
    p = p.apply(StepMessage('critic', 'f'));
    expect(p.steps.where((s) => !s.done).map((s) => s.step), ['image_generator']);
    p = p.apply(StepMessage('critic', 'f', passed: false));
    expect(p.retries, 1);
    expect(p.steps.where((s) => !s.done).map((s) => s.step), ['outfit_generator', 'critic', 'image_generator']);
  });

  test('ClosetPhoto の重複判定キー', () {
    final a = ClosetPhoto(id: '1', name: 'a.jpg', mimeType: 'image/jpeg', bytes: Uint8List(10));
    final b = ClosetPhoto(id: '2', name: 'a.jpg', mimeType: 'image/jpeg', bytes: Uint8List(10));
    expect(a.key, b.key);
  });
}
