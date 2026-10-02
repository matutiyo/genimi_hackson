import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';

import '../models.dart';
import '../theme.dart';
import '../widgets/photo_thumb.dart';

class StepState {
  const StepState(this.step, this.label, {this.done = false});
  final String step;
  final String label;
  final bool done;

  StepState copyWith({required bool done}) => StepState(step, label, done: done);
}

/// sending: サーバー応答待ち / running: 解析中 / done: 結果受信済み(完成演出中)
enum ProgressStatus { sending, running, done }

class ProgressState {
  ProgressState({
    this.status = ProgressStatus.sending,
    this.steps = const [],
    this.retries = 0,
    DateTime? startedAt,
    DateTime? lastUpdateAt,
  }) : startedAt = startedAt ?? DateTime.now(),
       lastUpdateAt = lastUpdateAt ?? DateTime.now();

  final ProgressStatus status;
  final List<StepState> steps;

  /// Critic 不合格による再生成の回数
  final int retries;
  final DateTime startedAt;

  /// 最後に進捗が動いた時刻(バーを滑らかに進めるのに使う)
  final DateTime lastUpdateAt;

  ProgressState copyWith({ProgressStatus? status, List<StepState>? steps, int? retries}) => ProgressState(
    status: status ?? this.status,
    steps: steps ?? this.steps,
    retries: retries ?? this.retries,
    startedAt: startedAt,
    lastUpdateAt: DateTime.now(),
  );

  /// 進捗メッセージを反映する
  ProgressState apply(StreamMessage msg) {
    switch (msg) {
      case StartMessage(:final steps):
        return copyWith(status: ProgressStatus.running, steps: [for (final s in steps) StepState(s.step, s.label)]);
      case StepMessage(step: 'critic', passed: false):
        // 不合格 → LoopAgent で再生成するので、生成・評価を未完了に戻す
        return copyWith(
          retries: retries + 1,
          steps: [
            for (final s in steps) s.step == 'outfit_generator' || s.step == 'critic' ? s.copyWith(done: false) : s,
          ],
        );
      case StepMessage(:final step):
        // 直列の段階が完了したら、それより前のステップもすべて完了扱いにする
        // (再生成上限で Critic 不合格のまま画像生成に進んだ場合など)
        final index = steps.indexWhere((s) => s.step == step);
        final sequential = !_parallelSteps.contains(step);
        return copyWith(
          steps: [
            for (final (i, s) in steps.indexed) i == index || (sequential && i < index) ? s.copyWith(done: true) : s,
          ],
        );
      case ResultMessage():
        return copyWith(status: ProgressStatus.done, steps: [for (final s in steps) s.copyWith(done: true)]);
      case ErrorMessage():
        return this;
    }
  }
}

/// 処理フロー(pipeline.py)の段階。ParallelAgent 配下は同じ段階にまとめて表示する
const _stages = [
  (id: 'event', title: '公演情報', active: '公演情報を確認しています', steps: ['event_parser']),
  (
    id: 'analyze',
    title: 'ライブの雰囲気と手持ち服を解析',
    active: 'カルチャー・MV・会場・手持ち服を同時に解析しています',
    steps: ['culture', 'mv_analyzer', 'venue_weather', 'closet_analyzer'],
  ),
  (id: 'integrate', title: 'スタイルの方向性を決定', active: 'スタイルの方向性をまとめています', steps: ['style_integrator']),
  (
    id: 'outfit',
    title: 'コーデを組んでセルフチェック',
    active: '手持ち服からコーデを組み、AIがセルフチェックしています',
    steps: ['outfit_generator', 'critic'],
  ),
  (id: 'image', title: 'コーデ画像を作成', active: '完成イメージ画像を作っています', steps: ['image_generator']),
];

/// ParallelAgent 配下のステップ(完了順が前後する)
final _parallelSteps = _stages[1].steps;

const _tips = [
  'スタンディング公演では、両手が空くショルダーバッグやサコッシュが便利です。',
  '会場内は冬でも暑くなりがち。脱ぎ着しやすい重ね着がおすすめです。',
  '厚底やヒールは長時間立つと疲れやすく、周りの足を踏む心配も。スニーカーが安心です。',
  'グッズのTシャツやタオルを会場で買って、その場で合わせるのも定番の楽しみ方です。',
  'アーティストの公式MVやアー写の色味をひとつ取り入れると、ぐっと「それっぽく」なります。',
  'コインロッカーは開演前に埋まりがち。荷物は少なめにしておくと動きやすいです。',
  '帽子や大きな髪飾りは後ろの人の視界をさえぎることがあるので、会場では外すのがマナーです。',
];

typedef _Stage = ({String id, String title, String active, List<StepState> steps});

List<_Stage> _buildStages(List<StepState> steps) {
  final byId = {for (final s in steps) s.step: s};
  final used = <String>{};
  final stages = <_Stage>[];
  for (final def in _stages) {
    final found = [for (final id in def.steps) ?byId[id]];
    used.addAll(found.map((s) => s.step));
    if (found.isNotEmpty) stages.add((id: def.id, title: def.title, active: def.active, steps: found));
  }
  // 未知のステップ(バックエンド側で追加された場合)は単独の段階として末尾に出す
  for (final s in steps) {
    if (!used.contains(s.step)) stages.add((id: s.step, title: s.label, active: '${s.label}中', steps: [s]));
  }
  return stages;
}

String _formatElapsed(int sec) => sec >= 60 ? '${sec ~/ 60}分${(sec % 60).toString().padLeft(2, '0')}秒' : '$sec秒';

/// F04 進捗表示(ロード/待機画面)
class ProgressView extends StatefulWidget {
  const ProgressView({super.key, required this.progress, required this.photos, required this.onCancel});

  final ProgressState progress;
  final List<ClosetPhoto> photos;
  final VoidCallback onCancel;

  @override
  State<ProgressView> createState() => _ProgressViewState();
}

class _ProgressViewState extends State<ProgressView> {
  late final Timer _timer;
  DateTime _now = DateTime.now();

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(milliseconds: 250), (_) => setState(() => _now = DateTime.now()));
  }

  @override
  void dispose() {
    _timer.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.progress;
    final stages = _buildStages(p.steps);
    final activeIndex = stages.indexWhere((st) => st.steps.any((s) => !s.done));
    final activeStage = activeIndex >= 0 ? stages[activeIndex] : null;
    final elapsed = max(0, _now.difference(p.startedAt).inSeconds);
    final tip = _tips[(elapsed ~/ 8) % _tips.length];
    final done = p.status == ProgressStatus.done;

    // 完了ステップ数 + 処理中ステップの経過時間に応じた「じわじわ進む」分
    final total = max(1, p.steps.length);
    final doneCount = p.steps.where((s) => s.done).length;
    final sinceUpdate = _now.difference(p.lastUpdateAt).inMilliseconds / 1000;
    final creep = p.status == ProgressStatus.running && activeStage != null ? 0.85 * (1 - exp(-sinceUpdate / 12)) : 0.0;
    final percent = switch (p.status) {
      ProgressStatus.done => 100.0,
      ProgressStatus.sending => min(4.0, sinceUpdate),
      ProgressStatus.running => min(99.0, (doneCount + creep) / total * 100),
    };

    final headline = switch (p.status) {
      ProgressStatus.done => 'コーディネートができました!',
      ProgressStatus.sending => '写真と公演情報を送信しています',
      _ when p.retries > 0 && activeStage?.id == 'outfit' => 'セルフチェックの結果を受けて、組み合わせを見直しています',
      _ => activeStage?.active ?? '仕上げをしています',
    };

    final closet = p.steps.where((s) => s.step == 'closet_analyzer').firstOrNull;
    final scanned = done || (closet?.done ?? false);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SectionCard(
          children: [
            SizedBox(
              height: 64,
              child: done ? const Icon(Icons.check_circle, color: AppColors.ok, size: 56) : const _Equalizer(),
            ),
            const SizedBox(height: 12),
            Semantics(
              liveRegion: true,
              child: Text(
                headline,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
              ),
            ),
            const SizedBox(height: 16),
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: LinearProgressIndicator(
                value: percent / 100,
                minHeight: 10,
                backgroundColor: AppColors.soft,
                semanticsLabel: '全体の進み具合',
              ),
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                Text('${percent.round()}%', style: const TextStyle(fontWeight: FontWeight.bold)),
                const Spacer(),
                Hint('経過 ${_formatElapsed(elapsed)}${done ? '' : ' ・ 目安 1〜2分'}'),
              ],
            ),
            if (!done) ...[const SizedBox(height: 8), const Hint('完了まで、この画面を開いたままお待ちください')],
            if (elapsed >= 150 && !done) ...[
              const SizedBox(height: 8),
              const Text('いつもより時間がかかっています。画面を閉じずにそのままお待ちください。', style: TextStyle(color: AppColors.ng)),
            ],
            if (widget.photos.isNotEmpty) ...[
              const SizedBox(height: 16),
              Row(
                children: [
                  if (scanned) const Icon(Icons.check, size: 16, color: AppColors.ok),
                  Text(scanned ? ' 手持ち服 ${widget.photos.length}枚の解析が完了' : '手持ち服 ${widget.photos.length}枚を読み取り中'),
                ],
              ),
              const SizedBox(height: 8),
              SizedBox(
                height: 48,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: widget.photos.length,
                  separatorBuilder: (_, _) => const SizedBox(width: 6),
                  itemBuilder: (_, i) => AnimatedOpacity(
                    duration: const Duration(milliseconds: 400),
                    opacity: scanned ? 1 : (0.45 + 0.55 * ((elapsed * 4 + _now.millisecond ~/ 250 + i) % 4) / 3),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(6),
                      child: PhotoThumb(photo: widget.photos[i], number: i + 1, size: 48),
                    ),
                  ),
                ),
              ),
            ],
            const SizedBox(height: 16),
            if (p.status == ProgressStatus.sending) const _StageRow(index: 0, title: '送信・準備', state: _RowState.active),
            for (final (i, st) in stages.indexed)
              _StageRow(
                index: i,
                title: st.title,
                badge: st.id == 'outfit' && p.retries > 0 ? '見直し ${p.retries}回' : null,
                state: st.steps.every((s) => s.done)
                    ? _RowState.done
                    : p.status == ProgressStatus.running && i == activeIndex
                    ? _RowState.active
                    : _RowState.pending,
                substeps: st.steps.length > 1 ? st.steps : null,
              ),
          ],
        ),
        if (!done) ...[
          SectionCard(
            children: [
              const Text(
                'ライブ服の豆知識',
                style: TextStyle(color: AppColors.accent2, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 4),
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 400),
                child: Text(tip, key: ValueKey(tip)),
              ),
            ],
          ),
          Center(
            child: OutlinedButton(onPressed: widget.onCancel, child: const Text('キャンセルして入力に戻る')),
          ),
        ],
      ],
    );
  }
}

enum _RowState { done, active, pending }

class _StageRow extends StatelessWidget {
  const _StageRow({required this.index, required this.title, required this.state, this.badge, this.substeps});

  final int index;
  final String title;
  final _RowState state;
  final String? badge;
  final List<StepState>? substeps;

  @override
  Widget build(BuildContext context) {
    final icon = switch (state) {
      _RowState.done => const Icon(Icons.check_circle, color: AppColors.ok, size: 24),
      _RowState.active => const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2.5)),
      _RowState.pending => CircleAvatar(
        radius: 12,
        backgroundColor: AppColors.soft,
        child: Text('${index + 1}', style: const TextStyle(fontSize: 12, color: AppColors.muted)),
      ),
    };
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 28, child: Center(child: icon)),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: 8,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        fontWeight: state == _RowState.active ? FontWeight.bold : FontWeight.normal,
                        color: state == _RowState.pending ? AppColors.muted : AppColors.text,
                      ),
                    ),
                    if (badge != null) Text(badge!, style: const TextStyle(color: AppColors.accent2, fontSize: 12)),
                  ],
                ),
                for (final s in substeps ?? const <StepState>[])
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Row(
                      children: [
                        if (s.done)
                          const Icon(Icons.check, size: 14, color: AppColors.ok)
                        else if (state == _RowState.active)
                          const SizedBox.square(dimension: 12, child: CircularProgressIndicator(strokeWidth: 1.5))
                        else
                          const Icon(Icons.circle, size: 6, color: AppColors.border),
                        const SizedBox(width: 6),
                        Text(s.label, style: const TextStyle(fontSize: 13, color: AppColors.muted)),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// 処理中の演出(イコライザー風のバー)
class _Equalizer extends StatefulWidget {
  const _Equalizer();

  @override
  State<_Equalizer> createState() => _EqualizerState();
}

class _EqualizerState extends State<_Equalizer> with SingleTickerProviderStateMixin {
  late final _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 1400))..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (_, _) => Row(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          for (var i = 0; i < 7; i++)
            Container(
              width: 8,
              margin: const EdgeInsets.symmetric(horizontal: 3),
              height: 14 + 46 * (0.5 + 0.5 * sin(2 * pi * _controller.value + i * 1.37)).abs(),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [AppColors.accent, AppColors.accent2],
                  begin: Alignment.bottomCenter,
                  end: Alignment.topCenter,
                ),
                borderRadius: BorderRadius.circular(4),
              ),
            ),
        ],
      ),
    );
  }
}
