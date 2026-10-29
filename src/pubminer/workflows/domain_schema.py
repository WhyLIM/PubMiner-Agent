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
    object_label: str = ""

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
        object_label=data.get("object_label", ""),
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


def merge_domains(base: DomainDefinition, extra: DomainDefinition) -> DomainDefinition:
    """默认 + 自定义合并：extra 并入 base。

    实体类型/谓词/方向/结局提示/导出映射取并集（同名时 extra 覆盖 base 词条说明）；
    验证阈值等安全红线（iv_min_documents、p_value_threshold）保留 base——
    自定义领域不得放宽独立验证门槛；签名模板沿用 base 保持聚合键稳定。
    """
    return DomainDefinition(
        name=f"{base.name}+{extra.name}",
        display=f"{base.display}＋{extra.display}",
        entity_label=base.entity_label,
        default_task=base.default_task or extra.default_task,
        entity_types={**base.entity_types, **extra.entity_types},
        predicates={**base.predicates, **extra.predicates},
        directions=list(dict.fromkeys([*base.directions, *extra.directions])),
        outcome_hints=list(dict.fromkeys([*base.outcome_hints, *extra.outcome_hints])),
        signature_template=base.signature_template,
        verification=base.verification,
        screen_hints=(f"{base.screen_hints}\n{extra.screen_hints}".strip()
                      if extra.screen_hints else base.screen_hints),
        extraction_fields_schema=extra.extraction_fields_schema or base.extraction_fields_schema,
        export_mappings={**base.export_mappings, **extra.export_mappings},
        object_label=base.object_label or extra.object_label,
    )
