// The panel layout: header (logo, signed-in admin, sign out), sidebar of sections (only those the role may open),
// and the chosen section. Sections of later steps show what they will contain.

import 'package:flutter/material.dart';

import '../api.dart';
import '../theme/app_theme.dart';
import 'accounts_screen.dart';
import 'audit_screen.dart';
import 'dashboard_screen.dart';
import 'data_sets_screen.dart';
import 'keys_model_screen.dart';
import 'password_screen.dart';
import 'settings_screen.dart';
import 'test_lab_screen.dart';
import 'users_screen.dart';

class Section {
  final String title;
  final IconData icon;
  final String minRole;
  final String? step; // step that builds it (null = ready)
  final String about;
  const Section(this.title, this.icon, this.minRole, this.about, {this.step});
}

const sections = [
  Section(
    'Dashboard',
    Icons.space_dashboard_outlined,
    'reviewer',
    'Health of server, MIRA, Supabase, OTX and WHOIS; OTX quota; checks today; slowest checks; errors.',
  ),
  Section(
    'Users & usage',
    Icons.people_alt_outlined,
    'admin',
    'Every app user: joined, last active, checks per day, verdict split; block / unblock.',
  ),
  Section(
    'Settings',
    Icons.tune,
    'admin',
    'Score cut-offs, weights, timeouts and on/off switches – versioned, with undo, live without restart.',
  ),
  Section(
    'API keys & AI model',
    Icons.key_outlined,
    'owner',
    'OTX and WHOIS keys (write-only) and the approved MIRA versions with test run and rollback.',
  ),
  Section(
    'Data sets',
    Icons.dataset_outlined,
    'reviewer',
    '"Wrong result?" reports, known-scam memory, official / trusted / blocked lists, CSV export.',
  ),
  Section(
    'Test lab',
    Icons.science_outlined,
    'admin',
    'Paste an SMS and see every reason, MIRA probabilities, OTX/WHOIS results and timings.',
  ),
  Section(
    'Scam trends',
    Icons.trending_up,
    'reviewer',
    'Top scam types, most-reported domains and newest scam domains this week and month.',
    step: 'A8',
  ),
  Section(
    'Ads',
    Icons.campaign_outlined,
    'admin',
    'The home-screen banner in the app: create, check the link, schedule, switch on/off, views and clicks.',
    step: 'A9',
  ),
  Section(
    'App control',
    Icons.phone_android,
    'admin',
    'Minimum app version ("please update") and the in-app notice.',
    step: 'A10',
  ),
  Section('Audit log', Icons.receipt_long_outlined, 'admin', 'Every admin action: who, what, when.'),
  Section(
    'Admin accounts',
    Icons.admin_panel_settings_outlined,
    'owner',
    'Admin IDs and roles: create, change role, reset password, disable.',
  ),
  Section('My password', Icons.password, 'reviewer', 'Change your own password.'),
];

class AdminShell extends StatefulWidget {
  final AdminApi api;
  final AdminAccount me;
  final VoidCallback onSignedOut;
  const AdminShell({super.key, required this.api, required this.me, required this.onSignedOut});

  @override
  State<AdminShell> createState() => _AdminShellState();
}

class _AdminShellState extends State<AdminShell> {
  late final List<Section> _mine = [
    for (final s in sections)
      if (widget.me.atLeast(s.minRole)) s,
  ];
  int _index = 0;

  /// Shows an error; a 401 (session ended) goes back to the sign-in screen.
  void _onError(Object e) {
    if (e is AdminApiException && e.signedOut) {
      widget.onSignedOut();
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
  }

  Future<void> _signOut() async {
    try {
      await widget.api.logout();
    } catch (_) {
      // already signed out on the server
    }
    widget.onSignedOut();
  }

  Widget _page(Section s) => switch (s.title) {
    'Dashboard' => DashboardScreen(api: widget.api, onError: _onError),
    'Users & usage' => UsersScreen(api: widget.api, onError: _onError),
    'Settings' => SettingsScreen(api: widget.api, onError: _onError),
    'API keys & AI model' => KeysModelScreen(api: widget.api, onError: _onError),
    'Data sets' => DataSetsScreen(api: widget.api, me: widget.me, onError: _onError),
    'Test lab' => TestLabScreen(api: widget.api, onError: _onError),
    'Audit log' => AuditScreen(api: widget.api, onError: _onError),
    'Admin accounts' => AccountsScreen(api: widget.api, me: widget.me, onError: _onError),
    'My password' => PasswordScreen(api: widget.api, onError: _onError),
    _ => _ComingSoon(section: s),
  };

  Widget _menu({required bool wide, VoidCallback? afterTap}) => ListView(
    padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 10),
    children: [
      for (var i = 0; i < _mine.length; i++)
        Padding(
          padding: const EdgeInsets.only(bottom: 2),
          child: ListTile(
            key: Key('nav_${_mine[i].title}'),
            selected: i == _index,
            selectedTileColor: AppColors.lavender,
            selectedColor: AppColors.purpleDark,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            leading: Icon(_mine[i].icon),
            title: Text(_mine[i].title, style: const TextStyle(fontWeight: FontWeight.w500)),
            trailing: _mine[i].step == null
                ? null
                : Text(_mine[i].step!, style: const TextStyle(fontSize: 11, color: Colors.black38)),
            onTap: () {
              setState(() => _index = i);
              afterTap?.call();
            },
          ),
        ),
    ],
  );

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 900;
    final header = Container(
      height: 64,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(bottom: BorderSide(color: Color(0xFFEDE9F2))),
      ),
      child: Row(
        children: [
          if (!wide)
            Builder(
              builder: (ctx) =>
                  IconButton(icon: const Icon(Icons.menu), onPressed: () => Scaffold.of(ctx).openDrawer()),
            ),
          const CheckScamMark(size: 34),
          const SizedBox(width: 8),
          Flexible(
            child: RichText(
              overflow: TextOverflow.ellipsis,
              maxLines: 1,
              text: const TextSpan(
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
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
          ),
          const Spacer(),
          if (wide)
            Chip(
              key: const Key('whoAmI'),
              avatar: const Icon(Icons.verified_user_outlined, size: 18, color: AppColors.purple),
              label: Text('${widget.me.username} · ${widget.me.role}'),
              backgroundColor: AppColors.lavender,
              side: BorderSide.none,
            )
          else
            Tooltip(
              message: '${widget.me.username} · ${widget.me.role}',
              child: const Icon(Icons.verified_user_outlined, color: AppColors.purple),
            ),
          const SizedBox(width: 8),
          IconButton(
            key: const Key('signOut'),
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout),
            onPressed: _signOut,
          ),
        ],
      ),
    );
    return Scaffold(
      drawer: wide
          ? null
          : Drawer(
              child: SafeArea(
                child: Builder(builder: (ctx) => _menu(wide: false, afterTap: () => Navigator.pop(ctx))),
              ),
            ),
      body: WaveBackground(
        child: Column(
          children: [
            header,
            Expanded(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (wide)
                    Container(
                      width: 250,
                      decoration: const BoxDecoration(
                        border: Border(right: BorderSide(color: Color(0xFFEDE9F2))),
                      ),
                      child: Material(color: const Color(0xF2FFFFFF), child: _menu(wide: true)),
                    ),
                  Expanded(
                    child: KeyedSubtree(key: ValueKey(_index), child: _page(_mine[_index])),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Page frame used by every section: title, short description, content.
class SectionPage extends StatelessWidget {
  final String title;
  final String about;
  final List<Widget> children;
  final Widget? action;
  const SectionPage({super.key, required this.title, required this.about, required this.children, this.action});

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.fromLTRB(28, 24, 28, 40),
    children: [
      Row(
        children: [
          Expanded(
            child: Text(
              title,
              style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w700, color: AppColors.ink),
            ),
          ),
          ?action,
        ],
      ),
      const SizedBox(height: 4),
      Text(about, style: const TextStyle(color: Colors.black54)),
      const SizedBox(height: 20),
      ...children,
    ],
  );
}

class _ComingSoon extends StatelessWidget {
  final Section section;
  const _ComingSoon({required this.section});

  @override
  Widget build(BuildContext context) => SectionPage(
    title: section.title,
    about: section.about,
    children: [
      Card(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Row(
            children: [
              Icon(section.icon, size: 40, color: AppColors.purple),
              const SizedBox(width: 16),
              Expanded(child: Text('This section is built in step ${section.step} of Phase 10A.')),
            ],
          ),
        ),
      ),
    ],
  );
}
