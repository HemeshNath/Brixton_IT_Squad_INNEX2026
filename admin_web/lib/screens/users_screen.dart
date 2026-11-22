// Users & usage (Phase 10A step A3): every app user with check counts and verdict split, search and sort,
// and a detail view with checks per day (30 days), sources, last checks, block / unblock and plan.
// Message texts are never shown here.

import 'package:flutter/material.dart';

import '../api.dart';
import '../theme/app_theme.dart';
import 'shell.dart';

const _verdictColor = {
  'safe': Color(0xFF2E7D32),
  'suspicious': Color(0xFFEF6C00),
  'dangerous': Color(0xFFC62828),
  'unknown': Colors.grey, // MIRA gave no answer (B6)
};

String _date(String? iso, {bool time = true}) {
  final t = iso == null ? null : DateTime.tryParse(iso)?.toLocal();
  if (t == null) return '–';
  String two(int n) => n.toString().padLeft(2, '0');
  final d = '${t.year}-${two(t.month)}-${two(t.day)}';
  return time ? '$d ${two(t.hour)}:${two(t.minute)}' : d;
}

/// Small Safe/Suspicious/Dangerous bar.
class VerdictBar extends StatelessWidget {
  final Map<String, dynamic> verdicts;
  final double width;
  const VerdictBar({super.key, required this.verdicts, this.width = 90});

  @override
  Widget build(BuildContext context) {
    final total = verdicts.values.fold<int>(0, (a, b) => a + (b as num).toInt());
    return Tooltip(
      message: 'Safe ${verdicts['safe']} · Suspicious ${verdicts['suspicious']} · Dangerous ${verdicts['dangerous']}'
          ' · Not checked ${verdicts['unknown'] ?? 0}',
      child: ClipRRect(
        borderRadius: BorderRadius.circular(4),
        child: SizedBox(
          width: width,
          height: 10,
          child: total == 0
              ? Container(color: AppColors.lavender)
              : Row(
                  children: [
                    for (final v in ['safe', 'suspicious', 'dangerous', 'unknown'])
                      if ((verdicts[v] as num? ?? 0) > 0)
                        Expanded(
                          flex: (verdicts[v] as num).toInt(),
                          child: Container(color: _verdictColor[v]),
                        ),
                  ],
                ),
        ),
      ),
    );
  }
}

class UsersScreen extends StatefulWidget {
  final AdminApi api;
  final void Function(Object error) onError;
  const UsersScreen({super.key, required this.api, required this.onError});

  @override
  State<UsersScreen> createState() => _UsersScreenState();
}

class _UsersScreenState extends State<UsersScreen> {
  final _search = TextEditingController();
  String _sort = 'last_seen';
  int _page = 1;
  Map<String, dynamic>? _d;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d = await widget.api.users(search: _search.text.trim(), sort: _sort, page: _page);
      if (mounted) setState(() => _d = d);
    } catch (e) {
      widget.onError(e);
    }
  }

  void _go({int page = 1, String? sort}) {
    setState(() {
      _page = page;
      _sort = sort ?? _sort;
    });
    _load();
  }

  Future<void> _open(String uid) async {
    await showDialog<void>(
      context: context,
      builder: (_) => _UserDialog(api: widget.api, uid: uid, onError: widget.onError),
    );
    _load(); // block / plan may have changed
  }

  @override
  Widget build(BuildContext context) {
    final d = _d;
    final summary = d == null ? null : Map<String, dynamic>.from(d['summary'] as Map);
    return SectionPage(
      title: 'Users & usage',
      about: 'Everyone who signed in to the app. Counts and verdicts only – message texts are never shown here.',
      action: IconButton(tooltip: 'Refresh', icon: const Icon(Icons.refresh), onPressed: _load),
      children: [
        if (summary != null)
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              _Stat('App users', '${summary['users']}', Icons.people_alt_outlined),
              _Stat('Active today', '${summary['active_today']}', Icons.today_outlined),
              _Stat('Blocked', '${summary['blocked']}', Icons.block, alert: (summary['blocked'] as num) > 0),
            ],
          ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SizedBox(
              width: 320,
              child: TextField(
                key: const Key('userSearch'),
                controller: _search,
                decoration: InputDecoration(
                  hintText: 'Search email or ID',
                  prefixIcon: const Icon(Icons.search),
                  border: const OutlineInputBorder(),
                  isDense: true,
                  suffixIcon: IconButton(icon: const Icon(Icons.arrow_forward), onPressed: () => _go()),
                ),
                onSubmitted: (_) => _go(),
              ),
            ),
            DropdownButton<String>(
              key: const Key('userSort'),
              value: _sort,
              items: const [
                DropdownMenuItem(value: 'last_seen', child: Text('Sort: last seen')),
                DropdownMenuItem(value: 'checks', child: Text('Sort: most checks')),
                DropdownMenuItem(value: 'joined', child: Text('Sort: newest')),
              ],
              onChanged: (v) => _go(sort: v),
            ),
          ],
        ),
        const SizedBox(height: 14),
        if (d == null)
          const Center(child: CircularProgressIndicator())
        else if ((d['results'] as List).isEmpty)
          const Card(
            margin: EdgeInsets.zero,
            child: Padding(padding: EdgeInsets.all(18), child: Text('No users found.')),
          )
        else
          Card(
            margin: EdgeInsets.zero,
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: DataTable(
                key: const Key('usersTable'),
                showCheckboxColumn: false,
                columns: const [
                  DataColumn(label: Text('User')),
                  DataColumn(label: Text('Joined')),
                  DataColumn(label: Text('Last seen')),
                  DataColumn(label: Text('Today'), numeric: true),
                  DataColumn(label: Text('7 days'), numeric: true),
                  DataColumn(label: Text('Total'), numeric: true),
                  DataColumn(label: Text('Verdicts')),
                  DataColumn(label: Text('Status')),
                ],
                rows: [for (final u in d['results'] as List) _row(Map<String, dynamic>.from(u as Map))],
              ),
            ),
          ),
        if (d != null)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Text('${d['total']} users · page $_page'),
                IconButton(
                  icon: const Icon(Icons.chevron_left),
                  onPressed: _page > 1 ? () => _go(page: _page - 1) : null,
                ),
                IconButton(
                  icon: const Icon(Icons.chevron_right),
                  onPressed: d['has_next'] == true ? () => _go(page: _page + 1) : null,
                ),
              ],
            ),
          ),
      ],
    );
  }

  DataRow _row(Map<String, dynamic> u) {
    final c = Map<String, dynamic>.from(u['checks'] as Map);
    final blocked = u['blocked'] == true;
    return DataRow(
      onSelectChanged: (_) => _open(u['uid'] as String),
      cells: [
        DataCell(
          Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${u['email']}'.isEmpty ? u['uid'] as String : '${u['email']}',
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
              Text('${u['kind']} · ${u['plan']}', style: const TextStyle(fontSize: 12, color: Colors.black54)),
            ],
          ),
        ),
        DataCell(Text(_date(u['joined_at'] as String?, time: false))),
        DataCell(Text(_date(u['last_seen_at'] as String?))),
        DataCell(Text('${c['today']}')),
        DataCell(Text('${c['week']}')),
        DataCell(Text('${c['total']}', style: const TextStyle(fontWeight: FontWeight.w700))),
        DataCell(VerdictBar(verdicts: Map<String, dynamic>.from(u['verdicts'] as Map))),
        DataCell(
          blocked
              ? const Chip(
                  label: Text('Blocked', style: TextStyle(color: Colors.white)),
                  backgroundColor: Color(0xFFC62828),
                  side: BorderSide.none,
                  visualDensity: VisualDensity.compact,
                )
              : const Text('Active', style: TextStyle(color: AppColors.protectedGreen)),
        ),
      ],
    );
  }
}

class _Stat extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final bool alert;
  const _Stat(this.label, this.value, this.icon, {this.alert = false});

  @override
  Widget build(BuildContext context) => SizedBox(
    width: 180,
    child: Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Icon(icon, color: alert ? const Color(0xFFC62828) : AppColors.purple),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(value, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
                  Text(
                    label,
                    style: const TextStyle(color: Colors.black54),
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

/// One user: numbers, 30-day chart, sources, last checks, block / unblock and plan.
class _UserDialog extends StatefulWidget {
  final AdminApi api;
  final String uid;
  final void Function(Object error) onError;
  const _UserDialog({required this.api, required this.uid, required this.onError});

  @override
  State<_UserDialog> createState() => _UserDialogState();
}

class _UserDialogState extends State<_UserDialog> {
  Map<String, dynamic>? _u;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final u = await widget.api.user(widget.uid);
      if (mounted) setState(() => _u = u);
    } catch (e) {
      if (mounted) Navigator.pop(context);
      widget.onError(e);
    }
  }

  Future<void> _setBlocked(bool blocked) async {
    if (blocked) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Block this user?'),
          content: const Text('The app will stop checking their messages until you unblock them.'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
            FilledButton(
              key: const Key('confirmBlock'),
              style: FilledButton.styleFrom(backgroundColor: const Color(0xFFC62828)),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Block'),
            ),
          ],
        ),
      );
      if (ok != true) return;
    }
    await _update(() => widget.api.updateUser(widget.uid, blocked: blocked));
  }

  Future<void> _update(Future<void> Function() action) async {
    try {
      await action();
      await _load();
    } catch (e) {
      widget.onError(e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final u = _u;
    return Dialog(
      insetPadding: const EdgeInsets.all(24),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 760, maxHeight: 760),
        child: u == null ? const SizedBox(height: 200, child: Center(child: CircularProgressIndicator())) : _body(u),
      ),
    );
  }

  Widget _body(Map<String, dynamic> u) {
    final c = Map<String, dynamic>.from(u['checks'] as Map);
    final blocked = u['blocked'] == true;
    final perDay = [for (final x in u['per_day'] as List) Map<String, dynamic>.from(x as Map)];
    final most = perDay.fold<int>(1, (m, x) => (x['checks'] as num).toInt() > m ? (x['checks'] as num).toInt() : m);
    return ListView(
      padding: const EdgeInsets.all(24),
      shrinkWrap: true,
      children: [
        Row(
          children: [
            const CircleAvatar(
              backgroundColor: AppColors.lavender,
              child: Icon(Icons.person, color: AppColors.purpleDark),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${u['email']}', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
                  Text(
                    '${u['kind']} sign-in · joined ${_date(u['joined_at'] as String?, time: false)} · '
                    'last seen ${_date(u['last_seen_at'] as String?)}',
                    style: const TextStyle(color: Colors.black54),
                  ),
                ],
              ),
            ),
            IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(context)),
          ],
        ),
        const SizedBox(height: 18),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            _Stat('Today', '${c['today']}', Icons.today_outlined),
            _Stat('Last 7 days', '${c['week']}', Icons.date_range_outlined),
            _Stat('All checks', '${c['total']}', Icons.fact_check_outlined),
            _Stat('Reports sent', '${u['reports_sent']}', Icons.flag_outlined),
          ],
        ),
        const SizedBox(height: 18),
        const Text('Checks per day (last 30 days)', style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        SizedBox(
          height: 110,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              for (final x in perDay)
                Expanded(
                  child: Tooltip(
                    message: '${x['day']}: ${x['checks']}',
                    child: Container(
                      height: 2 + 100 * (x['checks'] as num) / most,
                      margin: const EdgeInsets.symmetric(horizontal: 1.5),
                      decoration: BoxDecoration(
                        gradient: AppColors.brandGradient,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 18),
        Row(
          children: [
            const Text('Verdicts  ', style: TextStyle(fontWeight: FontWeight.w700)),
            VerdictBar(verdicts: Map<String, dynamic>.from(u['verdicts'] as Map), width: 200),
            const SizedBox(width: 20),
            const Text('Sources  ', style: TextStyle(fontWeight: FontWeight.w700)),
            Flexible(
              child: Text(
                (u['sources'] as Map).entries.map((e) => '${e.key} ${e.value}').join(' · '),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
        const SizedBox(height: 18),
        const Text('Last checks', style: TextStyle(fontWeight: FontWeight.w700)),
        for (final x in u['last_checks'] as List)
          ListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            leading: Icon(Icons.circle, size: 12, color: _verdictColor[(x as Map)['verdict']]),
            title: Text('${x['verdict']} · score ${x['score']} · ${x['source']}'),
            subtitle: Text(_date(x['at'] as String?)),
          ),
        if ((u['last_checks'] as List).isEmpty) const Text('No checks yet.'),
        const Divider(height: 32),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            DropdownButton<String>(
              key: const Key('userPlan'),
              value: u['plan'] as String,
              items: const [
                DropdownMenuItem(value: 'free', child: Text('Plan: free')),
                DropdownMenuItem(value: 'premium', child: Text('Plan: premium')),
              ],
              onChanged: (p) => _update(() => widget.api.updateUser(widget.uid, plan: p)),
            ),
            blocked
                ? FilledButton.icon(
                    key: const Key('unblockUser'),
                    onPressed: () => _setBlocked(false),
                    icon: const Icon(Icons.check_circle_outline),
                    label: const Text('Unblock'),
                  )
                : OutlinedButton.icon(
                    key: const Key('blockUser'),
                    style: OutlinedButton.styleFrom(foregroundColor: const Color(0xFFC62828)),
                    onPressed: () => _setBlocked(true),
                    icon: const Icon(Icons.block),
                    label: const Text('Block user'),
                  ),
            if (blocked)
              const Text(
                'Blocked – the app does not check their messages.',
                style: TextStyle(color: Color(0xFFC62828)),
              ),
          ],
        ),
      ],
    );
  }
}
