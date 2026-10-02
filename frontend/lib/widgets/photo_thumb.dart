import 'package:flutter/material.dart';

import '../models.dart';
import '../theme.dart';

/// 手持ち服の写真のサムネイル。表示できない形式(ブラウザの HEIC など)は番号のタイルで代替する
class PhotoThumb extends StatelessWidget {
  const PhotoThumb({super.key, required this.photo, required this.number, this.size});

  final ClosetPhoto photo;
  final int number;
  final double? size;

  @override
  Widget build(BuildContext context) {
    return Image.memory(
      photo.bytes,
      width: size,
      height: size,
      fit: BoxFit.cover,
      gaplessPlayback: true,
      cacheWidth: 320,
      errorBuilder: (_, _, _) => Container(
        width: size,
        height: size,
        color: AppColors.soft,
        alignment: Alignment.center,
        child: Text(
          size != null && size! < 60 ? '$number' : '$number\nプレビュー非対応',
          textAlign: TextAlign.center,
          style: const TextStyle(color: AppColors.muted, fontSize: 12),
        ),
      ),
    );
  }
}
