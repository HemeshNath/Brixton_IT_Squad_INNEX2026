// Flutter host activity + method channel 'checkscam/native': notification access, permissions, battery settings,
// SMS simulator, and opening the result screen when a CheckScam warning notification is tapped.

package com.checkscam.checkscam

import android.Manifest
import android.app.PendingIntent
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.util.concurrent.Executors

class MainActivity : FlutterActivity() {
    private val executor = Executors.newSingleThreadExecutor()
    private var channel: MethodChannel? = null
    private var pendingCheck: Map<String, String>? = null  // result from a tapped notification, not yet shown
    private var originalMessage: PendingIntent? = null      // opens the original SMS conversation

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        readCheckFrom(intent)  // app was closed and started from the notification
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        readCheckFrom(intent)  // app was already open: tell Flutter right away
        pendingCheck?.let { channel?.invokeMethod("openCheck", it); pendingCheck = null }
    }

    private fun readCheckFrom(intent: Intent?) {
        if (intent?.action != ACTION_OPEN_CHECK) return
        val json = intent.getStringExtra(EXTRA_CHECK_JSON) ?: return
        pendingCheck = mapOf(
            "json" to json,
            "message" to (intent.getStringExtra(EXTRA_MESSAGE) ?: ""),
            "sender" to (intent.getStringExtra(EXTRA_SENDER) ?: ""),
        )
        @Suppress("DEPRECATION")
        originalMessage = if (Build.VERSION.SDK_INT >= 33) intent.getParcelableExtra(EXTRA_OPEN_ORIGINAL, PendingIntent::class.java)
        else intent.getParcelableExtra(EXTRA_OPEN_ORIGINAL)
        intent.action = null  // handle each tap once (not again after rotation)
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        channel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "checkscam/native")
        channel!!.setMethodCallHandler { call, result ->
            when (call.method) {
                // Result screen: the tapped notification's result (once), and the original SMS.
                "takeLaunchCheck" -> {
                    result.success(pendingCheck)
                    pendingCheck = null
                }
                "openOriginalMessage" -> {
                    val sent = try { originalMessage?.send(); originalMessage != null } catch (e: Exception) { false }
                    result.success(sent)
                }
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

    companion object {
        const val ACTION_OPEN_CHECK = "com.checkscam.OPEN_CHECK"
        const val EXTRA_CHECK_JSON = "check_json"
        const val EXTRA_MESSAGE = "message"
        const val EXTRA_SENDER = "sender"
        const val EXTRA_OPEN_ORIGINAL = "open_original"
    }

    private fun hasNotificationPermission(): Boolean =
        Build.VERSION.SDK_INT < 33 ||
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
}
