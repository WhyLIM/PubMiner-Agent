"""可配置抽取字段 schema：领域相关字段由 JSON 定义，不改代码。

用法：
- `PUBMINER_EXTRACTION_SCHEMA=colorectal` 选择字段集
- 字段定义控制 LLM 抽取 prompt（额外要求 + study_context 字段）
- export_mappings 定义如何映射到 CBD 等外部格式
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    type: str  # string | text | boolean | number
    hint: str = ""


@dataclass(frozen=True)
class ExtractionSchema:
    name: str
    description: str
    version: str
    fields: tuple[FieldSpec, ...] = ()
    export_mappings: dict[str, dict[str, str]] = field(default_factory=dict)

    def prompt_fragment(self) -> str:
        """生成 prompt 中的 study_context 字段要求文本。"""
        if not self.fields:
            return ""
        lines = ["study_context (article-level, extract if explicitly stated):"]
        for f in self.fields:
            lines.append(f'  "{f.key}": null,  // {f.label}: {f.hint}')
        return "\n".join(lines)

    def field_keys(self) -> list[str]:
        return [f.key for f in self.fields]


def load_schema(path: str | Path) -> ExtractionSchema:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    fields = tuple(
        FieldSpec(key=f["key"], label=f["label"], type=f.get("type", "string"), hint=f.get("hint", ""))
        for f in data.get("fields", [])
    )
    return ExtractionSchema(
        name=data.get("name", ""),
        description=data.get("description", ""),
        version=data.get("version", "1.0"),
        fields=fields,
        export_mappings=data.get("export_mappings", {}),
    )


def discover_schemas(root: str | Path | None = None) -> dict[str, Path]:
    """扫描 schemas/extraction_fields/ 目录，返回 {name: path}。"""
    if root is None:
        root = Path(__file__).resolve().parents[2] / "schemas" / "extraction_fields"
    root = Path(root)
    if not root.exists():
        return {}
    return {p.stem: p for p in sorted(root.glob("*.json"))}
