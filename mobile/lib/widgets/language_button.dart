// "English / नेपाली" switch (Phase 9.6): a small button on the sign-in screen and a tile in the settings sheet.
// Both change the language through LanguageScope (saved in settings, also used by the Kotlin notifications).

import 'package:flutter/material.dart';

import '../l10n/strings.dart';

/// Asks which language to use and saves it.
Future<void> chooseLanguage(BuildContext context) async {
  final scope = LanguageScope.maybeOf(context);
  if (scope == null) return;
  final picked = await showDialog<String>(
    context: context,
    builder: (ctx) => SimpleDialog(
      title: const Text('Language / भाषा'),
      children: [
        for (final (code, name) in const [('en', 'English'), ('ne', 'नेपाली')])
          SimpleDialogOption(
            key: Key('language_$code'),
            onPressed: () => Navigator.pop(ctx, code),
            child: Row(children: [
              Icon(scope.language == code ? Icons.radio_button_checked : Icons.radio_button_unchecked, size: 20),
              const SizedBox(width: 10),
              Text(name, style: const TextStyle(fontSize: 16)),
            ]),
          ),
      ],
    ),
  );
  if (picked != null && picked != scope.language) await scope.setLanguage(picked);
}

/// Small "🌐 English" button.
class LanguageButton extends StatelessWidget {
  const LanguageButton({super.key});

  @override
  Widget build(BuildContext context) => TextButton.icon(
        onPressed: () => chooseLanguage(context),
        icon: const Icon(Icons.language, size: 18),
        label: Text(S.of(context).languageName),
      );
}

/// Settings-sheet tile: "Language · English".
class LanguageTile extends StatelessWidget {
  const LanguageTile({super.key});

  @override
  Widget build(BuildContext context) {
    final s = S.of(context);
    return ListTile(
      key: const Key('languageTile'),
      leading: const Icon(Icons.language),
      title: Text(s.language),
      subtitle: Text(s.languageName),
      onTap: () => chooseLanguage(context),
    );
  }
}
