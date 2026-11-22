// Admin sign-in: admin ID + password, on the purple waves with the logo.

import 'package:flutter/material.dart';

import '../api.dart';
import '../theme/app_theme.dart';

class LoginScreen extends StatefulWidget {
  final AdminApi api;
  final void Function(AdminAccount me) onSignedIn;
  const LoginScreen({super.key, required this.api, required this.onSignedIn});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _id = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  bool _hide = true;
  String? _error;

  Future<void> _signIn() async {
    if (_id.text.trim().isEmpty || _password.text.isEmpty) {
      setState(() => _error = 'Enter your admin ID and password.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final me = await widget.api.login(_id.text.trim(), _password.text);
      _password.clear();
      widget.onSignedIn(me);
    } on AdminApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: WaveBackground(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(28, 32, 28, 28),
                  child: AutofillGroup(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const CheckScamMark(size: 64),
                        const SizedBox(height: 8),
                        RichText(
                          text: const TextSpan(
                            style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                            children: [
                              TextSpan(
                                text: 'Check',
                                style: TextStyle(color: AppColors.ink),
                              ),
                              TextSpan(
                                text: 'Scam',
                                style: TextStyle(color: AppColors.purpleDark),
                              ),
                              TextSpan(
                                text: '  Admin',
                                style: TextStyle(color: AppColors.purple, fontWeight: FontWeight.w500),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 24),
                        TextField(
                          key: const Key('adminId'),
                          controller: _id,
                          autofillHints: const [AutofillHints.username],
                          decoration: const InputDecoration(
                            labelText: 'Admin ID',
                            prefixIcon: Icon(Icons.person_outline),
                            border: OutlineInputBorder(),
                          ),
                          onSubmitted: (_) => _signIn(),
                        ),
                        const SizedBox(height: 14),
                        TextField(
                          key: const Key('adminPassword'),
                          controller: _password,
                          obscureText: _hide,
                          autofillHints: const [AutofillHints.password],
                          decoration: InputDecoration(
                            labelText: 'Password',
                            prefixIcon: const Icon(Icons.lock_outline),
                            border: const OutlineInputBorder(),
                            suffixIcon: IconButton(
                              tooltip: _hide ? 'Show password' : 'Hide password',
                              icon: Icon(_hide ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                              onPressed: () => setState(() => _hide = !_hide),
                            ),
                          ),
                          onSubmitted: (_) => _signIn(),
                        ),
                        if (_error != null) ...[
                          const SizedBox(height: 12),
                          Text(
                            _error!,
                            key: const Key('loginError'),
                            style: TextStyle(color: Theme.of(context).colorScheme.error),
                          ),
                        ],
                        const SizedBox(height: 22),
                        SizedBox(
                          width: double.infinity,
                          height: 48,
                          child: FilledButton(
                            key: const Key('signIn'),
                            onPressed: _busy ? null : _signIn,
                            child: _busy
                                ? const SizedBox(
                                    width: 20,
                                    height: 20,
                                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                  )
                                : const Text('Sign in', style: TextStyle(fontSize: 16)),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
