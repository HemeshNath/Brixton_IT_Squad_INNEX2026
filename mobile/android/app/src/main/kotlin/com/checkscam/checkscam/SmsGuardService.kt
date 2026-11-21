// Notification listener: hides new SMS (and optional chat) notifications, checks them with the API, re-posts them with the verdict.

package com.checkscam.checkscam

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.provider.Telephony
import android.util.Log
import java.util.concurrent.Executors

/**
 * "Option B" interception: when the SMS app (or optionally WhatsApp/Viber) posts a
 * notification, we read sender + text, hide that notification, ask our API whether
 * it is a scam, then post our own notification with the verdict and the original text.
 *
 * The SMS itself is never touched - it stays in the SMS app. OTP messages and trusted
 * senders are left alone and never leave the phone.
 */
class SmsGuardService : NotificationListenerService() {

    private val executor = Executors.newFixedThreadPool(2)

    // key -> (time seen, whether we hid it). Messaging apps re-post the same
    // notification several times; we handle each message once.
    private val recent = object : LinkedHashMap<String, Pair<Long, Boolean>>(64, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Pair<Long, Boolean>>?) = size > 200
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        try {
            handle(sbn)
        } catch (e: Exception) {
            Log.w(TAG, "Could not handle notification", e)
        }
    }

    private fun handle(sbn: StatusBarNotification) {
        if (sbn.packageName == packageName) return
        val cfg = GuardConfig.load(this)
        if (!cfg.enabled || !isWatched(sbn.packageName, cfg)) return

        val n = sbn.notification
        if (n.flags and Notification.FLAG_GROUP_SUMMARY != 0) return
        if (n.flags and Notification.FLAG_ONGOING_EVENT != 0) return

        val msg = MessageExtractor.extract(n) ?: return
        val dedupeKey = "${sbn.packageName}|${msg.sender}|${msg.text}"

        synchronized(recent) {
            val seen = recent[dedupeKey]
            if (seen != null && System.currentTimeMillis() - seen.first < DEDUPE_MS) {
                if (seen.second) cancelNotification(sbn.key) // app re-posted what we already hid
                return
            }
        }

        if (LocalFilter.shouldSkip(msg)) {
            remember(dedupeKey, hidden = false)
            return
        }

        // Hide the original until we have a verdict.
        cancelNotification(sbn.key)
        remember(dedupeKey, hidden = true)
        val openOriginal = n.contentIntent

        executor.execute {
            val result = ApiClient.checkSms(this, cfg, msg, sbn.packageName)
            ResultNotifier.show(this, msg, result, openOriginal, dedupeKey.hashCode())
        }
    }

    private fun remember(key: String, hidden: Boolean) {
        synchronized(recent) { recent[key] = Pair(System.currentTimeMillis(), hidden) }
    }

    private fun isWatched(pkg: String, cfg: GuardConfig): Boolean {
        val defaultSms = try { Telephony.Sms.getDefaultSmsPackage(this) } catch (e: Exception) { null }
        if (pkg == defaultSms || pkg in SMS_APPS) return true
        return cfg.watchChatApps && pkg in CHAT_APPS
    }

    override fun onDestroy() {
        executor.shutdown()
        super.onDestroy()
    }

    companion object {
        const val TAG = "CheckScam"
        private const val DEDUPE_MS = 10 * 60 * 1000L
        val SMS_APPS = setOf(
            "com.google.android.apps.messaging",
            "com.samsung.android.messaging",
            "com.android.mms",
            "com.android.messaging",
            "com.oneplus.mms",
            "com.miui.smsextra",
        )
        val CHAT_APPS = setOf("com.whatsapp", "com.whatsapp.w4b", "com.viber.voip", "com.facebook.orca")
    }
}
