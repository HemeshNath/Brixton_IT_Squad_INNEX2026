// Home screen (team design, Phase 9): header with logo and settings, purple waves, the protection card,
// the "Paste your content here…" pill. After a check: the pill moves up, the checked message is shown in a
// yellow frame, then the explanation and the purple "likely N% Scam" card. History is in the settings (gear) menu.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/check_result.dart';
import '../services/api.dart';
import '../services/native_bridge.dart';
import '../services/settings.dart';
import '../theme/app_theme.dart';
import '../widgets/result_card.dart';
import 'check_detail_screen.dart';
import 'history_screen.dart';

class HomeScreen extends StatefulWidget {
  final AppSettings settings;
  final ApiService Function() apiFactory;
  final Future<void> Function() onSignOut;
  final String signedInAs; // Google email or development name, shown in settings

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
  bool _listenerOn = false;
  bool _notifOk = true;
  bool _checking = false;
  String? _error;
  CheckResult? _result;
  String _checkedText = '';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _refreshStatus();
    // A tapped CheckScam warning opens that message's result: now (app was open) or at start (app was closed).
    NativeBridge.onCheckTapped(_showTappedCheck);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final check = await NativeBridge.takeLaunchCheck();
      if (check != null && mounted) _showTappedCheck(check);
    });
  }

  void _showTappedCheck(TappedCheck check) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => CheckDetailScreen(
        result: check.result,
        message: check.message,
        sender: check.sender,
        apiFactory: widget.apiFactory,
        onOpenMessage: NativeBridge.openOriginalMessage,
      ),
    ));
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _text.dispose();
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
    FocusScope.of(context).unfocus();
    setState(() {
      _checking = true;
      _error = null;
    });
    try {
      final r = await widget.apiFactory().checkMessage(text);
      setState(() {
        _result = r;
        _checkedText = text;
      });
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  Future<void> _pasteFromClipboard() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final text = data?.text?.trim() ?? '';
    if (text.isEmpty) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Clipboard is empty.')));
      return;
    }
    _text.text = text;
    _text.selection = TextSelection.collapsed(offset: text.length);
  }

  Future<void> _simulate() async {
    final text = _text.text.trim().isNotEmpty
        ? _text.text.trim()
        : 'Dear customer, your eSewa wallet will be BLOCKED today. Update KYC: http://esewa-kyc.xyz/login';
    final verdict = await NativeBridge.simulateMessage('9812345678', text);
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

  void _openHistory() =>
      Navigator.push(context, MaterialPageRoute(builder: (_) => HistoryScreen(apiFactory: widget.apiFactory)));

  void _openSettings() {
    showModalBottomSheet(
      context: context,
      showDragHandle: true,
      builder: (ctx) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          if (widget.signedInAs.isNotEmpty)
            ListTile(leading: const Icon(Icons.account_circle), title: Text('Signed in as ${widget.signedInAs}')),
          ListTile(
            leading: const Icon(Icons.history),
            title: const Text('History'),
            onTap: () {
              Navigator.pop(ctx);
              _openHistory();
            },
          ),
          ListTile(
            leading: const Icon(Icons.notifications_active_outlined),
            title: const Text('Test as SMS'),
            subtitle: const Text('Shows the notification a real SMS would get'),
            onTap: () {
              Navigator.pop(ctx);
              _simulate();
            },
          ),
          ListTile(
            leading: const Icon(Icons.battery_saver),
            title: const Text('Battery settings'),
            onTap: () {
              Navigator.pop(ctx);
              NativeBridge.openBatterySettings();
            },
          ),
          ListTile(
            key: const Key('signOut'),
            leading: const Icon(Icons.logout),
            title: const Text('Sign out'),
            onTap: () async {
              Navigator.pop(ctx);
              await widget.onSignOut();
            },
          ),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final protected = _listenerOn && _notifOk && widget.settings.protectionEnabled;
    final hasResult = _result != null;
    final input = _ContentInput(
      controller: _text,
      checking: _checking,
      onSend: _check,
      onPlus: _pasteFromClipboard,
    );
    final error = _error == null
        ? const SizedBox.shrink()
        : Padding(
            padding: const EdgeInsets.only(top: 10),
            child: Text(_error!, key: const Key('error'), style: TextStyle(color: Theme.of(context).colorScheme.error)),
          );
    final protection = _ProtectionCard(
      protected: protected,
      listenerOn: _listenerOn,
      notifOk: _notifOk,
      settings: widget.settings,
      onChanged: () => setState(() {}),
    );

    return Scaffold(
      body: WaveBackground(
        child: SafeArea(
          child: Column(children: [
            CheckScamHeader(onSettings: _openSettings),
            Expanded(
              child: hasResult
                  ? ListView(
                      padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
                      children: [
                        input,
                        error,
                        const SizedBox(height: 20),
                        CheckedContent(text: _checkedText),
                        const SizedBox(height: 20),
                        ExplanationText(result: _result!),
                        const SizedBox(height: 20),
                        ScoreCard(result: _result!),
                        Align(
                          alignment: Alignment.centerRight,
                          child: TextButton.icon(
                            onPressed: _wrongVerdict,
                            icon: const Icon(Icons.flag_outlined, size: 18),
                            label: const Text('Wrong result?'),
                          ),
                        ),
                      ],
                    )
                  : LayoutBuilder(
                      builder: (ctx, box) => SingleChildScrollView(
                        padding: const EdgeInsets.symmetric(horizontal: 20),
                        child: ConstrainedBox(
                          constraints: BoxConstraints(minHeight: box.maxHeight),
                          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                            const SizedBox(height: 24),
                            protection,
                            const SizedBox(height: 28),
                            input,
                            error,
                            const SizedBox(height: 48),
                          ]),
                        ),
                      ),
                    ),
            ),
          ]),
        ),
      ),
    );
  }
}

/// "+  Paste your content here…  (↑)" pill from the design.
class _ContentInput extends StatelessWidget {
  final TextEditingController controller;
  final bool checking;
  final VoidCallback onSend;
  final VoidCallback onPlus;

  const _ContentInput({required this.controller, required this.checking, required this.onSend, required this.onPlus});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.inputBorder),
        boxShadow: const [BoxShadow(color: Color(0x1A4A148C), blurRadius: 14, offset: Offset(0, 4))],
      ),
      padding: const EdgeInsets.fromLTRB(4, 6, 8, 6),
      child: Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
        IconButton(
          key: const Key('pasteButton'),
          tooltip: 'Paste',
          icon: const Icon(Icons.add, size: 28, color: AppColors.ink),
          onPressed: onPlus,
        ),
        Expanded(
          child: TextField(
            key: const Key('messageInput'),
            controller: controller,
            minLines: 1,
            maxLines: 5,
            textInputAction: TextInputAction.newline,
            decoration: const InputDecoration(
              hintText: 'Paste your content here…',
              hintStyle: TextStyle(fontStyle: FontStyle.italic, color: Color(0xFF8A8494)),
              border: InputBorder.none,
            ),
          ),
        ),
        const SizedBox(width: 6),
        SizedBox(
          width: 44,
          height: 44,
          child: Material(
            color: AppColors.ink,
            shape: const CircleBorder(),
            child: InkWell(
              key: const Key('checkButton'),
              customBorder: const CircleBorder(),
              onTap: checking ? null : onSend,
              child: Center(
                child: checking
                    ? const SizedBox(
                        width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.arrow_upward, color: Colors.white),
              ),
            ),
          ),
        ),
      ]),
    );
  }
}

/// "Messages are protected" card (team design): shield + status, permission buttons when needed,
/// and the two switches. Shown on the home screen above the input.
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
    final color = protected ? AppColors.protectedGreen : AppColors.warningOrange;
    return Card(
      key: const Key('protectionCard'),
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 18, 16, 10),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(protected ? Icons.shield : Icons.shield_outlined, color: color, size: 34),
            const SizedBox(width: 12),
            Expanded(
              child: Text(protected ? 'Messages are protected' : 'Protection is off',
                  style: TextStyle(color: color, fontSize: 22, fontWeight: FontWeight.w500)),
            ),
          ]),
          const SizedBox(height: 6),
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
            title: const Text('Check new SMS automatically', style: TextStyle(fontSize: 17)),
            value: settings.protectionEnabled,
            onChanged: (v) async {
              await settings.setProtectionEnabled(v);
              onChanged();
            },
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Also check WhatsApp, Viber and Messenger', style: TextStyle(fontSize: 17)),
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
