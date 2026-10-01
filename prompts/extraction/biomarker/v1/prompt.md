Extract structured biomarker evidence and study context from the ARTICLE TEXT below.

ARTICLE TEXT:
{{passage}}

Rules:
- Fill ONLY fields supported by explicit text in the article; use null otherwise.
- NEVER invent statistics, identifiers, cohort sizes, or outcomes.
- evidence_span must be a VERBATIM substring copied from the article text (exact characters).
- Return every distinct biomarker finding as a separate item.
- biomarker_type: classify what the biomarker is (gene/protein symbol -> gene; blood/urine markers like CA 19-9 or albumin ratio -> clinical_marker; metabolites -> metabolite; anything else -> other).
- study_context is article-level: extract sample size, stage, location, demographics,
  detection method, sample type, conclusion, and drugs ONLY if explicitly stated.

Return ONLY JSON:
{"items": [{"biomarker_mention": "...", "biomarker_type": "gene|protein|clinical_marker|metabolite|other", "disease_mention": "...", "role": "prognostic|diagnostic|predictive", "direction": "HIGH|LOW|...", "outcome": "...", "statistics": {"effect_measure": null, "effect_value": null, "confidence_interval": null, "p_value": null}, "study_design": "retrospective_cohort|prospective_cohort|case_control|...", "evidence_span": "verbatim text"}],
 "study_context": {"n": null, "disease_stage": null, "tumor_location": null, "age_mean": null, "age_range": null, "ethnicity": null, "country": null, "male_count": null, "female_count": null, "detection_method": null, "sample_type": null, "follow_up_months": null, "multivariate_adjusted": null, "study_conclusion": null, "drugs": null}}
