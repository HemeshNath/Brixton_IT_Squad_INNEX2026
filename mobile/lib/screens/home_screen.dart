// Home screen: protection status and permissions, manual message check, 'Test as SMS', result card.

import 'package:flutter/material.dart';

import '../models/check_result.dart';
import '../services/api.dart';
import '../services/native_bridge.dart';
import '../services/settings.dart';
import '../widgets/result_card.dart';
import 'history_screen.dart';

class HomeScreen extends StatefulWidget {
  final AppSettings settings;
  final ApiService Function() apiFactory;
  final Future<void> Function() onSignOut;
  final String signedInAs; // Google email or development name, shown in the menu

  const HomeScreen({
    super.key,
    required this.settings,
    required this.apiFactory,
    required this.onSignOut,
    this.signedInAs = '',
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  final _text = TextEditingController();
  final _sender = TextEditingController();
  bool _listenerOn = false;
  bool _notifOk = true;
  bool _checking = false;
  String? _error;
  CheckResult? _result;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _refreshStatus();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  // Coming back from Android settings -> re-read the permission status.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _refreshStatus();
  }

  Future<void> _refreshStatus() async {
    try {
      final on = await NativeBridge.isListenerEnabled();
      final notif = await NativeBridge.hasNotificationPermission();
      if (mounted) {
        setState(() {
          _listenerOn = on;
          _notifOk = notif;
        });
      }
    } catch (_) {
      // Not on Android (e.g. widget tests) - leave defaults.
    }
  }

  Future<void> _check() async {
    final text = _text.text.trim();
    if (text.isEmpty) {
      setState(() => _error = 'Paste or type a message first.');
      return;
    }
    setState(() {
      _checking = true;
      _error = null;
      _result = null;
    });
    try {
      final r = await widget.apiFactory().checkMessage(text, sender: _sender.text.trim());
      setState(() => _result = r);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  Future<void> _simulate() async {
    final text = _text.text.trim();
    if (text.isEmpty) {
      setState(() => _error = 'Type a message to simulate.');
      return;
    }
    final verdict = await NativeBridge.simulateMessage(_sender.text.trim(), text);
    if (!mounted) return;
    final msg = switch (verdict) {
      'skipped' => 'Skipped: OTP or trusted sender – it would not leave your phone.',
      'failed' => 'Could not reach the server.',
      _ => 'Notification shown: $verdict',
    };
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  Future<void> _wrongVerdict() async {
    final r = _result;
    if (r == null) return;
    final label = await askCorrectLabel(context);
    if (label == null || !mounted) return;
    try {
      await widget.apiFactory().sendFeedback(r.checkId, label);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Thanks! This helps train our model.')));
      }
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final protected = _listenerOn && _notifOk && widget.settings.protectionEnabled;
    return Scaffold(
      appBar: AppBar(
        title: const Text('CheckScam'),
        actions: [
          IconButton(
            tooltip: 'History',
            icon: const Icon(Icons.history),
            onPressed: () => Navigator.push(
                context, MaterialPageRoute(builder: (_) => HistoryScreen(apiFactory: widget.apiFactory))),
          ),
          PopupMenuButton<String>(
            onSelected: (v) async {
              if (v == 'battery') await NativeBridge.openBatterySettings();
              if (v == 'signout') await widget.onSignOut();
            },
            itemBuilder: (_) => [
              if (widget.signedInAs.isNotEmpty)
                PopupMenuItem(enabled: false, child: Text('Signed in as ${widget.signedInAs}')),
              const PopupMenuItem(value: 'battery', child: Text('Battery settings')),
              const PopupMenuItem(value: 'signout', child: Text('Sign out')),
            ],
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _ProtectionCard(
            protected: protected,
            listenerOn: _listenerOn,
            notifOk: _notifOk,
            settings: widget.settings,
            onChanged: () => setState(() {}),
          ),
          const SizedBox(height: 16),
          Text('Check a message yourself', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          TextField(
            controller: _sender,
            decoration: const InputDecoration(labelText: 'Sender (optional)', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 8),
          TextField(
            key: const Key('messageInput'),
            controller: _text,
            minLines: 3,
            maxLines: 8,
            decoration: const InputDecoration(
              labelText: 'Message or link',
              hintText: 'Paste the SMS here…',
              border: OutlineInputBorder(),
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(_error!, key: const Key('error'), style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ],
          const SizedBox(height: 12),
          Row(children: [
            Expanded(
              child: FilledButton.icon(
                key: const Key('checkButton'),
                onPressed: _checking ? null : _check,
                icon: _checking
                    ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.search),
                label: Text(_checking ? 'Checking…' : 'Check'),
              ),
            ),
            const SizedBox(width: 8),
            OutlinedButton(onPressed: _simulate, child: const Text('Test as SMS')),
          ]),
          const SizedBox(height: 16),
          if (_result != null) ResultCard(result: _result!, onWrongVerdict: _wrongVerdict),
        ],
      ),
    );
  }
}

class _ProtectionCard extends StatelessWidget {
  final bool protected;
  final bool listenerOn;
  final bool notifOk;
  final AppSettings settings;
  final VoidCallback onChanged;

  const _ProtectionCard({
    required this.protected,
    required this.listenerOn,
    required this.notifOk,
    required this.settings,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final color = protected ? const Color(0xFF2E7D32) : const Color(0xFFEF6C00);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(protected ? Icons.shield : Icons.shield_outlined, color: color, size: 32),
            const SizedBox(width: 12),
            Expanded(
              child: Text(protected ? 'Messages are protected' : 'Protection is off',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(color: color)),
            ),
          ]),
          const SizedBox(height: 8),
          if (!listenerOn) ...[
            const Text('Allow CheckScam to read message notifications so it can check new SMS '
                'before you see them. OTPs and bank messages stay on your phone.'),
            const SizedBox(height: 8),
            FilledButton(onPressed: NativeBridge.openListenerSettings, child: const Text('Allow notification access')),
          ],
          if (!notifOk) ...[
            const SizedBox(height: 8),
            OutlinedButton(
                onPressed: NativeBridge.requestNotificationPermission, child: const Text('Allow CheckScam notifications')),
          ],
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Check new SMS automatically'),
            value: settings.protectionEnabled,
            onChanged: (v) async {
              await settings.setProtectionEnabled(v);
              onChanged();
            },
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Also check WhatsApp, Viber and Messenger'),
            value: settings.watchChatApps,
            onChanged: (v) async {
              await settings.setWatchChatApps(v);
              onChanged();
            },
          ),
        ]),
      ),
    );
  }
}
