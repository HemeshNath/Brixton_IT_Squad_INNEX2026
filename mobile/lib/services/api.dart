// HTTP client for the backend API with friendly error messages (no internet, timeout, 400/401/404/429/500).

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../models/check_result.dart';

class ApiException implements Exception {
  final String message;
  final int? statusCode;

  /// Short error kind (timeout, offline, signin, ...) so the app can show the message in Nepali too.
  final String code;
  ApiException(this.message, [this.statusCode, this.code = '']);
  @override
  String toString() => message;
}

class HistoryPage {
  final List<CheckResult> items;
  final bool hasNext;
  HistoryPage(this.items, this.hasNext);
}

class ApiService {
  final http.Client client;
  final String baseUrl;
  final String devUser;
  final String authToken;

  /// Returns a fresh Firebase ID token (Google sign-in). Called before every request.
  final Future<String?> Function()? tokenProvider;
  final Duration timeout;

  ApiService({
    required this.client,
    required this.baseUrl,
    this.devUser = '',
    this.authToken = '',
    this.tokenProvider,
    this.timeout = const Duration(seconds: 10),
    this.checkTimeout = const Duration(seconds: 95),
  });

  /// A message check waits much longer (B7): MIRA with the owner's prompt takes ~30-70 s; the server stops at 90 s.
  final Duration checkTimeout;

  /// Sign-in order: Google (fresh Firebase token) -> fixed token -> development name.
  Future<Map<String, String>> _headers() async {
    String? token;
    if (tokenProvider != null) {
      try {
        token = await tokenProvider!();
      } catch (_) {
        throw ApiException('Could not refresh your sign-in. Please sign in again.', 401, 'token');
      }
    }
    if (token == null || token.isEmpty) token = authToken.isEmpty ? null : authToken;
    return {
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token'
      else if (devUser.isNotEmpty) 'X-Dev-User': devUser,
    };
  }

  Future<dynamic> _send(Future<http.Response> Function(Map<String, String> headers) call,
      {bool auth = true, Duration? wait}) async {
    final headers = auth ? await _headers() : const <String, String>{};
    final http.Response r;
    try {
      r = await call(headers).timeout(wait ?? timeout);
    } on TimeoutException {
      throw ApiException('The server is taking too long. Please try again.', null, 'timeout');
    } on SocketException {
      throw ApiException('No internet connection, or the server is not reachable.', null, 'offline');
    } on http.ClientException {
      throw ApiException('Could not reach the server.', null, 'unreachable');
    }
    if (r.statusCode == 204) return null;
    dynamic body;
    try {
      body = r.body.isEmpty ? null : jsonDecode(utf8.decode(r.bodyBytes));
    } on FormatException {
      body = null;
    }
    if (r.statusCode >= 200 && r.statusCode < 300) return body;
    switch (r.statusCode) {
      case 400:
        final detail = body is Map ? (body['detail'] ?? body.values.first) : null;
        throw ApiException(detail is List ? '${detail.first}' : '${detail ?? 'Invalid input.'}', 400, 'invalid');
      case 401:
        throw ApiException('Please sign in again.', 401, 'signin');
      case 403:
        final detail = body is Map ? '${body['detail'] ?? ''}' : '';
        if (detail.toLowerCase().contains('blocked')) throw ApiException(detail, 403, 'blocked');
        throw ApiException(detail.isEmpty ? 'Not allowed.' : detail, 403, 'forbidden');
      case 404:
        throw ApiException('Not found.', 404, 'not_found');
      case 429:
        throw ApiException('Too many checks right now. Please wait a moment.', 429, 'too_many');
      default:
        throw ApiException('Server error (${r.statusCode}). Please try again later.', r.statusCode, 'server');
    }
  }

  Uri _u(String path, [Map<String, String>? q]) => Uri.parse('$baseUrl$path').replace(queryParameters: q);

  Future<String?> health() async {
    final body = await _send((_) => client.get(_u('/health')), auth: false);
    return body is Map ? body['model_version'] as String? : null;
  }

  Future<Map<String, dynamic>> me() async =>
      Map<String, dynamic>.from(await _send((h) => client.get(_u('/me'), headers: h)) as Map);

  Future<CheckResult> checkMessage(String text, {String sender = ''}) async {
    final body = await _send((h) => client.post(_u('/check/sms'),
        headers: h, body: jsonEncode({'text': text, 'sender': sender, 'source': 'manual'})), wait: checkTimeout);
    return CheckResult.fromJson(Map<String, dynamic>.from(body as Map));
  }

  Future<HistoryPage> history({int page = 1}) async {
    final body = await _send((h) => client.get(_u('/history', {'page': '$page'}), headers: h)) as Map;
    final items = (body['results'] as List)
        .map((e) => CheckResult.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
    return HistoryPage(items, body['has_next'] == true);
  }

  Future<void> deleteCheck(String id) => _send((h) => client.delete(_u('/history/$id'), headers: h));

  Future<void> sendFeedback(String checkId, String correctLabel, {String note = ''}) => _send((h) => client.post(
      _u('/feedback'),
      headers: h,
      body: jsonEncode({'check_id': checkId, 'correct_label': correctLabel, 'note': note})));
}
