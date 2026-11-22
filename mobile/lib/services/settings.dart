// Saved settings (server URL, sign-in, switches, language, onboarding seen). Shared with the Kotlin listener through SharedPreferences.

import 'package:shared_preferences/shared_preferences.dart';

import '../models/app_config.dart';

/// App settings. Stored with the legacy SharedPreferences API on purpose: the native
/// SmsGuardService reads the same file ("FlutterSharedPreferences", keys "flutter.*").
class AppSettings {
  static const _apiBase = 'api_base_url';
  static const _devUser = 'dev_user';
  static const _token = 'auth_token';
  static const _enabled = 'protection_enabled';
  static const _chatApps = 'watch_chat_apps';
  static const _language = 'language'; // "en" | "ne" (also read by the Kotlin notifications)
  static const _onboarded = 'onboarding_done';
  // App control (A10) - also read by the Kotlin listener
  static const _mustUpdate = 'must_update';
  static const _chatAppsAllowed = 'chat_apps_allowed';
  static const _syncedSenders = 'synced_trusted_senders'; // one sender ID per line
  static const _dismissedNotice = 'dismissed_notice';

  final SharedPreferences _p;
  AppSettings(this._p);

  static Future<AppSettings> load() async => AppSettings(await SharedPreferences.getInstance());

  String get apiBaseUrl => _p.getString(_apiBase) ?? '';
  String get devUser => _p.getString(_devUser) ?? '';
  String get authToken => _p.getString(_token) ?? '';
  bool get protectionEnabled => _p.getBool(_enabled) ?? true;
  bool get watchChatApps => _p.getBool(_chatApps) ?? false;
  String get language => _p.getString(_language) == 'ne' ? 'ne' : 'en';
  bool get onboardingDone => _p.getBool(_onboarded) ?? false;
  bool get mustUpdate => _p.getBool(_mustUpdate) ?? false;
  bool get chatAppsAllowed => _p.getBool(_chatAppsAllowed) ?? true;
  List<String> get syncedSenders => (_p.getString(_syncedSenders) ?? '').split('\n').where((s) => s.isNotEmpty).toList();
  String get dismissedNotice => _p.getString(_dismissedNotice) ?? '';
  Future<void> dismissNotice(String key) => _p.setString(_dismissedNotice, key);

  /// Stores what the server's app control says. Chat apps switched off on the server also switches them off here.
  Future<void> applyAppConfig(AppConfig c) async {
    await _p.setBool(_mustUpdate, c.mustUpdate);
    await _p.setBool(_chatAppsAllowed, c.chatAppsAllowed);
    if (!c.chatAppsAllowed) await _p.setBool(_chatApps, false);
    if (c.trustedSenders.isNotEmpty) await _p.setString(_syncedSenders, c.trustedSenders.join('\n'));
  }

  bool get isConfigured => apiBaseUrl.isNotEmpty && (devUser.isNotEmpty || authToken.isNotEmpty);

  Future<void> setApiBaseUrl(String v) => _p.setString(_apiBase, normalizeBaseUrl(v));
  Future<void> setDevUser(String v) => _p.setString(_devUser, v.trim());
  Future<void> setAuthToken(String v) => _p.setString(_token, v);
  Future<void> setProtectionEnabled(bool v) => _p.setBool(_enabled, v);
  Future<void> setWatchChatApps(bool v) => _p.setBool(_chatApps, v);
  Future<void> setLanguage(String v) => _p.setString(_language, v == 'ne' ? 'ne' : 'en');
  Future<void> setOnboardingDone(bool v) => _p.setBool(_onboarded, v);

  /// "192.168.1.5:8000" -> "http://192.168.1.5:8000/api/v1"
  static String normalizeBaseUrl(String input) {
    var url = input.trim();
    if (url.isEmpty) return '';
    if (!url.startsWith('http://') && !url.startsWith('https://')) url = 'http://$url';
    url = url.replaceAll(RegExp(r'/+$'), '');
    if (!url.endsWith('/api/v1')) url = '$url/api/v1';
    return url;
  }
}
