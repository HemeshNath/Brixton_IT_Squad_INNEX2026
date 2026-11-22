"""Readable name of the app a message came from (backend flow B1) - the "Source" line of MIRA's prompt.

The phone sends `source` ("sms" | "notification" | "manual") and `source_app` (the Android package name of
the app that showed the message, e.g. "com.whatsapp"). This turns them into a name such as "WhatsApp"."""
from __future__ import annotations

APP_NAMES = {
    "com.whatsapp": "WhatsApp",
    "com.whatsapp.w4b": "WhatsApp Business",
    "com.viber.voip": "Viber",
    "com.facebook.orca": "Messenger",
    "com.facebook.mlite": "Messenger Lite",
    "org.telegram.messenger": "Telegram",
    "org.thunderdog.challegram": "Telegram",
    "com.imo.android.imoim": "imo",
    "com.instagram.android": "Instagram",
}

FIXED = {"sms": "SMS", "manual": "Pasted into CheckScam", "link": "Link pasted into CheckScam"}


def source_name(source: str = "", source_app: str = "") -> str:
    """"sms" -> "SMS"; a chat app's notification -> its name ("WhatsApp"); unknown app -> "Other app"."""
    source = (source or "").strip().lower()
    app = (source_app or "").strip().lower()
    if app in APP_NAMES:
        return APP_NAMES[app]
    if source in FIXED:
        return FIXED[source]
    if source == "notification":
        return "Other app"
    return "SMS"
