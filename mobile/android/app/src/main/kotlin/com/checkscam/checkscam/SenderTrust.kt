// Sender trust (on the phone only): is the sender saved in the user's contacts, and how many messages has
// CheckScam seen from this sender before? Only these two small facts go to the server - the contacts list and
// the sender list never leave the phone. The sender list is stored hashed (SHA-256 with a random per-install salt).

package com.checkscam.checkscam

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.ContactsContract
import android.util.Log
import java.security.MessageDigest
import java.util.UUID

/** What the phone knows about a sender. null = unknown (e.g. no contacts permission, manual check). */
data class SenderFacts(val inContacts: Boolean?, val seenBefore: Int?)

object SenderTrust {
    private const val PREFS = "checkscam_senders"
    private const val SALT_KEY = "_salt"
    private const val MAX_SENDERS = 5000
    private val PHONE_RE = Regex("^\\+?\\d[\\d\\s-]{6,}$")

    /** True for a phone number ("+977 9812-345678"), false for a name or sender ID ("Ram", "NABIL"). */
    fun looksLikePhone(sender: String): Boolean = PHONE_RE.matches(sender.trim())

    /** Digits only, Nepal country code removed, last 10 digits: "+977-981 2345678" -> "9812345678". */
    fun normalizeNumber(sender: String): String {
        var d = sender.filter { it.isDigit() }
        if (d.startsWith("00977")) d = d.substring(5) else if (d.startsWith("977") && d.length > 10) d = d.substring(3)
        return d.takeLast(10)
    }

    /** One key per sender and app group: all SMS apps count as one ("sms"), chat apps each on their own. */
    fun senderKey(appGroup: String, sender: String): String {
        val who = if (looksLikePhone(sender)) normalizeNumber(sender) else sender.trim().lowercase()
        return "$appGroup|$who"
    }

    fun appGroup(sourceApp: String): String = if (sourceApp in SmsGuardService.CHAT_APPS) sourceApp else "sms"

    fun hasContactsPermission(ctx: Context): Boolean =
        ctx.checkSelfPermission(Manifest.permission.READ_CONTACTS) == PackageManager.PERMISSION_GRANTED

    /** Is the sender saved in the contacts? null when the permission is missing or the sender is blank. */
    fun inContacts(ctx: Context, sender: String): Boolean? {
        if (sender.isBlank() || !hasContactsPermission(ctx)) return null
        return try {
            if (looksLikePhone(sender)) {
                val uri = Uri.withAppendedPath(ContactsContract.PhoneLookup.CONTENT_FILTER_URI, Uri.encode(sender.trim()))
                ctx.contentResolver.query(uri, arrayOf(ContactsContract.PhoneLookup._ID), null, null, null)
                    ?.use { it.count > 0 } ?: false
            } else {
                // SMS apps and WhatsApp show the saved name instead of the number for contacts.
                ctx.contentResolver.query(
                    ContactsContract.Contacts.CONTENT_URI, arrayOf(ContactsContract.Contacts._ID),
                    "${ContactsContract.Contacts.DISPLAY_NAME_PRIMARY} = ? COLLATE NOCASE", arrayOf(sender.trim()), null,
                )?.use { it.count > 0 } ?: false
            }
        } catch (e: Exception) {
            Log.w(SmsGuardService.TAG, "Contacts lookup failed: ${e.javaClass.simpleName}")
            null
        }
    }

    /** How many messages from this sender CheckScam saw before this one; then counts this one. */
    @Synchronized
    fun recordAndCount(ctx: Context, sourceApp: String, sender: String): Int? {
        if (sender.isBlank()) return null
        val prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val salt = prefs.getString(SALT_KEY, null) ?: UUID.randomUUID().toString().also {
            prefs.edit().putString(SALT_KEY, it).apply()
        }
        val key = hash(salt, senderKey(appGroup(sourceApp), sender))
        val now = System.currentTimeMillis()
        val (before, first) = parse(prefs.getString(key, null))
        val edit = prefs.edit().putString(key, "${before + 1}|${first ?: now}|$now")
        if (before == 0 && prefs.all.size > MAX_SENDERS) dropOldest(prefs, edit)
        edit.apply()
        return before
    }

    /** "count|firstSeen|lastSeen" -> (count, firstSeen). */
    fun parse(value: String?): Pair<Int, Long?> {
        val parts = value?.split("|") ?: return Pair(0, null)
        return Pair(parts.getOrNull(0)?.toIntOrNull() ?: 0, parts.getOrNull(1)?.toLongOrNull())
    }

    fun hash(salt: String, key: String): String =
        MessageDigest.getInstance("SHA-256").digest((salt + key).toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }

    private fun dropOldest(prefs: android.content.SharedPreferences, edit: android.content.SharedPreferences.Editor) {
        val oldest = prefs.all.filterKeys { it != SALT_KEY }
            .minByOrNull { (it.value as? String)?.split("|")?.getOrNull(2)?.toLongOrNull() ?: 0L }
        oldest?.let { edit.remove(it.key) }
    }

    /** Both facts for one incoming message (also counts it). */
    fun facts(ctx: Context, sourceApp: String, sender: String): SenderFacts =
        SenderFacts(inContacts(ctx, sender), recordAndCount(ctx, sourceApp, sender))
}
