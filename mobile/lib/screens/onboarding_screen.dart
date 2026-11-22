// First-run setup guide (Phase 9.5), in the team's purple design: welcome + privacy, notification access,
// notification permission, and the battery / auto-start steps for the phone's brand.
// Shown once after sign-in, and again from Settings -> Setup guide.

import 'package:flutter/material.dart';

import '../l10n/strings.dart';
import '../services/native_bridge.dart';
import '../theme/app_theme.dart';
import '../widgets/language_button.dart';

class OnboardingScreen extends StatefulWidget {
  final Future<void> Function() onDone;
  const OnboardingScreen({super.key, required this.onDone});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> with WidgetsBindingObserver {
  static const _pageCount = 4;
  final _pages = PageController();
  int _page = 0;
  bool _listenerOn = false;
  bool _notifOk = false;
  String _brand = '';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _refresh();
    NativeBridge.manufacturer().then((m) {
      if (mounted) setState(() => _brand = m);
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _pages.dispose();
    super.dispose();
  }

  // Back from Android settings -> show the new status.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _refresh();
  }

  Future<void> _refresh() async {
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
      // Not on Android (widget tests).
    }
  }

  void _next() {
    if (_page < _pageCount - 1) {
      _pages.nextPage(duration: const Duration(milliseconds: 280), curve: Curves.easeOut);
    } else {
      widget.onDone();
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = S.of(context);
    final last = _page == _pageCount - 1;
    return Scaffold(
      body: WaveBackground(
        child: SafeArea(
          child: Column(children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 4, 12, 0),
              child: Row(children: [
                const LanguageButton(),
                const Spacer(),
                if (!last)
                  TextButton(key: const Key('onboardingSkip'), onPressed: widget.onDone, child: Text(s.skip)),
              ]),
            ),
            Expanded(
              child: PageView(
                controller: _pages,
                onPageChanged: (i) => setState(() => _page = i),
                children: [
                  _WelcomePage(s: s),
                  _StepPage(
                    icon: Icons.mark_chat_read_outlined,
                    title: s.accessTitle,
                    text: s.accessText,
                    done: _listenerOn,
                    doneText: s.allowed,
                    buttonKey: const Key('onboardingAccess'),
                    buttonText: s.allowAccess,
                    onPressed: NativeBridge.openListenerSettings,
                  ),
                  _StepPage(
                    icon: Icons.notifications_active_outlined,
                    title: s.notifTitle,
                    text: s.notifText,
                    done: _notifOk,
                    doneText: s.allowed,
                    buttonKey: const Key('onboardingNotif'),
                    buttonText: s.allowNotificationsShort,
                    onPressed: () async {
                      await NativeBridge.requestNotificationPermission();
                      await Future<void>.delayed(const Duration(seconds: 1));
                      _refresh();
                    },
                  ),
                  _BatteryPage(s: s, brand: _brand),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 8, 24, 20),
              child: Row(children: [
                for (var i = 0; i < _pageCount; i++)
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    margin: const EdgeInsets.only(right: 6),
                    width: i == _page ? 22 : 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color: i == _page ? AppColors.purpleDark : AppColors.lavender,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                const Spacer(),
                FilledButton(
                  key: const Key('onboardingNext'),
                  onPressed: _next,
                  style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 14)),
                  child: Text(last ? s.done : s.next),
                ),
              ]),
            ),
          ]),
        ),
      ),
    );
  }
}

/// White rounded card used by every page.
class _PageCard extends StatelessWidget {
  final List<Widget> children;
  const _PageCard({required this.children});

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 12),
        child: Card(
          margin: EdgeInsets.zero,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(22, 24, 22, 22),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
          ),
        ),
      );
}

class _WelcomePage extends StatelessWidget {
  final S s;
  const _WelcomePage({required this.s});

  @override
  Widget build(BuildContext context) => _PageCard(children: [
        const Center(child: CheckScamMark(size: 80)),
        const SizedBox(height: 14),
        Center(
          child: Text(s.welcomeTitle,
              key: const Key('onboardingWelcome'),
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700, color: AppColors.ink)),
        ),
        const SizedBox(height: 10),
        Text(s.welcomeText, style: const TextStyle(fontSize: 16, height: 1.4)),
        const SizedBox(height: 16),
        for (final line in [s.privacy1, s.privacy2, s.privacy3])
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Icon(Icons.lock_outline, color: AppColors.protectedGreen, size: 22),
              const SizedBox(width: 10),
              Expanded(child: Text(line, style: const TextStyle(fontSize: 15, height: 1.35))),
            ]),
          ),
      ]);
}

/// A permission step: icon, title, text, and either "Allowed ✓" or the button that opens the setting.
class _StepPage extends StatelessWidget {
  final IconData icon;
  final String title;
  final String text;
  final bool done;
  final String doneText;
  final Key buttonKey;
  final String buttonText;
  final VoidCallback onPressed;

  const _StepPage({
    required this.icon,
    required this.title,
    required this.text,
    required this.done,
    required this.doneText,
    required this.buttonKey,
    required this.buttonText,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) => _PageCard(children: [
        Icon(icon, size: 52, color: AppColors.purpleDark),
        const SizedBox(height: 12),
        Text(title, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: AppColors.ink)),
        const SizedBox(height: 10),
        Text(text, style: const TextStyle(fontSize: 16, height: 1.4)),
        const SizedBox(height: 20),
        if (done)
          Row(children: [
            const Icon(Icons.check_circle, color: AppColors.protectedGreen),
            const SizedBox(width: 8),
            Text(doneText,
                style: const TextStyle(color: AppColors.protectedGreen, fontSize: 17, fontWeight: FontWeight.w600)),
          ])
        else
          SizedBox(
            width: double.infinity,
            child: FilledButton(key: buttonKey, onPressed: onPressed, child: Text(buttonText)),
          ),
      ]);
}

/// Battery / auto-start steps for the phone's brand, with buttons to the matching settings pages.
class _BatteryPage extends StatelessWidget {
  final S s;
  final String brand;
  const _BatteryPage({required this.s, required this.brand});

  @override
  Widget build(BuildContext context) {
    final steps = s.batterySteps(brand);
    final shownBrand = brand.isEmpty ? 'Android' : brand[0].toUpperCase() + brand.substring(1);
    return _PageCard(children: [
      const Icon(Icons.battery_charging_full_rounded, size: 52, color: AppColors.purpleDark),
      const SizedBox(height: 12),
      Text(s.batteryTitle,
          key: const Key('onboardingBattery'),
          style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: AppColors.ink)),
      const SizedBox(height: 10),
      Text(s.batteryText(shownBrand), style: const TextStyle(fontSize: 16, height: 1.4)),
      const SizedBox(height: 12),
      for (var i = 0; i < steps.length; i++)
        Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            CircleAvatar(
              radius: 12,
              backgroundColor: AppColors.purpleDark,
              child: Text('${i + 1}', style: const TextStyle(color: Colors.white, fontSize: 13)),
            ),
            const SizedBox(width: 10),
            Expanded(child: Text(steps[i], style: const TextStyle(fontSize: 15, height: 1.35))),
          ]),
        ),
      const SizedBox(height: 8),
      SizedBox(
        width: double.infinity,
        child: FilledButton.icon(
          onPressed: NativeBridge.openAppDetails,
          icon: const Icon(Icons.info_outline),
          label: Text(s.openAppInfo),
        ),
      ),
      const SizedBox(height: 8),
      SizedBox(
        width: double.infinity,
        child: OutlinedButton.icon(
          onPressed: NativeBridge.openAutostart,
          icon: const Icon(Icons.restart_alt),
          label: Text(s.openAutostart),
        ),
      ),
      const SizedBox(height: 8),
      SizedBox(
        width: double.infinity,
        child: OutlinedButton.icon(
          onPressed: NativeBridge.openBatterySettings,
          icon: const Icon(Icons.battery_saver),
          label: Text(s.openBattery),
        ),
      ),
    ]);
  }
}
