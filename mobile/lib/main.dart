// App entry point: starts Firebase (Google sign-in) and loads saved settings, then shows the setup
// screen (not signed in yet), the first-run setup guide (once), or the home screen.
// Also holds the app language (English / Nepali) for all screens.

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'l10n/strings.dart';
import 'screens/home_screen.dart';
import 'screens/onboarding_screen.dart';
import 'screens/setup_screen.dart';
import 'services/api.dart';
import 'services/auth_service.dart';
import 'services/settings.dart';
import 'theme/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final settings = await AppSettings.load();
  final auth = await FirebaseAuthService.create(); // falls back to dev sign-in if Firebase is not set up
  runApp(CheckScamApp(settings: settings, auth: auth));
}

class CheckScamApp extends StatefulWidget {
  final AppSettings settings;
  final AuthService auth;
  const CheckScamApp({super.key, required this.settings, required this.auth});

  @override
  State<CheckScamApp> createState() => _CheckScamAppState();
}

class _CheckScamAppState extends State<CheckScamApp> {
  final _client = http.Client();
  late String _language = widget.settings.language;

  /// Signed in = Google (Firebase) user, or a development name (debug builds only).
  bool get _signedIn =>
      widget.settings.apiBaseUrl.isNotEmpty && (widget.auth.isSignedIn || widget.settings.devUser.isNotEmpty);

  ApiService get api => ApiService(
        client: _client,
        baseUrl: widget.settings.apiBaseUrl,
        devUser: widget.auth.isSignedIn ? '' : widget.settings.devUser,
        tokenProvider: widget.auth.isSignedIn ? widget.auth.idToken : null,
      );

  Future<void> _setLanguage(String language) async {
    await widget.settings.setLanguage(language);
    setState(() => _language = widget.settings.language);
  }

  Widget _home() {
    if (!_signedIn) {
      return SetupScreen(settings: widget.settings, auth: widget.auth, onDone: () => setState(() {}));
    }
    if (!widget.settings.onboardingDone) {
      return OnboardingScreen(onDone: () async {
        await widget.settings.setOnboardingDone(true);
        setState(() {});
      });
    }
    return HomeScreen(
      settings: widget.settings,
      apiFactory: () => api,
      onSignOut: _signOut,
      signedInAs: widget.auth.email ?? widget.settings.devUser,
    );
  }

  @override
  Widget build(BuildContext context) {
    return LanguageScope(
      language: _language,
      setLanguage: _setLanguage,
      child: MaterialApp(
        title: 'CheckScam',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light(), // team design: purple, light
        themeMode: ThemeMode.light,
        home: _home(),
      ),
    );
  }

  Future<void> _signOut() async {
    await widget.auth.signOut();
    await widget.settings.setDevUser('');
    await widget.settings.setAuthToken('');
    setState(() {});
  }
}
