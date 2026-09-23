"""版本化 prompt 资产（设计文档 §9.1）。

prompts/<name>/<version>/prompt.md + prompt.json（元数据：schema_version、
model_requirements、negative_cases）。production 只能引用已发布 pipeline
release 绑定的版本，不隐式使用 latest。
"""
from __future__ import annotations

import json
from pathlib import Path

from pubminer.application.ports import LLMError


class PromptNotFoundError(LLMError):
    pass


class Prompt:
    def __init__(self, name: str, version: str, text: str, meta: dict) -> None:
        self.name = name
        self.version = version
        self.text = text
        self.meta = meta

    @property
    def schema_version(self) -> str | None:
        return self.meta.get("schema_version")

    @property
    def system(self) -> str:
        return self.meta.get("system", "")

    def render(self, **variables: str) -> str:
        out = self.text
        for key, value in variables.items():
            out = out.replace("{{" + key + "}}", str(value))
        return out


def find_prompts_dir(start: str | Path | None = None) -> Path | None:
    """定位版本化 prompt 资产目录：环境变量优先，其次向上查找 prompts/。"""
    import os

    env_dir = os.environ.get("PUBMINER_PROMPTS_DIR")
    if env_dir and (Path(env_dir) / "agent-policy").exists():
        return Path(env_dir)
    current = Path(start or Path(__file__).resolve())
    for candidate in [current, *current.parents]:
        prompts_dir = candidate / "prompts"
        if (prompts_dir / "agent-policy").exists():
            return prompts_dir
    return None


class PromptRegistry:
    """从磁盘加载不可变 prompt 版本；同 (name, version) 内容恒定。"""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._cache: dict[tuple[str, str], Prompt] = {}

    @classmethod
    def discover(cls, start: str | Path | None = None) -> "PromptRegistry":
        """按 find_prompts_dir 规则自动定位；找不到时抛 PromptNotFoundError。"""
        found = find_prompts_dir(start)
        if found is None:
            raise PromptNotFoundError(
                "prompts/ directory not found; set PUBMINER_PROMPTS_DIR"
            )
        return cls(found)

    def get(self, name: str, version: str) -> Prompt:
        key = (name, version)
        if key in self._cache:
            return self._cache[key]
        directory = self.root / name / version
        prompt_file = directory / "prompt.md"
        if not prompt_file.exists():
            raise PromptNotFoundError(f"prompt {name}@{version} not found under {self.root}")
        meta: dict = {}
        meta_file = directory / "prompt.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        prompt = Prompt(name, version, prompt_file.read_text(encoding="utf-8"), meta)
        self._cache[key] = prompt
        return prompt

    def versions(self, name: str) -> list[str]:
        directory = self.root / name
        if not directory.exists():
            return []
        return sorted(p.name for p in directory.iterdir() if (p / "prompt.md").exists())
