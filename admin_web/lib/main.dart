// CheckScam web admin panel (Phase 10A): checks the sign-in cookie at start, then shows the sign-in screen or the
// panel. Same purple design as the phone app.

import 'package:flutter/material.dart';

import 'api.dart';
import 'screens/login_screen.dart';
import 'screens/shell.dart';
import 'theme/app_theme.dart';

void main() => runApp(AdminApp(api: AdminApi()));

class AdminApp extends StatefulWidget {
  final AdminApi api;
  const AdminApp({super.key, required this.api});

  @override
  State<AdminApp> createState() => _AdminAppState();
}

class _AdminAppState extends State<AdminApp> {
  AdminAccount? _me;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    widget.api.me().then((me) => _set(me)).catchError((_) => _set(null));
  }

  void _set(AdminAccount? me) {
    if (mounted) {
      setState(() {
        _me = me;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'CheckScam Admin',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      home: _loading
          ? const Scaffold(body: Center(child: CircularProgressIndicator()))
          : _me == null
          ? LoginScreen(api: widget.api, onSignedIn: _set)
          : AdminShell(api: widget.api, me: _me!, onSignedOut: () => _set(null)),
    );
  }
}
