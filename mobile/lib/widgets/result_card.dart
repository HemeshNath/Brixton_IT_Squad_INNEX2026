// Result card widget (colour, icon, score, reasons, advice) and the 'what was it really?' feedback dialog.

import 'package:flutter/material.dart';

import '../models/check_result.dart';

class VerdictStyle {
  final Color color;
  final IconData icon;
  final String title;
  const VerdictStyle(this.color, this.icon, this.title);

  static VerdictStyle of(String verdict) => switch (verdict) {
        'dangerous' => const VerdictStyle(Color(0xFFC62828), Icons.dangerous_rounded, 'Dangerous – likely a scam'),
        'suspicious' => const VerdictStyle(Color(0xFFEF6C00), Icons.warning_amber_rounded, 'Suspicious – be careful'),
        'safe' => const VerdictStyle(Color(0xFF2E7D32), Icons.verified_user_rounded, 'Looks safe'),
        _ => const VerdictStyle(Colors.grey, Icons.help_outline, 'Unknown'),
      };
}

class ResultCard extends StatelessWidget {
  final CheckResult result;
  final VoidCallback? onWrongVerdict;

  const ResultCard({super.key, required this.result, this.onWrongVerdict});

  @override
  Widget build(BuildContext context) {
    final style = VerdictStyle.of(result.verdict);
    final shown = result.reasons.where((r) => r.points > 0 || r.code.startsWith('TRUSTED')).toList();
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            color: style.color,
            padding: const EdgeInsets.all(16),
            child: Row(children: [
              Icon(style.icon, color: Colors.white, size: 36),
              const SizedBox(width: 12),
              Expanded(
                child: Text(style.title,
                    style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
              ),
              Text('${result.score}/100',
                  key: const Key('score'),
                  style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600)),
            ]),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(result.suggestion, style: Theme.of(context).textTheme.titleMedium),
              if (shown.isNotEmpty) ...[
                const SizedBox(height: 12),
                Text('Why', style: Theme.of(context).textTheme.labelLarge),
                const SizedBox(height: 4),
                for (final r in shown)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Icon(r.points > 0 ? Icons.remove_circle_outline : Icons.check_circle_outline,
                          size: 18, color: r.points > 0 ? style.color : Colors.green),
                      const SizedBox(width: 6),
                      Expanded(child: Text(r.text)),
                    ]),
                  ),
              ],
              if (result.checksSkipped.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text('Some checks were skipped: ${result.checksSkipped.join(', ')}',
                    style: Theme.of(context).textTheme.bodySmall),
              ],
              if (onWrongVerdict != null)
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton.icon(
                    onPressed: onWrongVerdict,
                    icon: const Icon(Icons.flag_outlined),
                    label: const Text('Wrong result?'),
                  ),
                ),
            ]),
          ),
        ],
      ),
    );
  }
}

/// Asks the user what the message really was and returns ham/spam/scam (or null).
Future<String?> askCorrectLabel(BuildContext context) => showDialog<String>(
      context: context,
      builder: (ctx) => SimpleDialog(
        title: const Text('What was this message really?'),
        children: [
          SimpleDialogOption(onPressed: () => Navigator.pop(ctx, 'scam'), child: const Text('A scam / fraud')),
          SimpleDialogOption(onPressed: () => Navigator.pop(ctx, 'spam'), child: const Text('An advertisement')),
          SimpleDialogOption(onPressed: () => Navigator.pop(ctx, 'ham'), child: const Text('A normal, safe message')),
        ],
      ),
    );
