// Calls into Kotlin (MainActivity) for notification access, permissions, battery settings and the SMS simulator.

import 'package:flutter/services.dart';

/// Talks to MainActivity.kt (channel "checkscam/native").
class NativeBridge {
  static const _ch = MethodChannel('checkscam/native');

  static Future<bool> isListenerEnabled() async => await _ch.invokeMethod<bool>('isListenerEnabled') ?? false;
  static Future<void> openListenerSettings() => _ch.invokeMethod('openListenerSettings');
  static Future<bool> hasNotificationPermission() async =>
      await _ch.invokeMethod<bool>('hasNotificationPermission') ?? false;
  static Future<void> requestNotificationPermission() => _ch.invokeMethod('requestNotificationPermission');
  static Future<void> openBatterySettings() => _ch.invokeMethod('openBatterySettings');

  /// Runs a message through the same path a real SMS takes and shows the notification.
  /// Returns the verdict, "skipped" (OTP / trusted sender) or "failed".
  static Future<String> simulateMessage(String sender, String text) async =>
      await _ch.invokeMethod<String>('simulateMessage', {'sender': sender, 'text': text}) ?? 'failed';
}
