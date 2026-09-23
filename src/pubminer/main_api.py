"""Evidence Agent API 启动入口：`pubminer-api` 或 `python -m pubminer.main_api`。"""
from __future__ import annotations

import os

from pubminer.settings import load_env_file


def create_default_app():
    from pubminer.api.app import create_app
    from pubminer.api.deps import build_container_from_env

    container, notes = build_container_from_env()
    for note in notes:
        print(f"[pubminer] {note}")
    return create_app(container)


def main() -> None:
    loaded = load_env_file()
    if loaded:
        print(f"[pubminer] loaded {loaded} vars from .env")
    import uvicorn

    app = create_default_app()
    uvicorn.run(app, host=os.environ.get("PUBMINER_HOST", "127.0.0.1"), port=int(os.environ.get("PUBMINER_PORT", "8001")))


if __name__ == "__main__":
    main()
