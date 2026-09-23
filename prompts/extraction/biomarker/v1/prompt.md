Extract structured biomarker evidence from the ARTICLE TEXT below.

ARTICLE TEXT:
{{passage}}

Rules:
- Fill ONLY fields supported by explicit text in the article; use null otherwise.
- NEVER invent statistics, identifiers, cohort sizes, or outcomes.
- evidence_span must be a VERBATIM substring copied from the article text (exact characters).
- Return every distinct biomarker finding as a separate item.
Return ONLY JSON:
{"items": [{"biomarker_mention": "...", "disease_mention": "...", "role": "prognostic|diagnostic|predictive", "direction": "HIGH|LOW|...", "outcome": "...", "statistics": {"effect_measure": null, "effect_value": null, "confidence_interval": null, "p_value": null}, "study_design": "retrospective_cohort|prospective_cohort|case_control|...", "evidence_span": "verbatim text"}]}
