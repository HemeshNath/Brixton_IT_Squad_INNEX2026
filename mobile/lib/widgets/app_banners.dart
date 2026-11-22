// Home-screen cards controlled from the admin panel: "please update" (A10), the in-app notice (A10) and the small ad
// banner (A9). Ads only ever show on the home screen, never next to a scam result.

import 'dart:async';

import 'package:flutter/material.dart';

import '../l10n/strings.dart';
import '../models/app_config.dart';
import '../services/native_bridge.dart';

/// Shown instead of the check box when this app version is older than the server's minimum version.
class UpdateCard extends StatelessWidget {
  final AppConfig config;
  const UpdateCard({super.key, required this.config});

  @override
  Widget build(BuildContext context) {
    final s = S.of(context);
    return Card(
      key: const Key('updateCard'),
      color: const Color(0xFFFFEBEE),
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.system_update, color: Color(0xFFB71C1C), size: 30),
            const SizedBox(width: 10),
            Expanded(child: Text(s.updateTitle, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700))),
          ]),
          const SizedBox(height: 8),
          Text(s.updateText(config.minVersion)),
          if (config.updateUrl.isNotEmpty) ...[
            const SizedBox(height: 10),
            FilledButton.icon(
              key: const Key('updateButton'),
              onPressed: () => NativeBridge.openUrl(config.updateUrl),
              icon: const Icon(Icons.download),
              label: Text(s.updateButton),
            ),
          ],
        ]),
      ),
    );
  }
}

/// The admin panel's in-app notice, in the app's language; can be closed (comes back when the text changes).
class NoticeCard extends StatelessWidget {
  final AppNotice notice;
  final VoidCallback onDismiss;
  const NoticeCard({super.key, required this.notice, required this.onDismiss});

  @override
  Widget build(BuildContext context) {
    final s = S.of(context);
    final ne = s.ne;
    final warning = notice.level == 'warning';
    final title = notice.title(ne), text = notice.text(ne);
    return Card(
      key: const Key('noticeCard'),
      color: warning ? const Color(0xFFFFF3E0) : const Color(0xFFE3F2FD),
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 4, 12),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(warning ? Icons.warning_amber_rounded : Icons.info_outline,
              color: warning ? const Color(0xFFEF6C00) : const Color(0xFF1565C0)),
          const SizedBox(width: 10),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (title.isNotEmpty) Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
              if (text.isNotEmpty) Text(text),
            ]),
          ),
          IconButton(key: const Key('noticeClose'), tooltip: s.dismiss, onPressed: onDismiss, icon: const Icon(Icons.close)),
        ]),
      ),
    );
  }
}

/// The small ad banner. Several ads take turns every 8 seconds; each ad's view is counted once per app session.
class AdBanner extends StatefulWidget {
  final List<AdItem> ads;
  final void Function(AdItem ad, String kind) onEvent; // "view" | "click"
  final Future<bool> Function(String url) openUrl;
  const AdBanner({super.key, required this.ads, required this.onEvent, this.openUrl = NativeBridge.openUrl});

  @override
  State<AdBanner> createState() => _AdBannerState();
}

class _AdBannerState extends State<AdBanner> {
  static final _counted = <int>{}; // views counted in this app session
  int _i = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _countView();
    if (widget.ads.length > 1) {
      _timer = Timer.periodic(const Duration(seconds: 8), (_) {
        if (!mounted) return;
        setState(() => _i = (_i + 1) % widget.ads.length);
        _countView();
      });
    }
  }

  void _countView() {
    final ad = widget.ads[_i];
    if (_counted.add(ad.id)) widget.onEvent(ad, 'view');
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ad = widget.ads[_i % widget.ads.length];
    final s = S.of(context);
    return Card(
      key: Key('adBanner_${ad.id}'),
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () {
          widget.onEvent(ad, 'click');
          widget.openUrl(ad.link);
        },
        child: Row(children: [
          if (ad.imageUrl != null)
            SizedBox(
              width: 76,
              height: 76,
              child: Image.network(ad.imageUrl!, fit: BoxFit.cover, errorBuilder: (_, _, _) => const SizedBox.shrink()),
            ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(14, 10, 10, 10),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                    decoration: BoxDecoration(color: Colors.black12, borderRadius: BorderRadius.circular(4)),
                    child: Text(s.adLabel, style: const TextStyle(fontSize: 10)),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(ad.title, maxLines: 1, overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                  ),
                ]),
                if (ad.body.isNotEmpty) Text(ad.body, maxLines: 2, overflow: TextOverflow.ellipsis),
              ]),
            ),
          ),
          const Padding(padding: EdgeInsets.only(right: 8), child: Icon(Icons.open_in_new, size: 18)),
        ]),
      ),
    );
  }
}

/// Tests: forget which ad views were already counted.
@visibleForTesting
void resetAdViewsForTests() => _AdBannerState._counted.clear();
