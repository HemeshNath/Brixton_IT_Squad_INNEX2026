// Result card widget (colour, icon, score, reasons, advice) and the 'what was it really?' feedback dialog.

import 'package:flutter/material.dart';

import '../l10n/strings.dart';
import '../models/check_result.dart';
import '../theme/app_theme.dart';

class VerdictStyle {
  final Color color;
  final IconData icon;
  const VerdictStyle(this.color, this.icon);

  static VerdictStyle of(String verdict) => switch (verdict) {
        'dangerous' => const VerdictStyle(Color(0xFFC62828), Icons.dangerous_rounded),
        'suspicious' => const VerdictStyle(Color(0xFFEF6C00), Icons.warning_amber_rounded),
        'safe' => const VerdictStyle(Color(0xFF2E7D32), Icons.verified_user_rounded),
        _ => const VerdictStyle(Colors.grey, Icons.help_outline),
      };
}

class ResultCard extends StatelessWidget {
  final CheckResult result;
  final VoidCallback? onWrongVerdict;

  const ResultCard({super.key, required this.result, this.onWrongVerdict});

  @override
  Widget build(BuildContext context) {
    final s = S.of(context);
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
                child: Text(s.verdictTitle(result.verdict),
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
              Text(s.suggestion(result.suggestion), style: Theme.of(context).textTheme.titleMedium),
              if (shown.isNotEmpty) ...[
                const SizedBox(height: 12),
                Text(s.why, style: Theme.of(context).textTheme.labelLarge),
                const SizedBox(height: 4),
                for (final r in shown)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Icon(r.points > 0 ? Icons.remove_circle_outline : Icons.check_circle_outline,
                          size: 18, color: r.points > 0 ? style.color : Colors.green),
                      const SizedBox(width: 6),
                      Expanded(child: Text(s.reason(r))),
                    ]),
                  ),
              ],
              if (result.checksSkipped.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(s.skippedChecks(result.checksSkipped),
                    style: Theme.of(context).textTheme.bodySmall),
              ],
              if (onWrongVerdict != null)
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton.icon(
                    onPressed: onWrongVerdict,
                    icon: const Icon(Icons.flag_outlined),
                    label: Text(s.wrongResult),
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
    final s = S.of(context);
    final verdictText = s.verdictTitle(result.verdict);
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
              TextSpan(text: s.likelyPrefix),
              TextSpan(text: '${result.score}%', style: const TextStyle(fontWeight: FontWeight.w800)),
              TextSpan(text: s.likelySuffix),
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
    final s = S.of(context);
    final reasons = result.reasons.where((r) => r.points > 0 && !r.code.startsWith('MIRA_NOT_SURE')).toList();
    final safe = result.reasons.where((r) => r.points <= 0 && r.code.startsWith('TRUSTED')).toList();
    final sentences = <String>[
      s.suggestion(result.suggestion),
      ...reasons.map((r) => _sentence(s.reason(r))),
      ...safe.map((r) => _sentence(s.reason(r))),
      if (result.checksSkipped.isNotEmpty) s.skippedChecks(result.checksSkipped),
    ];
    return Text(sentences.join(' '),
        key: const Key('explanation'), style: const TextStyle(fontSize: 16, height: 1.4, color: AppColors.ink));
  }

  static String _sentence(String s) => s.endsWith('.') || s.endsWith('।') ? s : (_isNepali(s) ? '$s।' : '$s.');
  static bool _isNepali(String s) => RegExp(r'[ऀ-ॿ]').hasMatch(s);
}

/// Asks the user what the message really was and returns ham/spam/scam (or null).
Future<String?> askCorrectLabel(BuildContext context) {
  final s = S.of(context);
  return showDialog<String>(
    context: context,
    builder: (ctx) => SimpleDialog(
      title: Text(s.whatWasIt),
      children: [
        SimpleDialogOption(onPressed: () => Navigator.pop(ctx, 'scam'), child: Text(s.labelScam)),
        SimpleDialogOption(onPressed: () => Navigator.pop(ctx, 'spam'), child: Text(s.labelSpam)),
        SimpleDialogOption(onPressed: () => Navigator.pop(ctx, 'ham'), child: Text(s.labelHam)),
      ],
    ),
  );
}
