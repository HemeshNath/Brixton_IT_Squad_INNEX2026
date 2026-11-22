// Calls into Kotlin (MainActivity) for notification access, permissions, battery settings, the SMS simulator,
// and the result of a tapped CheckScam warning notification.

import 'dart:convert';

import 'package:flutter/services.dart';

import '../models/check_result.dart';

/// A tapped CheckScam warning: the server's result plus the original message and sender (from the phone).
class TappedCheck {
  final CheckResult result;
  final String message;
  final String sender;
  const TappedCheck(this.result, this.message, this.sender);

  static TappedCheck? fromNative(Object? data) {
    if (data is! Map) return null;
    try {
      final json = jsonDecode(data['json'] as String? ?? '') as Map<String, dynamic>;
      return TappedCheck(CheckResult.fromJson(json), data['message'] as String? ?? '', data['sender'] as String? ?? '');
    } catch (_) {
      return null; // broken data: just open the home screen
    }
  }
}

/// Talks to MainActivity.kt (channel "checkscam/native").
class NativeBridge {
  static const _ch = MethodChannel('checkscam/native');

  static Future<bool> isListenerEnabled() async => await _ch.invokeMethod<bool>('isListenerEnabled') ?? false;
  static Future<void> openListenerSettings() => _ch.invokeMethod('openListenerSettings');
  static Future<bool> hasNotificationPermission() async =>
      await _ch.invokeMethod<bool>('hasNotificationPermission') ?? false;
  static Future<void> requestNotificationPermission() => _ch.invokeMethod('requestNotificationPermission');
  static Future<void> openBatterySettings() => _ch.invokeMethod('openBatterySettings');

  /// Opens a web link in the phone's browser (ads, "update the app"). False if no browser could open it.
  static Future<bool> openUrl(String url) async {
    try {
      return await _ch.invokeMethod<bool>('openUrl', {'url': url}) ?? false;
    } on MissingPluginException {
      return false; // not on Android (tests)
    }
  }

  /// Sender trust: contacts permission (contacts are checked on the phone only and never sent anywhere).
  static Future<bool> hasContactsPermission() async => await _ch.invokeMethod<bool>('hasContactsPermission') ?? false;
  static Future<void> requestContactsPermission() => _ch.invokeMethod('requestContactsPermission');

  /// Phone brand (Build.MANUFACTURER), e.g. "realme", for the battery guide. Empty when unknown.
  static Future<String> manufacturer() async {
    try {
      return await _ch.invokeMethod<String>('getManufacturer') ?? '';
    } on MissingPluginException {
      return ''; // not on Android (tests)
    }
  }

  /// Opens this app's Android "App info" page (battery, permissions).
  static Future<void> openAppDetails() => _ch.invokeMethod('openAppDetails');

  /// Opens the brand's auto-start page; falls back to App info. True if a brand page opened.
  static Future<bool> openAutostart() async => await _ch.invokeMethod<bool>('openAutostart') ?? false;

  /// Runs a message through the same path a real SMS takes and shows the notification.
  /// Returns the verdict, "skipped" (OTP / trusted sender) or "failed".
  static Future<String> simulateMessage(String sender, String text) async =>
      await _ch.invokeMethod<String>('simulateMessage', {'sender': sender, 'text': text}) ?? 'failed';

  /// The warning the app was opened from (null if it was opened normally). Returned once.
  static Future<TappedCheck?> takeLaunchCheck() async {
    try {
      return TappedCheck.fromNative(await _ch.invokeMethod<Object?>('takeLaunchCheck'));
    } on MissingPluginException {
      return null; // not on Android (tests)
    }
  }

  /// Opens the original SMS conversation of the tapped warning. False if it is not available.
  static Future<bool> openOriginalMessage() async =>
      await _ch.invokeMethod<bool>('openOriginalMessage') ?? false;

  /// Called when a warning is tapped while the app is already open.
  static void onCheckTapped(void Function(TappedCheck check) handler) {
    _ch.setMethodCallHandler((call) async {
      if (call.method == 'openCheck') {
        final check = TappedCheck.fromNative(call.arguments);
        if (check != null) handler(check);
      }
      return null;
    });
  }
}
