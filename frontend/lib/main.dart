import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:http/http.dart' as http;
import 'package:wakelock_plus/wakelock_plus.dart';

import 'api.dart';
import 'models.dart';
import 'screens/progress_view.dart';
import 'screens/result_view.dart';
import 'theme.dart';
import 'widgets/closet_section.dart';
import 'widgets/event_search_section.dart';

void main() => runApp(const LiveOutfitApp());

class LiveOutfitApp extends StatelessWidget {
  const LiveOutfitApp({super.key, this.api});

  /// テストで差し替える
  final Api? api;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'はじめてのライブ服',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      locale: const Locale('ja'),
      supportedLocales: const [Locale('ja')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      home: HomePage(api: api ?? Api()),
    );
  }
}

enum Phase { input, running, result }

const _phases = [(Phase.input, '入力'), (Phase.running, 'AIが考え中'), (Phase.result, '提案')];

/// 結果受信後に「できました」を見せてから結果画面に切り替えるまでの時間
const _donePause = Duration(milliseconds: 900);

class HomePage extends StatefulWidget {
  const HomePage({super.key, required this.api});
  final Api api;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  ClientConfig _config = const ClientConfig.fallback();
  Phase _phase = Phase.input;
  final EventForm _form = EventForm();
  List<ClosetPhoto> _photos = [];
  bool _consent = false;

  /// サーバー・通信のエラー(入力チェックのエラーは _checklist から都度計算する)
  List<String> _errors = [];

  /// 一度送信を試みたら、未入力項目をリアルタイムに表示する
  bool _attempted = false;
  String? _notice;
  ProgressState _progress = ProgressState();
  ProposalResult? _result;
  http.Client? _client;
  final _scroll = ScrollController();

  /// 処理中にアプリが裏に回ったか(通信が切れたときの説明に使う)
  bool _wentBackground = false;
  late final AppLifecycleListener _lifecycle = AppLifecycleListener(onHide: () => _wentBackground = true);

  @override
  void initState() {
    super.initState();
    _lifecycle; // 生成して監視を始める
    widget.api.fetchConfig().then((c) => mounted ? setState(() => _config = c) : null).catchError((_) {});
  }

  @override
  void dispose() {
    _lifecycle.dispose();
    _client?.close();
    _scroll.dispose();
    super.dispose();
  }

  List<({bool ok, String label, String error})> get _checklist => [
    (ok: _form.hasEvent, label: 'キーワード or アーティスト名', error: '検索キーワードまたはアーティスト名のどちらかを入力してください。'),
    (
      ok: _photos.isNotEmpty,
      label: '服の写真${_photos.isEmpty ? '' : '(${_photos.length}枚)'}',
      error: '手持ち服の画像を1枚以上追加してください。',
    ),
    (ok: _consent, label: '画像利用への同意', error: '画像の利用について同意してください。'),
  ];

  void _setPhase(Phase phase) {
    setState(() => _phase = phase);
    if (_scroll.hasClients) {
      _scroll.animateTo(0, duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
    }
  }

  Future<void> _submit() async {
    setState(() {
      _notice = null;
      _attempted = true;
      _errors = [];
    });
    if (!_checklist.every((c) => c.ok)) {
      _scroll.animateTo(0, duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
      return;
    }

    _progress = ProgressState();
    _setPhase(Phase.running);
    final client = _client = http.Client();
    // スマホは画面ロックやアプリ切替で通信が切れやすいので、処理中はスリープを防ぐ
    unawaited(WakelockPlus.enable().catchError((_) {}));
    _wentBackground = false;
    try {
      await for (final msg in widget.api.requestProposal(client, _form, _photos, _consent)) {
        if (!mounted || _client != client) return;
        setState(() => _progress = _progress.apply(msg));
        switch (msg) {
          case ResultMessage(:final result):
            await Future<void>.delayed(_donePause);
            if (!mounted || _client != client) return;
            _result = result;
            _setPhase(Phase.result);
          case ErrorMessage(:final message):
            _showErrors([message]);
          default:
        }
      }
    } on ValidationException catch (e) {
      if (_client == client) _showErrors(e.errors);
    } catch (_) {
      if (_client != client) return; // キャンセル済み
      _showErrors([
        _wentBackground
            ? '処理中に画面が閉じられた(または別のアプリに切り替えた)ため、通信が途切れました。画面を開いたまま、もう一度お試しください。'
            : 'サーバーと通信できませんでした。ネットワーク接続を確認して、もう一度お試しください。',
      ]);
    } finally {
      client.close();
      if (_client == client) _client = null;
      unawaited(WakelockPlus.disable().catchError((_) {}));
    }
  }

  void _showErrors(List<String> errors) {
    _errors = errors;
    _setPhase(Phase.input);
  }

  void _cancel() {
    _client?.close();
    _client = null;
    _notice = '提案をキャンセルしました。入力内容はそのまま残っています。';
    _setPhase(Phase.input);
  }

  @override
  Widget build(BuildContext context) {
    final items = _checklist;
    final shownErrors = [if (_attempted) ...items.where((c) => !c.ok).map((c) => c.error), ..._errors];

    final body = switch (_phase) {
      Phase.input => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_notice != null) _MessageBox(color: AppColors.ok, children: [Text(_notice!)]),
          if (shownErrors.isNotEmpty)
            _MessageBox(
              color: AppColors.accent,
              children: [
                const Text('入力内容を確認してください', style: TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(height: 4),
                Bullets(shownErrors),
              ],
            ),
          EventSearchSection(form: _form, api: widget.api, onChanged: () => setState(() {})),
          ClosetSection(
            photos: _photos,
            config: _config,
            consent: _consent,
            onPhotosChanged: (p) => setState(() => _photos = p),
            onConsentChanged: (v) => setState(() => _consent = v),
          ),
        ],
      ),
      Phase.running => ProgressView(progress: _progress, photos: _photos, onCancel: _cancel),
      Phase.result => ResultView(
        result: _result!,
        photos: _photos,
        onRestart: () {
          _errors = [];
          _notice = null;
          _setPhase(Phase.input);
        },
      ),
    };

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: SingleChildScrollView(
          controller: _scroll,
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 880),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _Header(phase: _phase, mock: _config.mock),
                  const SizedBox(height: 16),
                  body,
                ],
              ),
            ),
          ),
        ),
      ),
      bottomNavigationBar: _phase == Phase.input ? _SubmitBar(items: items, onSubmit: _submit) : null,
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.phase, required this.mock});
  final Phase phase;
  final bool mock;

  @override
  Widget build(BuildContext context) {
    final current = _phases.indexWhere((p) => p.$1 == phase);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(
              width: 44,
              height: 44,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(12),
                gradient: const LinearGradient(colors: [AppColors.accent, AppColors.accent2]),
              ),
              child: const Text('♪', style: TextStyle(color: Colors.white, fontSize: 22)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'はじめてのライブ服',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const Hint('行くライブと手持ちの服から、会場で浮かないコーディネートを提案します。'),
                ],
              ),
            ),
          ],
        ),
        if (mock) ...[const SizedBox(height: 8), const Pill('モックモード(Gemini未接続)')],
        const SizedBox(height: 12),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            for (final (i, (_, label)) in _phases.indexed)
              Semantics(
                selected: i == current,
                child: Pill(
                  '${i + 1} $label',
                  color: i == current ? AppColors.accent : (i < current ? AppColors.soft : Colors.white),
                  textColor: i == current ? Colors.white : AppColors.muted,
                  bold: i == current,
                ),
              ),
          ],
        ),
      ],
    );
  }
}

class _MessageBox extends StatelessWidget {
  const _MessageBox({required this.color, required this.children});
  final Color color;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Container(
    margin: const EdgeInsets.only(bottom: 16),
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: color.withValues(alpha: 0.08),
      border: Border.all(color: color.withValues(alpha: 0.5)),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Semantics(
      liveRegion: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
    ),
  );
}

/// 画面下に固定する送信バー(送信前チェックリスト付き)
class _SubmitBar extends StatelessWidget {
  const _SubmitBar({required this.items, required this.onSubmit});
  final List<({bool ok, String label, String error})> items;
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) {
    final ready = items.every((c) => c.ok);
    return Material(
      elevation: 8,
      color: Colors.white,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
          child: Center(
            heightFactor: 1, // 縦に広がって画面全体を覆わないようにする
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 880),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Wrap(
                    spacing: 12,
                    runSpacing: 4,
                    children: [
                      for (final c in items)
                        Semantics(
                          label: '${c.label}${c.ok ? '(OK)' : '(未入力)'}',
                          excludeSemantics: true,
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                c.ok ? Icons.check_circle : Icons.radio_button_unchecked,
                                size: 16,
                                color: c.ok ? AppColors.ok : AppColors.border,
                              ),
                              const SizedBox(width: 4),
                              Text(
                                c.label,
                                style: TextStyle(fontSize: 13, color: c.ok ? AppColors.text : AppColors.muted),
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  FilledButton(
                    style: ready
                        ? null
                        : FilledButton.styleFrom(backgroundColor: AppColors.accent.withValues(alpha: 0.55)),
                    onPressed: onSubmit,
                    child: const Text('コーディネートを提案してもらう'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
