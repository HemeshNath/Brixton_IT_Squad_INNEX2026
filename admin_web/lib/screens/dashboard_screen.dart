// Dashboard (Phase 10A step A2): service health, OTX quota, today's numbers, the last 7 days, slowest checks and
// recent server errors. Refreshes itself every 30 seconds.

import 'dart:async';

import 'package:flutter/material.dart';

import '../api.dart';
import '../theme/app_theme.dart';
import 'shell.dart';

const _statusColor = {
  'ok': AppColors.protectedGreen,
  'warning': AppColors.warningOrange,
  'down': Color(0xFFC62828),
  'off': Colors.black38,
};
const _verdictColor = {
  'safe': Color(0xFF2E7D32),
  'suspicious': Color(0xFFEF6C00),
  'dangerous': Color(0xFFC62828),
  'unknown': Colors.grey,
};

/// The owner's five classes (B8) + checks MIRA could not answer, in order, with colour and name.
const _classes = [
  ('low', Color(0xFF2E7D32), 'LOW RISK'),
  ('suspicious', Color(0xFFF9A825), 'SUSPICIOUS'),
  ('high', Color(0xFFEF6C00), 'HIGH RISK'),
  ('critical', Color(0xFFD84315), 'CRITICAL RISK'),
  ('very_harmful', Color(0xFFB71C1C), 'VERY HARMFUL'),
  ('unknown', Colors.grey, 'Not checked'),
];
const _serviceName = {
  'server': 'Server',
  'mira': 'MIRA model',
  'database': 'Database (Supabase)',
  'otx': 'AlienVault OTX',
  'whois': 'WHOIS / domain age',
};

String _ms(Object? v) {
  if (v == null) return '–';
  final n = (v as num).toInt();
  return n >= 1000 ? '${(n / 1000).toStringAsFixed(1)} s' : '$n ms';
}

String _time(String? iso) {
  final t = iso == null ? null : DateTime.tryParse(iso)?.toLocal();
  if (t == null) return '';
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(t.hour)}:${two(t.minute)}';
}

class DashboardScreen extends StatefulWidget {
  final AdminApi api;
  final void Function(Object error) onError;
  const DashboardScreen({super.key, required this.api, required this.onError});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  Map<String, dynamic>? _d;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 30), (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final d = await widget.api.dashboard();
      if (mounted) setState(() => _d = d);
    } catch (e) {
      _timer?.cancel(); // stop polling after an error (e.g. signed out)
      widget.onError(e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = _d;
    return SectionPage(
      title: 'Dashboard',
      about: d == null ? 'Loading…' : 'Updated ${_time(d['generated_at'] as String?)} · refreshes every 30 seconds.',
      action: IconButton(
        key: const Key('refreshDashboard'),
        tooltip: 'Refresh',
        icon: const Icon(Icons.refresh),
        onPressed: _load,
      ),
      children: d == null ? [const Center(child: CircularProgressIndicator())] : _content(d),
    );
  }

  List<Widget> _content(Map<String, dynamic> d) {
    final services = Map<String, dynamic>.from(d['services'] as Map);
    final today = Map<String, dynamic>.from(d['today'] as Map);
    final totals = Map<String, dynamic>.from(d['totals'] as Map);
    final errors = Map<String, dynamic>.from(d['errors'] as Map);
    final quota = Map<String, dynamic>.from(d['otx_quota'] as Map);
    return [
      _Heading('Services'),
      Wrap(
        spacing: 12,
        runSpacing: 12,
        children: [
          for (final e in services.entries)
            _ServiceCard(name: _serviceName[e.key] ?? e.key, data: Map<String, dynamic>.from(e.value as Map)),
        ],
      ),
      const SizedBox(height: 24),
      _Heading('Today (Nepal time)'),
      Wrap(
        spacing: 12,
        runSpacing: 12,
        children: [
          _Tile('Checks', '${today['checks']}', Icons.fact_check_outlined, key: const Key('tileChecks')),
          _Tile('Active users', '${today['active_users']}', Icons.people_alt_outlined),
          _Tile('Average time', _ms(today['avg_ms']), Icons.timer_outlined),
          _Tile(
            'Slowest 10 %',
            _ms(today['p90_ms']),
            Icons.hourglass_bottom,
            hint: '90 % of checks were faster than this',
          ),
          _Tile(
            'Over 5 s',
            '${today['slow_checks']}',
            Icons.warning_amber_rounded,
            alert: (today['slow_checks'] as num) > 0,
          ),
          _Tile(
            'Server errors',
            '${errors['today']}',
            Icons.error_outline,
            alert: (errors['today'] as num) > 0,
            key: const Key('tileErrors'),
          ),
          _Tile('Pending reports', '${totals['pending_reports']}', Icons.flag_outlined),
          _Tile('Known scams', '${totals['known_scams']}', Icons.shield_outlined),
          _Tile('App users', '${totals['users']}', Icons.person_outline),
        ],
      ),
      const SizedBox(height: 16),
      LayoutBuilder(
        builder: (ctx, box) {
          final cards = [
            _VerdictCard(
              verdicts: Map<String, dynamic>.from((today['risk_classes'] ?? today['verdicts']) as Map),
              owner: today['risk_classes'] != null,
            ),
            _QuotaCard(
              used: (quota['used'] as num).toInt(),
              limit: (quota['limit'] as num).toInt(),
              skipped: Map<String, dynamic>.from(today['skipped'] as Map),
            ),
            _WeekCard(week: [for (final w in d['week'] as List) Map<String, dynamic>.from(w as Map)]),
          ];
          return box.maxWidth >= 1000
              ? Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    for (final c in cards)
                      Expanded(
                        child: Padding(padding: const EdgeInsets.only(right: 12), child: c),
                      ),
                  ],
                )
              : Column(
                  children: [for (final c in cards) Padding(padding: const EdgeInsets.only(bottom: 12), child: c)],
                );
        },
      ),
      const SizedBox(height: 24),
      _Heading('Slowest checks today'),
      _SlowestTable(rows: [for (final r in d['slowest'] as List) Map<String, dynamic>.from(r as Map)]),
      const SizedBox(height: 24),
      _Heading('Recent server errors (${errors['since_start']} since the server started)'),
      _ErrorsCard(errors: [for (final e in errors['recent'] as List) Map<String, dynamic>.from(e as Map)]),
    ];
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

class _ServiceCard extends StatelessWidget {
  final String name;
  final Map<String, dynamic> data;
  const _ServiceCard({required this.name, required this.data});

  @override
  Widget build(BuildContext context) {
    final status = data['status'] as String? ?? 'off';
    final color = _statusColor[status] ?? Colors.grey;
    return SizedBox(
      width: 250,
      child: Card(
        margin: EdgeInsets.zero,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                margin: const EdgeInsets.only(top: 4),
                width: 12,
                height: 12,
                decoration: BoxDecoration(color: color, shape: BoxShape.circle),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(name, style: const TextStyle(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 2),
                    Text('${data['note']}', style: TextStyle(color: color, fontSize: 13)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Tile extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final bool alert;
  final String? hint;
  const _Tile(this.label, this.value, this.icon, {super.key, this.alert = false, this.hint});

  @override
  Widget build(BuildContext context) {
    final tile = SizedBox(
      width: 170,
      child: Card(
        margin: EdgeInsets.zero,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, color: alert ? const Color(0xFFC62828) : AppColors.purple, size: 22),
              const SizedBox(height: 8),
              Text(
                value,
                style: TextStyle(
                  fontSize: 26,
                  fontWeight: FontWeight.w800,
                  color: alert ? const Color(0xFFC62828) : AppColors.ink,
                ),
              ),
              Text(label, style: const TextStyle(color: Colors.black54)),
            ],
          ),
        ),
      ),
    );
    return hint == null ? tile : Tooltip(message: hint!, child: tile);
  }
}

class _CardBox extends StatelessWidget {
  final String title;
  final Widget child;
  const _CardBox(this.title, this.child);
  @override
  Widget build(BuildContext context) => Card(
    margin: EdgeInsets.zero,
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          child,
        ],
      ),
    ),
  );
}

class _VerdictCard extends StatelessWidget {
  final Map<String, dynamic> verdicts;
  final bool owner; // true: the owner's classes (B8); false: older safe / suspicious / dangerous counts
  const _VerdictCard({required this.verdicts, this.owner = false});

  @override
  Widget build(BuildContext context) {
    final total = verdicts.values.fold<int>(0, (a, b) => a + (b as num).toInt());
    final rows = owner
        ? _classes
        : [for (final v in ['safe', 'suspicious', 'dangerous', 'unknown']) (v, _verdictColor[v]!, v[0].toUpperCase() + v.substring(1))];
    return _CardBox(
      owner ? 'Risk classes today' : 'Verdicts today',
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: SizedBox(
              height: 14,
              child: total == 0
                  ? Container(color: AppColors.lavender)
                  : Row(
                      children: [
                        for (final (v, color, _) in rows)
                          if ((verdicts[v] as num? ?? 0) > 0)
                            Expanded(
                              flex: (verdicts[v] as num).toInt(),
                              child: Container(color: color),
                            ),
                      ],
                    ),
            ),
          ),
          const SizedBox(height: 10),
          for (final (v, color, name) in rows)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Row(
                children: [
                  Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                  ),
                  const SizedBox(width: 8),
                  Expanded(child: Text(name)),
                  Text('${verdicts[v] ?? 0}', style: const TextStyle(fontWeight: FontWeight.w700)),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _QuotaCard extends StatelessWidget {
  final int used;
  final int limit;
  final Map<String, dynamic> skipped;
  const _QuotaCard({required this.used, required this.limit, required this.skipped});

  @override
  Widget build(BuildContext context) {
    final share = limit == 0 ? 0.0 : (used / limit).clamp(0.0, 1.0);
    return _CardBox(
      'OTX lookups today',
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$used of $limit', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: share,
              minHeight: 10,
              backgroundColor: AppColors.lavender,
              color: share >= 0.8 ? AppColors.warningOrange : AppColors.purple,
            ),
          ),
          const SizedBox(height: 14),
          const Text('Parts skipped today', style: TextStyle(color: Colors.black54)),
          const SizedBox(height: 4),
          if (skipped.isEmpty)
            const Text('None – every check ran in full.')
          else
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final e in skipped.entries)
                  Chip(
                    label: Text('${e.key}: ${e.value}'),
                    visualDensity: VisualDensity.compact,
                    side: BorderSide.none,
                  ),
              ],
            ),
        ],
      ),
    );
  }
}

class _WeekCard extends StatelessWidget {
  final List<Map<String, dynamic>> week;
  const _WeekCard({required this.week});

  @override
  Widget build(BuildContext context) {
    final most = week.fold<int>(0, (m, w) => (w['checks'] as num).toInt() > m ? (w['checks'] as num).toInt() : m);
    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    return _CardBox(
      'Checks in the last 7 days',
      SizedBox(
        height: 150,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            for (final w in week)
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    Text('${w['checks']}', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 4),
                    Container(
                      height: most == 0 ? 2 : 2 + 100 * (w['checks'] as num) / most,
                      margin: const EdgeInsets.symmetric(horizontal: 6),
                      decoration: BoxDecoration(
                        gradient: AppColors.brandGradient,
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      days[(DateTime.tryParse('${w['day']}')?.weekday ?? 1) - 1],
                      style: const TextStyle(fontSize: 12, color: Colors.black54),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _SlowestTable extends StatelessWidget {
  final List<Map<String, dynamic>> rows;
  const _SlowestTable({required this.rows});

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) {
      return const Card(
        margin: EdgeInsets.zero,
        child: Padding(padding: EdgeInsets.all(18), child: Text('No checks today yet.')),
      );
    }
    return Card(
      margin: EdgeInsets.zero,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          key: const Key('slowestTable'),
          columns: const [
            DataColumn(label: Text('Time')),
            DataColumn(label: Text('Total')),
            DataColumn(label: Text('Links')),
            DataColumn(label: Text('MIRA')),
            DataColumn(label: Text('Verdict')),
            DataColumn(label: Text('Source')),
            DataColumn(label: Text('Skipped')),
          ],
          rows: [
            for (final r in rows)
              DataRow(
                cells: [
                  DataCell(Text(_time(r['created_at'] as String?))),
                  DataCell(Text(_ms(r['total_ms']), style: const TextStyle(fontWeight: FontWeight.w700))),
                  DataCell(Text(_ms((r['timings_ms'] as Map?)?['links']))),
                  DataCell(Text(_ms((r['timings_ms'] as Map?)?['mira']))),
                  DataCell(Text('${r['verdict']} ${r['score']}', style: TextStyle(color: _verdictColor[r['verdict']]))),
                  DataCell(Text('${r['source']}')),
                  DataCell(Text((r['skipped'] as List).join(', '))),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

class _ErrorsCard extends StatelessWidget {
  final List<Map<String, dynamic>> errors;
  const _ErrorsCard({required this.errors});

  @override
  Widget build(BuildContext context) => Card(
    margin: EdgeInsets.zero,
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: errors.isEmpty
          ? const Row(
              children: [
                Icon(Icons.check_circle_outline, color: AppColors.protectedGreen),
                SizedBox(width: 8),
                Text('No server errors.'),
              ],
            )
          : Column(
              children: [
                for (final e in errors)
                  ListTile(
                    dense: true,
                    leading: const Icon(Icons.error_outline, color: Color(0xFFC62828)),
                    title: Text('${e['status']} · ${e['method']} ${e['path']}'),
                    subtitle: Text('${_time(e['at'] as String?)}  ${e['error']}'),
                  ),
              ],
            ),
    ),
  );
}
