// History screen: lists past checks (paged), swipe to delete, tap for details and 'Wrong result?' feedback.

import 'package:flutter/material.dart';

import '../models/check_result.dart';
import '../services/api.dart';
import '../widgets/result_card.dart';

class HistoryScreen extends StatefulWidget {
  final ApiService Function() apiFactory;
  const HistoryScreen({super.key, required this.apiFactory});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  final List<CheckResult> _items = [];
  int _page = 0;
  bool _hasNext = true;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadMore();
  }

  Future<void> _reload() async {
    setState(() {
      _items.clear();
      _page = 0;
      _hasNext = true;
    });
    await _loadMore();
  }

  Future<void> _loadMore() async {
    if (_loading || !_hasNext) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final page = await widget.apiFactory().history(page: _page + 1);
      setState(() {
        _items.addAll(page.items);
        _page += 1;
        _hasNext = page.hasNext;
      });
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _delete(CheckResult c) async {
    try {
      await widget.apiFactory().deleteCheck(c.checkId);
      setState(() => _items.remove(c));
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  void _open(CheckResult c) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            if (c.sender.isNotEmpty) Text('From: ${c.sender}', style: Theme.of(ctx).textTheme.labelLarge),
            const SizedBox(height: 4),
            Text(c.text),
            const SizedBox(height: 12),
            ResultCard(
              result: c,
              onWrongVerdict: () async {
                final label = await askCorrectLabel(ctx);
                if (label == null) return;
                try {
                  await widget.apiFactory().sendFeedback(c.checkId, label);
                  if (ctx.mounted) Navigator.pop(ctx);
                  if (mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Thanks for the feedback!')));
                  }
                } on ApiException catch (e) {
                  if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
                }
              },
            ),
          ]),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Checked messages')),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: _items.isEmpty && !_loading
            ? ListView(children: [
                const SizedBox(height: 120),
                Center(child: Text(_error ?? 'No checked messages yet.')),
              ])
            : ListView.builder(
                itemCount: _items.length + (_hasNext ? 1 : 0),
                itemBuilder: (ctx, i) {
                  if (i >= _items.length) {
                    _loadMore();
                    return const Padding(
                        padding: EdgeInsets.all(16), child: Center(child: CircularProgressIndicator()));
                  }
                  final c = _items[i];
                  final style = VerdictStyle.of(c.verdict);
                  return Dismissible(
                    key: ValueKey(c.checkId),
                    direction: DismissDirection.endToStart,
                    background: Container(
                      color: Colors.red,
                      alignment: Alignment.centerRight,
                      padding: const EdgeInsets.only(right: 16),
                      child: const Icon(Icons.delete, color: Colors.white),
                    ),
                    onDismissed: (_) => _delete(c),
                    child: ListTile(
                      leading: Icon(style.icon, color: style.color),
                      title: Text(c.sender.isEmpty ? '(no sender)' : c.sender, maxLines: 1),
                      subtitle: Text(c.text, maxLines: 2, overflow: TextOverflow.ellipsis),
                      trailing: Text('${c.score}', style: TextStyle(color: style.color, fontWeight: FontWeight.bold)),
                      onTap: () => _open(c),
                    ),
                  );
                },
              ),
      ),
    );
  }
}
