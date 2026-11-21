// Sign-in: Google account through Firebase Authentication. Gives a fresh Firebase ID token for
// every API call. If Firebase is not configured (no google-services.json) Google sign-in is
// reported as unavailable and the app falls back to the development sign-in.

import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';
import 'package:google_sign_in/google_sign_in.dart';

class AuthException implements Exception {
  final String message;
  AuthException(this.message);
  @override
  String toString() => message;
}

/// What the screens need from sign-in. A fake implementation is used in tests.
abstract class AuthService {
  /// False when Firebase could not start (e.g. google-services.json missing).
  bool get googleAvailable;
  bool get isSignedIn;
  String? get email;

  /// Opens the Google account picker. Returns the email, or null if the user cancelled.
  Future<String?> signInWithGoogle();

  /// Fresh Firebase ID token for the signed-in user (refreshed automatically), or null.
  Future<String?> idToken();

  Future<void> signOut();
}

class FirebaseAuthService implements AuthService {
  bool _googleInitialized = false;

  /// Starts Firebase. Returns a working service, or [UnavailableAuthService] if Firebase is not set up.
  static Future<AuthService> create() async {
    try {
      await Firebase.initializeApp();
      return FirebaseAuthService();
    } catch (e) {
      debugPrint('Firebase not available: $e');
      return UnavailableAuthService();
    }
  }

  @override
  bool get googleAvailable => true;

  @override
  bool get isSignedIn => FirebaseAuth.instance.currentUser != null;

  @override
  String? get email => FirebaseAuth.instance.currentUser?.email;

  @override
  Future<String?> signInWithGoogle() async {
    try {
      if (!_googleInitialized) {
        // serverClientId is read from google-services.json (default_web_client_id).
        await GoogleSignIn.instance.initialize();
        _googleInitialized = true;
      }
      final account = await GoogleSignIn.instance.authenticate();
      final googleIdToken = account.authentication.idToken;
      if (googleIdToken == null) throw AuthException('Google did not return a sign-in token. Please try again.');
      final result = await FirebaseAuth.instance.signInWithCredential(
        GoogleAuthProvider.credential(idToken: googleIdToken),
      );
      return result.user?.email ?? account.email;
    } on GoogleSignInException catch (e) {
      if (e.code == GoogleSignInExceptionCode.canceled) return null;
      throw AuthException('Google sign-in failed (${e.code.name}). Check the SHA-1 in Firebase and try again.');
    } on FirebaseAuthException catch (e) {
      throw AuthException('Sign-in failed: ${e.message ?? e.code}');
    }
  }

  @override
  Future<String?> idToken() async => FirebaseAuth.instance.currentUser?.getIdToken();

  @override
  Future<void> signOut() async {
    await FirebaseAuth.instance.signOut();
    if (_googleInitialized) await GoogleSignIn.instance.signOut();
  }
}

/// Used when Firebase is not configured: Google sign-in is off, development sign-in still works.
class UnavailableAuthService implements AuthService {
  @override
  bool get googleAvailable => false;
  @override
  bool get isSignedIn => false;
  @override
  String? get email => null;
  @override
  Future<String?> signInWithGoogle() async =>
      throw AuthException('Google sign-in is not set up in this app build (google-services.json missing).');
  @override
  Future<String?> idToken() async => null;
  @override
  Future<void> signOut() async {}
}
