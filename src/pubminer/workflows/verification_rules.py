"""规则辅助验证：纯规则预计算统计提示，注入 LLM prompt 减少 UNCERTAIN。

设计原则（§8.4）：规则只产生**提示**（hint），LLM 做最终仲裁。
规则输出不能替代 LLM 判定，只能校准它。
"""
from __future__ import annotations

import re

_P_VALUE_RE = re.compile(r"p\s*[<=]\s*(0?\.\d+)", re.IGNORECASE)
_HR_RE = re.compile(r"(?:HR|hazard ratio)[^\d]*([\d.]+)", re.IGNORECASE)
_SIGNIFICANT_WORDS = ("significantly", "significant", "p < 0.05", "p=0.0")


def extract_p_value(text: str) -> float | None:
    """从文本中提取第一个 p 值数字。"""
    match = _P_VALUE_RE.search(text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def rule_assess(span_text: str, statistics: dict | None = None) -> dict:
    """纯规则评估：返回 statistically_significant 提示与理由。

    供 verification prompt 注入；LLM 仍做最终仲裁。
    statistics.p_value 优先于 span 文本中的正则匹配。
    """
    # statistics.p_value 直接解析（最可靠信号）
    if statistics and statistics.get("p_value"):
        try:
            p = float(str(statistics["p_value"]).lstrip("<").strip())
            return {
                "statistically_significant": p < 0.05,
                "rule_reasons": [f"rule: statistics p={p}"],
            }
        except ValueError:
            pass

    combined = span_text
    if statistics:
        for key in ("p_value", "effect_value", "confidence_interval"):
            v = statistics.get(key)
            if v:
                combined += f" {v}"

    p = extract_p_value(combined)
    if p is not None:
        significant = p < 0.05
        return {
            "statistically_significant": significant,
            "rule_reasons": [f"rule: p={p} {'<' if significant else '>='} 0.05"],
        }

    # 无显式 p 值时看显著性关键词
    lower = combined.lower()
    if any(w in lower for w in _SIGNIFICANT_WORDS):
        return {"statistically_significant": True, "rule_reasons": ["rule: significant keyword found"]}
    return {"statistically_significant": None, "rule_reasons": []}
