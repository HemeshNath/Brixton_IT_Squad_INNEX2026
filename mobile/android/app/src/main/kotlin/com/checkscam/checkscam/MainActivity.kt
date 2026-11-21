// Flutter host activity + method channel 'checkscam/native': notification access, permissions, battery settings, SMS simulator.

package com.checkscam.checkscam

import android.Manifest
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.util.concurrent.Executors

class MainActivity : FlutterActivity() {
    private val executor = Executors.newSingleThreadExecutor()

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "checkscam/native").setMethodCallHandler { call, result ->
            when (call.method) {
                "isListenerEnabled" -> result.success(isListenerEnabled())
                "openListenerSettings" -> {
                    startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                    result.success(null)
                }
                "hasNotificationPermission" -> result.success(hasNotificationPermission())
                "requestNotificationPermission" -> {
                    if (Build.VERSION.SDK_INT >= 33 && !hasNotificationPermission()) {
                        requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
                    }
                    result.success(null)
                }
                "openBatterySettings" -> {
                    startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                    result.success(null)
                }
                // Demo/testing: runs the same check + notification as a real SMS would get.
                "simulateMessage" -> {
                    val msg = IncomingMessage(call.argument<String>("sender") ?: "", call.argument<String>("text") ?: "")
                    val ctx = applicationContext
                    executor.execute {
                        val skipped = LocalFilter.shouldSkip(msg)
                        val res = if (skipped) null else ApiClient.checkSms(ctx, GuardConfig.load(ctx), msg, "simulator")
                        if (!skipped) ResultNotifier.show(ctx, msg, res, null, msg.hashCode())
                        runOnUiThread { result.success(if (skipped) "skipped" else (res?.verdict ?: "failed")) }
                    }
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun isListenerEnabled(): Boolean {
        val flat = Settings.Secure.getString(contentResolver, "enabled_notification_listeners") ?: return false
        val me = ComponentName(this, SmsGuardService::class.java).flattenToString()
        return flat.split(":").any { it == me }
    }

    private fun hasNotificationPermission(): Boolean =
        Build.VERSION.SDK_INT < 33 ||
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
}
