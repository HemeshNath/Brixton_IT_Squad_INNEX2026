// Admin accounts (owner only): list, create, change role, reset password, disable / enable.

import 'package:flutter/material.dart';

import '../api.dart';
import '../theme/app_theme.dart';
import 'shell.dart';

const roles = ['owner', 'admin', 'reviewer'];
const roleHelp = {
  'owner': 'everything, incl. API keys and admin accounts',
  'admin': 'settings, users, ads, audit log',
  'reviewer': 'reports and known scams; can view the lists',
};

class AccountsScreen extends StatefulWidget {
  final AdminApi api;
  final AdminAccount me;
  final void Function(Object error) onError;
  const AccountsScreen({super.key, required this.api, required this.me, required this.onError});

  @override
  State<AccountsScreen> createState() => _AccountsScreenState();
}

class _AccountsScreenState extends State<AccountsScreen> {
  List<AdminAccount>? _list;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final l = await widget.api.accounts();
      if (mounted) setState(() => _list = l);
    } catch (e) {
      widget.onError(e);
    }
  }

  Future<void> _run(Future<void> Function() action, String done) async {
    try {
      await action();
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(done)));
      await _load();
    } catch (e) {
      widget.onError(e);
    }
  }

  Future<void> _create() async {
    final r = await showDialog<(String, String, String)>(context: context, builder: (_) => const _NewAccountDialog());
    if (r != null) await _run(() => widget.api.createAccount(r.$1, r.$2, r.$3), 'Admin ${r.$1} created.');
  }

  Future<void> _resetPassword(AdminAccount a) async {
    final pw = await showDialog<String>(
      context: context,
      builder: (_) => _PasswordDialog(username: a.username),
    );
    if (pw != null) await _run(() => widget.api.updateAccount(a.id, password: pw), 'Password of ${a.username} reset.');
  }

  @override
  Widget build(BuildContext context) {
    final list = _list;
    return SectionPage(
      title: 'Admin accounts',
      about:
          'Who can sign in to this panel. Roles: owner – ${roleHelp['owner']}; admin – ${roleHelp['admin']}; '
          'reviewer – ${roleHelp['reviewer']}.',
      action: FilledButton.icon(
        key: const Key('newAccount'),
        onPressed: _create,
        icon: const Icon(Icons.person_add_alt),
        label: const Text('New admin'),
      ),
      children: [
        if (list == null)
          const Center(child: CircularProgressIndicator())
        else
          for (final a in list)
            Card(
              margin: const EdgeInsets.only(bottom: 10),
              child: ListTile(
                leading: CircleAvatar(
                  backgroundColor: a.active ? AppColors.lavender : Colors.black12,
                  child: Icon(Icons.person, color: a.active ? AppColors.purpleDark : Colors.black38),
                ),
                title: Text(
                  a.username + (a.id == widget.me.id ? '  (you)' : ''),
                  style: TextStyle(fontWeight: FontWeight.w600, color: a.active ? null : Colors.black38),
                ),
                subtitle: Text(
                  a.active
                      ? 'Last sign-in: ${a.lastLoginAt == null ? 'never' : a.lastLoginAt!.substring(0, 16).replaceFirst('T', ' ')}'
                      : 'Disabled',
                ),
                trailing: Wrap(
                  crossAxisAlignment: WrapCrossAlignment.center,
                  spacing: 6,
                  children: [
                    DropdownButton<String>(
                      value: a.role,
                      underline: const SizedBox(),
                      items: [for (final r in roles) DropdownMenuItem(value: r, child: Text(r))],
                      onChanged: a.id == widget.me.id
                          ? null
                          : (r) => _run(() => widget.api.updateAccount(a.id, role: r), '${a.username} is now $r.'),
                    ),
                    IconButton(
                      tooltip: 'Reset password',
                      icon: const Icon(Icons.lock_reset),
                      onPressed: () => _resetPassword(a),
                    ),
                    if (a.id != widget.me.id)
                      IconButton(
                        tooltip: a.active ? 'Disable' : 'Enable',
                        icon: Icon(a.active ? Icons.block : Icons.check_circle_outline),
                        onPressed: () => _run(
                          () => widget.api.updateAccount(a.id, active: !a.active),
                          '${a.username} ${a.active ? 'disabled' : 'enabled'}.',
                        ),
                      ),
                  ],
                ),
              ),
            ),
      ],
    );
  }
}

class _NewAccountDialog extends StatefulWidget {
  const _NewAccountDialog();
  @override
  State<_NewAccountDialog> createState() => _NewAccountDialogState();
}

class _NewAccountDialogState extends State<_NewAccountDialog> {
  final _id = TextEditingController();
  final _pw = TextEditingController();
  String _role = 'reviewer';

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('New admin'),
    content: SizedBox(
      width: 360,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _id,
            decoration: const InputDecoration(labelText: 'Admin ID (letters, numbers, . _ -)'),
          ),
          TextField(
            controller: _pw,
            obscureText: true,
            decoration: const InputDecoration(
              labelText: 'Password',
              helperText: '10+ characters, upper and lower case, a number',
            ),
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            initialValue: _role,
            decoration: const InputDecoration(labelText: 'Role'),
            items: [for (final r in roles) DropdownMenuItem(value: r, child: Text('$r – ${roleHelp[r]}'))],
            onChanged: (r) => setState(() => _role = r ?? 'reviewer'),
          ),
        ],
      ),
    ),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
      FilledButton(
        onPressed: () => Navigator.pop(context, (_id.text.trim(), _pw.text, _role)),
        child: const Text('Create'),
      ),
    ],
  );
}

class _PasswordDialog extends StatefulWidget {
  final String username;
  const _PasswordDialog({required this.username});
  @override
  State<_PasswordDialog> createState() => _PasswordDialogState();
}

class _PasswordDialogState extends State<_PasswordDialog> {
  final _pw = TextEditingController();

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text('New password for ${widget.username}'),
    content: SizedBox(
      width: 360,
      child: TextField(
        controller: _pw,
        obscureText: true,
        decoration: const InputDecoration(
          labelText: 'New password',
          helperText: 'They are signed out everywhere and the lock is removed',
        ),
      ),
    ),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
      FilledButton(onPressed: () => Navigator.pop(context, _pw.text), child: const Text('Reset')),
    ],
  );
}
