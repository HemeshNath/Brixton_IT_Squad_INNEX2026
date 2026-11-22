// Calls to the backend admin API (/api/v1/admin). The panel is served by the same server, so the browser sends
// the HTTP-only sign-in cookie by itself. Every change carries "X-Admin-Request: 1".

import 'dart:convert';

import 'package:http/http.dart' as http;

class AdminApiException implements Exception {
  final String message;
  final int statusCode;
  AdminApiException(this.message, this.statusCode);
  bool get signedOut => statusCode == 401;
  @override
  String toString() => message;
}

class AdminAccount {
  final int id;
  final String username;
  final String role; // owner | admin | reviewer
  final bool active;
  final String? lastLoginAt;
  const AdminAccount(this.id, this.username, this.role, this.active, this.lastLoginAt);

  factory AdminAccount.fromJson(Map<String, dynamic> j) => AdminAccount(
    j['id'] as int,
    j['username'] as String,
    j['role'] as String,
    j['active'] as bool? ?? true,
    j['last_login_at'] as String?,
  );

  static const _rank = {'reviewer': 0, 'admin': 1, 'owner': 2};

  /// True if this account has at least [role].
  bool atLeast(String role) => (_rank[this.role] ?? -1) >= (_rank[role] ?? 99);
}

class PageOf<T> {
  final List<T> items;
  final int total;
  final bool hasNext;
  const PageOf(this.items, this.total, this.hasNext);
}

class AdminApi {
  final http.Client client;
  final Uri base; // e.g. https://host/api/v1/admin/

  AdminApi({http.Client? client, Uri? base})
    : client = client ?? http.Client(),
      base = base ?? Uri.base.resolve('/api/v1/admin/');

  static const _change = {'Content-Type': 'application/json', 'X-Admin-Request': '1'};

  Future<dynamic> _send(Future<http.Response> call, {Duration wait = const Duration(seconds: 15)}) async {
    final http.Response r;
    try {
      r = await call.timeout(wait);
    } catch (_) {
      throw AdminApiException('Cannot reach the server.', 0);
    }
    dynamic body;
    try {
      body = r.body.isEmpty ? null : jsonDecode(utf8.decode(r.bodyBytes));
    } on FormatException {
      body = null;
    }
    if (r.statusCode >= 200 && r.statusCode < 300) return body;
    final detail = body is Map ? body['detail'] : null;
    throw AdminApiException(detail is String ? detail : 'Error ${r.statusCode}', r.statusCode);
  }

  Uri _u(String path, [Map<String, String>? q]) => base.resolve(path).replace(queryParameters: q);
  Future<dynamic> _get(String path, [Map<String, String>? q]) => _send(client.get(_u(path, q)));
  Future<dynamic> _post(String path, [Object? body]) =>
      _send(client.post(_u(path), headers: _change, body: jsonEncode(body ?? {})));

  // ---- sign-in ----
  Future<AdminAccount> login(String username, String password) async =>
      AdminAccount.fromJson(await _post('auth/login', {'username': username, 'password': password}));
  Future<void> logout() => _post('auth/logout');
  Future<AdminAccount?> me() async {
    try {
      return AdminAccount.fromJson(await _get('auth/me'));
    } on AdminApiException catch (e) {
      if (e.signedOut) return null;
      rethrow;
    }
  }

  Future<void> changePassword(String current, String next) =>
      _post('auth/password', {'current_password': current, 'new_password': next});

  // ---- admin accounts (owner) ----
  Future<List<AdminAccount>> accounts() async => [
    for (final a in await _get('accounts') as List) AdminAccount.fromJson(a as Map<String, dynamic>),
  ];
  Future<void> createAccount(String username, String password, String role) =>
      _post('accounts', {'username': username, 'password': password, 'role': role});
  Future<void> updateAccount(int id, {String? role, bool? active, String? password}) =>
      _post('accounts/$id', {'role': ?role, 'active': ?active, 'password': ?password});

  // ---- dashboard (reviewer+) ----
  Future<Map<String, dynamic>> dashboard() async => await _get('dashboard') as Map<String, dynamic>;

  // ---- app users (admin+) ----
  Future<Map<String, dynamic>> users({String search = '', String sort = 'last_seen', int page = 1}) async =>
      await _get('users', {'search': search, 'sort': sort, 'page': '$page'}) as Map<String, dynamic>;
  Future<Map<String, dynamic>> user(String uid) async =>
      await _get('users/${Uri.encodeComponent(uid)}') as Map<String, dynamic>;
  Future<void> updateUser(String uid, {bool? blocked, String? plan}) =>
      _post('users/${Uri.encodeComponent(uid)}', {'blocked': ?blocked, 'plan': ?plan});

  // ---- live settings (admin+) ----
  Future<Map<String, dynamic>> settings() async => await _get('settings') as Map<String, dynamic>;
  Future<Map<String, dynamic>> saveSettings(Map<String, dynamic> data, String note) async =>
      await _post('settings', {'data': data, 'note': note}) as Map<String, dynamic>;
  Future<Map<String, dynamic>> settingsHistory({int page = 1}) async =>
      await _get('settings/history', {'page': '$page'}) as Map<String, dynamic>;
  Future<Map<String, dynamic>> restoreSettings(int number) async =>
      await _post('settings/restore/$number') as Map<String, dynamic>;

  // ---- API keys and AI model (owner) ----
  Future<List<Map<String, dynamic>>> keys() async => [
    for (final k in await _get('keys') as List) Map<String, dynamic>.from(k as Map),
  ];
  Future<Map<String, dynamic>> testKey(String name, String value) async =>
      await _post('keys/$name/test', {'value': value}) as Map<String, dynamic>;
  Future<Map<String, dynamic>> saveKey(String name, String value, {bool skipTest = false}) async =>
      await _post('keys/$name', {'value': value, 'skip_test': skipTest}) as Map<String, dynamic>;
  Future<void> deleteKey(String name) => _send(client.delete(_u('keys/$name'), headers: _change));
  Future<Map<String, dynamic>> model() async => await _get('model') as Map<String, dynamic>;
  Future<int> startModelTest(String id) async => (await _post('model/test/$id') as Map)['test_id'] as int;
  Future<Map<String, dynamic>> modelTest(int testId) async => await _get('model/tests/$testId') as Map<String, dynamic>;
  Future<void> switchModel(String id, String note) => _post('model/switch/$id', {'note': note});

  // ---- data sets: reports, known scams, lists (reviewer+ / admin+) ----
  Future<Map<String, dynamic>> reports({String status = 'pending', int page = 1}) async =>
      await _get('reports', {'status': status, 'page': '$page'}) as Map<String, dynamic>;
  Future<Map<String, dynamic>> reviewReport(int id, String action, {String category = ''}) async =>
      await _post('reports/$id', {'action': action, 'category': category}) as Map<String, dynamic>;
  Future<Map<String, dynamic>> knownScams({String search = '', int page = 1}) async =>
      await _get('known-scams', {'search': search, 'page': '$page'}) as Map<String, dynamic>;
  Future<Map<String, dynamic>> addKnownScam(String text, String category) async =>
      await _post('known-scams', {'text': text, 'category': category}) as Map<String, dynamic>;
  Future<void> deleteKnownScam(int id) => _send(client.delete(_u('known-scams/$id'), headers: _change));
  Future<List<Map<String, dynamic>>> lists() async => [
    for (final l in await _get('lists') as List) Map<String, dynamic>.from(l as Map),
  ];
  Future<Map<String, dynamic>> listEntries(String name, {String search = ''}) async =>
      await _get('lists/$name', {'search': search}) as Map<String, dynamic>;
  Future<Map<String, dynamic>> addListEntry(String name, String value, String label) async =>
      await _post('lists/$name', {'value': value, 'label': label}) as Map<String, dynamic>;
  Future<void> removeListEntry(String name, String value) =>
      _send(client.delete(_u('lists/$name', {'value': value}), headers: _change));

  /// Full address of a CSV export (opened in a new tab; the browser sends the sign-in cookie).
  Uri exportUrl(String file) => base.resolve(file);

  // ---- test lab (admin+) ----
  /// One check with the owner's flow (B8). MIRA with the owner's prompt takes ~30-70 s, so this waits up to 95 s.
  Future<Map<String, dynamic>> testLab(String text,
          {String source = 'SMS', bool linkLookups = true, bool? inContacts, int? seenBefore}) async =>
      await _send(
            client.post(_u('test-lab'), headers: _change,
                body: jsonEncode({
                  'text': text,
                  'source': source,
                  'use_link_lookups': linkLookups,
                  'sender_in_contacts': inContacts,
                  'sender_seen_before': seenBefore,
                })),
            wait: const Duration(seconds: 95),
          )
          as Map<String, dynamic>;

  // ---- audit log (admin+) ----
  Future<PageOf<Map<String, dynamic>>> audit({int page = 1}) async {
    final j = await _get('audit', {'page': '$page'}) as Map<String, dynamic>;
    return PageOf(
      [for (final x in j['results'] as List) x as Map<String, dynamic>],
      j['total'] as int,
      j['has_next'] == true,
    );
  }
}
