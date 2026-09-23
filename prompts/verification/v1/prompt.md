Verify whether the PASSAGE supports, contradicts, or is uncertain about the CLAIM.

CLAIM: {{claim}}
PASSAGE: {{passage}}

Consider: entity correctness, disease correctness, endpoint correctness, statistical
significance, analysis type, independent validation. Polarity must be one of
SUPPORT | CONTRADICT | NO_EFFECT | UNCERTAIN. Confidence is NOT truth.
Return ONLY JSON: {"polarity": "...", "entity_correct": true|false|null, "disease_correct": true|false|null, "endpoint_correct": true|false|null, "statistically_significant": true|false|null, "analysis_type": "univariate|multivariate|unknown", "independent_validation": true|false|null, "reasons": ["..."], "needs_human_review": true|false}
