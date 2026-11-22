// API keys & AI model (Phase 10A step A5, owner only).
// Keys: write-only - the panel shows only where a key comes from and its last 4 characters; a new key is tested
// with its provider before it is saved. AI model: approved versions, a test run on the data set (scams caught,
// normal messages flagged), and switching / rolling back after a finished test.

import 'dart:async';

import 'package:flutter/material.dart';

import '../api.dart';
import '../theme/app_theme.dart';
import 'shell.dart';

String _date(String? iso) {
  final t = iso == null ? null : DateTime.tryParse(iso)?.toLocal();
  if (t == null) return '';
  String two(int n) => n.toString().padLeft(2, '0');
  return '${t.year}-${two(t.month)}-${two(t.day)} ${two(t.hour)}:${two(t.minute)}';
}

class KeysModelScreen extends StatefulWidget {
  final AdminApi api;
  final void Function(Object error) onError;
  const KeysModelScreen({super.key, required this.api, required this.onError});

  @override
  State<KeysModelScreen> createState() => _KeysModelScreenState();
}

class _KeysModelScreenState extends State<KeysModelScreen> {
  List<Map<String, dynamic>>? _keys;
  Map<String, dynamic>? _model;
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final k = await widget.api.keys();
      final m = await widget.api.model();
      if (!mounted) return;
      setState(() {
        _keys = k;
        _model = m;
      });
      _pollIfBusy(m);
    } catch (e) {
      widget.onError(e);
    }
  }

  /// While a test runs or a switch loads, refresh every 3 seconds.
  void _pollIfBusy(Map<String, dynamic> m) {
    final busy =
        (m['live'] as Map)['switching_to'] != null ||
        (m['versions'] as List).any((v) => ((v as Map)['last_test'] as Map?)?['status'] == 'running');
    _poll?.cancel();
    if (busy) _poll = Timer(const Duration(seconds: 3), _load);
  }

  void _snack(String text) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _editKey(Map<String, dynamic> k) async {
    final saved = await showDialog<bool>(
      context: context,
      builder: (_) => _KeyDialog(api: widget.api, keyInfo: k),
    );
    if (saved == true) {
      _snack('${k['label']} saved and in use.');
      _load();
    }
  }

  Future<void> _removeKey(Map<String, dynamic> k) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Remove the ${k['label']} saved here?'),
        content: const Text('The key from the server\'s .env file is used again (if there is one).'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Remove')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await widget.api.deleteKey(k['name'] as String);
      _snack('Key removed.');
      _load();
    } catch (e) {
      widget.onError(e);
    }
  }

  Future<void> _test(String id) async {
    try {
      await widget.api.startModelTest(id);
      _snack('Test started. It takes a few minutes; checks still work meanwhile.');
      _load();
    } catch (e) {
      widget.onError(e);
    }
  }

  Future<void> _switch(Map<String, dynamic> v) async {
    final note = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Use ${v['label']}?'),
        content: SizedBox(
          width: 420,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'It loads in the background (about a minute). Checks keep using the current version '
                'until it is ready. You can switch back at any time.',
              ),
              TextField(
                controller: note,
                decoration: const InputDecoration(labelText: 'Note (why?)'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            key: const Key('confirmSwitch'),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Switch'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await widget.api.switchModel(v['id'] as String, note.text.trim());
      _snack('Loading ${v['label']}…');
      _load();
    } catch (e) {
      widget.onError(e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final keys = _keys, model = _model;
    return SectionPage(
      title: 'API keys & AI model',
      about: 'Keys are never shown – only where they come from and their last 4 characters.',
      action: IconButton(tooltip: 'Reload', icon: const Icon(Icons.refresh), onPressed: _load),
      children: keys == null || model == null
          ? [const Center(child: CircularProgressIndicator())]
          : [
              const _Heading('API keys'),
              for (final k in keys) _keyCard(k),
              const SizedBox(height: 24),
              const _Heading('AI model'),
              _liveCard(Map<String, dynamic>.from(model['live'] as Map)),
              const SizedBox(height: 10),
              for (final v in model['versions'] as List) _versionCard(Map<String, dynamic>.from(v as Map)),
              if ((model['history'] as List).isNotEmpty) ...[
                const SizedBox(height: 14),
                const Text('Switches', style: TextStyle(fontWeight: FontWeight.w700)),
                for (final h in model['history'] as List)
                  Text(
                    '${_date((h as Map)['created_at'] as String?)} · ${h['version_id']} · ${h['chosen_by']}'
                    '${'${h['note']}'.isEmpty ? '' : ' – ${h['note']}'}',
                  ),
              ],
            ],
    );
  }

  Widget _keyCard(Map<String, dynamic> k) {
    final source = k['source'] as String;
    final (text, color) = switch (source) {
      'panel' => ('Saved here · ends in ${k['last4']}', AppColors.protectedGreen),
      '.env' => ('From the server .env file · ends in ${k['last4']}', AppColors.purple),
      _ => ('Not set', Colors.black45),
    };
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 14, 12, 14),
        child: Row(
          children: [
            const Icon(Icons.key, color: AppColors.purple),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${k['label']}', style: const TextStyle(fontWeight: FontWeight.w700)),
                  Text(
                    text,
                    key: Key('keySource_${k['name']}'),
                    style: TextStyle(color: color),
                  ),
                  if (source == 'panel')
                    Text(
                      'by ${k['updated_by']} · ${_date(k['updated_at'] as String?)}'
                      '${k['tested_ok'] == true ? ' · tested ✓' : ' · saved without a test'}',
                      style: const TextStyle(fontSize: 12, color: Colors.black54),
                    ),
                  Text('${k['help']}', style: const TextStyle(fontSize: 12, color: Colors.black54)),
                ],
              ),
            ),
            if (source == 'panel')
              IconButton(tooltip: 'Remove', icon: const Icon(Icons.delete_outline), onPressed: () => _removeKey(k)),
            FilledButton.tonal(
              key: Key('editKey_${k['name']}'),
              onPressed: () => _editKey(k),
              child: Text(source == 'none' ? 'Add key' : 'Replace'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _liveCard(Map<String, dynamic> live) {
    final switching = live['switching_to'];
    return Card(
      margin: EdgeInsets.zero,
      child: ListTile(
        leading: Icon(
          Icons.memory,
          color: live['status'] == 'ready' ? AppColors.protectedGreen : AppColors.warningOrange,
        ),
        title: Text(
          'In use: ${live['version'] ?? live['version_id']}',
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
        subtitle: Text(
          switching != null
              ? 'Loading $switching… checks keep using the current version until it is ready.'
              : 'Status: ${live['status']}${live['load_seconds'] == null ? '' : ' · loaded in ${(live['load_seconds'] as num).round()} s'}',
        ),
      ),
    );
  }

  Widget _versionCard(Map<String, dynamic> v) {
    final t = v['last_test'] == null ? null : Map<String, dynamic>.from(v['last_test'] as Map);
    final r = t == null ? null : Map<String, dynamic>.from(t['result'] as Map);
    final running = t?['status'] == 'running';
    final done = t?['status'] == 'done';
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${v['label']}', style: const TextStyle(fontWeight: FontWeight.w700)),
                      Text(
                        '${v['model_id']} @ ${(v['revision'] as String).substring(0, 7)}'
                        '${v['live'] == true ? ' · in use' : ''}'
                        '${v['downloaded'] == true || v['live'] == true ? '' : ' · not downloaded on the server'}',
                        style: const TextStyle(fontSize: 12, color: Colors.black54),
                      ),
                    ],
                  ),
                ),
                OutlinedButton.icon(
                  key: Key('testModel_${v['id']}'),
                  onPressed: running ? null : () => _test(v['id'] as String),
                  icon: const Icon(Icons.science_outlined, size: 18),
                  label: Text(running ? 'Testing…' : 'Run test'),
                ),
                const SizedBox(width: 8),
                if (v['live'] != true)
                  FilledButton(
                    key: Key('switchModel_${v['id']}'),
                    onPressed: done ? () => _switch(v) : null,
                    child: const Text('Use this version'),
                  ),
              ],
            ),
            if (running) ...[
              const SizedBox(height: 12),
              LinearProgressIndicator(
                value: (r?['total'] as num? ?? 0) == 0 ? null : (r!['done'] as num) / (r['total'] as num),
                color: AppColors.purple,
                backgroundColor: AppColors.lavender,
              ),
              Text('${r?['done'] ?? 0} of ${r?['total'] ?? '?'} messages'),
            ],
            if (t?['status'] == 'failed')
              Text('Last test failed (${r?['error']}).', style: const TextStyle(color: Color(0xFFC62828))),
            if (done && r != null) ...[
              const SizedBox(height: 12),
              Text(
                'Last test: ${_date(t!['finished_at'] as String?)} · ${r['messages']} messages · MIRA + message rules only '
                '(no OTX / WHOIS)',
                style: const TextStyle(fontSize: 12, color: Colors.black54),
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: [
                  _Metric('Scams caught', r['scams_caught_pct'], good: true),
                  _Metric('Scams Dangerous', r['scams_dangerous_pct'], good: true),
                  _Metric('Normal → Dangerous', r['normal_dangerous_pct'], good: false),
                  _Metric('Normal → Suspicious', r['normal_suspicious_pct'], good: false),
                  _Metric('Ads → Dangerous', r['ads_dangerous_pct'], good: false),
                  _Metric('MIRA time', r['avg_mira_ms'], unit: ' ms'),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Heading extends StatelessWidget {
  final String text;
  const _Heading(this.text);
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: Text(
      text,
      style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700, color: AppColors.purpleDark),
    ),
  );
}

/// One number from a test run. `good` = higher is better (green) / lower is better (red when high).
class _Metric extends StatelessWidget {
  final String label;
  final Object? value;
  final bool? good;
  final String unit;
  const _Metric(this.label, this.value, {this.good, this.unit = '%'});

  @override
  Widget build(BuildContext context) {
    final n = value as num?;
    Color color = AppColors.ink;
    if (n != null && good != null && unit == '%') {
      color = good!
          ? (n >= 80 ? AppColors.protectedGreen : AppColors.warningOrange)
          : (n <= 5 ? AppColors.protectedGreen : const Color(0xFFC62828));
    }
    return Container(
      width: 150,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: AppColors.contentFill, borderRadius: BorderRadius.circular(12)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            n == null ? '–' : '${unit == '%' ? n.toStringAsFixed(n % 1 == 0 ? 0 : 1) : n}$unit',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: color),
          ),
          Text(label, style: const TextStyle(fontSize: 12, color: Colors.black54)),
        ],
      ),
    );
  }
}

/// Add / replace a key: type it (hidden), test it, save. The value never comes back from the server.
class _KeyDialog extends StatefulWidget {
  final AdminApi api;
  final Map<String, dynamic> keyInfo;
  const _KeyDialog({required this.api, required this.keyInfo});

  @override
  State<_KeyDialog> createState() => _KeyDialogState();
}

class _KeyDialogState extends State<_KeyDialog> {
  final _value = TextEditingController();
  bool _hide = true;
  bool _busy = false;
  String? _message;
  bool? _ok;
  bool _offerSkip = false;

  String get _name => widget.keyInfo['name'] as String;

  Future<void> _run(Future<void> Function() action) async {
    if (_value.text.trim().length < 8) {
      setState(() {
        _message = 'The key looks too short.';
        _ok = false;
      });
      return;
    }
    setState(() => _busy = true);
    try {
      await action();
    } on AdminApiException catch (e) {
      setState(() {
        _message = e.message;
        _ok = false;
        _offerSkip = e.statusCode == 502;
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _test() => _run(() async {
    final r = await widget.api.testKey(_name, _value.text.trim());
    setState(() {
      _message = r['message'] as String;
      _ok = r['ok'] as bool?;
    });
  });

  Future<void> _save({bool skip = false}) => _run(() async {
    await widget.api.saveKey(_name, _value.text.trim(), skipTest: skip);
    if (mounted) Navigator.pop(context, true);
  });

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text('${widget.keyInfo['label']}'),
    content: SizedBox(
      width: 440,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${widget.keyInfo['help']}', style: const TextStyle(fontSize: 13, color: Colors.black54)),
          const SizedBox(height: 12),
          TextField(
            key: const Key('keyValue'),
            controller: _value,
            obscureText: _hide,
            autocorrect: false,
            enableSuggestions: false,
            decoration: InputDecoration(
              labelText: 'New key',
              border: const OutlineInputBorder(),
              suffixIcon: IconButton(
                icon: Icon(_hide ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                onPressed: () => setState(() => _hide = !_hide),
              ),
            ),
          ),
          if (_message != null)
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Text(
                _message!,
                key: const Key('keyMessage'),
                style: TextStyle(color: _ok == true ? AppColors.protectedGreen : const Color(0xFFC62828)),
              ),
            ),
        ],
      ),
    ),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
      if (_offerSkip) TextButton(onPressed: _busy ? null : () => _save(skip: true), child: const Text('Save anyway')),
      OutlinedButton(key: const Key('testKey'), onPressed: _busy ? null : _test, child: const Text('Test')),
      FilledButton(key: const Key('saveKey'), onPressed: _busy ? null : _save, child: const Text('Test and save')),
    ],
  );
}
