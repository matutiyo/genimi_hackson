import 'package:flutter/material.dart';

/// 旧 Web 版(React)と同じ配色
abstract final class AppColors {
  static const bg = Color(0xFFF6F3EF);
  static const surface = Colors.white;
  static const text = Color(0xFF1F1B24);
  static const muted = Color(0xFF6B6572);
  static const border = Color(0xFFE4DED6);
  static const accent = Color(0xFFD6334F);
  static const accent2 = Color(0xFF7A3CF0);
  static const ok = Color(0xFF1F8A5B);
  static const ng = Color(0xFFB8651B);
  static const soft = Color(0xFFF1EBE4);
}

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: AppColors.accent,
    primary: AppColors.accent,
    secondary: AppColors.accent2,
    surface: AppColors.surface,
    error: AppColors.accent,
  );
  const radius = BorderRadius.all(Radius.circular(12));
  return ThemeData(
    colorScheme: scheme,
    scaffoldBackgroundColor: AppColors.bg,
    textTheme: Typography.blackMountainView.apply(bodyColor: AppColors.text, displayColor: AppColors.text),
    inputDecorationTheme: const InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      isDense: true,
      border: OutlineInputBorder(
        borderRadius: radius,
        borderSide: BorderSide(color: AppColors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: radius,
        borderSide: BorderSide(color: AppColors.border),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(48, 48),
        shape: const RoundedRectangleBorder(borderRadius: radius),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(44, 44),
        shape: const RoundedRectangleBorder(borderRadius: radius),
      ),
    ),
  );
}

/// 白い角丸カード(各セクションの外枠)
class SectionCard extends StatelessWidget {
  const SectionCard({super.key, required this.children, this.title, this.step, this.trailing});

  final String? title;

  /// 見出しの前に出す番号(入力画面の ①② など)
  final int? step;
  final Widget? trailing;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    // ListTile などのタップ演出が見えるよう、背景は Material で塗る(影だけ外側の DecoratedBox)
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        boxShadow: const [BoxShadow(color: Color(0x0F1F1B24), blurRadius: 24, offset: Offset(0, 8))],
      ),
      child: Material(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (title != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Row(
                    children: [
                      if (step != null) ...[
                        CircleAvatar(
                          radius: 13,
                          backgroundColor: AppColors.accent,
                          child: Text('$step', style: const TextStyle(color: Colors.white, fontSize: 14)),
                        ),
                        const SizedBox(width: 8),
                      ],
                      Expanded(
                        child: Text(
                          title!,
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
                        ),
                      ),
                      ?trailing,
                    ],
                  ),
                ),
              ...children,
            ],
          ),
        ),
      ),
    );
  }
}

/// 箇条書き
class Bullets extends StatelessWidget {
  const Bullets(this.items, {super.key});
  final List<String> items;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final item in items)
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('・'),
                Expanded(child: Text(item)),
              ],
            ),
          ),
      ],
    );
  }
}

/// 補足の小さい文字
class Hint extends StatelessWidget {
  const Hint(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) => Text(text, style: const TextStyle(color: AppColors.muted, fontSize: 13));
}

/// 小さなラベル(Chip は読み上げでチェックボックス扱いになるため、表示専用にはこれを使う)
class Pill extends StatelessWidget {
  const Pill(this.text, {super.key, this.color = Colors.white, this.textColor = AppColors.muted, this.bold = false});

  final String text;
  final Color color;
  final Color textColor;
  final bool bold;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
    decoration: BoxDecoration(
      color: color,
      border: Border.all(color: AppColors.border),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Text(
      text,
      style: TextStyle(fontSize: 13, color: textColor, fontWeight: bold ? FontWeight.bold : FontWeight.normal),
    ),
  );
}
