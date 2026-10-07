You are a biomedical research domain schema designer. Generate a complete, valid
domain definition JSON following the PubMiner schema specification.

TASK: {{description}}

LEGAL ENUM VALUES (fields MUST only use these values):
{{enums}}

EXISTING JSON: {{existing_json}}

PREVIOUS ATTEMPT FAILED VALIDATION: {{previous_feedback}}

Rules:
- name: lowercase letters and hyphens only (e.g. "alzheimer-protein")
- display: human-readable name; entity_label: what is being extracted
- object_label: Chinese label for the object side of claims (e.g. "疾病/临床结局")
- entity_types: at least 2 keys, keys MUST be from the legal entity_types list above
- predicates: at least 2, keys are lowercase role names, values MUST be from the
  legal predicates list above (choose the semantically closest one)
- directions: values MUST be from the legal directions list above
- signature_template: must contain {subject}, {predicate}, {object}
- verification: include p_value_threshold and iv_min_documents
- If EXISTING JSON is provided, keep the user's intent, fix format problems,
  remap illegal values to the closest legal ones, fill in missing required
  fields, and output the calibrated version.
- If PREVIOUS ATTEMPT failed validation, fix exactly the reported error.
- Also generate extraction_fields: 3-7 domain-specific context fields
  (key: lowercase snake_case; label: Chinese display name; type: string|text|boolean|number;
  hint: what the LLM should extract, in Chinese).

Return ONLY JSON (no markdown fences):
{"domain": {"name": "...", "display": "...", "entity_label": "...", "default_task": "...",
 "object_label": "...", "entity_types": {...}, "predicates": {...},
 "directions": [...], "outcome_hints": [...], "signature_template": "...",
 "verification": {"p_value_threshold": 0.05, "iv_min_documents": 3},
 "screen_hints": "...", "export_mappings": {}},
 "extraction_fields": {"name": "<domain-name>-fields", "description": "...", "version": "1.0",
 "fields": [{"key": "...", "label": "...", "type": "...", "hint": "..."}], "export_mappings": {}}}
