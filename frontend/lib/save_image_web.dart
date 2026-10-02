import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

/// 生成したコーデ画像をブラウザでダウンロードする
Future<void> saveImage(Uint8List bytes, String mimeType) async {
  final blob = web.Blob([bytes.toJS].toJS, web.BlobPropertyBag(type: mimeType));
  final url = web.URL.createObjectURL(blob);
  web.HTMLAnchorElement()
    ..href = url
    ..download = 'live-outfit.${mimeType.split('/').last}'
    ..click();
  // すぐに解放するとダウンロードが始まらないブラウザがあるため少し待つ
  await Future<void>.delayed(const Duration(seconds: 1));
  web.URL.revokeObjectURL(url);
}
