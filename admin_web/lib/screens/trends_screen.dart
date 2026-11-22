// Scam trends (Phase 10A step A8): risk classes per day, top and newest risky link domains, sources and the most
// common warnings over the last 7 or 30 days. Counts and domains only - never message texts.

import 'package:flutter/material.dart';

import '../api.dart';
import '../theme/app_theme.dart';
import 'shell.dart';
import 'test_lab_screen.dart' show classColor;

const _warningNames = {
  'ASKS_CREDENTIALS': 'Asks for OTP / password / bank details',
  'OFFERS_PRIZE': 'Offers a prize / offer / lottery',
  'BAD_IP_REPUTATION': 'Link has a bad IP reputation',
  'BAD_DOMAIN': 'Link has bad domain information',
  'URGENCY': 'Shows urgency',
  'SENDER_NEW': 'First message from a new sender',
  'SENDER_IN_CONTACTS': 'Sender is a saved contact',
  'SENDER_FREQUENT': 'Frequent sender',
};

class TrendsScreen extends StatefulWidget {
  final AdminApi api;
  final void Function(Object error) onError;
  const TrendsScreen({super.key, required this.api, required this.onError});

  @override
  State<TrendsScreen> createState() => _TrendsScreenState();
}

class _TrendsScreenState extends State<TrendsScreen> {
  int _days = 7;
  Map<String, dynamic>? _t;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final t = await widget.api.trends(days: _days);
      if (mounted) setState(() => _t = t);
    } catch (e) {
      widget.onError(e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = _t;
    return SectionPage(
      title: 'Scam trends',
      about: 'What CheckScam saw over the last days: risk classes per day, the riskiest link domains, where messages '
          'came from and the most common warnings. Counts only - message texts are never shown.',
      action: SegmentedButton<int>(
        key: const Key('trendsDays'),
        segments: const [ButtonSegment(value: 7, label: Text('7 days')), ButtonSegment(value: 30, label: Text('30 days'))],
        selected: {_days},
        onSelectionChanged: (s) {
          setState(() {
            _days = s.first;
            _t = null;
          });
          _load();
        },
      ),
      children: t == null
          ? const [Center(child: Padding(padding: EdgeInsets.all(40), child: CircularProgressIndicator()))]
          : [
              Wrap(spacing: 12, runSpacing: 12, children: [
                _stat('Checks', '${t['checks']}'),
                _stat('Critical or very harmful', '${((t['risky_share'] as num) * 100).round()}%'),
                for (final c in t['classes'] as List)
                  _stat('${c['label']}', '${(t['totals'] as Map)[c['id']]}', color: classColor[c['id']] ?? Colors.grey),
              ]),
              const SizedBox(height: 16),
              _box('Risk classes per day', _dayChart(t)),
              const SizedBox(height: 14),
              Wrap(spacing: 14, runSpacing: 14, children: [
                SizedBox(width: 520, child: _box('Most-seen link domains', _domains(t['top_domains'] as List, 'domainsTop'))),
                SizedBox(
                  width: 520,
                  child: _box('Newest risky domains (61%+)', _domains(t['newest_risky_domains'] as List, 'domainsNew')),
                ),
                SizedBox(width: 340, child: _box('Where messages came from', _counts(t['sources'] as Map))),
                SizedBox(width: 400, child: _box('Most common warnings', _counts(t['warnings'] as Map, names: _warningNames))),
              ]),
            ],
    );
  }

  Widget _dayChart(Map<String, dynamic> t) {
    final days = [for (final d in t['per_day'] as List) Map<String, dynamic>.from(d as Map)];
    final classes = [for (final c in t['classes'] as List) '${(c as Map)['id']}'];
    final max = days.fold<int>(1, (m, d) => [m, classes.fold<int>(0, (s, c) => s + (d[c] as int))].reduce((a, b) => a > b ? a : b));
    return SizedBox(
      height: 190,
      child: Row(
        key: const Key('trendsChart'),
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          for (final d in days)
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 2),
                child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
                  Text('${classes.fold<int>(0, (s, c) => s + (d[c] as int))}', style: const TextStyle(fontSize: 10)),
                  for (final c in classes.reversed)
                    if ((d[c] as int) > 0)
                      Container(height: 150 * (d[c] as int) / max, color: classColor[c] ?? Colors.grey),
                  const SizedBox(height: 4),
                  Text((d['day'] as String).substring(5), style: const TextStyle(fontSize: 9, color: Colors.black54)),
                ]),
              ),
            ),
        ],
      ),
    );
  }

  Widget _domains(List rows, String key) => rows.isEmpty
      ? const Text('None in this period.')
      : Column(key: Key(key), children: [
          for (final r in rows)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              title: Text('${(r as Map)['domain']}', style: const TextStyle(fontWeight: FontWeight.w600)),
              subtitle: Text('${r['count']}× · first seen ${(r['first_seen'] as String).substring(0, 10)}'),
              trailing: Text('avg ${r['avg_score']}% · max ${r['max_score']}%',
                  style: TextStyle(color: (r['max_score'] as num) >= 61 ? const Color(0xFFB71C1C) : Colors.black87)),
            ),
        ]);

  Widget _counts(Map m, {Map<String, String> names = const {}}) => m.isEmpty
      ? const Text('None in this period.')
      : Column(children: [
          for (final e in m.entries)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(children: [
                Expanded(child: Text(names['${e.key}'] ?? '${e.key}')),
                Text('${e.value}', style: const TextStyle(fontWeight: FontWeight.w700)),
              ]),
            ),
        ]);

  Widget _stat(String label, String value, {Color color = AppColors.purpleDark}) => Card(
    margin: EdgeInsets.zero,
    child: Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(value, style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: color)),
        Text(label, style: const TextStyle(fontSize: 12, color: Colors.black54)),
      ]),
    ),
  );

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
