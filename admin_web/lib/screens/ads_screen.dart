// Ads (Phase 10A step A9): the home-screen banner in the phone app. Create or change an ad (title, text, link,
// language, start / end date, optional PNG/JPEG picture), see whether its link passed the safety check (OTX, WHOIS
// domain age, block list - a risky link cannot be switched on), switch it on/off, re-check, delete, views and clicks.

import 'package:flutter/material.dart';

import '../api.dart';
import '../pick_image.dart';
import '../theme/app_theme.dart';
import 'shell.dart';

const _statusColor = {
  'showing': Color(0xFF2E7D32),
  'scheduled': Color(0xFF1565C0),
  'ended': Colors.grey,
  'off': Colors.grey,
};

String _day(String iso) => iso.substring(0, 10);

class AdsScreen extends StatefulWidget {
  final AdminApi api;
  final void Function(Object error) onError;
  const AdsScreen({super.key, required this.api, required this.onError});

  @override
  State<AdsScreen> createState() => _AdsScreenState();
}

class _AdsScreenState extends State<AdsScreen> {
  List<Map<String, dynamic>>? _ads;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final ads = await widget.api.ads();
      if (mounted) setState(() => _ads = ads);
    } catch (e) {
      widget.onError(e);
    }
  }

  Future<void> _edit([Map<String, dynamic>? ad]) async {
    final saved = await showDialog<bool>(
      context: context,
      builder: (_) => _AdDialog(api: widget.api, ad: ad),
    );
    if (saved == true) _load();
  }

  Future<void> _run(Future<void> Function() action, String done) async {
    try {
      await action();
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(done)));
      _load();
    } on AdminApiException catch (e) {
      if (e.signedOut) {
        widget.onError(e);
      } else if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final ads = _ads;
    return SectionPage(
      title: 'Ads',
      about: 'The small banner on the app\'s home screen (never on a scam result). An ad shows between its dates, in '
          'its language, and only if its link passed the safety check: no OTX threat reports, domain at least 30 '
          'days old, not on the block list.',
      action: FilledButton.icon(
        key: const Key('newAd'),
        onPressed: () => _edit(),
        icon: const Icon(Icons.add),
        label: const Text('New ad'),
      ),
      children: ads == null
          ? const [Center(child: Padding(padding: EdgeInsets.all(40), child: CircularProgressIndicator()))]
          : ads.isEmpty
              ? const [Card(child: Padding(padding: EdgeInsets.all(24), child: Text('No ads yet. The app shows no banner.')))]
              : [for (final ad in ads) _card(ad)],
    );
  }

  Widget _card(Map<String, dynamic> ad) {
    final check = Map<String, dynamic>.from(ad['link_check'] as Map? ?? {});
    final problems = [for (final p in check['problems'] as List? ?? []) '$p'];
    final notes = [for (final n in check['notes'] as List? ?? []) '$n'];
    final status = ad['status'] as String;
    return Card(
      key: Key('ad_${ad['id']}'),
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: SizedBox(
              width: 96,
              height: 96,
              child: ad['image_url'] == null
                  ? Container(color: AppColors.lavender, child: const Icon(Icons.campaign_outlined, size: 40))
                  : Image.network(widget.api.adImageUrl(ad['image_url'] as String).toString(), fit: BoxFit.cover,
                      errorBuilder: (_, _, _) => const Icon(Icons.broken_image_outlined)),
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Expanded(child: Text('${ad['title']}', style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700))),
                Chip(
                  label: Text(status.toUpperCase(), style: const TextStyle(color: Colors.white, fontSize: 11)),
                  backgroundColor: _statusColor[status] ?? Colors.grey,
                  side: BorderSide.none,
                ),
              ]),
              if ('${ad['body']}'.isNotEmpty) Text('${ad['body']}'),
              Text('${ad['link']}', style: const TextStyle(fontSize: 13, color: AppColors.purpleDark)),
              const SizedBox(height: 4),
              Text('${_day(ad['starts_at'] as String)} → ${_day(ad['ends_at'] as String)} · language: ${ad['language']} · '
                  '${ad['views']} views · ${ad['clicks']} taps (${((ad['click_rate'] as num) * 100).toStringAsFixed(1)}%)',
                  style: const TextStyle(fontSize: 12, color: Colors.black54)),
              const SizedBox(height: 6),
              Row(children: [
                Icon(check['ok'] == true ? Icons.verified_outlined : Icons.gpp_bad_outlined,
                    size: 18, color: check['ok'] == true ? AppColors.protectedGreen : const Color(0xFFB71C1C)),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    check['ok'] == true ? 'Link passed the safety check' : 'Link failed: ${problems.join(' ')}',
                    key: Key('adCheck_${ad['id']}'),
                    style: TextStyle(fontSize: 13, color: check['ok'] == true ? AppColors.protectedGreen : const Color(0xFFB71C1C)),
                  ),
                ),
              ]),
              for (final n in notes) Text('· $n', style: const TextStyle(fontSize: 12, color: Colors.black54)),
              const SizedBox(height: 6),
              Wrap(spacing: 8, children: [
                OutlinedButton(onPressed: () => _edit(ad), child: const Text('Edit')),
                OutlinedButton(
                  onPressed: () => _run(() => widget.api.recheckAd(ad['id'] as int), 'Link checked again.'),
                  child: const Text('Check link again'),
                ),
                TextButton(
                  onPressed: () => _run(() => widget.api.deleteAd(ad['id'] as int), 'Ad deleted.'),
                  child: const Text('Delete', style: TextStyle(color: Color(0xFFB71C1C))),
                ),
              ]),
            ]),
          ),
        ]),
      ),
    );
  }
}

class _AdDialog extends StatefulWidget {
  final AdminApi api;
  final Map<String, dynamic>? ad;
  const _AdDialog({required this.api, this.ad});

  @override
  State<_AdDialog> createState() => _AdDialogState();
}

class _AdDialogState extends State<_AdDialog> {
  late final _title = TextEditingController(text: widget.ad?['title'] as String? ?? '');
  late final _body = TextEditingController(text: widget.ad?['body'] as String? ?? '');
  late final _link = TextEditingController(text: widget.ad?['link'] as String? ?? 'https://');
  late String _language = widget.ad?['language'] as String? ?? 'all';
  late DateTime _start = DateTime.tryParse(widget.ad?['starts_at'] as String? ?? '')?.toLocal() ?? DateTime.now();
  late DateTime _end =
      DateTime.tryParse(widget.ad?['ends_at'] as String? ?? '')?.toLocal() ?? DateTime.now().add(const Duration(days: 14));
  late bool _active = widget.ad?['active'] as bool? ?? true;
  String? _image; // data URL of a newly picked picture; "" = remove; null = keep
  bool _busy = false;
  String? _problem;

  Future<void> _pick() async {
    final data = await pickImageDataUrl();
    if (data != null) setState(() => _image = data);
  }

  Future<void> _date(bool start) async {
    final picked = await showDatePicker(
      context: context,
      initialDate: start ? _start : _end,
      firstDate: DateTime.now().subtract(const Duration(days: 365)),
      lastDate: DateTime.now().add(const Duration(days: 730)),
    );
    if (picked != null) setState(() => start ? _start = picked : _end = picked.add(const Duration(hours: 23, minutes: 59)));
  }

  Future<void> _save() async {
    setState(() {
      _busy = true;
      _problem = null;
    });
    try {
      await widget.api.saveAd({
        'title': _title.text.trim(),
        'body': _body.text.trim(),
        'link': _link.text.trim(),
        'language': _language,
        'starts_at': _start.toUtc().toIso8601String(),
        'ends_at': _end.toUtc().toIso8601String(),
        'active': _active,
        'image': _image,
      }, id: widget.ad?['id'] as int?);
      if (mounted) Navigator.pop(context, true);
    } on AdminApiException catch (e) {
      setState(() => _problem = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.ad == null ? 'New ad' : 'Change ad'),
      content: SizedBox(
        width: 460,
        child: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(key: const Key('adTitle'), controller: _title, maxLength: 80,
                decoration: const InputDecoration(labelText: 'Title')),
            TextField(key: const Key('adBody'), controller: _body, maxLength: 200, maxLines: 2,
                decoration: const InputDecoration(labelText: 'Text (optional)')),
            TextField(key: const Key('adLink'), controller: _link,
                decoration: const InputDecoration(labelText: 'Link (checked for safety when saved)')),
            const SizedBox(height: 10),
            DropdownButtonFormField<String>(
              initialValue: _language,
              decoration: const InputDecoration(labelText: 'Language'),
              items: const [
                DropdownMenuItem(value: 'all', child: Text('English and Nepali')),
                DropdownMenuItem(value: 'en', child: Text('English only')),
                DropdownMenuItem(value: 'ne', child: Text('Nepali only')),
              ],
              onChanged: (v) => setState(() => _language = v ?? 'all'),
            ),
            const SizedBox(height: 10),
            Row(children: [
              Expanded(child: OutlinedButton(onPressed: () => _date(true), child: Text('From ${_start.toIso8601String().substring(0, 10)}'))),
              const SizedBox(width: 8),
              Expanded(child: OutlinedButton(onPressed: () => _date(false), child: Text('Until ${_end.toIso8601String().substring(0, 10)}'))),
            ]),
            const SizedBox(height: 10),
            Row(children: [
              OutlinedButton.icon(onPressed: _pick, icon: const Icon(Icons.image_outlined), label: const Text('Picture (PNG/JPEG, 500 KB)')),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  _image == null
                      ? (widget.ad?['has_image'] == true ? 'Keeps the current picture' : 'No picture')
                      : _image == '' ? 'Picture will be removed' : 'New picture chosen',
                  style: const TextStyle(fontSize: 12),
                ),
              ),
              if (_image != '' && (_image != null || widget.ad?['has_image'] == true))
                IconButton(tooltip: 'Remove picture', onPressed: () => setState(() => _image = ''), icon: const Icon(Icons.close)),
            ]),
            SwitchListTile(
              key: const Key('adActive'),
              contentPadding: EdgeInsets.zero,
              title: const Text('Switched on'),
              subtitle: const Text('Only possible when the link passes the check'),
              value: _active,
              onChanged: (v) => setState(() => _active = v),
            ),
            if (_problem != null)
              Text(_problem!, key: const Key('adProblem'), style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ]),
        ),
      ),
      actions: [
        TextButton(onPressed: _busy ? null : () => Navigator.pop(context, false), child: const Text('Cancel')),
        FilledButton(
          key: const Key('adSave'),
          onPressed: _busy ? null : _save,
          child: Text(_busy ? 'Checking the link…' : 'Save'),
        ),
      ],
    );
  }
}
