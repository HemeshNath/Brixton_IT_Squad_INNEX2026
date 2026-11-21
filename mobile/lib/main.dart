// App entry point: starts Firebase (Google sign-in) and loads saved settings, then shows the setup
// screen (not signed in yet) or the home screen.

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'screens/home_screen.dart';
import 'screens/setup_screen.dart';
import 'services/api.dart';
import 'services/auth_service.dart';
import 'services/settings.dart';

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

  /// Signed in = Google (Firebase) user, or a development name (debug builds only).
  bool get _signedIn =>
      widget.settings.apiBaseUrl.isNotEmpty && (widget.auth.isSignedIn || widget.settings.devUser.isNotEmpty);

  ApiService get api => ApiService(
        client: _client,
        baseUrl: widget.settings.apiBaseUrl,
        devUser: widget.auth.isSignedIn ? '' : widget.settings.devUser,
        tokenProvider: widget.auth.isSignedIn ? widget.auth.idToken : null,
      );

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'CheckScam',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(colorSchemeSeed: const Color(0xFF1565C0), useMaterial3: true),
      darkTheme: ThemeData(colorSchemeSeed: const Color(0xFF1565C0), brightness: Brightness.dark, useMaterial3: true),
      home: _signedIn
          ? HomeScreen(
              settings: widget.settings,
              apiFactory: () => api,
              onSignOut: _signOut,
              signedInAs: widget.auth.email ?? widget.settings.devUser,
            )
          : SetupScreen(settings: widget.settings, auth: widget.auth, onDone: () => setState(() {})),
    );
  }

  Future<void> _signOut() async {
    await widget.auth.signOut();
    await widget.settings.setDevUser('');
    await widget.settings.setAuthToken('');
    setState(() {});
  }
}
