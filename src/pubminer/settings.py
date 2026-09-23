"""极简 .env 加载器：无第三方依赖。

规则：每行 KEY=VALUE；支持整行注释（#）；值两端空白与成对引号剥除；
兼容 Windows CRLF。已存在的环境变量优先（不覆盖），便于命令行临时覆盖。
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_FILE = ".env"


def load_env_file(path: str | Path = DEFAULT_ENV_FILE, *, override: bool = False) -> int:
    """加载 .env 到 os.environ；返回实际设置的变量数。"""
    env_file = Path(path)
    if not env_file.exists():
        return 0
    loaded = 0
    for raw_line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip().rstrip("\r")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if not override and key in os.environ and os.environ[key]:
            continue
        os.environ[key] = value
        loaded += 1
    return loaded
