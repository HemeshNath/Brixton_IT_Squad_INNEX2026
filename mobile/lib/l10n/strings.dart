// All texts shown in the app, in English and Nepali (Phase 9.6). The chosen language is saved in settings
// ("flutter.language": "en" or "ne") so the Kotlin notifications use it too.
// S.of(context) gives the texts; LanguageScope (in main.dart) holds the current language.

import 'package:flutter/widgets.dart';

import '../models/check_result.dart';
import '../services/api.dart';

/// Holds the current language for the whole app and a way to change it.
class LanguageScope extends InheritedWidget {
  final String language; // "en" | "ne"
  final Future<void> Function(String language) setLanguage;

  const LanguageScope({super.key, required this.language, required this.setLanguage, required super.child});

  static LanguageScope? maybeOf(BuildContext context) => context.dependOnInheritedWidgetOfExactType<LanguageScope>();

  @override
  bool updateShouldNotify(LanguageScope old) => old.language != language;
}

class S {
  final bool ne; // true = Nepali
  const S(this.ne);

  static const en = S(false);
  static const nepali = S(true);

  /// Texts in the current language (English when no LanguageScope is above, e.g. in tests).
  static S of(BuildContext context) => LanguageScope.maybeOf(context)?.language == 'ne' ? nepali : en;

  String _t(String english, String nepali) => ne ? nepali : english;

  // ---- language switch ----
  String get language => _t('Language', 'भाषा');
  String get languageName => _t('English', 'नेपाली');

  // ---- sign-in screen ----
  String get tagline => _t('Scam protection for your messages', 'तपाईंका सन्देशहरूको ठगी सुरक्षा');
  String get serverAddress => _t('Server address', 'सर्भरको ठेगाना');
  String get enterServer => _t('Enter the server address.', 'सर्भरको ठेगाना लेख्नुहोस्।');
  String get signInGoogle => _t('Sign in with Google', 'Google बाट साइन इन गर्नुहोस्');
  String get googleNotSetUp =>
      _t('Google sign-in is not set up in this build yet.', 'यो संस्करणमा Google साइन इन अझै मिलाइएको छैन।');
  String get devSignInTitle => _t('Development sign-in (debug builds only)', 'डेभलपमेन्ट साइन इन (डिबग संस्करण मात्र)');
  String get yourName => _t('Your name', 'तपाईंको नाम');
  String get useDevSignIn => _t('Use development sign-in', 'डेभलपमेन्ट साइन इन प्रयोग गर्नुहोस्');
  String get enterDevName =>
      _t('Enter a name for the development sign-in.', 'डेभलपमेन्ट साइन इनका लागि नाम लेख्नुहोस्।');

  // ---- home screen ----
  String get pasteHint => _t('Paste your content here…', 'आफ्नो सन्देश यहाँ टाँस्नुहोस्…');
  String get paste => _t('Paste', 'टाँस्नुहोस्');
  String get pasteFirst => _t('Paste or type a message first.', 'पहिले सन्देश टाँस्नुहोस् वा लेख्नुहोस्।');
  String get clipboardEmpty => _t('Clipboard is empty.', 'क्लिपबोर्ड खाली छ।');
  String get protectedTitle => _t('Messages are protected', 'सन्देशहरू सुरक्षित छन्');
  String get protectionOff => _t('Protection is off', 'सुरक्षा बन्द छ');
  String get allowAccessText => _t(
      'Allow CheckScam to read message notifications so it can check new SMS before you see them. '
          'OTPs and bank messages stay on your phone.',
      'नयाँ SMS तपाईंले हेर्नुअघि जाँच्न CheckScam लाई सन्देशका सूचनाहरू पढ्ने अनुमति दिनुहोस्। '
          'OTP र बैंकका सन्देशहरू तपाईंकै फोनमा रहन्छन्।');
  String get allowAccess => _t('Allow notification access', 'सूचना पढ्ने अनुमति दिनुहोस्');
  String get allowNotifications => _t('Allow CheckScam notifications', 'CheckScam का सूचनाहरूलाई अनुमति दिनुहोस्');
  String get allowContacts => _t('Allow contacts (trust people you know)', 'सम्पर्क सूचीलाई अनुमति दिनुहोस् (चिनेका मान्छेलाई भरोसा)');
  String get allowContactsText => _t('Messages from saved contacts get more trust. Your contacts never leave your phone.',
      'सम्पर्क सूचीमा भएका मान्छेका सन्देशलाई बढी भरोसा गरिन्छ। तपाईंको सम्पर्क सूची फोनबाहिर कहिल्यै जाँदैन।');
  String get autoCheck => _t('Check new SMS automatically', 'नयाँ SMS आफैं जाँच्ने');
  String get chatApps => _t('Also check WhatsApp, Viber and Messenger', 'WhatsApp, Viber र Messenger पनि जाँच्ने');
  String get wrongResult => _t('Wrong result?', 'नतिजा गलत छ?');
  String get thanksFeedback => _t('Thanks! This helps train our model.', 'धन्यवाद! यसले हाम्रो मोडेल सुधार्न मद्दत गर्छ।');
  String get skippedLocal => _t('Skipped: OTP or trusted sender – it would not leave your phone.',
      'छोडियो: OTP वा भरपर्दो पठाउने – यो तपाईंको फोनबाट बाहिर जाँदैन।');
  String get serverUnreachable => _t('Could not reach the server.', 'सर्भरमा पुग्न सकिएन।');
  String notificationShown(String verdict) =>
      _t('Notification shown: $verdict', 'सूचना देखाइयो: ${verdictShort(verdict)}');

  // ---- settings sheet ----
  String signedInAs(String who) => _t('Signed in as $who', '$who को रूपमा साइन इन');
  String get history => _t('History', 'इतिहास');
  String get testAsSms => _t('Test as SMS', 'SMS जस्तै परीक्षण');
  String get testAsSmsSub =>
      _t('Shows the notification a real SMS would get', 'साँचो SMS आउँदा देखिने सूचना देखाउँछ');
  String get batterySettings => _t('Battery settings', 'ब्याट्री सेटिङ');
  String get setupGuide => _t('Setup guide', 'सेटअप गाइड');
  String get signOut => _t('Sign out', 'साइन आउट');

  // ---- result views ----
  String from(String sender) => _t('From: $sender', 'पठाउने: $sender');
  String get back => _t('Back', 'पछाडि');
  String get openMessage => _t('Open message', 'सन्देश खोल्नुहोस्');
  String get cannotOpenMessage =>
      _t('The original message cannot be opened.', 'मूल सन्देश खोल्न सकिएन।');
  String get likelyPrefix => _t('This content is likely ', 'यो सन्देश ');
  String get likelySuffix => _t(' Scam', ' ठगी हुन सक्छ');
  String get why => _t('Why', 'किन');
  String skippedChecks(List<String> names) => _t('Some checks could not run this time (${names.join(', ')}).',
      'यसपटक केही जाँच गर्न सकिएन (${names.join(', ')})।');

  String verdictTitle(String verdict) => switch (verdict) {
        'dangerous' => _t('Dangerous – likely a scam', 'खतरनाक – ठगी हुन सक्छ'),
        'suspicious' => _t('Suspicious – be careful', 'शंकास्पद – सावधान रहनुहोस्'),
        'safe' => _t('Looks safe', 'सुरक्षित देखिन्छ'),
        _ => _t('Unknown', 'थाहा भएन'),
      };

  /// Title for the owner's risk class (B7); an older verdict falls back to verdictTitle.
  String riskTitle(String level) => switch (level) {
        'low' => _t('LOW RISK', 'कम जोखिम'),
        'suspicious' => _t('SUSPICIOUS', 'शंकास्पद'),
        'high' => _t('HIGH RISK', 'उच्च जोखिम'),
        'critical' => _t('CRITICAL RISK', 'गम्भीर जोखिम'),
        'very_harmful' => _t('VERY HARMFUL', 'अत्यन्त हानिकारक'),
        'unknown' => _t('Not checked', 'जाँच भएन'),
        _ => verdictTitle(level),
      };

  String get checkingTakesTime => _t('Checking… this can take up to a minute.', 'जाँच हुँदैछ… एक मिनेटसम्म लाग्न सक्छ।');

  String verdictShort(String verdict) => switch (verdict) {
        'dangerous' => _t('dangerous', 'खतरनाक'),
        'suspicious' => _t('suspicious', 'शंकास्पद'),
        'safe' => _t('safe', 'सुरक्षित'),
        _ => verdict,
      };

  /// The server's advice sentence. Known sentences are translated; anything new stays in English.
  String suggestion(String english) => ne ? (_nepaliSuggestions[english] ?? english) : english;

  /// One reason in the current language. English uses the server's text; Nepali uses its own text per code.
  String reason(Reason r) => ne ? (_nepaliReason(r) ?? r.text) : r.text;

  // ---- feedback dialog ----
  String get whatWasIt => _t('What was this message really?', 'यो सन्देश वास्तवमा के थियो?');
  String get labelScam => _t('A scam / fraud', 'ठगी / धोखा');
  String get labelSpam => _t('An advertisement', 'विज्ञापन');
  String get labelHam => _t('A normal, safe message', 'सामान्य, सुरक्षित सन्देश');

  // ---- history ----
  String get historyTitle => _t('Checked messages', 'जाँचिएका सन्देशहरू');
  String get noHistory => _t('No checked messages yet.', 'अहिलेसम्म कुनै सन्देश जाँचिएको छैन।');
  String get noSender => _t('(no sender)', '(पठाउने छैन)');
  String get thanksShort => _t('Thanks for the feedback!', 'प्रतिक्रियाका लागि धन्यवाद!');

  // ---- onboarding (Phase 9.5) ----
  String get skip => _t('Skip', 'छोड्नुहोस्');
  String get next => _t('Next', 'अर्को');
  String get done => _t('Done', 'सकियो');
  String get welcomeTitle => _t('Welcome to CheckScam', 'CheckScam मा स्वागत छ');
  String get welcomeText => _t('CheckScam checks every new SMS for scams and tells you if it is safe.',
      'CheckScam ले हरेक नयाँ SMS ठगी हो कि होइन जाँच्छ र सुरक्षित छ कि छैन भन्छ।');
  String get privacy1 => _t('OTPs and messages from your bank never leave your phone.',
      'OTP र तपाईंको बैंकका सन्देशहरू कहिल्यै फोनबाट बाहिर जाँदैनन्।');
  String get privacy2 => _t('Phone numbers, names and account numbers are hidden before a check.',
      'जाँच गर्नुअघि फोन नम्बर, नाम र खाता नम्बर लुकाइन्छ।');
  String get privacy3 => _t('You can turn checking off at any time.', 'तपाईं जुनसुकै बेला जाँच बन्द गर्न सक्नुहुन्छ।');
  String get accessTitle => _t('Read message notifications', 'सन्देशका सूचना पढ्ने अनुमति');
  String get accessText => _t(
      'CheckScam needs notification access to see new SMS. In the list, find CheckScam and turn it on.',
      'नयाँ SMS हेर्न CheckScam लाई सूचना पढ्ने अनुमति चाहिन्छ। सूचीमा CheckScam खोजेर अन गर्नुहोस्।');
  String get notifTitle => _t('Show warnings', 'चेतावनी देखाउने');
  String get notifText => _t('Allow CheckScam to show notifications, so it can warn you about a scam.',
      'ठगीबारे चेतावनी दिन CheckScam लाई सूचना देखाउने अनुमति दिनुहोस्।');
  String get allowNotificationsShort => _t('Allow notifications', 'सूचनालाई अनुमति दिनुहोस्');
  String get allowed => _t('Allowed', 'अनुमति दिइयो');
  String get batteryTitle => _t('Keep CheckScam running', 'CheckScam लाई चलिरहन दिनुहोस्');
  String batteryText(String brand) => _t(
      'Some phones stop apps in the background to save battery. Then new SMS are not checked. '
          'Follow these steps for your $brand phone:',
      'केही फोनले ब्याट्री बचाउन पृष्ठभूमिका एपहरू बन्द गर्छन्। त्यसपछि नयाँ SMS जाँचिँदैन। '
          'तपाईंको $brand फोनका लागि यी चरणहरू गर्नुहोस्:');
  String get openBattery => _t('Open battery settings', 'ब्याट्री सेटिङ खोल्नुहोस्');
  String get openAutostart => _t('Open auto-start settings', 'अटो-स्टार्ट सेटिङ खोल्नुहोस्');
  String get openAppInfo => _t('Open app info', 'एपको जानकारी खोल्नुहोस्');

  /// Battery / auto-start steps for the phone's brand (from Build.MANUFACTURER).
  List<String> batterySteps(String manufacturer) {
    final m = manufacturer.toLowerCase();
    if (m.contains('realme') || m.contains('oppo') || m.contains('oneplus')) {
      return [
        _t('Open app info → Battery → choose "Allow background activity" (or "Don\'t optimise").',
            'एपको जानकारी → Battery → "Allow background activity" (वा "Don\'t optimise") छान्नुहोस्।'),
        _t('Turn on "Auto launch" / "Allow auto-start" for CheckScam.',
            'CheckScam का लागि "Auto launch" / "Allow auto-start" अन गर्नुहोस्।'),
        _t('In recent apps, pull CheckScam down and tap the lock so it is not closed.',
            'हालका एपहरूमा CheckScam लाई तल तानेर लक थिच्नुहोस्, ताकि यो बन्द नहोस्।'),
      ];
    }
    if (m.contains('xiaomi') || m.contains('redmi') || m.contains('poco')) {
      return [
        _t('Open app info → Battery saver → choose "No restrictions".',
            'एपको जानकारी → Battery saver → "No restrictions" छान्नुहोस्।'),
        _t('Open auto-start settings and turn CheckScam on.', 'अटो-स्टार्ट सेटिङ खोलेर CheckScam अन गर्नुहोस्।'),
        _t('In recent apps, long-press CheckScam and tap the lock.', 'हालका एपहरूमा CheckScam थिचिराखेर लक थिच्नुहोस्।'),
      ];
    }
    if (m.contains('vivo') || m.contains('iqoo')) {
      return [
        _t('Open app info → Battery → choose "Allow high background power use".',
            'एपको जानकारी → Battery → "Allow high background power use" छान्नुहोस्।'),
        _t('Open auto-start settings and turn CheckScam on.', 'अटो-स्टार्ट सेटिङ खोलेर CheckScam अन गर्नुहोस्।'),
        _t('In recent apps, pull CheckScam down to lock it.', 'हालका एपहरूमा CheckScam लाई तल तानेर लक गर्नुहोस्।'),
      ];
    }
    if (m.contains('samsung')) {
      return [
        _t('Open app info → Battery → choose "Unrestricted".', 'एपको जानकारी → Battery → "Unrestricted" छान्नुहोस्।'),
        _t('In Settings → Battery → Background usage limits, make sure CheckScam is not in "Sleeping apps".',
            'Settings → Battery → Background usage limits मा CheckScam "Sleeping apps" मा नभएको हेर्नुहोस्।'),
      ];
    }
    if (m.contains('huawei') || m.contains('honor')) {
      return [
        _t('Open battery settings → App launch → turn off "Manage automatically" for CheckScam and allow all three.',
            'ब्याट्री सेटिङ → App launch → CheckScam का लागि "Manage automatically" बन्द गरेर तीनवटै अनुमति दिनुहोस्।'),
      ];
    }
    return [
      _t('Open battery settings and choose "Don\'t optimise" / "Unrestricted" for CheckScam.',
          'ब्याट्री सेटिङ खोलेर CheckScam का लागि "Don\'t optimise" / "Unrestricted" छान्नुहोस्।'),
      _t('If your phone has auto-start settings, turn CheckScam on there too.',
          'तपाईंको फोनमा अटो-स्टार्ट सेटिङ छ भने त्यहाँ पनि CheckScam अन गर्नुहोस्।'),
    ];
  }

  // ---- server / network errors ----
  /// An API error in the current language. English keeps the exact message (it may come from the server).
  String apiError(ApiException e) {
    if (!ne) return e.message;
    return switch (e.code) {
      'timeout' => 'सर्भरले धेरै समय लियो। फेरि प्रयास गर्नुहोस्।',
      'offline' => 'इन्टरनेट छैन, वा सर्भरमा पुग्न सकिएन।',
      'unreachable' => 'सर्भरमा पुग्न सकिएन।',
      'token' => 'साइन इन नवीकरण गर्न सकिएन। फेरि साइन इन गर्नुहोस्।',
      'signin' => 'फेरि साइन इन गर्नुहोस्।',
      'blocked' => 'तपाईंको CheckScam खाता रोकिएको छ। सहयोगका लागि सम्पर्क गर्नुहोस्।',
      'forbidden' => 'यो काम गर्न अनुमति छैन।',
      'not_found' => 'भेटिएन।',
      'too_many' => 'अहिले धेरै जाँच भइरहेका छन्। केही बेर पर्खनुहोस्।',
      'invalid' => 'गलत इनपुट: ${e.message}',
      'firebase' => 'सर्भरमा Google साइन इन अझै मिलाइएको छैन (FIREBASE_CREDENTIALS)।',
      'server' => 'सर्भरमा त्रुटि (${e.statusCode})। पछि फेरि प्रयास गर्नुहोस्।',
      _ => e.message,
    };
  }
}

const _nepaliSuggestions = {
  'This is very likely a scam. Never share your OTP, PIN or password with anyone.':
      'यो ठगी हुने सम्भावना धेरै छ। आफ्नो OTP, PIN वा पासवर्ड कसैलाई नदिनुहोस्।',
  'This is very likely a scam. Do not open the link or enter any details.':
      'यो ठगी हुने सम्भावना धेरै छ। लिंक नखोल्नुहोस् र कुनै विवरण नभर्नुहोस्।',
  'This is very likely a scam. Do not reply, call back or send money.':
      'यो ठगी हुने सम्भावना धेरै छ। जवाफ नदिनुहोस्, फोन नगर्नुहोस् र पैसा नपठाउनुहोस्।',
  'Be careful. Do not click links or send money until you confirm with the company through its official number or app.':
      'सावधान रहनुहोस्। कम्पनीको आधिकारिक नम्बर वा एपबाट पक्का नगरेसम्म लिंक नथिच्नुहोस् र पैसा नपठाउनुहोस्।',
  'No scam signs found. Still, never share your OTP or PIN with anyone.':
      'ठगीका कुनै संकेत भेटिएन। तैपनि आफ्नो OTP वा PIN कसैलाई नदिनुहोस्।',
  'CheckScam could not check this message. Be careful with links and never share your OTP or PIN.':
      'CheckScam ले यो सन्देश जाँच्न सकेन। लिंकमा सावधान रहनुहोस् र आफ्नो OTP वा PIN कसैलाई नदिनुहोस्।',
};

const _nepaliRiskClass = {
  'LOW': 'कम जोखिम',
  'SUSPICIOUS': 'शंकास्पद',
  'HIGH': 'उच्च जोखिम',
  'CRITICAL': 'गम्भीर जोखिम',
  'VERY_HARMFUL': 'अत्यन्त हानिकारक',
};

String? _firstNumber(String s) => RegExp(r'\d+').firstMatch(s)?.group(0);

/// Nepali text for a reason code. Numbers and names are taken from the server's English text where needed.
String? _nepaliReason(Reason r) {
  final c = r.code;
  final t = r.text;
  if (c.startsWith('NEW_DOMAIN')) {
    final days = _firstNumber(t);
    return days == null ? 'लिंकको डोमेन भर्खरै दर्ता गरिएको हो' : 'लिंकको डोमेन $days दिन अघि मात्र दर्ता गरिएको हो';
  }
  if (c.startsWith('RISK_')) {
    final pct = RegExp(r'(\d+)%').firstMatch(t)?.group(1);
    final name = _nepaliRiskClass[c.substring(5)];
    return name == null ? null : 'MIRA: $name${pct == null ? '' : ' ($pct%)'}';
  }
  switch (c) {
    // the owner's five questions (B7)
    case 'ASKS_CREDENTIALS':
      return 'OTP, पासवर्ड वा बैंक सम्बन्धी विवरण माग्छ';
    case 'OFFERS_PRIZE':
      return 'पुरस्कार, अफर वा चिट्ठा दिने कुरा गर्छ';
    case 'BAD_IP_REPUTATION':
      return 'लिंकको IP को प्रतिष्ठा राम्रो छैन';
    case 'BAD_DOMAIN':
      return 'लिंकको डोमेन जानकारी राम्रो छैन';
    case 'URGENCY':
      return 'तुरुन्त गर्न दबाब दिन्छ';
    case 'NOT_CHECKED':
      return 'MIRA ले यो सन्देश जाँच्न सकेन';
    // sender trust
    case 'SENDER_IN_CONTACTS':
      return 'पठाउने तपाईंको सम्पर्क सूचीमा छ';
    case 'SENDER_FREQUENT':
      final n = _firstNumber(t);
      return 'यो पठाउनेबाट तपाईंलाई प्रायः सन्देश आउँछ${n == null ? '' : ' (पहिले $n वटा)'}';
    case 'SENDER_NEW':
      return 'यो पठाउनेबाट आएको पहिलो सन्देश हो';
    case 'MIRA_SCAM':
      return 'सन्देश ठगी जस्तो देखिन्छ${_sure(t)}';
    case 'MIRA_AD':
      return 'सन्देश विज्ञापन जस्तो देखिन्छ${_sure(t)}';
    case 'MIRA_NORMAL':
      return 'सन्देश सामान्य जस्तो देखिन्छ${_sure(t)}';
    case 'MIRA_NOT_SURE':
      return 'सन्देशको जाँच पक्का थिएन, त्यसैले यसको अंक कम गनिन्छ';
    case 'ASKS_SECRET':
      return 'सन्देशले OTP, PIN वा पासवर्ड पठाउन वा भर्न भन्छ';
    case 'BRAND_MISMATCH':
      final brand = RegExp(r'mentions (.+?) but').firstMatch(t)?.group(1);
      return brand == null
          ? 'सन्देशमा कम्पनीको नाम छ तर लिंक त्यसको आधिकारिक साइट होइन'
          : 'सन्देशमा $brand को नाम छ तर लिंक $brand को आधिकारिक साइट होइन';
    case 'GAMBLING_WORDS':
      return 'सन्देशले जुवा वा बेटिङमा बोलाउँछ';
    case 'BLOCKED_DOMAIN':
      return 'लिंक CheckScam को रोक-सूचीमा रहेको वेबसाइटमा जान्छ';
    case 'BLOCKED_SENDER':
      return 'पठाउने CheckScam को रोक-सूचीमा छ';
    case 'KNOWN_SCAM':
      final pct = RegExp(r'(\d+)%').firstMatch(t)?.group(1);
      return 'पहिले चिनिएको ठगी सन्देशसँग मिल्छ${pct == null ? '' : ' ($pct% मिल्दो)'}';
    case 'TRUSTED_LINK':
      return 'लिंक कम्पनीको आधिकारिक साइटमा जान्छ';
    case 'TRUSTED_SENDER':
      return 'पठाउने ID चिनिएको कम्पनीको हो';
    case 'HARD_OTP_LINK':
      return 'OTP/PIN माग्छ र आधिकारिक नभएको साइटको लिंक दिन्छ';
    case 'OTX_REPORTED':
      final n = _firstNumber(t);
      return 'लिंकको सर्भर वा डोमेनबारे AlienVault OTX मा ${n ?? 'केही'} वटा खतरा रिपोर्ट छन्';
    case 'IP_HOST':
      return 'लिंकमा नामको सट्टा IP ठेगाना मात्र छ';
    case 'NO_HTTPS':
      return 'लिंक सुरक्षित छैन (HTTPS छैन)';
    case 'SUSPICIOUS_TLD':
      final tld = RegExp(r'\(\.([a-z0-9-]+)\)').firstMatch(t)?.group(1);
      return 'लिंकको डोमेनको अन्त्य जोखिमपूर्ण छ${tld == null ? '' : ' (.$tld)'}';
    case 'SHORTENER':
      return 'लिंक छोटो पारिएको छ, त्यसैले साँचो ठेगाना लुकेको छ';
    case 'COMPLEX_HOST':
      return 'लिंकको ठेगाना असामान्य रूपमा लामो वा जटिल छ';
    case 'BRAND_IN_DOMAIN':
      final brand = RegExp(r"'(.+?)'").firstMatch(t)?.group(1);
      return 'लिंकले ${brand ?? 'कम्पनी'} भएको बहाना गर्छ तर यो आधिकारिक साइट होइन';
    case 'TYPOSQUAT':
      final dom = RegExp(r'looks like (\S+)').firstMatch(t)?.group(1);
      return 'लिंक ${dom ?? 'आधिकारिक साइट'} जस्तै देखिन्छ तर हिज्जे फरक छ';
  }
  return null;
}

String _sure(String english) {
  final pct = RegExp(r'(\d+)%').firstMatch(english)?.group(1);
  return pct == null ? '' : ' ($pct% पक्का)';
}
