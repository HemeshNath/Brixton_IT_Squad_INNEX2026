// Helpers for SmsGuardService: settings from Flutter, reading message notifications, on-phone OTP/trusted filter, API call, verdict notification.

package com.checkscam.checkscam

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.util.Log
import com.google.android.gms.tasks.Tasks
import com.google.firebase.FirebaseApp
import com.google.firebase.auth.FirebaseAuth
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.TimeUnit

data class IncomingMessage(val sender: String, val text: String)

data class CheckResult(val verdict: String, val score: Int, val suggestion: String, val topReason: String?)

/** Settings written by the Flutter side through shared_preferences ("flutter." prefix). */
data class GuardConfig(
    val enabled: Boolean,
    val watchChatApps: Boolean,
    val apiBaseUrl: String,
    val devUser: String,
    val authToken: String,
) {
    companion object {
        fun load(ctx: Context): GuardConfig {
            val p = ctx.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
            return GuardConfig(
                enabled = p.getBoolean("flutter.protection_enabled", true),
                watchChatApps = p.getBoolean("flutter.watch_chat_apps", false),
                apiBaseUrl = p.getString("flutter.api_base_url", "") ?: "",
                devUser = p.getString("flutter.dev_user", "") ?: "",
                authToken = p.getString("flutter.auth_token", "") ?: "",
            )
        }
    }
}

object MessageExtractor {
    private val summaryText = Regex("""^\d+\s+(new\s+)?messages?$""", RegexOption.IGNORE_CASE)

    fun extract(n: Notification): IncomingMessage? {
        val extras = n.extras ?: return null
        var sender = (extras.getCharSequence(Notification.EXTRA_CONVERSATION_TITLE)
            ?: extras.getCharSequence(Notification.EXTRA_TITLE))?.toString() ?: ""
        var text: String? = null

        // MessagingStyle notifications keep each message in EXTRA_MESSAGES; take the newest.
        @Suppress("DEPRECATION")
        val messages = extras.getParcelableArray(Notification.EXTRA_MESSAGES)
        if (!messages.isNullOrEmpty()) {
            val last = messages.last() as? Bundle
            text = last?.getCharSequence("text")?.toString()
            last?.getCharSequence("sender")?.toString()?.let { if (it.isNotBlank()) sender = it }
        }
        if (text.isNullOrBlank()) {
            text = (extras.getCharSequence(Notification.EXTRA_BIG_TEXT)
                ?: extras.getCharSequence(Notification.EXTRA_TEXT))?.toString()
        }
        val clean = text?.trim() ?: return null
        if (clean.isEmpty() || summaryText.matches(clean)) return null
        return IncomingMessage(sender.trim(), clean)
    }
}

/** Decides on the phone which messages never leave it (privacy). */
object LocalFilter {
    private val otpWord = Regex("""\b(otp|one[- ]time|verification code|passcode|code)\b|ओटीपी""", RegexOption.IGNORE_CASE)
    private val otpDigits = Regex("""(?<!\d)\d{4,8}(?!\d)""")
    private val link = Regex("""https?://|www\.|\b[a-z0-9-]+\.(com|np|xyz|top|click|ly|net|org|info|link|me)\b""", RegexOption.IGNORE_CASE)
    private val trustedSenders = setOf(
        "esewa", "khalti", "imepay", "fonepay", "ntc", "nepaltelecom", "ncell", "nabil", "nicasia",
        "globalime", "nimb", "himalayan", "sanima", "kumari", "prabhu", "laxmisunrise", "nepalbank", "rbb",
    )

    fun isOtp(text: String) = otpWord.containsMatchIn(text) && otpDigits.containsMatchIn(text) && !link.containsMatchIn(text)

    fun isTrustedSender(sender: String): Boolean {
        val key = sender.lowercase().replace(Regex("[^a-z0-9]"), "")
        return key.isNotEmpty() && trustedSenders.any { key == it || key.startsWith(it) }
    }

    /** OTPs are skipped always. Trusted senders are skipped only when the message has no link. */
    fun shouldSkip(msg: IncomingMessage) = isOtp(msg.text) || (isTrustedSender(msg.sender) && !link.containsMatchIn(msg.text))
}

object ApiClient {
    /**
     * A fresh Firebase ID token for the signed-in Google user, or null when Firebase is not
     * configured (no google-services.json) or nobody is signed in. Firebase refreshes the token
     * itself when it is close to expiring, so this works even hours after sign-in.
     */
    private fun firebaseToken(ctx: Context): String? = try {
        if (FirebaseApp.getApps(ctx).isEmpty()) null
        else FirebaseAuth.getInstance().currentUser?.let { user ->
            Tasks.await(user.getIdToken(false), 5, TimeUnit.SECONDS).token
        }
    } catch (e: Exception) {
        Log.w(SmsGuardService.TAG, "No Firebase token: ${e.javaClass.simpleName}")
        null
    }

    fun checkSms(ctx: Context, cfg: GuardConfig, msg: IncomingMessage, sourceApp: String): CheckResult? {
        if (cfg.apiBaseUrl.isBlank()) return null
        // Sign-in order: Google (Firebase) -> token saved by Flutter -> development name.
        val token = firebaseToken(ctx) ?: cfg.authToken.ifBlank { null }
        var conn: HttpURLConnection? = null
        return try {
            conn = (URL(cfg.apiBaseUrl.trimEnd('/') + "/check/sms").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 3000
                readTimeout = 5000
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                if (token != null) setRequestProperty("Authorization", "Bearer $token")
                else if (cfg.devUser.isNotBlank()) setRequestProperty("X-Dev-User", cfg.devUser)
            }
            val source = if (sourceApp in SmsGuardService.CHAT_APPS) "notification" else "sms"
            val body = JSONObject()
                .put("text", msg.text)
                .put("sender", msg.sender)
                .put("source_app", sourceApp)
                .put("source", source)
            conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            if (conn.responseCode != 200) {
                Log.w(SmsGuardService.TAG, "API returned ${conn.responseCode}")
                return null
            }
            val json = JSONObject(conn.inputStream.bufferedReader(Charsets.UTF_8).readText())
            val reasons = json.optJSONArray("reasons")
            var top: String? = null
            if (reasons != null) {
                var best = -1
                for (i in 0 until reasons.length()) {
                    val r = reasons.getJSONObject(i)
                    if (r.optInt("points") > best) { best = r.optInt("points"); top = r.optString("text") }
                }
            }
            CheckResult(json.optString("verdict", "unknown"), json.optInt("score"), json.optString("suggestion"), top)
        } catch (e: Exception) {
            Log.w(SmsGuardService.TAG, "Check failed: ${e.javaClass.simpleName}")
            null
        } finally {
            conn?.disconnect()
        }
    }
}

object ResultNotifier {
    private const val CHANNEL_ID = "checkscam_results"

    fun ensureChannel(ctx: Context) {
        val nm = ctx.getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CHANNEL_ID) == null) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "Checked messages", NotificationManager.IMPORTANCE_HIGH).apply {
                    description = "Your messages after CheckScam has checked them"
                }
            )
        }
    }

    fun show(ctx: Context, msg: IncomingMessage, result: CheckResult?, openOriginal: PendingIntent?, id: Int) {
        ensureChannel(ctx)
        val from = msg.sender.ifBlank { "Unknown sender" }
        val (title, color) = when (result?.verdict) {
            "dangerous" -> "⛔ Scam warning · $from" to Color.rgb(198, 40, 40)
            "suspicious" -> "⚠️ Be careful · $from" to Color.rgb(239, 108, 0)
            "safe" -> "✅ $from" to Color.rgb(46, 125, 50)
            else -> "$from · not verified" to Color.GRAY
        }
        val details = buildString {
            append(msg.text)
            if (result != null && result.verdict != "safe") {
                append("\n\n")
                result.topReason?.let { append(it).append(". ") }
                append(result.suggestion)
            }
            if (result == null) append("\n\nCheckScam could not check this message (no connection).")
        }
        val openApp = PendingIntent.getActivity(
            ctx, 0, Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        // Tapping a safe message opens the SMS thread; a risky one opens CheckScam first.
        val tap = if (result?.verdict == "safe" || result == null) openOriginal ?: openApp else openApp

        val notification = Notification.Builder(ctx, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(msg.text)
            .setStyle(Notification.BigTextStyle().bigText(details))
            .setColor(color)
            .setContentIntent(tap)
            .setAutoCancel(true)
            .setCategory(Notification.CATEGORY_MESSAGE)
            .build()
        ctx.getSystemService(NotificationManager::class.java).notify(id, notification)
    }
}
