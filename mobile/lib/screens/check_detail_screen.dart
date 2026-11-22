// Result screen for one message (Phase 9.0): opened by tapping a CheckScam warning notification.
// Same look as the home result view (team design): sender, the message in the yellow frame, the explanation,
// the purple "likely N% Scam" card, "Wrong result?" and a button to open the original SMS.

import 'package:flutter/material.dart';

import '../models/check_result.dart';
import '../services/api.dart';
import '../widgets/result_card.dart';
import '../theme/app_theme.dart';

class CheckDetailScreen extends StatelessWidget {
  final CheckResult result;
  final String message; // original text from the phone (falls back to the server's masked text)
  final String sender;
  final ApiService Function()? apiFactory; // for "Wrong result?" (null = hidden)
  final Future<bool> Function()? onOpenMessage; // opens the original SMS (null = hidden)

  const CheckDetailScreen({
    super.key,
    required this.result,
    this.message = '',
    this.sender = '',
    this.apiFactory,
    this.onOpenMessage,
  });

  Future<void> _wrongResult(BuildContext context) async {
    final label = await askCorrectLabel(context);
    if (label == null || !context.mounted || apiFactory == null) return;
    try {
      await apiFactory!().sendFeedback(result.checkId, label);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Thanks! This helps train our model.')));
      }
    } on ApiException catch (e) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _openMessage(BuildContext context) async {
    final opened = await onOpenMessage!();
    if (!opened && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('The original message cannot be opened.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = message.isNotEmpty ? message : result.text;
    final from = sender.isNotEmpty ? sender : result.sender;
    return Scaffold(
      body: WaveBackground(
        child: SafeArea(
          child: Column(children: [
            Row(children: [
              IconButton(
                key: const Key('backButton'),
                tooltip: 'Back',
                icon: const Icon(Icons.arrow_back, color: AppColors.ink),
                onPressed: () => Navigator.of(context).maybePop(),
              ),
              const Expanded(child: CheckScamHeader()),
            ]),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
                children: [
                  if (from.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text('From: $from',
                          key: const Key('detailSender'),
                          style: const TextStyle(fontWeight: FontWeight.w600, color: AppColors.ink)),
                    ),
                  if (text.isNotEmpty) CheckedContent(text: text, maxLines: 20),
                  const SizedBox(height: 20),
                  ExplanationText(result: result),
                  const SizedBox(height: 20),
                  ScoreCard(result: result),
                  const SizedBox(height: 8),
                  Row(children: [
                    if (onOpenMessage != null)
                      TextButton.icon(
                        key: const Key('openMessage'),
                        onPressed: () => _openMessage(context),
                        icon: const Icon(Icons.sms_outlined, size: 18),
                        label: const Text('Open message'),
                      ),
                    const Spacer(),
                    if (apiFactory != null && result.checkId.isNotEmpty)
                      TextButton.icon(
                        onPressed: () => _wrongResult(context),
                        icon: const Icon(Icons.flag_outlined, size: 18),
                        label: const Text('Wrong result?'),
                      ),
                  ]),
                ],
              ),
            ),
          ]),
        ),
      ),
    );
  }
}
