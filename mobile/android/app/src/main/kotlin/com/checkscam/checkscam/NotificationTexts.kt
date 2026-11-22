// Texts of the CheckScam verdict notification in English or Nepali (Phase 9.6). The language comes from the
// app setting "flutter.language". Pure functions (no Android calls), so they are covered by JVM unit tests.

package com.checkscam.checkscam

class NotificationTexts(language: String) {
    private val ne = language == "ne"
    private fun t(english: String, nepali: String) = if (ne) nepali else english

    val channelName get() = t("Checked messages", "जाँचिएका सन्देशहरू")
    val channelDescription get() = t("Your messages after CheckScam has checked them", "CheckScam ले जाँचेपछिका तपाईंका सन्देशहरू")
    val unknownSender get() = t("Unknown sender", "अज्ञात पठाउने")
    val notChecked get() = t(
        "CheckScam could not check this message (no connection).",
        "CheckScam ले यो सन्देश जाँच्न सकेन (जडान छैन)।",
    )

    fun title(verdict: String?, from: String): String = when (verdict) {
        "dangerous" -> t("⛔ Scam warning · $from", "⛔ ठगीको चेतावनी · $from")
        "suspicious" -> t("⚠️ Be careful · $from", "⚠️ सावधान · $from")
        "safe" -> "✅ $from"
        else -> t("$from · not verified", "$from · जाँच भएन")
    }

    /** The strongest reason: the server's English text, or a Nepali text per reason code. */
    fun reason(code: String?, english: String?): String? {
        if (!ne || code == null) return english
        return nepaliReasons.entries.firstOrNull { code.startsWith(it.key) }?.value ?: english
    }

    /** The server's advice sentence; known sentences are translated, anything new stays in English. */
    fun suggestion(english: String): String = if (ne) nepaliSuggestions[english] ?: english else english

    /** Ends a sentence with "." (English) or "।" (Nepali) unless it already has one. */
    fun sentence(s: String): String = if (s.endsWith(".") || s.endsWith("।")) s else s + t(".", "।")

    companion object {
        private val nepaliReasons = linkedMapOf(
            "NEW_DOMAIN" to "लिंकको डोमेन भर्खरै दर्ता गरिएको हो",
            "MIRA_SCAM" to "सन्देश ठगी जस्तो देखिन्छ",
            "MIRA_AD" to "सन्देश विज्ञापन जस्तो देखिन्छ",
            "MIRA_NORMAL" to "सन्देश सामान्य जस्तो देखिन्छ",
            "ASKS_SECRET" to "सन्देशले OTP, PIN वा पासवर्ड माग्छ",
            "BRAND_MISMATCH" to "सन्देशमा कम्पनीको नाम छ तर लिंक त्यसको आधिकारिक साइट होइन",
            "BRAND_IN_DOMAIN" to "लिंकले कम्पनी भएको बहाना गर्छ तर आधिकारिक साइट होइन",
            "TYPOSQUAT" to "लिंक आधिकारिक साइट जस्तै देखिन्छ तर हिज्जे फरक छ",
            "GAMBLING_WORDS" to "सन्देशले जुवा वा बेटिङमा बोलाउँछ",
            "OTX_REPORTED" to "लिंकबारे AlienVault OTX मा खतरा रिपोर्ट छन्",
            "IP_HOST" to "लिंकमा नामको सट्टा IP ठेगाना मात्र छ",
            "NO_HTTPS" to "लिंक सुरक्षित छैन (HTTPS छैन)",
            "SUSPICIOUS_TLD" to "लिंकको डोमेनको अन्त्य जोखिमपूर्ण छ",
            "SHORTENER" to "लिंक छोटो पारिएको छ, साँचो ठेगाना लुकेको छ",
            "COMPLEX_HOST" to "लिंकको ठेगाना असामान्य रूपमा लामो वा जटिल छ",
            "HARD_OTP_LINK" to "OTP/PIN माग्छ र आधिकारिक नभएको साइटको लिंक दिन्छ",
        )

        private val nepaliSuggestions = mapOf(
            "This is very likely a scam. Never share your OTP, PIN or password with anyone." to
                "यो ठगी हुने सम्भावना धेरै छ। आफ्नो OTP, PIN वा पासवर्ड कसैलाई नदिनुहोस्।",
            "This is very likely a scam. Do not open the link or enter any details." to
                "यो ठगी हुने सम्भावना धेरै छ। लिंक नखोल्नुहोस् र कुनै विवरण नभर्नुहोस्।",
            "This is very likely a scam. Do not reply, call back or send money." to
                "यो ठगी हुने सम्भावना धेरै छ। जवाफ नदिनुहोस्, फोन नगर्नुहोस् र पैसा नपठाउनुहोस्।",
            "Be careful. Do not click links or send money until you confirm with the company through its official number or app." to
                "सावधान रहनुहोस्। कम्पनीको आधिकारिक नम्बर वा एपबाट पक्का नगरेसम्म लिंक नथिच्नुहोस् र पैसा नपठाउनुहोस्।",
            "No scam signs found. Still, never share your OTP or PIN with anyone." to
                "ठगीका कुनै संकेत भेटिएन। तैपनि आफ्नो OTP वा PIN कसैलाई नदिनुहोस्।",
        )
    }
}
