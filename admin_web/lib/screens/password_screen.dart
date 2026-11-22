// My password: change your own admin password (other signed-in browsers are signed out).

import 'package:flutter/material.dart';

import '../api.dart';
import 'shell.dart';

class PasswordScreen extends StatefulWidget {
  final AdminApi api;
  final void Function(Object error) onError;
  const PasswordScreen({super.key, required this.api, required this.onError});

  @override
  State<PasswordScreen> createState() => _PasswordScreenState();
}

class _PasswordScreenState extends State<PasswordScreen> {
  final _current = TextEditingController();
  final _next = TextEditingController();
  final _repeat = TextEditingController();
  String? _message;
  bool _ok = false;

  void _show(String message, {required bool ok}) => setState(() {
    _message = message;
    _ok = ok;
  });

  Future<void> _save() async {
    if (_next.text != _repeat.text) {
      _show('The two new passwords are different.', ok: false);
      return;
    }
    try {
      await widget.api.changePassword(_current.text, _next.text);
      _current.clear();
      _next.clear();
      _repeat.clear();
      _show('Password changed. Other browsers were signed out.', ok: true);
    } on AdminApiException catch (e) {
      if (e.signedOut) {
        widget.onError(e);
      } else {
        _show(e.message, ok: false);
      }
    }
  }

  Widget _field(TextEditingController c, String label, Key key) => Padding(
    padding: const EdgeInsets.only(bottom: 14),
    child: TextField(
      key: key,
      controller: c,
      obscureText: true,
      decoration: InputDecoration(labelText: label, border: const OutlineInputBorder()),
    ),
  );

  @override
  Widget build(BuildContext context) => SectionPage(
    title: 'My password',
    about: 'At least 10 characters, with upper and lower case letters and a number.',
    children: [
      Align(
        alignment: Alignment.centerLeft,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 440),
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(22),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _field(_current, 'Current password', const Key('currentPassword')),
                  _field(_next, 'New password', const Key('newPassword')),
                  _field(_repeat, 'Repeat new password', const Key('repeatPassword')),
                  if (_message != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(
                        _message!,
                        key: const Key('passwordMessage'),
                        style: TextStyle(color: _ok ? Colors.green.shade700 : Theme.of(context).colorScheme.error),
                      ),
                    ),
                  FilledButton(key: const Key('savePassword'), onPressed: _save, child: const Text('Change password')),
                ],
              ),
            ),
          ),
        ),
      ),
    ],
  );
}
