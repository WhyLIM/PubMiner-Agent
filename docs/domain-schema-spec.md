# 领域与抽取字段 Schema 规范

## 概述

PubMiner Evidence Agent 通过两个 JSON 文件定义一个研究领域：

| 文件 | 位置 | 作用 |
|---|---|---|
| 领域定义 | `schemas/domains/{name}.json` | 定义谓词、方向、签名模板、验证阈值、导出映射 |
| 抽取字段 | `schemas/extraction_fields/{name}.json` | 定义 LLM 需额外抽取的研究上下文字段 |

两者配合使用：领域定义控制管线行为（怎么检索、怎么验证、怎么聚类），抽取字段控制 LLM 从文献中提取哪些研究上下文信息。

## 一、领域定义 (`domains/{name}.json`)

### 完整 JSON Schema

```json
{
  "name": "<string, 必填, 小写字母+连字符, 唯一标识>",
  "display": "<string, 必填, 展示名称>",
  "entity_label": "<string, 必填, 抽取对象统称>",
  "default_task": "<string, 可选, 默认任务类型>",
  "entity_types": {
    "<KEY>": "<display_string>"
  },
  "predicates": {
    "<role_key>": "<PREDICATE_VALUE>"
  },
  "directions": ["<DIRECTION_VALUE>", ...],
  "outcome_hints": ["<hint>", ...],
  "signature_template": "<string, 必须含 {subject} {predicate} {object}>",
  "verification": {
    "p_value_threshold": <float>,
    "iv_min_documents": <int>
  },
  "screen_hints": "<string>",
  "extraction_fields_schema": "<string|null, 关联的抽取字段 schema 名>",
  "export_mappings": {
    "<format>": { "<predicate>": "<display>" }
  }
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | ✅ | 唯一小写标识符，用于 `PUBMINER_LLM_DOMAIN` 环境变量 |
| `display` | string | ✅ | 人类可读的展示名称 |
| `entity_label` | string | ✅ | 抽取对象的统称（如 "biomarker"），注入抽取 prompt |
| `default_task` | string | | 默认任务类型 |
| `entity_types` | object | ✅ | 键值对：`TYPE_KEY` → 展示名。用于实体归一化路由和实体创建 |
| `predicates` | object | ✅ | 键值对：`role_key` → 谓词值。role_key 是 LLM 输出的角色字符串（小写），谓词值用于构建 canonical signature |
| `directions` | array | ✅ | 合法方向值列表（大写）。LLM 输出的 direction 必须在此列表中 |
| `outcome_hints` | array | | 常见结局指标提示（注入筛选 prompt） |
| `signature_template` | string | ✅ | 签名模板，必须含 `{subject}` `{predicate}` `{object}` 占位符 |
| `verification.p_value_threshold` | float | | p 值显著性阈值（默认 0.05） |
| `verification.iv_min_documents` | int | | 独立验证所需最少独立文献数（默认 3） |
| `screen_hints` | string | | 注入筛选 prompt 的领域提示 |
| `extraction_fields_schema` | string\|null | | 关联的抽取字段 schema 名称 |
| `export_mappings` | object | | 导出格式映射（如 cbd: {PROGNOSTIC: "Prognosis"}） |

### 约束

- `predicates` 的值必须能映射到 `Predicate` 枚举（PROGNOSTIC/DIAGNOSTIC/PREDICTIVE/THERAPEUTIC/INHIBITS/ACTIVATES/ASSOCIATED 等）
- `entity_types` 的键必须能映射到 `EntityType` 枚举（GENE/PROTEIN/DISEASE/DRUG/CLINICAL_MARKER/METABOLITE/OTHER 等）
- `directions` 的值映射到 `Direction` 枚举
- `signature_template` 中 `{direction}` 是可选的

### 完整示例：Biomarker 研究

```json
{
  "name": "biomarker",
  "display": "Biomarker Evidence Extraction",
  "entity_label": "biomarker",
  "default_task": "prognostic_biomarker",
  "entity_types": {
    "GENE": "gene",
    "PROTEIN": "protein",
    "CLINICAL_MARKER": "clinical_marker",
    "METABOLITE": "metabolite",
    "OTHER": "other"
  },
  "predicates": {
    "prognostic": "PROGNOSTIC",
    "diagnostic": "DIAGNOSTIC",
    "predictive": "PREDICTIVE",
    "therapeutic": "THERAPEUTIC"
  },
  "directions": ["HIGH", "LOW", "OVEREXPRESSION", "UNDEREXPRESSION", "AMPLIFICATION", "DELETION", "MUTATION", "POSITIVE", "NEGATIVE", "UNSPECIFIED"],
  "outcome_hints": ["overall survival", "disease-free survival", "progression-free survival"],
  "signature_template": "{subject} | {predicate} | {object} | {direction}",
  "verification": { "p_value_threshold": 0.05, "iv_min_documents": 3 },
  "screen_hints": "prognostic biomarker, independent cohort validation preferred",
  "extraction_fields_schema": "colorectal",
  "export_mappings": {
    "cbd": { "PROGNOSTIC": "Prognosis", "DIAGNOSTIC": "Diagnosis" }
  }
}
```

### 完整示例：药物靶点研究

```json
{
  "name": "drug-target",
  "display": "Drug-Target Interaction Extraction",
  "entity_label": "drug-target interaction",
  "default_task": "drug_target_interaction",
  "entity_types": {
    "DRUG": "drug",
    "TARGET": "target_protein",
    "PATHWAY": "pathway",
    "OTHER": "other"
  },
  "predicates": {
    "inhibits": "INHIBITS",
    "activates": "ACTIVATES",
    "binds": "BINDS",
    "modulates": "MODULATES"
  },
  "directions": ["AGONIST", "ANTAGONIST", "INHIBITOR", "ACTIVATOR", "UNSPECIFIED"],
  "outcome_hints": ["IC50", "EC50", "Ki", "binding affinity"],
  "signature_template": "{subject} | {predicate} | {object}",
  "verification": { "p_value_threshold": 0.05, "iv_min_documents": 2 },
  "screen_hints": "drug-target interaction, binding affinity"
}
```

## 二、抽取字段 (`extraction_fields/{name}.json`)

### 完整 JSON Schema

```json
{
  "name": "<string, 必填>",
  "description": "<string, 必填>",
  "version": "<string, 必填>",
  "fields": [
    {
      "key": "<string, 必填, 唯一键>",
      "label": "<string, 必填, 中文展示名>",
      "type": "<string: string|text|boolean|number>",
      "hint": "<string, LLM 抽取提示>"
    }
  ],
  "export_mappings": {
    "<format>": { "<field_key>": "<external_field_name>" }
  }
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | ✅ | schema 标识符 |
| `description` | string | ✅ | 描述 |
| `version` | string | ✅ | 版本号 |
| `fields` | array | ✅ | 领域特有字段列表 |
| `fields[].key` | string | ✅ | 字段键（存入 JSON 的键名） |
| `fields[].label` | string | ✅ | 中文展示名 |
| `fields[].type` | string | ✅ | string / text / boolean / number |
| `fields[].hint` | string | | LLM 抽取提示 |
| `export_mappings` | object | | 导出映射：`{格式名: {字段键: 外部字段名}}` |

### 完整示例：结直肠癌（CBD 领域）

```json
{
  "name": "colorectal-cancer-biomarker",
  "description": "结直肠癌生物标志物数据库（CBD）字段集",
  "version": "1.0",
  "fields": [
    {"key": "detection_method", "label": "检测方法", "type": "string", "hint": "如 IHC / qPCR / western blot / FISH"},
    {"key": "sample_type", "label": "样本类型", "type": "string", "hint": "如 tissue / blood / serum / stool"},
    {"key": "tumor_location", "label": "肿瘤位置", "type": "string", "hint": "如 colon / rectum / colorectal"},
    {"key": "cancer_stage", "label": "肿瘤分期", "type": "string", "hint": "如 I-III / Tis / IV"},
    {"key": "study_conclusion", "label": "研究结论", "type": "text", "hint": "作者的主要结论（一句话）"},
    {"key": "drugs", "label": "相关药物", "type": "string", "hint": "文中提及的相关治疗药物"},
    {"key": "multivariate_adjusted", "label": "多变量校正", "type": "boolean", "hint": "是否进行了多变量统计校正"}
  ],
  "export_mappings": {
    "cbd": {
      "detection_method": "experiment",
      "sample_type": "source",
      "tumor_location": "location",
      "cancer_stage": "stage",
      "study_conclusion": "conclusion",
      "drugs": "drugs"
    }
  }
}
```

## 三、通用字段（固定，不通过 schema 配置）

以下字段对所有研究领域通用，硬编码在 `BiomarkerEvidence` 模型中：

| 字段 | 说明 | 为什么是通用的 |
|---|---|---|
| `biomarker_mention` / `subject_mention` | 研究对象名称 | 任何证据提取都需要 |
| `biomarker_type` / `subject_type` | 对象类型 | 归一化路由需要 |
| `disease_mention` | 疾病/上下文 | 生物医学证据的锚点 |
| `role` | 研究角色（由领域 schema 的 predicates 定义合法值） | 决定 claim 的谓词 |
| `direction` | 方向（由领域 schema 的 directions 定义合法值） | 签名的组成部分 |
| `outcome` | 结局指标 | 领域 schema 的 outcome_hints 提示 LLM |
| `statistics` | {effect_measure, effect_value, CI, p_value} | 定量证据的核心 |
| `study_design` | 研究设计类型 | 证据强度评分需要 |
| `evidence_span` | 原文逐字摘录 | grounding 红线 |
| `evidence_source` | abstract / fulltext | 证据来源追踪 |

## 四、LLM 自动生成

用户可以用自然语言描述一个新领域，LLM 自动生成完整的领域定义和抽取字段。生成结果展示给用户预览/编辑，确认后保存。

**调用方式**：`POST /api/v1/schemas/generate`
**输入**：`{"description": "我想研究阿尔茨海默病中的蛋白质生物标志物"}`
**输出**：完整的 domain JSON + extraction fields JSON

生成的 schema 经 Pydantic 校验后返回，确保格式正确。用户在前端预览/修改后调用 save 端点持久化。
