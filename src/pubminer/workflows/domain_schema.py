"""领域定义加载器：研究领域由 JSON schema 文件驱动，管线代码通用。

一个领域定义了：抽取什么实体、允许哪些谓词/方向、签名格式、
验证阈值、筛选提示、导出映射。换研究领域 = 改一个 JSON 文件 +
一个 prompt 变量，不改管线代码。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DOMAINS_DIR = Path(__file__).resolve().parents[3] / "schemas" / "domains"


@dataclass(frozen=True)
class DomainDefinition:
    name: str
    display: str
    entity_label: str
    default_task: str
    entity_types: dict[str, str]
    predicates: dict[str, str]  # role_key -> predicate value (e.g. "prognostic" -> "PROGNOSTIC")
    directions: list[str]
    outcome_hints: list[str]
    signature_template: str
    verification: dict
    screen_hints: str
    extraction_fields_schema: str | None = None
    export_mappings: dict[str, dict] = field(default_factory=dict)

    @property
    def iv_min_documents(self) -> int:
        return self.verification.get("iv_min_documents", 3)

    @property
    def p_value_threshold(self) -> float:
        return self.verification.get("p_value_threshold", 0.05)

    def predicate_for_role(self, role: str) -> str:
        """role 字符串（如 "prognostic"）→ 领域定义的谓词值（如 "PROGNOSTIC"）。"""
        return self.predicates.get(role.lower(), "ASSOCIATED")

    def direction_is_valid(self, direction: str) -> bool:
        return direction.upper() in [d.upper() for d in self.directions]

    def entity_type_for(self, mention_type: str) -> str:
        return self.entity_types.get(mention_type.upper(), "OTHER")

    def export_application(self, predicate: str) -> str:
        for mapping in self.export_mappings.values():
            if predicate in mapping:
                return mapping[predicate]
        return predicate


def load_domain(path: str | Path) -> DomainDefinition:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return DomainDefinition(
        name=data["name"],
        display=data.get("display", data["name"]),
        entity_label=data.get("entity_label", "entity"),
        default_task=data.get("default_task", ""),
        entity_types=data.get("entity_types", {}),
        predicates=data.get("predicates", {}),
        directions=data.get("directions", []),
        outcome_hints=data.get("outcome_hints", []),
        signature_template=data.get("signature_template", "{subject} | {predicate} | {object} | {direction}"),
        verification=data.get("verification", {}),
        screen_hints=data.get("screen_hints", ""),
        extraction_fields_schema=data.get("extraction_fields_schema"),
        export_mappings=data.get("export_mappings", {}),
    )


def discover_domains(root: Path | None = None) -> dict[str, Path]:
    root = root or DEFAULT_DOMAINS_DIR
    if not root.exists():
        return {}
    return {p.stem: p for p in sorted(root.glob("*.json"))}


def load_domain_by_name(name: str, root: Path | None = None) -> DomainDefinition:
    """按名称加载领域定义；不存在时抛 FileNotFoundError。"""
    available = discover_domains(root)
    path = available.get(name)
    if path is None:
        raise FileNotFoundError(
            f"domain {name!r} not found; available: {', '.join(sorted(available))}"
        )
    return load_domain(path)
