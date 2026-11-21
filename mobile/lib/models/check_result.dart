// Data classes for one check result returned by the API (verdict, score, reasons, suggestion...).

class Reason {
  final String code;
  final String text;
  final int points;

  const Reason({required this.code, required this.text, required this.points});

  factory Reason.fromJson(Map<String, dynamic> j) => Reason(
        code: j['code'] as String? ?? '',
        text: j['text'] as String? ?? '',
        points: (j['points'] as num?)?.toInt() ?? 0,
      );
}

class CheckResult {
  final String checkId;
  final String verdict; // safe | suspicious | dangerous
  final int score;
  final String? label; // ham | spam | scam
  final List<Reason> reasons;
  final String suggestion;
  final List<String> checksSkipped;
  final String sender;
  final String text;
  final DateTime? createdAt;

  const CheckResult({
    required this.checkId,
    required this.verdict,
    required this.score,
    required this.label,
    required this.reasons,
    required this.suggestion,
    this.checksSkipped = const [],
    this.sender = '',
    this.text = '',
    this.createdAt,
  });

  factory CheckResult.fromJson(Map<String, dynamic> j) => CheckResult(
        checkId: j['check_id'] as String? ?? '',
        verdict: j['verdict'] as String? ?? 'unknown',
        score: (j['score'] as num?)?.toInt() ?? 0,
        label: j['label'] as String?,
        reasons: ((j['reasons'] as List?) ?? [])
            .map((e) => Reason.fromJson(Map<String, dynamic>.from(e as Map)))
            .toList(),
        suggestion: j['suggestion'] as String? ?? '',
        checksSkipped: ((j['checks_skipped'] as List?) ?? []).map((e) => '$e').toList(),
        sender: j['sender'] as String? ?? '',
        text: j['text'] as String? ?? '',
        createdAt: DateTime.tryParse(j['created_at'] as String? ?? ''),
      );
}
