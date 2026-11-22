// Test lab (Phase 10A step A7, owner's flow since B8): paste a message, pick where it came from, and see exactly how
// the live system judges it - the owner's output (Probability + Class), MIRA's probability for each of the five
// classes and each of the five questions, the Context (URL, IP Reputation, Domain Information), the full prompt MIRA
// was shown, the link facts, skipped parts and timings. Nothing is saved to any user's history.

import 'package:flutter/material.dart';

import '../api.dart';
import '../theme/app_theme.dart';
import 'shell.dart';

/// Colours of the owner's five classes (same as the phone app).
const classColor = {
  'low': Color(0xFF2E7D32),
  'suspicious': Color(0xFFF9A825),
  'high': Color(0xFFEF6C00),
  'critical': Color(0xFFD84315),
  'very_harmful': Color(0xFFB71C1C),
};

const _sources = ['SMS', 'WhatsApp', 'WhatsApp Business', 'Viber', 'Messenger', 'Telegram', 'Pasted into CheckScam'];

String _ms(Object? v) {
  if (v == null) return '–';
  final n = (v as num).toInt();
  return n >= 1000 ? '${(n / 1000).toStringAsFixed(1)} s' : '$n ms';
}

String _pct(Object? v) => v == null ? '–' : '${((v as num) * 100).toStringAsFixed(0)}%';

class TestLabScreen extends StatefulWidget {
  final AdminApi api;
  final void Function(Object error) onError;
  const TestLabScreen({super.key, required this.api, required this.onError});

  @override
  State<TestLabScreen> createState() => _TestLabScreenState();
}

class _TestLabScreenState extends State<TestLabScreen> {
  final _text = TextEditingController();
  String _source = 'SMS';
  String _contact = 'unknown'; // sender trust, as the phone would send it: unknown | yes | no
  final _seen = TextEditingController();
  bool _lookups = true;
  bool _busy = false;
  Map<String, dynamic>? _r;
  String? _problem;

  static const _examples = {
    'Hospital (example 1)': 'दाइ मा अस्पताल मा छु दुर्घटना भको छ रु १०,००० पठाउ त एकदम जरुरी छ ।',
    'Free Rs 1,700 (example 2)':
        'https://gzukw.buzz/lCNnbWPxgz/np-en?1121151371053211318&s=ms&t=1795230523& 🎉१७औँ वार्षिकोत्सवको अवसरमा '
        'रु. १,७०० निःशुल्क प्राप्त गर्नुहोस्!💸 gzukw.buzz',
    'Fake KYC':
        'Dear customer, your eSewa wallet will be BLOCKED today due to incomplete KYC. Update now: '
        'http://esewa-kyc.xyz/login',
    'Normal': 'Hi, are we still meeting at 5 today? Let me know.',
  };

  Future<void> _run() async {
    if (_text.text.trim().isEmpty) {
      setState(() => _problem = 'Paste a message first.');
      return;
    }
    setState(() {
      _busy = true;
      _problem = null;
    });
    try {
      final seen = int.tryParse(_seen.text.trim());
      final r = await widget.api.testLab(_text.text,
          source: _source,
          linkLookups: _lookups,
          inContacts: _contact == 'unknown' ? null : _contact == 'yes',
          seenBefore: seen == null || seen < 0 ? null : seen);
      if (mounted) setState(() => _r = r);
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
    final r = _r;
    return SectionPage(
      title: 'Test lab',
      about: 'Paste a message to see exactly how the live system judges it (trained model, link lookups, the five '
          'questions and sender trust). A check takes a few seconds. Nothing is saved to any history.',
      children: [
        Card(
          margin: EdgeInsets.zero,
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    const Padding(padding: EdgeInsets.only(top: 6), child: Text('Examples: ')),
                    for (final e in _examples.entries)
                      ActionChip(label: Text(e.key), onPressed: () => setState(() => _text.text = e.value)),
                  ],
                ),
                const SizedBox(height: 12),
                TextField(
                  key: const Key('labText'),
                  controller: _text,
                  minLines: 3,
                  maxLines: 8,
                  decoration: const InputDecoration(labelText: 'Message', border: OutlineInputBorder()),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 16,
                  runSpacing: 8,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    SizedBox(
                      width: 260,
                      child: DropdownButtonFormField<String>(
                        key: const Key('labSource'),
                        initialValue: _source,
                        isExpanded: true, // long names ("Pasted into CheckScam") are cut instead of overflowing
                        decoration: const InputDecoration(
                          labelText: 'Source (where it came from)',
                          isDense: true,
                          border: OutlineInputBorder(),
                        ),
                        items: [for (final s in _sources) DropdownMenuItem(value: s, child: Text(s))],
                        onChanged: (v) => setState(() => _source = v ?? 'SMS'),
                      ),
                    ),
                    SizedBox(
                      width: 210,
                      child: DropdownButtonFormField<String>(
                        key: const Key('labContact'),
                        initialValue: _contact,
                        isExpanded: true,
                        decoration: const InputDecoration(
                          labelText: 'Sender in contacts?',
                          isDense: true,
                          border: OutlineInputBorder(),
                        ),
                        items: const [
                          DropdownMenuItem(value: 'unknown', child: Text('Unknown')),
                          DropdownMenuItem(value: 'yes', child: Text('Yes, saved contact')),
                          DropdownMenuItem(value: 'no', child: Text('No')),
                        ],
                        onChanged: (v) => setState(() => _contact = v ?? 'unknown'),
                      ),
                    ),
                    SizedBox(
                      width: 210,
                      child: TextField(
                        key: const Key('labSeen'),
                        controller: _seen,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          labelText: 'Messages seen before',
                          hintText: 'empty = unknown, 0 = new',
                          isDense: true,
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ),
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Switch(
                          key: const Key('labLookups'),
                          value: _lookups,
                          onChanged: (v) => setState(() => _lookups = v),
                        ),
                        const Text('Look links up in AlienVault OTX (uses OTX quota)'),
                      ],
                    ),
                  ],
                ),
                if (_problem != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: Text(_problem!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                  ),
                const SizedBox(height: 12),
                Align(
                  alignment: Alignment.centerRight,
                  child: FilledButton.icon(
                    key: const Key('labRun'),
                    onPressed: _busy ? null : _run,
                    icon: _busy
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        : const Icon(Icons.science_outlined),
                    label: Text(_busy ? 'Checking…' : 'Check'),
                  ),
                ),
              ],
            ),
          ),
        ),
        if (r != null) ..._result(r),
      ],
    );
  }

  List<Widget> _result(Map<String, dynamic> r) {
    final riskClass = r['risk_class'] as String?;
    final color = classColor[riskClass] ?? Colors.grey;
    final owner = r['owner_result'] == null ? null : Map<String, dynamic>.from(r['owner_result'] as Map);
    final detail = Map<String, dynamic>.from(r['detail'] as Map? ?? {});
    final mira = detail['mira'] == null ? null : Map<String, dynamic>.from(detail['mira'] as Map);
    // one entry per site: "https://x.xyz/a" and the bare "x.xyz" in the same message are the same site
    final seenHosts = <String>{};
    final links = [
      for (final l in detail['links'] as List? ?? [])
        if (seenHosts.add('${(l as Map)['host'] ?? l['domain']}'.toLowerCase())) Map<String, dynamic>.from(l),
    ];
    final context = Map<String, dynamic>.from(r['context'] as Map? ?? {});
    final timings = Map<String, dynamic>.from(r['timings_ms'] as Map? ?? {});
    final skipped = [for (final s in r['checks_skipped'] as List? ?? []) '$s'];
    return [
      const SizedBox(height: 20),
      Card(
        key: const Key('labVerdict'),
        margin: EdgeInsets.zero,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Row(
            children: [
              Container(
                width: 84,
                height: 84,
                alignment: Alignment.center,
                decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(18)),
                child: Text(
                  owner == null ? '–' : '${r['score']}%',
                  style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.w900),
                ),
              ),
              const SizedBox(width: 18),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      owner == null ? 'NOT CHECKED' : '${owner['Class']}',
                      style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: color),
                    ),
                    if (owner != null)
                      SelectableText(
                        '{"Probability": "${owner['Probability']}", "Class": "${owner['Class']}"}',
                        key: const Key('labOwnerResult'),
                        style: const TextStyle(fontFamily: 'monospace', fontSize: 13),
                      ),
                    if (r['decided_by'] == 'trained_model')
                      Text(
                        'Decided by the trained model (${r['trained_model']['model']}, T=${r['trained_model']['temperature']})'
                        '${r['trained_model']['questions_asked'] == true ? " · brackets from old MIRA's answers" : ' · the five questions answered instantly'}',
                        key: const Key('labDecidedBy'),
                        style: const TextStyle(fontSize: 13, color: AppColors.purpleDark),
                      ),
                    if ((r['sender_trust'] as List? ?? []).isNotEmpty)
                      Text(
                        '${r['decided_by'] == 'trained_model' ? 'Trained model' : 'MIRA'} said ${r['mira_probability']}% → sender trust '
                        '${[for (final x in r['sender_trust'] as List) '${(x as Map)['points'] > 0 ? '+' : ''}${x['points']} ${x['text']}'].join(', ')}'
                        ' → ${r['score']}%',
                        key: const Key('labTrust'),
                        style: const TextStyle(fontSize: 13, color: AppColors.purpleDark),
                      ),
                    const SizedBox(height: 4),
                    Text('${r['suggestion']}'),
                    const SizedBox(height: 6),
                    Text(
                      'Phone verdict: ${r['verdict']} · settings v${r['settings_version']} · prompt ${r['prompt_version']} · '
                      '${r['model_version'] == '' ? 'MIRA not used' : r['model_version']}',
                      style: const TextStyle(fontSize: 12, color: Colors.black54),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
      const SizedBox(height: 14),
      _box(
        r['decided_by'] == 'trained_model' ? 'Old MIRA' : 'MIRA',
        mira == null
            ? Text(skipped.contains('mira')
                ? 'MIRA gave no answer (switched off, still loading or too slow).'
                : r['decided_by'] == 'trained_model'
                    ? 'Not used: old MIRA is replaced by the trained model. The five questions are answered instantly from words, OTX and WHOIS.'
                    : 'Not used.')
            : _miraView(mira),
      ),
      const SizedBox(height: 14),
      _box(
        'Context (what the prompt was filled with)',
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final k in const [
              ('source', 'Source'),
              ('url', 'URL'),
              ('ip_reputation', 'IP Reputation (AlienVault OTX)'),
            ])
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: SelectableText.rich(TextSpan(children: [
                  TextSpan(text: '${k.$2}: ', style: const TextStyle(fontWeight: FontWeight.w700)),
                  TextSpan(text: '${context[k.$1] ?? '–'}'),
                ])),
              ),
          ],
        ),
      ),
      const SizedBox(height: 14),
      _box(
        'Links',
        links.isEmpty
            ? const Text('No links in the message.')
            : Column(children: [for (final l in links) _linkView(l)]),
      ),
      const SizedBox(height: 14),
      _box(
        'Other facts',
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Skipped parts: ${skipped.isEmpty ? 'none' : skipped.join(', ')}'),
            const SizedBox(height: 8),
            Wrap(
              spacing: 10,
              children: [
                for (final k in ['links', 'trained_model', 'mira', 'total'])
                  if (timings.containsKey(k)) Chip(label: Text('$k: ${_ms(timings[k])}'), side: BorderSide.none),
              ],
            ),
            const SizedBox(height: 8),
            const Text('Masked text (what is stored and what fills "Content"):', style: TextStyle(color: Colors.black54)),
            SelectableText('${r['masked_text']}'),
          ],
        ),
      ),
    ];
  }

  Widget _miraView(Map<String, dynamic> mira) {
    final classes = [for (final c in mira['classes'] as List) Map<String, dynamic>.from(c as Map)];
    final questions = [for (final q in mira['questions'] as List) Map<String, dynamic>.from(q as Map)];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Which class fits? (Probability = Σ class probability × anchor)',
            style: TextStyle(fontWeight: FontWeight.w600)),
        for (final c in classes)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 3),
            child: Row(
              children: [
                SizedBox(width: 46, child: Text(_pct(c['p']), textAlign: TextAlign.right)),
                const SizedBox(width: 8),
                SizedBox(
                  width: 140,
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(
                      value: (c['p'] as num).toDouble(),
                      minHeight: 8,
                      color: classColor[c['id']],
                      backgroundColor: AppColors.lavender,
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(child: Text('${c['label']}  (${c['range']}, anchor ${c['anchor']})')),
              ],
            ),
          ),
        const SizedBox(height: 12),
        const Text('The five questions', style: TextStyle(fontWeight: FontWeight.w600)),
        for (final q in questions)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(q['warning'] == true ? Icons.warning_amber_rounded : Icons.check_circle_outline,
                    size: 18, color: q['warning'] == true ? AppColors.warningOrange : AppColors.protectedGreen),
                const SizedBox(width: 6),
                Expanded(
                  child: Text('${_pct(q['p_yes'])} Yes · ${q['n']}. ${q['text']}'
                      '${q['warning'] == true ? '  → warning' : ''}'),
                ),
              ],
            ),
          ),
        const SizedBox(height: 8),
        ExpansionTile(
          key: const Key('labPrompt'),
          tilePadding: EdgeInsets.zero,
          title: const Text('The prompt MIRA was shown'),
          children: [
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              color: AppColors.contentFill,
              child: SelectableText('${mira['prompt']}', style: const TextStyle(fontFamily: 'monospace', fontSize: 12)),
            ),
          ],
        ),
      ],
    );
  }

  Widget _linkView(Map<String, dynamic> l) {
    final whois = l['whois'] == null ? null : Map<String, dynamic>.from(l['whois'] as Map);
    final facts = <String>[
      if (l['ip'] != null) 'IP ${l['ip']}',
      if (l['country'] != null) 'country ${l['country']}',
      if (l['otx_text'] != null) 'OTX: ${l['otx_text']}' else 'OTX: no reply',
      if (whois != null && '${whois['registered_on']}'.isNotEmpty) 'registered ${whois['registered_on']}',
      if (l['domain_age_days'] != null) '${l['domain_age_days']} days old',
      if (l['registrar'] != null) 'registrar ${l['registrar']}',
      if (l['shared_hosting'] == true) 'shared hosting',
    ];
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${l['host']}', style: const TextStyle(fontWeight: FontWeight.w700)),
          Text(facts.join(' · '), style: const TextStyle(fontSize: 13)),
        ],
      ),
    );
  }

  Widget _box(String title, Widget child) => Card(
    margin: EdgeInsets.zero,
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: AppColors.purpleDark),
          ),
          const SizedBox(height: 10),
          child,
        ],
      ),
    ),
  );
}
