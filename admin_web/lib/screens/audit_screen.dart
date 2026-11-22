// Audit log (admin+): every admin action, newest first, 20 per page.

import 'package:flutter/material.dart';

import '../api.dart';
import 'shell.dart';

class AuditScreen extends StatefulWidget {
  final AdminApi api;
  final void Function(Object error) onError;
  const AuditScreen({super.key, required this.api, required this.onError});

  @override
  State<AuditScreen> createState() => _AuditScreenState();
}

class _AuditScreenState extends State<AuditScreen> {
  PageOf<Map<String, dynamic>>? _data;
  int _page = 1;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d = await widget.api.audit(page: _page);
      if (mounted) setState(() => _data = d);
    } catch (e) {
      widget.onError(e);
    }
  }

  void _go(int page) {
    setState(() => _page = page);
    _load();
  }

  static String _when(String? iso) {
    final t = iso == null ? null : DateTime.tryParse(iso)?.toLocal();
    if (t == null) return '';
    String two(int n) => n.toString().padLeft(2, '0');
    return '${t.year}-${two(t.month)}-${two(t.day)} ${two(t.hour)}:${two(t.minute)}';
  }

  static String _detail(Map<String, dynamic> d) =>
      d.entries.where((e) => e.value != null).map((e) => '${e.key}: ${e.value}').join(' · ');

  @override
  Widget build(BuildContext context) {
    final d = _data;
    return SectionPage(
      title: 'Audit log',
      about: 'Every admin action: who, what, when. Failed sign-ins are listed too.',
      action: IconButton(tooltip: 'Refresh', icon: const Icon(Icons.refresh), onPressed: _load),
      children: [
        if (d == null)
          const Center(child: CircularProgressIndicator())
        else
          Card(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: DataTable(
                key: const Key('auditTable'),
                columns: const [
                  DataColumn(label: Text('When')),
                  DataColumn(label: Text('Admin')),
                  DataColumn(label: Text('Action')),
                  DataColumn(label: Text('Details')),
                  DataColumn(label: Text('IP')),
                ],
                rows: [
                  for (final a in d.items)
                    DataRow(
                      cells: [
                        DataCell(Text(_when(a['created_at'] as String?))),
                        DataCell(Text('${a['admin']}')),
                        DataCell(
                          Text(
                            '${a['action']}',
                            style: TextStyle(
                              color: '${a['action']}'.contains('fail') || '${a['action']}'.contains('blocked')
                                  ? Colors.red.shade700
                                  : null,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                        DataCell(Text(_detail(Map<String, dynamic>.from(a['detail'] as Map? ?? {})))),
                        DataCell(Text('${a['ip']}')),
                      ],
                    ),
                ],
              ),
            ),
          ),
        if (d != null)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Text('${d.total} actions · page $_page'),
                IconButton(icon: const Icon(Icons.chevron_left), onPressed: _page > 1 ? () => _go(_page - 1) : null),
                IconButton(icon: const Icon(Icons.chevron_right), onPressed: d.hasNext ? () => _go(_page + 1) : null),
              ],
            ),
          ),
      ],
    );
  }
}
