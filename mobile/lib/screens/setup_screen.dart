// Sign-in screen: server address + "Sign in with Google" (Firebase). Debug builds also offer the
// development sign-in (a name sent as X-Dev-User). The server is checked before anything is saved.

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../services/api.dart';
import '../services/auth_service.dart';
import '../services/settings.dart';

class SetupScreen extends StatefulWidget {
  final AppSettings settings;
  final AuthService auth;
  final VoidCallback onDone;
  final http.Client? client; // injected in tests

  const SetupScreen({super.key, required this.settings, required this.auth, required this.onDone, this.client});

  @override
  State<SetupScreen> createState() => _SetupScreenState();
}

class _SetupScreenState extends State<SetupScreen> {
  late final _server = TextEditingController(text: widget.settings.apiBaseUrl);
  late final _name = TextEditingController(text: widget.settings.devUser);
  late final http.Client _client = widget.client ?? http.Client();
  String? _error;
  bool _busy = false;

  /// Checks the address and that the server is up. Returns the normalised URL or null (error shown).
  Future<String?> _checkServer() async {
    final base = AppSettings.normalizeBaseUrl(_server.text);
    if (base.isEmpty) {
      setState(() => _error = 'Enter the server address.');
      return null;
    }
    await ApiService(client: _client, baseUrl: base).health();
    return base;
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } on AuthException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _googleSignIn() => _run(() async {
        final base = await _checkServer();
        if (base == null) return;
        final email = await widget.auth.signInWithGoogle();
        if (email == null) return; // user closed the account picker
        try {
          await ApiService(client: _client, baseUrl: base, tokenProvider: widget.auth.idToken).me();
        } on ApiException catch (e) {
          await widget.auth.signOut(); // keep app and server in step
          if (e.statusCode == 503) {
            throw ApiException('The server is not set up for Google sign-in yet (FIREBASE_CREDENTIALS).', 503);
          }
          rethrow;
        }
        await widget.settings.setApiBaseUrl(base);
        await widget.settings.setDevUser('');
        widget.onDone();
      });

  Future<void> _devSignIn() => _run(() async {
        final name = _name.text.trim();
        if (name.isEmpty) {
          setState(() => _error = 'Enter a name for the development sign-in.');
          return;
        }
        final base = await _checkServer();
        if (base == null) return;
        await ApiService(client: _client, baseUrl: base, devUser: name).me();
        await widget.settings.setApiBaseUrl(base);
        await widget.settings.setDevUser(name);
        widget.onDone();
      });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 32),
            Icon(Icons.shield_rounded, size: 72, color: theme.colorScheme.primary),
            const SizedBox(height: 12),
            Text('CheckScam', textAlign: TextAlign.center, style: theme.textTheme.headlineMedium),
            const SizedBox(height: 4),
            const Text('Scam protection for your messages', textAlign: TextAlign.center),
            const SizedBox(height: 32),
            TextField(
              key: const Key('serverInput'),
              controller: _server,
              keyboardType: TextInputType.url,
              decoration: const InputDecoration(
                labelText: 'Server address',
                hintText: '192.168.1.5:8000 or https://xyz.trycloudflare.com',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              key: const Key('googleButton'),
              onPressed: _busy || !widget.auth.googleAvailable ? null : _googleSignIn,
              icon: _busy
                  ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.account_circle),
              label: const Text('Sign in with Google'),
            ),
            if (!widget.auth.googleAvailable) ...[
              const SizedBox(height: 8),
              Text('Google sign-in is not set up in this build yet.',
                  key: const Key('googleUnavailable'), textAlign: TextAlign.center, style: theme.textTheme.bodySmall),
            ],
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, key: const Key('setupError'), style: TextStyle(color: theme.colorScheme.error)),
            ],
            if (kDebugMode) ...[
              const SizedBox(height: 32),
              const Divider(),
              Text('Development sign-in (debug builds only)', style: theme.textTheme.labelLarge),
              const SizedBox(height: 8),
              TextField(
                key: const Key('devNameInput'),
                controller: _name,
                decoration: const InputDecoration(labelText: 'Your name', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 8),
              OutlinedButton(
                key: const Key('devButton'),
                onPressed: _busy ? null : _devSignIn,
                child: const Text('Use development sign-in'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
