"""解析缓存测试：命中免外部调用、跨 run 复用、put 幂等。"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from pubminer.infrastructure.db.base import session_scope
from pubminer.infrastructure.db.orm_cache import ResolutionCacheRow
from pubminer.infrastructure.db.repositories.normalize_cache import ResolutionCacheRepository
from pubminer.workflows.normalize_cache import CachedEntityResolver, normalize_mention_key
from pubminer.workflows.ports import ResolutionCandidate

ALEMBIC_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def session_factory(tmp_path):
    import os
    import subprocess
    import sys

    db = tmp_path / "cache.db"
    env = {**os.environ, "PUBMINER_DB_URL": f"sqlite:///{db.as_posix()}", "PYTHONUTF8": "1"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_ROOT / "alembic.ini"), "upgrade", "head"],
        cwd=ALEMBIC_ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    from pubminer.infrastructure.db.base import create_engine_from_url, make_session_factory

    engine = create_engine_from_url(f"sqlite:///{db.as_posix()}")
    yield make_session_factory(engine)
    engine.dispose()


class CountingResolver:
    def __init__(self):
        self.calls = 0

    def resolve(self, mention, entity_type):
        self.calls += 1
        return [ResolutionCandidate(
            entity_id="t", name="KRAS", identifier="NCBIGene:3845", score=1.0,
        )], False


def _cand_dict(c):
    return {"entity_id": c.entity_id, "name": c.name,
            "identifier": c.identifier, "score": c.score}


class TestResolutionCache:
    def test_cache_hit_avoids_resolver_call(self, session_factory):

        inner = CountingResolver()
        cached = CachedEntityResolver(inner, session_factory)

        with session_scope(session_factory) as session:
            cands, review = cached.resolve("KRAS", "GENE", session=session)
            assert inner.calls == 1
            assert cands[0].identifier == "NCBIGene:3845"

        with session_scope(session_factory) as session2:
            cands2, review2 = cached.resolve("  kras  ", "GENE", session=session2)  # 键归一化相同
            assert inner.calls == 1, "命中缓存时不得再调 resolver"
            assert cands2[0].identifier == "NCBIGene:3845"

    def test_mention_key_normalization(self):
        assert normalize_mention_key("  CA 19-9 ") == "ca199"

    def test_put_idempotent_per_type(self, session_factory):

        with session_scope(session_factory) as session:
            repo = ResolutionCacheRepository(session)
            repo.put_candidates("KRAS", "GENE", [{"identifier": "NCBIGene:3845"}])
            repo.put_candidates("KRAS", "GENE", [{"identifier": "NCBIGene:3845"}])  # 覆盖
            repo.put_candidates("KRAS", "DISEASE", [{"identifier": "MESH:D001474"}])
            rows = session.execute(select(ResolutionCacheRow)).scalars().all()
            assert len(rows) == 2
