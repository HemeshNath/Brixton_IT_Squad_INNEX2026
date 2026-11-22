// Settings (Phase 10A step A4): on/off switches, time limits and score numbers, built from the server's field
// list. Saving makes a new version that is live at once; the history shows what each version changed and can
// undo back to any version (including the defaults).

import 'package:flutter/material.dart';

import '../api.dart';
import '../theme/app_theme.dart';
import 'shell.dart';

String _fmt(Object? v) => v is bool ? (v ? 'on' : 'off') : '$v';

String _date(String? iso) {
  final t = iso == null ? null : DateTime.tryParse(iso)?.toLocal();
  if (t == null) return '';
  String two(int n) => n.toString().padLeft(2, '0');
  return '${t.year}-${two(t.month)}-${two(t.day)} ${two(t.hour)}:${two(t.minute)}';
}

class SettingsScreen extends StatefulWidget {
  final AdminApi api;
  final void Function(Object error) onError;
  const SettingsScreen({super.key, required this.api, required this.onError});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  Map<String, dynamic>? _server; // GET /settings
  Map<String, Map<String, dynamic>> _edit = {}; // values in the form
  final Map<String, TextEditingController> _text = {};
  final _note = TextEditingController();
  List<Map<String, dynamic>> _history = [];
  String? _problem;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    for (final c in _text.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final s = await widget.api.settings();
      final h = await widget.api.settingsHistory();
      if (!mounted) return;
      setState(() {
        _server = s;
        _history = [for (final x in h['results'] as List) Map<String, dynamic>.from(x as Map)];
        _resetForm();
      });
    } catch (e) {
      widget.onError(e);
    }
  }

  Map<String, dynamic> get _data => Map<String, dynamic>.from(_server!['data'] as Map);
  List<Map<String, dynamic>> get _fields => [
    for (final f in _server!['fields'] as List) Map<String, dynamic>.from(f as Map),
  ];

  void _resetForm() {
    _edit = {for (final e in _data.entries) e.key: Map<String, dynamic>.from(e.value as Map)};
    for (final f in _fields) {
      if (f['type'] == 'bool') continue;
      final id = '${f['group']}.${f['key']}';
      (_text[id] ??= TextEditingController()).text = _fmt(_edit[f['group']]![f['key']]);
    }
    _problem = null;
    _note.clear();
  }

  /// Form values with numbers read from the text boxes. Null + message if a box is not a number.
  Map<String, dynamic>? _collect() {
    final out = {for (final e in _edit.entries) e.key: Map<String, dynamic>.from(e.value)};
    for (final f in _fields) {
      if (f['type'] == 'bool') continue;
      final raw = _text['${f['group']}.${f['key']}']!.text.trim();
      final num? n = f['type'] == 'int' ? int.tryParse(raw) : double.tryParse(raw);
      if (n == null) {
        setState(() => _problem = '${f['label']}: enter a ${f['type'] == 'int' ? 'whole number' : 'number'}.');
        return null;
      }
      out[f['group']]![f['key']] = n;
    }
    return out;
  }

  List<String> _changedLabels(Map<String, dynamic> next) => [
    for (final f in _fields)
      if ('${(_data[f['group']] as Map)[f['key']]}' != '${next[f['group']][f['key']]}')
        '${f['label']}: ${_fmt((_data[f['group']] as Map)[f['key']])} → ${_fmt(next[f['group']][f['key']])}',
  ];

  Future<void> _save() async {
    final next = _collect();
    if (next == null) return;
    final changed = _changedLabels(next);
    if (changed.isEmpty) {
      setState(() => _problem = 'Nothing changed.');
      return;
    }
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Save and make live?'),
        content: SizedBox(
          width: 460,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('The next checks use these values at once:'),
              const SizedBox(height: 8),
              for (final c in changed) Text('• $c'),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            key: const Key('confirmSave'),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    setState(() => _saving = true);
    try {
      final r = await widget.api.saveSettings(next, _note.text.trim());
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Version ${(r['version'] as Map)['number']} is live.')));
      }
      await _load();
    } on AdminApiException catch (e) {
      if (e.signedOut) {
        widget.onError(e);
      } else {
        setState(() => _problem = e.message);
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _restore(int number) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(number == 0 ? 'Go back to the defaults?' : 'Go back to version $number?'),
        content: const Text('This is saved as a new version and is live at once. Nothing in the history is deleted.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            key: const Key('confirmRestore'),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Undo'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      final r = await widget.api.restoreSettings(number);
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Version ${(r['version'] as Map)['number']} is live.')));
      }
      await _load();
    } catch (e) {
      widget.onError(e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = _server;
    if (s == null) {
      return const SectionPage(
        title: 'Settings',
        about: 'Loading…',
        children: [Center(child: CircularProgressIndicator())],
      );
    }
    final version = Map<String, dynamic>.from(s['version'] as Map);
    final groups = Map<String, dynamic>.from(s['groups'] as Map);
    return SectionPage(
      title: 'Settings',
      about:
          'Live version ${version['number']} (${s['scoring_version']})'
          '${version['created_by'] == '' ? '' : ' · saved by ${version['created_by']} ${_date(version['created_at'] as String?)}'}'
          ' · changes apply to the next check, no restart needed.',
      action: IconButton(tooltip: 'Reload', icon: const Icon(Icons.refresh), onPressed: _load),
      children: [
        LayoutBuilder(
          builder: (ctx, box) {
            final cards = [for (final g in groups.entries) _groupCard(g.key, g.value as String)];
            final columns = box.maxWidth >= 1100 ? 2 : 1;
            final width = (box.maxWidth - (columns - 1) * 14) / columns;
            return Wrap(
              spacing: 14,
              runSpacing: 14,
              children: [for (final c in cards) SizedBox(width: width, child: c)],
            );
          },
        ),
        const SizedBox(height: 18),
        Card(
          margin: EdgeInsets.zero,
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextField(
                  key: const Key('settingsNote'),
                  controller: _note,
                  maxLength: 200,
                  decoration: const InputDecoration(labelText: 'Note (why this change?)', border: OutlineInputBorder()),
                ),
                if (_problem != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: Text(
                      _problem!,
                      key: const Key('settingsProblem'),
                      style: TextStyle(color: Theme.of(context).colorScheme.error),
                    ),
                  ),
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    TextButton(onPressed: () => setState(_resetForm), child: const Text('Reset form')),
                    const SizedBox(width: 8),
                    FilledButton.icon(
                      key: const Key('saveSettings'),
                      onPressed: _saving ? null : _save,
                      icon: const Icon(Icons.save_outlined),
                      label: const Text('Save and make live'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 28),
        const Text(
          'History',
          style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700, color: AppColors.purpleDark),
        ),
        const SizedBox(height: 10),
        for (final h in _history) _historyCard(h, live: h['number'] == version['number']),
      ],
    );
  }

  Widget _groupCard(String group, String title) {
    final fields = _fields.where((f) => f['group'] == group).toList();
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            const SizedBox(height: 8),
            for (final f in fields) _fieldRow(f),
          ],
        ),
      ),
    );
  }

  Widget _fieldRow(Map<String, dynamic> f) {
    final group = f['group'] as String, key = f['key'] as String;
    final original = (_data[group] as Map)[key];
    final help = f['help'] as String? ?? '';
    if (f['type'] == 'bool') {
      final value = _edit[group]![key] as bool;
      return SwitchListTile(
        key: Key('field_$key'),
        contentPadding: EdgeInsets.zero,
        title: Text(f['label'] as String, style: TextStyle(fontWeight: value != original ? FontWeight.w700 : null)),
        subtitle: help.isEmpty ? null : Text(help, style: const TextStyle(fontSize: 12)),
        value: value,
        onChanged: (v) => setState(() => _edit[group]![key] = v),
      );
    }
    final controller = _text['$group.$key']!;
    final changed = controller.text.trim() != _fmt(original);
    final range = '${_fmt(f['min'])}–${_fmt(f['max'])}';
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Expanded(
            child: Tooltip(
              message: help.isEmpty ? 'Allowed: $range' : '$help\nAllowed: $range',
              child: Text(
                f['label'] as String,
                style: TextStyle(
                  fontWeight: changed ? FontWeight.w700 : null,
                  color: changed ? AppColors.purple : null,
                ),
              ),
            ),
          ),
          SizedBox(
            width: 110,
            child: TextField(
              key: Key('field_$key'),
              controller: controller,
              textAlign: TextAlign.right,
              keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
              decoration: InputDecoration(isDense: true, border: const OutlineInputBorder(), helperText: range),
              onChanged: (_) => setState(() {}),
            ),
          ),
        ],
      ),
    );
  }

  Widget _historyCard(Map<String, dynamic> h, {required bool live}) {
    final changes = [for (final c in h['changes'] as List) Map<String, dynamic>.from(c as Map)];
    final number = h['number'] as int;
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 12, 12, 12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            CircleAvatar(
              radius: 16,
              backgroundColor: live ? AppColors.purple : AppColors.lavender,
              child: Text('$number', style: TextStyle(color: live ? Colors.white : AppColors.purpleDark, fontSize: 13)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    [
                      if ('${h['note']}'.isNotEmpty) '${h['note']}' else 'Version $number',
                      if (live) '(live)',
                    ].join('  '),
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                  if (h['created_by'] != '')
                    Text(
                      '${h['created_by']} · ${_date(h['created_at'] as String?)}',
                      style: const TextStyle(fontSize: 12, color: Colors.black54),
                    ),
                  for (final c in changes.take(8))
                    Text('${c['label']}: ${_fmt(c['old'])} → ${_fmt(c['new'])}', style: const TextStyle(fontSize: 13)),
                  if (changes.length > 8)
                    Text('… and ${changes.length - 8} more', style: const TextStyle(fontSize: 13)),
                ],
              ),
            ),
            if (!live)
              TextButton.icon(
                key: Key('restore_$number'),
                onPressed: () => _restore(number),
                icon: const Icon(Icons.undo, size: 18),
                label: Text(number == 0 ? 'Back to defaults' : 'Undo to this'),
              ),
          ],
        ),
      ),
    );
  }
}
