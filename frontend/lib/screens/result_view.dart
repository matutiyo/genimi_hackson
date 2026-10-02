import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models.dart';
import '../save_image.dart';
import '../theme.dart';
import '../widgets/photo_thumb.dart';

const _categoryLabel = {
  'tops': 'トップス',
  'outer': 'アウター',
  'bottoms': 'ボトムス',
  'onepiece': 'ワンピース',
  'shoes': '靴',
  'bag': 'バッグ',
  'accessory': 'アクセサリー',
  'headwear': '帽子',
  'other': 'その他',
};

const _venueLabel = {
  'standing': 'オールスタンディング',
  'seated': '着席',
  'outdoor': '野外',
  'mixed': 'スタンディング/着席混在',
  'unknown': '不明',
};

const _scoreLabel = {
  'color_match': '色調の一致',
  'silhouette_match': 'シルエット',
  'practicality': '会場・天候への適合',
  'blend_in': '浮かず埋もれない',
};

/// F03 / P14 最終結果の表示(コーデ画像・選定理由・カルチャー解説・注意事項)
class ResultView extends StatelessWidget {
  const ResultView({super.key, required this.result, required this.photos, required this.onRestart});

  final ProposalResult result;
  final List<ClosetPhoto> photos;
  final VoidCallback onRestart;

  @override
  Widget build(BuildContext context) {
    final r = result;
    final event = r.event;
    final image = r.imageBase64 == null ? null : base64Decode(r.imageBase64!);
    final heading = Theme.of(context).textTheme;

    final hero = SectionCard(
      children: [
        if (event != null)
          Text(
            [
              event.artistName + (event.eventTitle != null ? ' / ${event.eventTitle}' : ''),
              ?event.eventDate,
              ?event.venue,
            ].join(' ・ '),
            style: const TextStyle(color: AppColors.muted),
          ),
        const SizedBox(height: 4),
        Text(r.outfitTitle ?? 'コーディネート提案', style: heading.headlineSmall?.copyWith(fontWeight: FontWeight.bold)),
        const SizedBox(height: 16),
        if (image != null) ...[
          GestureDetector(
            onTap: () => _zoom(context, image),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Image.memory(
                image,
                fit: BoxFit.contain,
                semanticLabel: '提案コーディネートのイメージ画像',
                errorBuilder: (_, _, _) => Container(
                  height: 120,
                  alignment: Alignment.center,
                  color: AppColors.soft,
                  child: const Hint('画像を表示できませんでした'),
                ),
              ),
            ),
          ),
          Wrap(
            spacing: 8,
            children: [
              TextButton.icon(
                onPressed: () => _zoom(context, image),
                icon: const Icon(Icons.zoom_in),
                label: const Text('拡大して見る'),
              ),
              if (kIsWeb)
                TextButton.icon(
                  onPressed: () => saveImage(image, r.imageMimeType ?? 'image/png'),
                  icon: const Icon(Icons.download),
                  label: const Text('画像を保存'),
                ),
            ],
          ),
        ] else
          Container(
            height: 120,
            alignment: Alignment.center,
            decoration: BoxDecoration(color: AppColors.soft, borderRadius: BorderRadius.circular(12)),
            child: const Hint('画像は生成できませんでした'),
          ),
        const SizedBox(height: 12),
        Text('使うアイテム', style: heading.titleSmall?.copyWith(fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        for (final item in r.items)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: item.imageIndex < photos.length
                      ? PhotoThumb(photo: photos[item.imageIndex], number: item.imageIndex + 1, size: 52)
                      : Container(
                          width: 52,
                          height: 52,
                          color: AppColors.soft,
                          alignment: Alignment.center,
                          child: Text('${item.imageIndex + 1}'),
                        ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        _categoryLabel[item.category] ?? item.category,
                        style: const TextStyle(fontSize: 12, color: AppColors.muted),
                      ),
                      Text(item.name),
                    ],
                  ),
                ),
              ],
            ),
          ),
        if (r.missingSuggestions.isNotEmpty)
          Text.rich(
            TextSpan(
              children: [
                const TextSpan(
                  text: '足すならこれ: ',
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
                TextSpan(text: r.missingSuggestions.join('、')),
              ],
            ),
          ),
      ],
    );

    final reason = SectionCard(
      title: 'このコーデを選んだ理由',
      children: [
        Text(r.reason ?? ''),
        if (r.stylingTips.isNotEmpty) ...[
          const SizedBox(height: 12),
          const Text('着こなしのコツ', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          Bullets(r.stylingTips),
        ],
      ],
    );

    final culture = r.culture;
    final mv = r.mvStyle;
    final vw = r.venueWeather;
    final critic = r.critic;
    final details = [
      if (culture != null && culture.covered)
        SectionCard(
          title: '${culture.genreName}系ライブのファッション文化',
          children: [
            Text(culture.explanation ?? ''),
            if (culture.sourceUrl != null) ...[
              const SizedBox(height: 8),
              InkWell(
                onTap: () => launchUrl(Uri.parse(culture.sourceUrl!)),
                child: Text(
                  '出典: ${culture.sourceTitle ?? culture.sourceUrl}',
                  style: const TextStyle(color: AppColors.accent2, decoration: TextDecoration.underline),
                ),
              ),
            ],
          ],
        ),
      if (mv != null && mv.analyzedFrom != 'none')
        SectionCard(
          title: '公式MVから読み取った世界観',
          children: [
            Text(mv.overallVibe),
            const SizedBox(height: 8),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [for (final c in mv.colorPalette) Pill(c, textColor: AppColors.text)],
            ),
            if (mv.analyzedFrom == 'thumbnail') const Hint('※サムネイル画像からの推定です'),
          ],
        ),
      if (vw != null)
        SectionCard(
          title: '会場・季節のポイント',
          children: [
            Text('会場形態: ${_venueLabel[vw.venueType] ?? vw.venueType}'),
            if (vw.season != null) Text('季節: ${vw.season}'),
            if (vw.weatherNote.isNotEmpty) ...[const SizedBox(height: 8), Text(vw.weatherNote)],
            if (vw.venueNotes.isNotEmpty) ...[const SizedBox(height: 8), Bullets(vw.venueNotes)],
          ],
        ),
      if (critic != null)
        SectionCard(
          title: 'AIセルフチェック',
          trailing: Pill(
            critic.passed ? '合格' : '要注意',
            color: critic.passed ? AppColors.ok : AppColors.ng,
            textColor: Colors.white,
            bold: true,
          ),
          children: [
            for (final MapEntry(:key, :value) in critic.scores.entries)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  children: [
                    SizedBox(width: 130, child: Text(_scoreLabel[key] ?? key, style: const TextStyle(fontSize: 13))),
                    Expanded(
                      child: LinearProgressIndicator(
                        value: value / 5,
                        minHeight: 8,
                        borderRadius: BorderRadius.circular(4),
                        backgroundColor: AppColors.soft,
                        color: value >= 4
                            ? AppColors.ok
                            : value >= 3
                            ? AppColors.accent2
                            : AppColors.ng,
                      ),
                    ),
                    SizedBox(width: 24, child: Text('$value', textAlign: TextAlign.end)),
                  ],
                ),
              ),
            if (critic.iteration > 1) const Hint('1回目の評価を受けて、組み合わせを見直しています。'),
          ],
        ),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        hero,
        reason,
        LayoutBuilder(
          builder: (context, constraints) {
            if (constraints.maxWidth < 640) return Column(children: details);
            // 広い画面では2列に並べる
            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: Column(children: [for (var i = 0; i < details.length; i += 2) details[i]])),
                const SizedBox(width: 16),
                Expanded(child: Column(children: [for (var i = 1; i < details.length; i += 2) details[i]])),
              ],
            );
          },
        ),
        if (r.notes.isNotEmpty) SectionCard(title: '注意事項', children: [Bullets(r.notes)]),
        Center(
          child: OutlinedButton(onPressed: onRestart, child: const Text('条件を変えてもう一度')),
        ),
      ],
    );
  }

  void _zoom(BuildContext context, Uint8List image) {
    showDialog<void>(
      context: context,
      builder: (context) => Dialog.fullscreen(
        backgroundColor: Colors.black,
        child: Stack(
          children: [
            InteractiveViewer(maxScale: 5, child: Center(child: Image.memory(image))),
            Positioned(
              right: 8,
              top: 8,
              child: SafeArea(
                child: IconButton(
                  tooltip: '閉じる',
                  color: Colors.white,
                  icon: const Icon(Icons.close),
                  onPressed: () => Navigator.pop(context),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
