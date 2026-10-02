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

  /// 詳細検索を開いているか(最初は閉じておく)
  bool _showDetails = false;

  /// 詳細検索の値が選んだ候補から入ったままか(利用者が手で直したら false)
  bool _filledFromCandidate = false;

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

  /// キーワードが空でも、詳細検索のアーティスト名・公演名があれば検索できる
  bool get _canSearch =>
      _keyword.text.trim().isNotEmpty || _artist.text.trim().isNotEmpty || _title.text.trim().isNotEmpty;

  Future<void> _search() async {
    if (!_canSearch || _searching) return;
    final keyword = _keyword.text.trim();
    if (_selected != null) {
      // 検索し直すときは選択を外す。候補から入っただけの値は絞り込み条件に残さない
      if (_filledFromCandidate) _clearDetails();
      _selected = null;
      form
        ..mvUrl = null
        ..mvTitle = null;
      _sync();
    }
    final narrowed = form.detailCount > 0;
    FocusScope.of(context).unfocus();
    setState(() {
      _showDetails = false; // 結果が検索欄のすぐ下に見えるよう閉じる(条件は残る)
      _searching = true;
      _searchError = null;
      _result = null;
    });
    try {
      final result = await widget.api.searchEvents(keyword, conditions: form.searchConditions);
      if (!mounted) return;
      setState(() {
        _result = result;
        if (result.candidates.isEmpty) {
          _searchError = narrowed
              ? '条件に合う公演が見つかりませんでした。詳細検索の条件を減らすか、キーワードを変えてください。'
              : '該当する公演が見つかりませんでした。キーワードを変えるか、詳細検索に公演の情報を入力してください。';
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
      _filledFromCandidate = true;
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

  void _clearDetails() {
    for (final c in [_artist, _title, _genre, _venue, _date]) {
      c.clear();
    }
  }

  /// 詳細検索を手で変えた
  void _editDetails() {
    _filledFromCandidate = false;
    _sync();
  }

  void _clearSelection() {
    setState(() {
      _selected = null;
      _clearDetails();
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
    _editDetails();
  }

  @override
  Widget build(BuildContext context) {
    final result = _result;
    return SectionCard(
      step: 1,
      title: '行くライブを検索',
      children: [
        const Hint('アーティスト名やツアー名など、キーワードで公演を探します。日付や会場で絞り込みたいときは「詳細検索」を開いてください。'),
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
              onPressed: _searching || !_canSearch ? null : _search,
              child: _searching
                  ? const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('検索'),
            ),
          ],
        ),
        _DetailToggle(
          open: _showDetails,
          count: form.detailCount,
          onTap: () => setState(() => _showDetails = !_showDetails),
        ),
        AnimatedSize(
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
          alignment: Alignment.topCenter,
          child: _showDetails ? _detailPanel() : const SizedBox(width: double.infinity),
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
      ],
    );
  }

  /// 詳細検索(任意項目)。検索の絞り込みに使い、送信時は検索結果より優先する
  Widget _detailPanel() {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 4),
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 2),
      decoration: BoxDecoration(color: AppColors.soft, borderRadius: BorderRadius.circular(12)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Hint('入力した条件で検索結果を絞り込みます。候補を選ぶと自動で入り、ここで修正できます。検索しなくても、ここに入れた内容で提案できます。'),
          const SizedBox(height: 12),
          _field(_artist, 'アーティスト名'),
          _field(_title, '公演名'),
          _field(_genre, 'ジャンル', hint: '例: パンク、ヒップホップ、V系'),
          _field(_venue, '会場', hint: '例: Zepp Haneda'),
          _field(
            _date,
            '公演日',
            readOnly: true,
            onTap: _pickDate,
            suffix: _date.text.isEmpty
                ? const Icon(Icons.calendar_today, size: 18)
                : IconButton(
                    tooltip: '公演日を消す',
                    icon: const Icon(Icons.clear, size: 18),
                    onPressed: () {
                      _date.clear();
                      _editDetails();
                    },
                  ),
          ),
          if (form.detailCount > 0)
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: () {
                  _clearDetails();
                  _editDetails();
                },
                child: const Text('条件をクリア'),
              ),
            ),
        ],
      ),
    );
  }

  Widget _field(
    TextEditingController controller,
    String label, {
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
        decoration: InputDecoration(labelText: label, hintText: hint, suffixIcon: suffix),
        onChanged: (_) => _editDetails(),
      ),
    );
  }
}

/// 「詳細検索」の開閉ボタン。閉じていても入力済みの件数を表示する
class _DetailToggle extends StatelessWidget {
  const _DetailToggle({required this.open, required this.count, required this.onTap});

  final bool open;
  final int count;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Padding(
        padding: const EdgeInsets.only(top: 8),
        child: TextButton.icon(
          onPressed: onTap,
          icon: AnimatedRotation(
            turns: open ? 0.5 : 0,
            duration: const Duration(milliseconds: 200),
            child: const Icon(Icons.expand_more),
          ),
          label: Text('詳細検索(任意)${count > 0 ? '・$count件入力中' : ''}'),
        ),
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
