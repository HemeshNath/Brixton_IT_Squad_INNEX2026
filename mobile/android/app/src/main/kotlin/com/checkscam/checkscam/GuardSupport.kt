// Helpers for SmsGuardService: settings from Flutter, reading message notifications, on-phone OTP/trusted filter, API call, verdict notification.

package com.checkscam.checkscam

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
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

/** Server verdict. `raw` is the full JSON answer, handed to the app's result screen when the notification is tapped. */
data class CheckResult(
    val verdict: String,
    val score: Int,
    val suggestion: String,
    val topReason: String?,
    val raw: String = "",
    val topCode: String? = null, // reason code of topReason, used for the Nepali text
    val riskClass: String? = null, // owner's class (B7): low | suspicious | high | critical | very_harmful
) {
    /** What the notification's title and colour follow: the risk class when there is one, else the verdict. */
    val level: String get() = riskClass ?: verdict
}

/** The reason to show (B7): the first warning (owner's questions), else the reason with the most points. */
fun pickTopReason(codes: List<String>, texts: List<String>, points: List<Int>): Pair<String?, String?> {
    val firstWarning = codes.indices.firstOrNull {
        !codes[it].startsWith("RISK_") && codes[it] != "NOT_CHECKED" && (points.getOrNull(it) ?: 0) >= 0
    }  // a trust reason (negative points, e.g. saved contact) is never shown as the warning
    val i = firstWarning ?: points.indices.maxByOrNull { points[it] } ?: return Pair(null, null)
    return Pair(texts[i], codes[i])
}

/** Notification colour per owner risk class / verdict (same colours as the app). */
fun levelColor(level: String?): Int = when (level) {
    "very_harmful" -> 0xFFB71C1C.toInt()
    "critical" -> 0xFFD84315.toInt()
    "high" -> 0xFFEF6C00.toInt()
    "suspicious" -> 0xFFF9A825.toInt()
    "low" -> 0xFF2E7D32.toInt()
    "dangerous" -> 0xFFC62828.toInt()
    "safe" -> 0xFF2E7D32.toInt()
    else -> 0xFF9E9E9E.toInt()
}

/** Settings written by the Flutter side through shared_preferences ("flutter." prefix). */
data class GuardConfig(
    val enabled: Boolean,
    val watchChatApps: Boolean,
    val apiBaseUrl: String,
    val devUser: String,
    val authToken: String,
    val language: String = "en", // "en" | "ne" (app setting), used for the notification texts
    val syncedTrustedSenders: Set<String> = emptySet(), // official sender IDs from the server (A10)
) {
    companion object {
        fun load(ctx: Context): GuardConfig {
            val p = ctx.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
            return GuardConfig(
                // A10: an app older than the server's minimum version stops checking until it is updated
                enabled = p.getBoolean("flutter.protection_enabled", true) && !p.getBoolean("flutter.must_update", false),
                // A10: the admin panel can switch chat apps off for everyone
                watchChatApps = p.getBoolean("flutter.watch_chat_apps", false) && p.getBoolean("flutter.chat_apps_allowed", true),
                apiBaseUrl = p.getString("flutter.api_base_url", "") ?: "",
                devUser = p.getString("flutter.dev_user", "") ?: "",
                authToken = p.getString("flutter.auth_token", "") ?: "",
                language = p.getString("flutter.language", "en") ?: "en",
                syncedTrustedSenders = (p.getString("flutter.synced_trusted_senders", "") ?: "")
                    .split("\n").map { LocalFilter.senderKey(it) }.filter { it.isNotEmpty() }.toSet(),
            )
        }
    }
}

object MessageExtractor {
    private val summaryText = Regex("""^\d+\s+(new\s+)?messages?$""", RegexOption.IGNORE_CASE)

    /** Reads the notification's fields, then picks the message with [pick]. */
    fun extract(n: Notification): IncomingMessage? {
        val extras = n.extras ?: return null
        // MessagingStyle notifications keep each message in EXTRA_MESSAGES; only the newest is needed.
        @Suppress("DEPRECATION")
        val last = extras.getParcelableArray(Notification.EXTRA_MESSAGES)?.lastOrNull() as? Bundle
        return pick(
            conversationTitle = extras.getCharSequence(Notification.EXTRA_CONVERSATION_TITLE)?.toString(),
            title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString(),
            lastMessageSender = last?.getCharSequence("sender")?.toString(),
            lastMessageText = last?.getCharSequence("text")?.toString(),
            bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString(),
            text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString(),
        )
    }

    /**
     * Picks sender and text (pure, unit-tested): the newest MessagingStyle message first, else the big text,
     * else the normal text. Summaries like "3 new messages" and empty texts give null.
     */
    fun pick(
        conversationTitle: String?,
        title: String?,
        lastMessageSender: String?,
        lastMessageText: String?,
        bigText: String?,
        text: String?,
    ): IncomingMessage? {
        var sender = conversationTitle ?: title ?: ""
        if (!lastMessageSender.isNullOrBlank()) sender = lastMessageSender
        val chosen = listOf(lastMessageText, bigText, text).firstOrNull { !it.isNullOrBlank() }
        val clean = chosen?.trim() ?: return null
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

    fun senderKey(sender: String) = sender.lowercase().replace(Regex("[^a-z0-9]"), "")

    /** Built-in official sender IDs plus the server's list (A10: synced every time the app opens). */
    fun isTrustedSender(sender: String, extra: Set<String> = emptySet()): Boolean {
        val key = senderKey(sender)
        return key.isNotEmpty() && (trustedSenders + extra).any { key == it || key.startsWith(it) }
    }

    /** OTPs are skipped always. Trusted senders are skipped only when the message has no link. */
    fun shouldSkip(msg: IncomingMessage, extra: Set<String> = emptySet()) =
        isOtp(msg.text) || (isTrustedSender(msg.sender, extra) && !link.containsMatchIn(msg.text))
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

    fun checkSms(ctx: Context, cfg: GuardConfig, msg: IncomingMessage, sourceApp: String,
                 facts: SenderFacts = SenderFacts(null, null)): CheckResult? {
        if (cfg.apiBaseUrl.isBlank()) return null
        // Sign-in order: Google (Firebase) -> token saved by Flutter -> development name.
        val token = firebaseToken(ctx) ?: cfg.authToken.ifBlank { null }
        var conn: HttpURLConnection? = null
        return try {
            conn = (URL(cfg.apiBaseUrl.trimEnd('/') + "/check/sms").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 3000
                readTimeout = 25_000 // trained model ~0.1 s + link lookups up to a few seconds (server stops at 20 s)
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
                // sender trust (only these two facts leave the phone; null = unknown)
                .put("sender_in_contacts", facts.inContacts ?: JSONObject.NULL)
                .put("sender_seen_before", facts.seenBefore ?: JSONObject.NULL)
            conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            if (conn.responseCode != 200) {
                Log.w(SmsGuardService.TAG, "API returned ${conn.responseCode}")
                return null
            }
            val json = JSONObject(conn.inputStream.bufferedReader(Charsets.UTF_8).readText())
            val reasons = json.optJSONArray("reasons")
            val codes = mutableListOf<String>()
            val texts = mutableListOf<String>()
            val points = mutableListOf<Int>()
            if (reasons != null) {
                for (i in 0 until reasons.length()) {
                    val r = reasons.getJSONObject(i)
                    codes.add(r.optString("code")); texts.add(r.optString("text")); points.add(r.optInt("points"))
                }
            }
            val (top, topCode) = pickTopReason(codes, texts, points)
            CheckResult(
                json.optString("verdict", "unknown"), json.optInt("score"), json.optString("suggestion"), top,
                json.toString(), topCode, if (json.isNull("risk_class")) null else json.optString("risk_class"),
            )
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

    /** Creates the channel, or updates its name/description when the app language changed. */
    fun ensureChannel(ctx: Context, texts: NotificationTexts) {
        ctx.getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL_ID, texts.channelName, NotificationManager.IMPORTANCE_HIGH).apply {
                description = texts.channelDescription
            }
        )
    }

    /** B7: shown at once while the server checks (~30-70 s), so the hidden message is still visible.
     *  The result notification later replaces it (same id). */
    fun showChecking(ctx: Context, msg: IncomingMessage, openOriginal: PendingIntent?, id: Int) {
        val texts = NotificationTexts(GuardConfig.load(ctx).language)
        ensureChannel(ctx, texts)
        val from = msg.sender.ifBlank { texts.unknownSender }
        val builder = Notification.Builder(ctx, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(texts.checkingTitle(from))
            .setContentText(msg.text)
            .setStyle(Notification.BigTextStyle().bigText(msg.text + "\n\n" + texts.checkingText))
            .setColor(levelColor(null))
            .setOnlyAlertOnce(true)
            .setCategory(Notification.CATEGORY_MESSAGE)
        openOriginal?.let { builder.setContentIntent(it) }
        ctx.getSystemService(NotificationManager::class.java).notify(id, builder.build())
    }

    fun show(ctx: Context, msg: IncomingMessage, result: CheckResult?, openOriginal: PendingIntent?, id: Int) {
        val texts = NotificationTexts(GuardConfig.load(ctx).language)
        ensureChannel(ctx, texts)
        val from = msg.sender.ifBlank { texts.unknownSender }
        val title = texts.title(result?.level, from)
        val color = levelColor(result?.level)
        val details = buildString {
            append(msg.text)
            if (result != null && result.level !in setOf("safe", "low")) {
                append("\n\n")
                texts.reason(result.topCode, result.topReason)?.let { append(texts.sentence(it)).append(" ") }
                append(texts.suggestion(result.suggestion))
            }
            if (result == null) append("\n\n").append(texts.notChecked)
        }
        // Tapping a warning opens CheckScam on the result screen for THIS message. Each notification gets its
        // own request code, so the results of two notifications never overwrite each other.
        val appIntent = Intent(ctx, MainActivity::class.java).apply {
            action = MainActivity.ACTION_OPEN_CHECK
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            if (result != null) {
                putExtra(MainActivity.EXTRA_CHECK_JSON, result.raw)
                putExtra(MainActivity.EXTRA_MESSAGE, msg.text)    // original text, shown only on this phone
                putExtra(MainActivity.EXTRA_SENDER, msg.sender)
                openOriginal?.let { putExtra(MainActivity.EXTRA_OPEN_ORIGINAL, it) }
            }
        }
        val openApp = PendingIntent.getActivity(
            ctx, id, appIntent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        // Tapping a safe message opens the SMS thread; a risky one opens CheckScam first.
        val tap = if (result == null || result.level in setOf("safe", "low")) openOriginal ?: openApp else openApp

        val notification = Notification.Builder(ctx, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification) // white S silhouette (status bar icon)
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
