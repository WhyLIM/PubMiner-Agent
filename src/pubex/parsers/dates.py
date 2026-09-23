"""出版日期提取。

复刻 legacy `extract_publication_date`：在 DP（优先）与 SO 中检索
"YYYY Mon D" 形式的日期；均未命中时返回 None（legacy 输出 'NA'）。
"""
from __future__ import annotations

import re
from typing import Mapping

DATE_PATTERN = re.compile(r"\b\d{4}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\b")


def extract_publication_date(record: Mapping[str, object]) -> str | None:
    """从 MEDLINE 记录提取出版日期；缺失返回 None。"""
    for key in ("DP", "SO"):
        value = record.get(key)
        if isinstance(value, str):
            match = DATE_PATTERN.search(value)
            if match:
                return match.group()
    return None
