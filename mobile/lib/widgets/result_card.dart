// Result card widget (colour, icon, score, reasons, advice) and the 'what was it really?' feedback dialog.

import 'package:flutter/material.dart';

import '../models/check_result.dart';
import '../theme/app_theme.dart';

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

/// Purple gradient card from the team design: "This content is likely N% Scam" + big "N%".
/// N is the check's score (0-100); the verdict word is shown underneath.
class ScoreCard extends StatelessWidget {
  final CheckResult result;
  const ScoreCard({super.key, required this.result});

  @override
  Widget build(BuildContext context) {
    final verdictText = switch (result.verdict) {
      'dangerous' => 'Dangerous – likely a scam',
      'suspicious' => 'Suspicious – be careful',
      'safe' => 'Looks safe',
      _ => 'Unknown',
    };
    return Container(
      key: const Key('scoreCard'),
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(20, 22, 20, 18),
      decoration: BoxDecoration(
        gradient: AppColors.cardGradient,
        borderRadius: BorderRadius.circular(22),
        boxShadow: const [BoxShadow(color: Color(0x444A148C), blurRadius: 18, offset: Offset(0, 6))],
      ),
      child: Column(children: [
        RichText(
          textAlign: TextAlign.center,
          text: TextSpan(
            style: const TextStyle(color: Colors.white, fontSize: 19),
            children: [
              const TextSpan(text: 'This content is likely '),
              TextSpan(text: '${result.score}%', style: const TextStyle(fontWeight: FontWeight.w800)),
              const TextSpan(text: ' Scam'),
            ],
          ),
        ),
        const SizedBox(height: 4),
        Text('${result.score}%',
            key: const Key('scorePercent'),
            style: const TextStyle(color: Colors.white, fontSize: 84, fontWeight: FontWeight.w900, height: 1.05)),
        const SizedBox(height: 6),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
          decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.18), borderRadius: BorderRadius.circular(20)),
          child: Text(verdictText, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
        ),
      ]),
    );
  }
}

/// The checked message in the yellow frame.
class CheckedContent extends StatelessWidget {
  final String text;
  final int maxLines;
  const CheckedContent({super.key, required this.text, this.maxLines = 6});

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('checkedContent'),
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.contentFill,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.contentBorder, width: 2.5),
      ),
      child: Text(text, maxLines: maxLines, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 15, height: 1.35)),
    );
  }
}

/// The explanation paragraph: advice first, then the reasons in plain sentences.
class ExplanationText extends StatelessWidget {
  final CheckResult result;
  const ExplanationText({super.key, required this.result});

  @override
  Widget build(BuildContext context) {
    final reasons = result.reasons.where((r) => r.points > 0 && !r.code.startsWith('MIRA_NOT_SURE')).toList();
    final safe = result.reasons.where((r) => r.points <= 0 && r.code.startsWith('TRUSTED')).toList();
    final sentences = <String>[
      result.suggestion,
      ...reasons.map((r) => _sentence(r.text)),
      ...safe.map((r) => _sentence(r.text)),
      if (result.checksSkipped.isNotEmpty) 'Some checks could not run this time (${result.checksSkipped.join(', ')}).',
    ];
    return Text(sentences.join(' '),
        key: const Key('explanation'), style: const TextStyle(fontSize: 16, height: 1.4, color: AppColors.ink));
  }

  static String _sentence(String s) => s.endsWith('.') ? s : '$s.';
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
