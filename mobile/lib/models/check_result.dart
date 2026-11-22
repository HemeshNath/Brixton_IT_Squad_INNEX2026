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
  final String verdict; // safe | suspicious | dangerous | unknown
  final int score;
  /// The owner's risk class (B7): low | suspicious | high | critical | very_harmful (null = MIRA gave no answer).
  final String? riskClass;
  /// The owner's output line, e.g. "54% (Shows urgency)".
  final String? ownerProbability;
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
    this.riskClass,
    this.ownerProbability,
  });

  /// What the colour and title follow: the risk class when there is one, else the verdict.
  String get level => riskClass ?? verdict;

  /// The warnings to list (the class itself is shown as the title, so its RISK_ line is left out).
  List<Reason> get warnings => reasons.where((r) => !r.code.startsWith('RISK_')).toList();

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
        riskClass: j['risk_class'] as String?,
        ownerProbability: (j['owner_result'] as Map?)?['Probability'] as String?,
      );
}
