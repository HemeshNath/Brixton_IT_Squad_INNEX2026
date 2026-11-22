// App control (A10) and ads (A9) as the phone gets them from the server.

/// This app's version. Keep it the same as `version:` in pubspec.yaml (without the +build number).
const kAppVersion = '1.0.0';

class AppNotice {
  final String level; // info | warning
  final String titleEn, textEn, titleNe, textNe;
  const AppNotice({this.level = 'info', this.titleEn = '', this.textEn = '', this.titleNe = '', this.textNe = ''});

  factory AppNotice.fromJson(Map<String, dynamic> j) => AppNotice(
        level: j['level'] as String? ?? 'info',
        titleEn: j['title_en'] as String? ?? '',
        textEn: j['text_en'] as String? ?? '',
        titleNe: j['title_ne'] as String? ?? '',
        textNe: j['text_ne'] as String? ?? '',
      );

  /// Changes whenever the notice text changes, so a dismissed notice comes back when it is replaced.
  String get key => Object.hash(level, titleEn, textEn, titleNe, textNe).toString();
  String title(bool ne) => ne && titleNe.isNotEmpty ? titleNe : titleEn;
  String text(bool ne) => ne && textNe.isNotEmpty ? textNe : textEn;
}

class AppConfig {
  final bool mustUpdate;
  final String minVersion, latestVersion, updateUrl;
  final AppNotice? notice;
  final bool chatAppsAllowed;
  final List<String> trustedSenders;
  const AppConfig({
    this.mustUpdate = false,
    this.minVersion = kAppVersion,
    this.latestVersion = kAppVersion,
    this.updateUrl = '',
    this.notice,
    this.chatAppsAllowed = true,
    this.trustedSenders = const [],
  });

  factory AppConfig.fromJson(Map<String, dynamic> j) => AppConfig(
        mustUpdate: j['must_update'] == true,
        minVersion: j['min_version'] as String? ?? kAppVersion,
        latestVersion: j['latest_version'] as String? ?? kAppVersion,
        updateUrl: j['update_url'] as String? ?? '',
        notice: j['notice'] is Map ? AppNotice.fromJson(Map<String, dynamic>.from(j['notice'] as Map)) : null,
        chatAppsAllowed: j['chat_apps_allowed'] != false,
        trustedSenders: [for (final s in (j['trusted_senders'] as List?) ?? []) '$s'],
      );
}

class AdItem {
  final int id;
  final String title, body, link;
  final String? imageUrl; // full address, or null
  const AdItem({required this.id, required this.title, this.body = '', required this.link, this.imageUrl});
}
