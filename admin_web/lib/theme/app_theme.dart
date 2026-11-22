// CheckScam look - COPY of mobile/lib/theme/app_theme.dart (keep both the same): purple brand colours,
// soft purple waves, the team logo. Used by every admin panel screen.

import 'package:flutter/material.dart';

class AppColors {
  static const purple = Color(0xFF7B1FA2);
  static const purpleDark = Color(0xFF4A148C);
  static const purpleLight = Color(0xFFC051D9);
  static const lavender = Color(0xFFE9DDF8);
  static const ink = Color(0xFF1D1B22);
  static const inputBorder = Color(0xFFE3DEEA);
  static const contentBorder = Color(0xFFF2C94C); // yellow frame around the checked message
  static const contentFill = Color(0xFFF4F1F8);
  static const protectedGreen = Color(0xFF2E7D32);
  static const warningOrange = Color(0xFFEF6C00);

  static const brandGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [purpleLight, purple, purpleDark],
  );

  static const cardGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFFB13ED0), Color(0xFF6A11B5), Color(0xFFB24AC9)],
    stops: [0.0, 0.55, 1.0],
  );
}

class AppTheme {
  static ThemeData light() {
    final scheme = ColorScheme.fromSeed(
      seedColor: AppColors.purple,
      brightness: Brightness.light,
    ).copyWith(primary: AppColors.purple, onPrimary: Colors.white, surface: Colors.white);
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: Colors.white,
      appBarTheme: const AppBarTheme(backgroundColor: Colors.white, foregroundColor: AppColors.ink, elevation: 0),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith((s) => Colors.white),
        trackColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? AppColors.purple : const Color(0xFFD9D3E2),
        ),
        trackOutlineColor: WidgetStateProperty.all(Colors.transparent),
      ),
      cardTheme: CardThemeData(
        color: const Color(0xFFF5F3F9),
        elevation: 2,
        shadowColor: Colors.black26,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(backgroundColor: AppColors.purple, foregroundColor: Colors.white),
      ),
    );
  }
}

/// The team's CheckScam logo (assets/images/logo.png, transparent background). `size` = height.
class CheckScamMark extends StatelessWidget {
  final double size;
  const CheckScamMark({super.key, this.size = 40});

  @override
  Widget build(BuildContext context) {
    return Image.asset('assets/images/logo.png', height: size, fit: BoxFit.contain, semanticLabel: 'CheckScam logo');
  }
}

/// Header: logo + "Check" (dark) "Scam" (purple) + gear button.
class CheckScamHeader extends StatelessWidget {
  final VoidCallback? onSettings;
  const CheckScamHeader({super.key, this.onSettings});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 8, 8, 8),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Color(0xFFEDE9F2))),
      ),
      child: Row(
        children: [
          const CheckScamMark(size: 38),
          const SizedBox(width: 10),
          RichText(
            text: const TextSpan(
              style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700, letterSpacing: -0.3),
              children: [
                TextSpan(
                  text: 'Check',
                  style: TextStyle(color: AppColors.ink),
                ),
                TextSpan(
                  text: 'Scam',
                  style: TextStyle(color: AppColors.purpleDark),
                ),
              ],
            ),
          ),
          const Spacer(),
          if (onSettings != null)
            IconButton(
              key: const Key('settingsButton'),
              tooltip: 'Settings',
              icon: const Icon(Icons.settings, size: 28, color: AppColors.ink),
              onPressed: onSettings,
            ),
        ],
      ),
    );
  }
}

/// Soft purple waves: top-left corner and along the bottom, behind the screen content.
class WaveBackground extends StatelessWidget {
  final Widget child;
  const WaveBackground({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        const Positioned.fill(
          child: IgnorePointer(child: CustomPaint(painter: _WavePainter())),
        ),
        child,
      ],
    );
  }
}

class _WavePainter extends CustomPainter {
  const _WavePainter();

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    final soft = Paint()..color = AppColors.lavender.withValues(alpha: 0.55);
    final softer = Paint()..color = AppColors.lavender.withValues(alpha: 0.35);

    // top-left corner
    canvas.drawPath(
      Path()
        ..moveTo(0, h * 0.10)
        ..quadraticBezierTo(w * 0.22, h * 0.12, w * 0.45, 0)
        ..lineTo(0, 0)
        ..close(),
      softer,
    );
    canvas.drawPath(
      Path()
        ..moveTo(0, h * 0.16)
        ..quadraticBezierTo(w * 0.10, h * 0.07, w * 0.32, 0)
        ..lineTo(0, 0)
        ..close(),
      soft,
    );

    // bottom
    canvas.drawPath(
      Path()
        ..moveTo(0, h * 0.86)
        ..cubicTo(w * 0.30, h * 0.80, w * 0.55, h * 0.95, w, h * 0.84)
        ..lineTo(w, h)
        ..lineTo(0, h)
        ..close(),
      softer,
    );
    canvas.drawPath(
      Path()
        ..moveTo(w * 0.35, h)
        ..cubicTo(w * 0.60, h * 0.95, w * 0.80, h * 0.90, w, h * 0.88)
        ..lineTo(w, h)
        ..close(),
      soft,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
