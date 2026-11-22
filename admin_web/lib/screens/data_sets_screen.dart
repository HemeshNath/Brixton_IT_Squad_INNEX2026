// Data sets (Phase 10A step A6): "Wrong result?" reports, the known-scam memory, and the four lists
// (official & allowed sites, trusted sender IDs, blocked sites, blocked senders). Reviewers handle reports and the
// memory; admins also change the lists and download the CSV exports. Every change is live for the next check.

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api.dart';
import '../theme/app_theme.dart';
import 'shell.dart';

const _labelText = {'scam': 'a scam', 'spam': 'an advertisement', 'ham': 'a normal message'};
const _labelColor = {'scam': Color(0xFFC62828), 'spam': Color(0xFFEF6C00), 'ham': Color(0xFF2E7D32)};

String _date(String? iso) {
  final t = iso == null ? null : DateTime.tryParse(iso)?.toLocal();
  if (t == null) return '';
  String two(int n) => n.toString().padLeft(2, '0');
  return '${t.year}-${two(t.month)}-${two(t.day)} ${two(t.hour)}:${two(t.minute)}';
}

/// The masked message in the app's yellow frame.
class _MessageBox extends StatelessWidget {
  final String text;
  const _MessageBox(this.text);
  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: AppColors.contentFill,
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: AppColors.contentBorder, width: 2),
    ),
    child: SelectableText(text, style: const TextStyle(height: 1.35)),
  );
}

class DataSetsScreen extends StatefulWidget {
  final AdminApi api;
  final AdminAccount me;
  final void Function(Object error) onError;
  const DataSetsScreen({super.key, required this.api, required this.me, required this.onError});

  @override
  State<DataSetsScreen> createState() => _DataSetsScreenState();
}

class _DataSetsScreenState extends State<DataSetsScreen> {
  String _view = 'reports'; // reports | memory | <list name>
  List<Map<String, dynamic>> _lists = [];
  int? _pending;

  @override
  void initState() {
    super.initState();
    _loadOverview();
  }

  Future<void> _loadOverview() async {
    try {
      final l = await widget.api.lists();
      final r = await widget.api.reports();
      if (mounted) {
        setState(() {
          _lists = l;
          _pending = ((r['counts'] as Map?)?['pending'] as num?)?.toInt();
        });
      }
    } catch (e) {
      widget.onError(e);
    }
  }

  Future<void> _export(String file) async {
    final ok = await launchUrl(widget.api.exportUrl(file), webOnlyWindowName: '_blank');
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not open the download.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final canEdit = widget.me.atLeast('admin');
    final chips = <(String, String)>[
      ('reports', _pending == null ? 'Reports' : 'Reports ($_pending pending)'),
      ('memory', 'Known scams'),
      for (final l in _lists) (l['name'] as String, '${l['title']} (${l['count']})'),
    ];
    return SectionPage(
      title: 'Data sets',
      about: canEdit
          ? 'Reports, known scams and the lists the checks use. Changes are live for the next check.'
          : 'Review reports and the known-scam memory. The lists can be viewed; admins change them.',
      action: canEdit
          ? PopupMenuButton<String>(
              key: const Key('exportMenu'),
              tooltip: 'Download CSV',
              icon: const Icon(Icons.download_outlined),
              onSelected: _export,
              itemBuilder: (_) => const [
                PopupMenuItem(value: 'dataset.csv', child: Text('Approved reports (labelled data)')),
                PopupMenuItem(value: 'known-scams.csv', child: Text('Known-scam memory')),
              ],
            )
          : null,
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final (id, label) in chips)
              ChoiceChip(
                key: Key('view_$id'),
                label: Text(label),
                selected: _view == id,
                selectedColor: AppColors.lavender,
                onSelected: (_) => setState(() => _view = id),
              ),
          ],
        ),
        const SizedBox(height: 18),
        KeyedSubtree(
          key: ValueKey(_view),
          child: switch (_view) {
            'reports' => _ReportsView(api: widget.api, onError: widget.onError, onChanged: _loadOverview),
            'memory' => _MemoryView(api: widget.api, onError: widget.onError),
            _ => _ListView(
              api: widget.api,
              info: _lists.firstWhere((l) => l['name'] == _view),
              canEdit: canEdit,
              onError: widget.onError,
              onChanged: _loadOverview,
            ),
          },
        ),
      ],
    );
  }
}

// ---------------- reports ----------------

class _ReportsView extends StatefulWidget {
  final AdminApi api;
  final void Function(Object error) onError;
  final VoidCallback onChanged;
  const _ReportsView({required this.api, required this.onError, required this.onChanged});

  @override
  State<_ReportsView> createState() => _ReportsViewState();
}

class _ReportsViewState extends State<_ReportsView> {
  String _status = 'pending';
  int _page = 1;
  Map<String, dynamic>? _d;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d = await widget.api.reports(status: _status, page: _page);
      if (mounted) setState(() => _d = d);
    } catch (e) {
      widget.onError(e);
    }
  }

  Future<void> _review(Map<String, dynamic> r, String action) async {
    var category = '';
    if (action == 'approve' && r['correct_label'] == 'scam') {
      final c = TextEditingController();
      final ok = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Approve as a scam'),
          content: SizedBox(
            width: 420,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('It joins the known-scam memory: similar messages get extra points from now on.'),
                TextField(
                  key: const Key('reportCategory'),
                  controller: c,
                  decoration: const InputDecoration(labelText: 'Scam type (optional), e.g. fake KYC'),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
            FilledButton(
              key: const Key('confirmApprove'),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Approve'),
            ),
          ],
        ),
      );
      if (ok != true) return;
      category = c.text.trim();
    }
    try {
      final res = await widget.api.reviewReport(r['id'] as int, action, category: category);
      if (mounted) {
        final joined = res['known_scam_id'] != null;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              action == 'reject'
                  ? 'Report rejected.'
                  : joined
                  ? 'Approved – added to the known-scam memory.'
                  : 'Approved.',
            ),
          ),
        );
      }
      widget.onChanged();
      await _load();
    } catch (e) {
      widget.onError(e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = _d;
    final counts = d == null ? const {} : Map<String, dynamic>.from(d['counts'] as Map? ?? {});
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SegmentedButton<String>(
          segments: [
            for (final s in ['pending', 'approved', 'rejected'])
              ButtonSegment(value: s, label: Text('${s[0].toUpperCase()}${s.substring(1)} (${counts[s] ?? 0})')),
          ],
          selected: {_status},
          onSelectionChanged: (v) {
            setState(() {
              _status = v.first;
              _page = 1;
            });
            _load();
          },
        ),
        const SizedBox(height: 14),
        if (d == null)
          const Center(child: CircularProgressIndicator())
        else if ((d['results'] as List).isEmpty)
          Card(
            margin: EdgeInsets.zero,
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Text(_status == 'pending' ? 'No reports waiting. 🎉' : 'Nothing here yet.'),
            ),
          )
        else
          for (final r in d['results'] as List) _reportCard(Map<String, dynamic>.from(r as Map)),
        if (d != null && (d['total'] as num) > 20)
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              Text('${d['total']} reports · page $_page'),
              IconButton(
                icon: const Icon(Icons.chevron_left),
                onPressed: _page > 1
                    ? () {
                        setState(() => _page--);
                        _load();
                      }
                    : null,
              ),
              IconButton(
                icon: const Icon(Icons.chevron_right),
                onPressed: d['has_next'] == true
                    ? () {
                        setState(() => _page++);
                        _load();
                      }
                    : null,
              ),
            ],
          ),
      ],
    );
  }

  Widget _reportCard(Map<String, dynamic> r) {
    final label = r['correct_label'] as String;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.flag, color: _labelColor[label], size: 20),
                const SizedBox(width: 6),
                Expanded(
                  child: Text.rich(
                    TextSpan(
                      children: [
                        const TextSpan(text: 'User says this was '),
                        TextSpan(
                          text: _labelText[label] ?? label,
                          style: TextStyle(fontWeight: FontWeight.w700, color: _labelColor[label]),
                        ),
                      ],
                    ),
                  ),
                ),
                Text(_date(r['created_at'] as String?), style: const TextStyle(fontSize: 12, color: Colors.black54)),
              ],
            ),
            const SizedBox(height: 10),
            _MessageBox('${r['text']}'),
            if ('${r['note']}'.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('Note: ${r['note']}', style: const TextStyle(fontStyle: FontStyle.italic)),
            ],
            if (r['status'] == 'pending')
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    OutlinedButton.icon(
                      key: Key('reject_${r['id']}'),
                      onPressed: () => _review(r, 'reject'),
                      icon: const Icon(Icons.close, size: 18),
                      label: const Text('Reject'),
                    ),
                    const SizedBox(width: 8),
                    FilledButton.icon(
                      key: Key('approve_${r['id']}'),
                      onPressed: () => _review(r, 'approve'),
                      icon: const Icon(Icons.check, size: 18),
                      label: const Text('Approve'),
                    ),
                  ],
                ),
              )
            else
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  '${r['status']} ${_date(r['reviewed_at'] as String?)}',
                  style: const TextStyle(fontSize: 12, color: Colors.black54),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

// ---------------- known-scam memory ----------------

class _MemoryView extends StatefulWidget {
  final AdminApi api;
  final void Function(Object error) onError;
  const _MemoryView({required this.api, required this.onError});

  @override
  State<_MemoryView> createState() => _MemoryViewState();
}

class _MemoryViewState extends State<_MemoryView> {
  final _search = TextEditingController();
  int _page = 1;
  Map<String, dynamic>? _d;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d = await widget.api.knownScams(search: _search.text.trim(), page: _page);
      if (mounted) setState(() => _d = d);
    } catch (e) {
      widget.onError(e);
    }
  }

  Future<void> _add() async {
    final added = await showDialog<bool>(
      context: context,
      builder: (_) => _AddScamDialog(api: widget.api),
    );
    if (added == true) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Added to the known-scam memory.')));
      }
      _load();
    }
  }

  Future<void> _delete(Map<String, dynamic> k) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Remove this known scam?'),
        content: const Text('Similar messages will no longer get the "known scam" points.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            key: const Key('confirmRemoveScam'),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await widget.api.deleteKnownScam(k['id'] as int);
      _load();
    } catch (e) {
      widget.onError(e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = _d;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            SizedBox(
              width: 320,
              child: TextField(
                controller: _search,
                decoration: InputDecoration(
                  hintText: 'Search text or scam type',
                  prefixIcon: const Icon(Icons.search),
                  isDense: true,
                  border: const OutlineInputBorder(),
                  suffixIcon: IconButton(
                    icon: const Icon(Icons.arrow_forward),
                    onPressed: () {
                      _page = 1;
                      _load();
                    },
                  ),
                ),
                onSubmitted: (_) {
                  _page = 1;
                  _load();
                },
              ),
            ),
            const Spacer(),
            FilledButton.icon(
              key: const Key('addScam'),
              onPressed: _add,
              icon: const Icon(Icons.add),
              label: const Text('Add a scam'),
            ),
          ],
        ),
        const SizedBox(height: 6),
        const Text(
          'New messages very similar to these get extra points ("Matches a known scam"). Texts are stored masked.',
          style: TextStyle(fontSize: 12, color: Colors.black54),
        ),
        const SizedBox(height: 12),
        if (d == null)
          const Center(child: CircularProgressIndicator())
        else ...[
          Text('${d['total']} known scams'),
          const SizedBox(height: 8),
          for (final k in d['results'] as List)
            Card(
              margin: const EdgeInsets.only(bottom: 10),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 8, 12),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('${(k as Map)['text']}', maxLines: 4, overflow: TextOverflow.ellipsis),
                          const SizedBox(height: 4),
                          Text(
                            '#${k['id']} · ${'${k['category']}'.isEmpty ? 'no type' : k['category']} · '
                            'from ${k['source']} · ${_date(k['created_at'] as String?)}',
                            style: const TextStyle(fontSize: 12, color: Colors.black54),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      key: Key('removeScam_${k['id']}'),
                      tooltip: 'Remove',
                      icon: const Icon(Icons.delete_outline),
                      onPressed: () => _delete(Map<String, dynamic>.from(k)),
                    ),
                  ],
                ),
              ),
            ),
          if (d['has_next'] == true || _page > 1)
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Text('page $_page'),
                IconButton(
                  icon: const Icon(Icons.chevron_left),
                  onPressed: _page > 1
                      ? () {
                          setState(() => _page--);
                          _load();
                        }
                      : null,
                ),
                IconButton(
                  icon: const Icon(Icons.chevron_right),
                  onPressed: d['has_next'] == true
                      ? () {
                          setState(() => _page++);
                          _load();
                        }
                      : null,
                ),
              ],
            ),
        ],
      ],
    );
  }
}

class _AddScamDialog extends StatefulWidget {
  final AdminApi api;
  const _AddScamDialog({required this.api});
  @override
  State<_AddScamDialog> createState() => _AddScamDialogState();
}

class _AddScamDialogState extends State<_AddScamDialog> {
  final _text = TextEditingController();
  final _category = TextEditingController();
  String? _problem;
  bool _busy = false;

  Future<void> _save() async {
    setState(() => _busy = true);
    try {
      await widget.api.addKnownScam(_text.text, _category.text.trim());
      if (mounted) Navigator.pop(context, true);
    } on AdminApiException catch (e) {
      setState(() => _problem = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Add a known scam'),
    content: SizedBox(
      width: 480,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            key: const Key('scamText'),
            controller: _text,
            minLines: 3,
            maxLines: 8,
            decoration: const InputDecoration(
              labelText: 'Scam message',
              helperText: 'Phone numbers, names and account numbers are hidden before saving.',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            key: const Key('scamCategory'),
            controller: _category,
            decoration: const InputDecoration(labelText: 'Scam type (optional)', border: OutlineInputBorder()),
          ),
          if (_problem != null)
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Text(
                _problem!,
                key: const Key('scamProblem'),
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
        ],
      ),
    ),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
      FilledButton(key: const Key('saveScam'), onPressed: _busy ? null : _save, child: const Text('Add')),
    ],
  );
}

// ---------------- lists ----------------

class _ListView extends StatefulWidget {
  final AdminApi api;
  final Map<String, dynamic> info;
  final bool canEdit;
  final void Function(Object error) onError;
  final VoidCallback onChanged;
  const _ListView({
    required this.api,
    required this.info,
    required this.canEdit,
    required this.onError,
    required this.onChanged,
  });

  @override
  State<_ListView> createState() => _ListViewState();
}

class _ListViewState extends State<_ListView> {
  final _search = TextEditingController();
  final _value = TextEditingController();
  final _label = TextEditingController();
  Map<String, dynamic>? _d;
  String? _problem;

  String get _name => widget.info['name'] as String;
  bool get _blocked => _name.startsWith('blocked');

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d = await widget.api.listEntries(_name, search: _search.text.trim());
      if (mounted) setState(() => _d = d);
    } catch (e) {
      widget.onError(e);
    }
  }

  void _snack(String text) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _add() async {
    if (_value.text.trim().isEmpty) {
      setState(() => _problem = 'Enter a ${widget.info['value_label'].toString().toLowerCase()}.');
      return;
    }
    try {
      final r = await widget.api.addListEntry(_name, _value.text.trim(), _label.text.trim());
      _value.clear();
      _label.clear();
      setState(() => _problem = null);
      _snack(r['warning'] as String? ?? '${r['value']} added – live for the next check.');
      widget.onChanged();
      _load();
    } on AdminApiException catch (e) {
      if (e.signedOut) {
        widget.onError(e);
      } else {
        setState(() => _problem = e.message);
      }
    }
  }

  Future<void> _remove(Map<String, dynamic> e) async {
    final builtIn = e['source'] == 'built-in';
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(builtIn ? 'Switch off ${e['value']}?' : 'Remove ${e['value']}?'),
        content: Text(
          builtIn
              ? 'It is part of the built-in list. It stops counting until you add it again.'
              : 'It is removed from the list for the next check.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            key: const Key('confirmRemoveEntry'),
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(builtIn ? 'Switch off' : 'Remove'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await widget.api.removeListEntry(_name, e['value'] as String);
      widget.onChanged();
      _load();
    } catch (err) {
      widget.onError(err);
    }
  }

  Future<void> _switchOn(Map<String, dynamic> e) async {
    try {
      await widget.api.addListEntry(_name, e['value'] as String, '');
      widget.onChanged();
      _load();
    } catch (err) {
      widget.onError(err);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = _d;
    final color = _blocked ? const Color(0xFFC62828) : AppColors.protectedGreen;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('${widget.info['help']}', style: const TextStyle(color: Colors.black54)),
        const SizedBox(height: 12),
        if (widget.canEdit)
          Card(
            margin: EdgeInsets.zero,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Wrap(
                spacing: 12,
                runSpacing: 12,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  SizedBox(
                    width: 280,
                    child: TextField(
                      key: const Key('entryValue'),
                      controller: _value,
                      decoration: InputDecoration(
                        labelText: '${widget.info['value_label']}',
                        isDense: true,
                        border: const OutlineInputBorder(),
                      ),
                      onSubmitted: (_) => _add(),
                    ),
                  ),
                  SizedBox(
                    width: 240,
                    child: TextField(
                      key: const Key('entryLabel'),
                      controller: _label,
                      decoration: InputDecoration(
                        labelText: '${widget.info['label_label']} (optional)',
                        isDense: true,
                        border: const OutlineInputBorder(),
                      ),
                      onSubmitted: (_) => _add(),
                    ),
                  ),
                  FilledButton.icon(
                    key: const Key('addEntry'),
                    style: _blocked ? FilledButton.styleFrom(backgroundColor: const Color(0xFFC62828)) : null,
                    onPressed: _add,
                    icon: Icon(_blocked ? Icons.block : Icons.add),
                    label: Text(_blocked ? 'Block' : 'Add'),
                  ),
                  if (_problem != null)
                    Text(
                      _problem!,
                      key: const Key('entryProblem'),
                      style: TextStyle(color: Theme.of(context).colorScheme.error),
                    ),
                ],
              ),
            ),
          ),
        const SizedBox(height: 12),
        SizedBox(
          width: 320,
          child: TextField(
            controller: _search,
            decoration: const InputDecoration(
              hintText: 'Search',
              prefixIcon: Icon(Icons.search),
              isDense: true,
              border: OutlineInputBorder(),
            ),
            onChanged: (_) => _load(),
          ),
        ),
        const SizedBox(height: 12),
        if (d == null)
          const Center(child: CircularProgressIndicator())
        else if ((d['results'] as List).isEmpty)
          Card(
            margin: EdgeInsets.zero,
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Text(_blocked ? 'Nothing blocked yet.' : 'No entries.'),
            ),
          )
        else
          Card(
            margin: EdgeInsets.zero,
            child: Column(
              children: [
                for (final e in d['results'] as List)
                  ListTile(
                    dense: true,
                    leading: Icon(
                      _blocked ? Icons.block : Icons.verified_outlined,
                      color: (e as Map)['active'] == true ? color : Colors.black26,
                    ),
                    title: Text(
                      '${e['value']}',
                      style: TextStyle(
                        fontWeight: FontWeight.w600,
                        decoration: e['active'] == true ? null : TextDecoration.lineThrough,
                        color: e['active'] == true ? null : Colors.black38,
                      ),
                    ),
                    subtitle: Text(
                      [
                        if ('${e['label'] ?? ''}'.isNotEmpty) '${e['label']}',
                        e['source'] == 'built-in' ? 'built-in' : 'added by ${e['changed_by']}',
                        if (e['active'] != true) 'switched off by ${e['changed_by']}',
                      ].join(' · '),
                    ),
                    trailing: !widget.canEdit
                        ? null
                        : e['active'] == true
                        ? IconButton(
                            key: Key('removeEntry_${e['value']}'),
                            tooltip: e['source'] == 'built-in' ? 'Switch off' : 'Remove',
                            icon: Icon(e['source'] == 'built-in' ? Icons.toggle_on_outlined : Icons.delete_outline),
                            onPressed: () => _remove(Map<String, dynamic>.from(e)),
                          )
                        : TextButton(
                            onPressed: () => _switchOn(Map<String, dynamic>.from(e)),
                            child: const Text('Switch on'),
                          ),
                  ),
              ],
            ),
          ),
      ],
    );
  }
}
