// App control (Phase 10A step A10): minimum app version ("please update"), latest version and update link, the
// in-app notice in English and Nepali, and the switch that lets phones watch chat apps (WhatsApp, Viber, Messenger).
// The phone also gets the official sender list from the server (shown here for reference).

import 'package:flutter/material.dart';

import '../api.dart';
import '../theme/app_theme.dart';
import 'shell.dart';

class AppControlScreen extends StatefulWidget {
  final AdminApi api;
  final void Function(Object error) onError;
  const AppControlScreen({super.key, required this.api, required this.onError});

  @override
  State<AppControlScreen> createState() => _AppControlScreenState();
}

class _AppControlScreenState extends State<AppControlScreen> {
  final _min = TextEditingController();
  final _latest = TextEditingController();
  final _url = TextEditingController();
  final _titleEn = TextEditingController();
  final _textEn = TextEditingController();
  final _titleNe = TextEditingController();
  final _textNe = TextEditingController();
  bool _noticeOn = false;
  String _level = 'info';
  bool _chatApps = true;
  bool _loaded = false;
  bool _busy = false;
  String? _info;
  String? _problem;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d = await widget.api.appControl();
      final n = Map<String, dynamic>.from(d['notice'] as Map? ?? {});
      setState(() {
        _min.text = '${d['min_version']}';
        _latest.text = '${d['latest_version']}';
        _url.text = '${d['update_url']}';
        _noticeOn = n['active'] == true;
        _level = '${n['level'] ?? 'info'}';
        _titleEn.text = '${n['title_en'] ?? ''}';
        _textEn.text = '${n['text_en'] ?? ''}';
        _titleNe.text = '${n['title_ne'] ?? ''}';
        _textNe.text = '${n['text_ne'] ?? ''}';
        _chatApps = d['chat_apps_allowed'] != false;
        _info = d['updated_by'] == '' ? 'Not changed yet (defaults).' : 'Last changed by ${d['updated_by']}.';
        _loaded = true;
      });
    } catch (e) {
      widget.onError(e);
    }
  }

  Future<void> _save() async {
    setState(() {
      _busy = true;
      _problem = null;
    });
    try {
      await widget.api.saveAppControl({
        'min_version': _min.text.trim(),
        'latest_version': _latest.text.trim(),
        'update_url': _url.text.trim(),
        'chat_apps_allowed': _chatApps,
        'notice': {
          'active': _noticeOn,
          'level': _level,
          'title_en': _titleEn.text.trim(),
          'text_en': _textEn.text.trim(),
          'title_ne': _titleNe.text.trim(),
          'text_ne': _textNe.text.trim(),
        },
      });
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Saved. Phones get it next time they open the app.')));
      _load();
    } on AdminApiException catch (e) {
      if (e.signedOut) {
        widget.onError(e);
      } else {
        setState(() => _problem = e.message);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_loaded) {
      return const Center(child: CircularProgressIndicator());
    }
    return SectionPage(
      title: 'App control',
      about: 'Settings the phone app reads every time it opens: the minimum version, an in-app notice and whether chat '
          'apps may be watched. ${_info ?? ''}',
      children: [
        _box('App version', Column(children: [
          Row(children: [
            Expanded(child: TextField(key: const Key('acMin'), controller: _min,
                decoration: const InputDecoration(labelText: 'Minimum version (older apps must update)', hintText: '1.0.0'))),
            const SizedBox(width: 12),
            Expanded(child: TextField(key: const Key('acLatest'), controller: _latest,
                decoration: const InputDecoration(labelText: 'Latest version', hintText: '1.0.0'))),
          ]),
          TextField(key: const Key('acUrl'), controller: _url,
              decoration: const InputDecoration(labelText: 'Update link (where to get the new app)', hintText: 'https://…')),
        ])),
        const SizedBox(height: 14),
        _box('In-app notice', Column(children: [
          SwitchListTile(
            key: const Key('acNoticeOn'),
            contentPadding: EdgeInsets.zero,
            title: const Text('Show the notice on the home screen'),
            value: _noticeOn,
            onChanged: (v) => setState(() => _noticeOn = v),
          ),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'info', label: Text('Information'), icon: Icon(Icons.info_outline)),
              ButtonSegment(value: 'warning', label: Text('Warning'), icon: Icon(Icons.warning_amber_rounded)),
            ],
            selected: {_level},
            onSelectionChanged: (s) => setState(() => _level = s.first),
          ),
          TextField(key: const Key('acTitleEn'), controller: _titleEn, maxLength: 80,
              decoration: const InputDecoration(labelText: 'Title (English)')),
          TextField(key: const Key('acTextEn'), controller: _textEn, maxLength: 400, maxLines: 2,
              decoration: const InputDecoration(labelText: 'Text (English)')),
          TextField(key: const Key('acTitleNe'), controller: _titleNe, maxLength: 80,
              decoration: const InputDecoration(labelText: 'Title (Nepali)')),
          TextField(key: const Key('acTextNe'), controller: _textNe, maxLength: 400, maxLines: 2,
              decoration: const InputDecoration(labelText: 'Text (Nepali)')),
        ])),
        const SizedBox(height: 14),
        _box('Chat apps', SwitchListTile(
          key: const Key('acChatApps'),
          contentPadding: EdgeInsets.zero,
          title: const Text('Phones may watch WhatsApp, Viber and Messenger'),
          subtitle: const Text('Off: phones check SMS only, and the app hides its chat-apps switch.'),
          value: _chatApps,
          onChanged: (v) => setState(() => _chatApps = v),
        )),
        const SizedBox(height: 14),
        _box('Official senders', const Text('Phones get the official sender list (Data sets → Trusted senders) every '
            'time they open the app, so the on-phone filter matches the server.')),
        if (_problem != null)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(_problem!, key: const Key('acProblem'), style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        const SizedBox(height: 14),
        Align(
          alignment: Alignment.centerRight,
          child: FilledButton(key: const Key('acSave'), onPressed: _busy ? null : _save, child: const Text('Save')),
        ),
      ],
    );
  }

  Widget _box(String title, Widget child) => Card(
    margin: EdgeInsets.zero,
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: AppColors.purpleDark)),
        const SizedBox(height: 10),
        child,
      ]),
    ),
  );
}
