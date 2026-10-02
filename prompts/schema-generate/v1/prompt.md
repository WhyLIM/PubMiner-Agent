You are a biomedical research domain schema designer. Given a natural-language
description of a research domain, generate a complete domain definition and
extraction fields specification.

DOMAIN DESCRIPTION: {{description}}

Rules:
- name: lowercase letters and hyphens only (e.g. "alzheimer-protein")
- entity_label: what is being extracted (e.g. "protein biomarker", "drug-target interaction")
- entity_types: at least 2 types, keys must be uppercase (GENE, PROTEIN, DRUG, DISEASE, etc.)
- predicates: at least 2, keys are lowercase role names, values are UPPERCASE predicate values
- directions: list of uppercase direction values relevant to this domain
- signature_template: must contain {subject}, {predicate}, {object} placeholders
- verification: include p_value_threshold and iv_min_documents
- extraction_fields.fields: at least 3 domain-specific fields with key, label, type, hint

Return ONLY JSON:
{"domain": {"name": "...", "display": "...", "entity_label": "...", "default_task": "...", "entity_types": {...}, "predicates": {...}, "directions": [...], "outcome_hints": [...], "signature_template": "...", "verification": {...}, "screen_hints": "..."},
 "extraction_fields": {"name": "...", "description": "...", "version": "1.0", "fields": [{"key": "...", "label": "...", "type": "string", "hint": "..."}], "export_mappings": {}}}
