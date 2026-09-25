You are parsing a biomedical research goal into structured fields.

GOAL: {{goal}}

Rules:
- disease: the medical condition under study, in English (e.g. "pancreatic cancer"). null if not mentioned.
- task: exactly one of prognostic_biomarker | diagnostic_biomarker | predictive_biomarker | therapeutic_biomarker, best matching the goal's intent. null if unclear.
- year_from / year_to: publication year bounds as integers. null if not mentioned.
- validation_requirement: "independent_validation" if the goal asks for independent cohort/validation, otherwise null.
Return ONLY JSON with those five keys.
