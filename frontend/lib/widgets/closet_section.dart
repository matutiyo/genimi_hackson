import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../models.dart';
import '../theme.dart';
import 'photo_thumb.dart';

/// 長辺がこれを超える写真は縮小する(Gemini の解析にはこれで十分)
const _maxEdge = 1600.0;
const _jpegQuality = 85;

const _extTypes = {
  'jpg': 'image/jpeg',
  'jpeg': 'image/jpeg',
  'png': 'image/png',
  'webp': 'image/webp',
  'heic': 'image/heic',
  'heif': 'image/heif',
};

String formatBytes(int bytes) => bytes < 1024 * 1024
    ? '${(bytes / 1024).round().clamp(1, 1023)}KB'
    : '${(bytes / 1024 / 1024).toStringAsFixed(1)}MB';

/// F02 手持ち服・クローゼット画像の登録(複数枚)
class ClosetSection extends StatefulWidget {
  const ClosetSection({
    super.key,
    required this.photos,
    required this.config,
    required this.consent,
    required this.onPhotosChanged,
    required this.onConsentChanged,
  });

  final List<ClosetPhoto> photos;
  final ClientConfig config;
  final bool consent;
  final ValueChanged<List<ClosetPhoto>> onPhotosChanged;
  final ValueChanged<bool> onConsentChanged;

  @override
  State<ClosetSection> createState() => _ClosetSectionState();
}

class _ClosetSectionState extends State<ClosetSection> {
  final _picker = ImagePicker();
  List<String> _warnings = [];
  bool _picking = false;
  bool _showTips = false;
  int _seq = 0;

  int get _remaining => widget.config.maxImages - widget.photos.length;

  /// カメラ撮影はスマホ・タブレットのみ表示する
  bool get _canUseCamera =>
      defaultTargetPlatform == TargetPlatform.android || defaultTargetPlatform == TargetPlatform.iOS;

  Future<void> _pick({bool camera = false}) async {
    if (_remaining <= 0) {
      setState(() => _warnings = ['写真は${widget.config.maxImages}枚まで追加できます。']);
      return;
    }
    setState(() => _picking = true);
    try {
      // image_picker が長辺 1600px・JPEG 品質 85 に縮小する(EXIF の向きも反映される)
      final files = camera
          ? [
              ?await _picker.pickImage(
                source: ImageSource.camera,
                maxWidth: _maxEdge,
                maxHeight: _maxEdge,
                imageQuality: _jpegQuality,
              ),
            ]
          : await _picker.pickMultiImage(maxWidth: _maxEdge, maxHeight: _maxEdge, imageQuality: _jpegQuality);
      await _add(files);
    } catch (e) {
      setState(() => _warnings = ['写真を読み込めませんでした。もう一度お試しください。']);
    } finally {
      if (mounted) setState(() => _picking = false);
    }
  }

  Future<void> _add(List<XFile> files) async {
    final warnings = <String>[];
    final next = [...widget.photos];
    final maxBytes = widget.config.maxImageMb * 1024 * 1024;
    for (final f in files) {
      final ext = f.name.split('.').last.toLowerCase();
      final mime = widget.config.allowedTypes.contains(f.mimeType) ? f.mimeType! : _extTypes[ext];
      if (mime == null || !widget.config.allowedTypes.contains(mime)) {
        warnings.add('「${f.name}」は対応していない形式です(JPEG / PNG / WebP / HEIC)。');
        continue;
      }
      if (next.length >= widget.config.maxImages) {
        warnings.add('写真は${widget.config.maxImages}枚までのため、一部を追加しませんでした。');
        break;
      }
      final bytes = await f.readAsBytes();
      if (bytes.length > maxBytes) {
        warnings.add('「${f.name}」は${widget.config.maxImageMb}MBを超えています。');
        continue;
      }
      final photo = ClosetPhoto(id: 'photo-${_seq++}', name: f.name, mimeType: mime, bytes: bytes);
      if (next.any((p) => p.key == photo.key)) {
        warnings.add('「${f.name}」はすでに追加済みです。');
        continue;
      }
      next.add(photo);
    }
    if (!mounted) return;
    setState(() => _warnings = warnings);
    widget.onPhotosChanged(next);
  }

  void _remove(ClosetPhoto photo) {
    setState(() => _warnings = []);
    widget.onPhotosChanged([...widget.photos]..remove(photo));
  }

  @override
  Widget build(BuildContext context) {
    final photos = widget.photos;
    return SectionCard(
      step: 2,
      title: '手持ちの服',
      trailing: Text('${photos.length} / ${widget.config.maxImages}枚', style: const TextStyle(color: AppColors.muted)),
      children: [
        Hint(
          '服の写真を追加してください(${widget.config.maxImages}枚・1枚${widget.config.maxImageMb}MBまで)。'
          '大きな写真は自動で縮小してから送信します。',
        ),
        const SizedBox(height: 12),
        if (photos.isNotEmpty || _picking)
          GridView.extent(
            maxCrossAxisExtent: 110,
            mainAxisSpacing: 8,
            crossAxisSpacing: 8,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            children: [
              for (final (i, p) in photos.indexed)
                Stack(
                  fit: StackFit.expand,
                  children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(10),
                      child: PhotoThumb(photo: p, number: i + 1),
                    ),
                    Positioned(left: 4, top: 4, child: _Badge('${i + 1}')),
                    Positioned(left: 4, bottom: 4, child: _Badge(formatBytes(p.bytes.length))),
                    Positioned(
                      right: 0,
                      top: 0,
                      child: IconButton(
                        tooltip: '${i + 1}枚目を削除',
                        style: IconButton.styleFrom(backgroundColor: Colors.black54, foregroundColor: Colors.white),
                        iconSize: 16,
                        visualDensity: VisualDensity.compact,
                        icon: const Icon(Icons.close),
                        onPressed: () => _remove(p),
                      ),
                    ),
                  ],
                ),
              if (_picking)
                Container(
                  decoration: BoxDecoration(color: AppColors.soft, borderRadius: BorderRadius.circular(10)),
                  alignment: Alignment.center,
                  child: const Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [CircularProgressIndicator(strokeWidth: 2), SizedBox(height: 6), Hint('準備中')],
                  ),
                ),
            ],
          ),
        if (photos.isNotEmpty) const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            OutlinedButton.icon(
              onPressed: _picking || _remaining <= 0 ? null : _pick,
              icon: const Icon(Icons.add_photo_alternate_outlined),
              label: const Text('写真を選ぶ'),
            ),
            if (_canUseCamera)
              OutlinedButton.icon(
                onPressed: _picking || _remaining <= 0 ? null : () => _pick(camera: true),
                icon: const Icon(Icons.photo_camera_outlined),
                label: const Text('カメラで撮る'),
              ),
            TextButton(
              onPressed: () => setState(() => _showTips = !_showTips),
              child: Text('上手に撮るコツ ${_showTips ? '▲' : '▼'}'),
            ),
            if (photos.isNotEmpty)
              TextButton(
                style: TextButton.styleFrom(foregroundColor: AppColors.ng),
                onPressed: () {
                  setState(() => _warnings = []);
                  widget.onPhotosChanged([]);
                },
                child: const Text('すべて削除'),
              ),
          ],
        ),
        if (_showTips)
          Container(
            margin: const EdgeInsets.only(top: 8),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: AppColors.soft, borderRadius: BorderRadius.circular(10)),
            child: const Bullets([
              '平置き or ハンガー掛けで、服の形がわかるように撮る',
              '明るい場所で撮ると色を正しく読み取れます',
              '自分が写らないように撮影してください(人物は解析に使いません)',
              '靴やアクセサリーも1枚あると、コーデ全体を組みやすくなります',
            ]),
          ),
        if (_warnings.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: DefaultTextStyle.merge(
              style: const TextStyle(color: AppColors.ng),
              child: Bullets(_warnings),
            ),
          ),
        const SizedBox(height: 8),
        CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
          value: widget.consent,
          onChanged: (v) => widget.onConsentChanged(v ?? false),
          title: const Text('自分で撮影した(または利用許諾を得た)画像です。画像は提案の生成にのみ使われ、保存されません。', style: TextStyle(fontSize: 14)),
        ),
      ],
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
    decoration: BoxDecoration(color: Colors.black54, borderRadius: BorderRadius.circular(6)),
    child: Text(text, style: const TextStyle(color: Colors.white, fontSize: 11)),
  );
}
