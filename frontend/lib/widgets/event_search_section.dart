import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api.dart';
import '../models.dart';
import '../theme.dart';

/// F05 公演情報の入力(キーワード検索 → 候補から選ぶ / 手入力)。
///
/// 公演ページや MV の URL はユーザーに入力させない。公式MVは検索結果で見つかったものだけを使う。
class EventSearchSection extends StatefulWidget {
  const EventSearchSection({super.key, required this.form, required this.api, required this.onChanged});

  /// 親が保持する入力内容(画面を行き来しても残す)。このウィジェットが直接書き換える
  final EventForm form;
  final Api api;
  final VoidCallback onChanged;

  @override
  State<EventSearchSection> createState() => _EventSearchSectionState();
}

class _EventSearchSectionState extends State<EventSearchSection> {
  late final _keyword = TextEditingController(text: widget.form.keyword);
  late final _artist = TextEditingController(text: widget.form.artistName);
  late final _title = TextEditingController(text: widget.form.eventTitle);
  late final _genre = TextEditingController(text: widget.form.genre);
  late final _venue = TextEditingController(text: widget.form.venue);
  late final _date = TextEditingController(text: widget.form.eventDate);

  bool _searching = false;
  String? _searchError;
  EventSearchResult? _result;
  EventCandidate? _selected;

  /// 手入力欄を開いているか(候補を選ぶか、手入力の内容があれば開いた状態で始める)
  late bool _showDetails = widget.form.artistName.isNotEmpty;

  EventForm get form => widget.form;

  @override
  void dispose() {
    for (final c in [_keyword, _artist, _title, _genre, _venue, _date]) {
      c.dispose();
    }
    super.dispose();
  }

  void _sync() {
    form
      ..keyword = _keyword.text
      ..artistName = _artist.text
      ..eventTitle = _title.text
      ..genre = _genre.text
      ..venue = _venue.text
      ..eventDate = _date.text;
    widget.onChanged();
  }

  Future<void> _search() async {
    final keyword = _keyword.text.trim();
    if (keyword.isEmpty || _searching) return;
    FocusScope.of(context).unfocus();
    setState(() {
      _searching = true;
      _searchError = null;
      _result = null;
    });
    try {
      final result = await widget.api.searchEvents(keyword);
      if (!mounted) return;
      setState(() {
        _result = result;
        if (result.candidates.isEmpty) {
          _searchError = '「$keyword」に該当する公演が見つかりませんでした。キーワードを変えるか、下の欄に手入力してください。';
        }
      });
    } on ValidationException catch (e) {
      if (mounted) setState(() => _searchError = e.errors.join('\n'));
    } on ApiException catch (e) {
      if (mounted) setState(() => _searchError = e.message);
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  void _select(EventCandidate c) {
    setState(() {
      _selected = c;
      _showDetails = true;
      _artist.text = c.artistName;
      _title.text = c.eventTitle ?? '';
      _genre.text = c.genreHint ?? '';
      _venue.text = c.venue ?? '';
      _date.text = c.eventDate ?? '';
      form
        ..mvUrl = c.mvUrl
        ..mvTitle = c.mvTitle
        ..useMv = true;
    });
    _sync();
  }

  void _clearSelection() {
    setState(() {
      _selected = null;
      for (final c in [_artist, _title, _genre, _venue, _date]) {
        c.clear();
      }
      form
        ..mvUrl = null
        ..mvTitle = null;
    });
    _sync();
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime.tryParse(_date.text) ?? now,
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 3),
      locale: const Locale('ja'),
    );
    if (picked == null) return;
    _date.text = picked.toIso8601String().substring(0, 10);
    _sync();
  }

  @override
  Widget build(BuildContext context) {
    final result = _result;
    return SectionCard(
      step: 1,
      title: '行くライブを検索',
      children: [
        const Hint('アーティスト名やツアー名など、キーワードで公演を探します。見つからない場合は手入力でも大丈夫です。'),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _keyword,
                textInputAction: TextInputAction.search,
                style: const TextStyle(fontSize: 16),
                decoration: const InputDecoration(
                  labelText: '検索キーワード',
                  hintText: '例: アーティスト名 ツアー 2026',
                  prefixIcon: Icon(Icons.search),
                ),
                onChanged: (_) => _sync(),
                onSubmitted: (_) => _search(),
              ),
            ),
            const SizedBox(width: 8),
            FilledButton(
              onPressed: _searching ? null : _search,
              child: _searching
                  ? const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('検索'),
            ),
          ],
        ),
        if (_searching) ...[const SizedBox(height: 12), const Hint('公演情報を検索しています(10秒ほどかかることがあります)')],
        if (_searchError != null) ...[
          const SizedBox(height: 12),
          Text(_searchError!, style: const TextStyle(color: AppColors.ng)),
        ],
        if (result != null && result.candidates.isNotEmpty && _selected == null) ...[
          const SizedBox(height: 16),
          Text(
            '見つかった公演(${result.candidates.length}件)— 行く公演を選んでください',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          for (final c in result.candidates) _CandidateTile(candidate: c, onTap: () => _select(c)),
        ],
        if (_selected != null) ...[
          const SizedBox(height: 16),
          _CandidateTile(candidate: _selected!, selected: true, onTap: _clearSelection),
          if (form.mvUrl != null)
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: form.useMv,
              onChanged: (v) {
                setState(() => form.useMv = v);
                _sync();
              },
              title: const Text('公式MVの雰囲気も参考にする'),
              subtitle: Text(form.mvTitle ?? '公式MV', maxLines: 1, overflow: TextOverflow.ellipsis),
            ),
        ],
        if (result != null && result.sources.isNotEmpty) _Sources(result.sources),
        const SizedBox(height: 8),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: () => setState(() => _showDetails = !_showDetails),
            icon: Icon(_showDetails ? Icons.expand_less : Icons.expand_more),
            label: Text(_selected != null ? '内容を確認・修正する' : '公演情報を手入力する'),
          ),
        ),
        if (_showDetails) ...[
          const Hint('手入力した内容は検索結果より優先します。キーワードだけで送信した場合は、AIが検索結果の1件目を使います。'),
          const SizedBox(height: 12),
          _field(_artist, 'アーティスト名'),
          _field(_title, '公演名', optional: true),
          _field(_genre, 'ジャンル', optional: true, hint: '例: パンク、ヒップホップ、V系'),
          _field(_venue, '会場', optional: true, hint: '例: Zepp Haneda'),
          _field(
            _date,
            '公演日',
            optional: true,
            readOnly: true,
            onTap: _pickDate,
            suffix: _date.text.isEmpty
                ? const Icon(Icons.calendar_today, size: 18)
                : IconButton(
                    tooltip: '公演日を消す',
                    icon: const Icon(Icons.clear, size: 18),
                    onPressed: () {
                      _date.clear();
                      _sync();
                    },
                  ),
          ),
        ],
      ],
    );
  }

  Widget _field(
    TextEditingController controller,
    String label, {
    bool optional = false,
    String? hint,
    bool readOnly = false,
    VoidCallback? onTap,
    Widget? suffix,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextField(
        controller: controller,
        readOnly: readOnly,
        onTap: onTap,
        style: const TextStyle(fontSize: 16),
        decoration: InputDecoration(labelText: optional ? '$label(任意)' : label, hintText: hint, suffixIcon: suffix),
        onChanged: (_) => _sync(),
      ),
    );
  }
}

class _CandidateTile extends StatelessWidget {
  const _CandidateTile({required this.candidate, required this.onTap, this.selected = false});

  final EventCandidate candidate;
  final VoidCallback onTap;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    final c = candidate;
    final details = [c.eventDate, c.venue, c.genreHint].whereType<String>().join(' ・ ');
    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 8),
      color: selected ? const Color(0xFFFDEEF1) : AppColors.soft,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: selected ? AppColors.accent : Colors.transparent, width: 1.5),
      ),
      child: ListTile(
        onTap: onTap,
        leading: Icon(
          selected ? Icons.check_circle : Icons.music_note,
          color: selected ? AppColors.accent : AppColors.muted,
        ),
        title: Text(
          [c.artistName, c.eventTitle].whereType<String>().join(' / '),
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (details.isNotEmpty) Text(details),
            if (c.mvUrl != null) const Text('公式MVあり', style: TextStyle(color: AppColors.ok, fontSize: 12)),
          ],
        ),
        trailing: selected
            ? const Text('変更', style: TextStyle(color: AppColors.accent))
            : const Icon(Icons.chevron_right),
      ),
    );
  }
}

/// 検索で参照したページ(出典)
class _Sources extends StatelessWidget {
  const _Sources(this.sources);
  final List<SearchSource> sources;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Wrap(
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: 4,
        children: [
          const Hint('参照した情報源:'),
          for (final s in sources)
            InkWell(
              onTap: () => launchUrl(Uri.parse(s.url)),
              child: Text(
                s.title,
                style: const TextStyle(fontSize: 13, color: AppColors.accent2, decoration: TextDecoration.underline),
              ),
            ),
        ],
      ),
    );
  }
}
