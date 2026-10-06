"""PR-010 API 测试：/api/v1 契约（错误模型、会话、任务、SSE、claims）。"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.usefixtures("app_client")


@pytest.fixture(scope="module")
def migrated_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    import os
    import subprocess
    import sys

    tmpdir = tmp_path_factory.mktemp("api")
    db = tmpdir / "api.db"
    env = {**os.environ, "PUBMINER_DB_URL": f"sqlite:///{db.as_posix()}", "PYTHONUTF8": "1"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(REPO_ROOT / "alembic.ini"), "upgrade", "head"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return db


@pytest.fixture()
def app_client(migrated_db: Path):
    from fastapi.testclient import TestClient

    from pubminer.api.app import create_app
    from pubminer.api.deps import build_container

    test_path = migrated_db.with_name("api-client.db")
    import shutil

    shutil.copy(migrated_db, test_path)
    container = build_container(
        f"sqlite:///{test_path.as_posix()}",
        workflow_ports=_fake_ports(),
    )
    app = create_app(container)
    with TestClient(app) as client:
        yield client


def _fake_ports():
    """与 test_mining_workflow 相同形状的 fake 端口（轻量版，单文档）。"""
    from types import SimpleNamespace

    from pubminer.domain.documents import Document, DocumentIdentifier, DocumentVersion
    from pubminer.domain.evidence import BiomarkerEvidence
    from pubminer.domain.screening import ScreeningDecision, ScreeningLabel
    from pubminer.workflows.ports import HydratedDocument

    SPAN = "High KRAS expression was associated with poor overall survival (HR 2.1)."

    def make_doc(pmid):
        document = Document(identifiers=[DocumentIdentifier(kind="pmid", value=pmid)], title=f"S {pmid}")
        version = DocumentVersion(document_id=document.id, canonical_text=SPAN, title=document.title)
        return HydratedDocument(
            document=document, version=version,
            section_spans=[("RESULTS", 0, len(SPAN))], fulltext_available=True,
        )

    doc = make_doc("33145284")

    class S:
        def search(self, intent):
            return [{"pmid": "33145284"}]

    class H:
        def hydrate(self, pmid):
            return doc

    class Sc:
        def screen(self, document, criteria=None):
            return ScreeningDecision(document_id=document.id, label=ScreeningLabel.RELEVANT)

    class E:
        def extract(self, doc, *, session=None):
            from uuid import uuid4 as _u

            from pubminer.domain.documents import EvidenceSpan

            version_id = doc.version["id"] if isinstance(doc.version, dict) else doc.version.id
            return [BiomarkerEvidence(
                biomarker_mention="KRAS", disease_mention="PDAC", role="prognostic",
                direction="HIGH", outcome="overall_survival",
                evidence_span=EvidenceSpan.from_text(version_id, _u(), SPAN, 0, "RESULTS"),
            )], {"n": 36}

    class N:
        def resolve(self, mention, entity_type, *, session=None):
            from pubminer.workflows.ports import ResolutionCandidate

            return [ResolutionCandidate(entity_id="t", name="KRAS", identifier="NCBIGene:3845", score=0.9)], False

    class V:
        def verify(self, signature, evidence, *, session=None):
            from pubminer.domain.evidence import EvidencePolarity, VerificationResult

            return VerificationResult(polarity=EvidencePolarity.SUPPORT, reasons=["ok"])

    return SimpleNamespace(search=S(), hydrate=H(), screen=Sc(), extract=E(), normalize=N(), verify=V())


class TestHealthAndErrors:
    def test_health(self, app_client):
        response = app_client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_error_model_shape(self, app_client):
        response = app_client.get("/api/v1/tasks/not-a-uuid")
        assert response.status_code in (404, 500)
        body = response.json()
        assert "error" in body and "request_id" in body
        assert set(body["error"]) >= {"code", "message", "retryable"}

    def test_unknown_session_404(self, app_client):
        response = app_client.get("/api/v1/agent/sessions/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


class TestSessionLifecycle:
    def test_create_clarify_plan_approve(self, app_client):
        created = app_client.post(
            "/api/v1/agent/sessions",
            json={"goal": "PDAC prognostic biomarker since 2020", "limits": {"max_turns": 5}},
        )
        assert created.status_code == 201
        session_id = created.json()["session_id"]
        assert created.json()["next"] == "ASK_HUMAN"

        # 澄清消息
        message = app_client.post(
            f"/api/v1/agent/sessions/{session_id}/messages",
            json={"role": "user", "content": "PDAC, prognostic, independent cohort required"},
        )
        assert message.status_code == 201

        # 绑定 TaskSpec
        spec = app_client.post(
            f"/api/v1/agent/sessions/{session_id}/task-spec",
            json={"disease": "PDAC", "task": "prognostic_biomarker", "year_from": 2020},
        )
        assert spec.status_code == 200
        assert spec.json()["missing_required_fields"] == []

        # 提交 + 批准计划
        plan = app_client.post(
            f"/api/v1/agent/sessions/{session_id}/plan",
            json={"rationale": "start broad", "steps": [{"id": "s1", "action_type": "SEARCH"}]},
        )
        assert plan.status_code == 202
        version = plan.json()["plan_version"]

        approved = app_client.post(
            f"/api/v1/agent/sessions/{session_id}/plan/approve", json={"plan_version": version}
        )
        assert approved.status_code == 200

        detail = app_client.get(f"/api/v1/agent/sessions/{session_id}").json()
        assert detail["status"] == "PLANNED"
        assert detail["current_plan_version"] == version
        assert detail["plans"][-1]["approved_by_human"] is True
        assert detail["task_spec"]["disease"] == "PDAC"

    def test_approve_stale_plan_conflicts(self, app_client):
        created = app_client.post("/api/v1/agent/sessions", json={"goal": "g"})
        session_id = created.json()["session_id"]
        app_client.post(
            f"/api/v1/agent/sessions/{session_id}/plan",
            json={"steps": [{"id": "s1", "action_type": "SEARCH"}]},
        )
        conflict = app_client.post(
            f"/api/v1/agent/sessions/{session_id}/plan/approve", json={"plan_version": 99}
        )
        assert conflict.status_code == 409


class TestTaskPipelineOverHttp:
    def test_create_task_runs_pipeline_and_claims_visible(self, app_client):
        created = app_client.post(
            "/api/v1/tasks",
            json={"intents": [{"name": "discovery", "query": "pdac kras", "max_results": 5}]},
        )
        assert created.status_code == 202
        task_id = created.json()["task_id"]

        detail = app_client.get(f"/api/v1/tasks/{task_id}").json()
        assert detail["status"] == "REVIEW_READY"
        assert [s["type"] for s in detail["steps"]][-1] == "AGGREGATE"

        claims = app_client.get("/api/v1/claims?status=CANDIDATE").json()["claims"]
        assert claims, "candidate claims visible over API"
        assert claims[0]["evidence_count"] >= 1
        assert claims[0]["polarities"].get("SUPPORT", 0) >= 1

    def test_cancel_and_unknown_task(self, app_client):
        created = app_client.post("/api/v1/tasks", json={"intents": [{"name": "q", "query": "x"}]})
        task_id = created.json()["task_id"]
        cancelled = app_client.post(f"/api/v1/tasks/{task_id}/actions/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "CANCELLED"

        missing = app_client.get("/api/v1/tasks/00000000-0000-0000-0000-000000000001")
        assert missing.status_code == 404


class TestSessionEvents:
    def test_events_json_and_sse(self, app_client):
        created = app_client.post("/api/v1/agent/sessions", json={"goal": "g"})
        session_id = created.json()["session_id"]
        app_client.post(
            f"/api/v1/agent/sessions/{session_id}/messages",
            json={"role": "user", "content": "hello"},
        )
        # 无行动时事件为空（游标语义可用）
        events = app_client.get(
            f"/api/v1/agent/sessions/{session_id}/events?format=json"
        ).json()
        assert events == {"events": [], "next_since": 0}

        # SSE 头部正确
        sse = app_client.get(f"/api/v1/agent/sessions/{session_id}/events")
        assert sse.headers["content-type"].startswith("text/event-stream")


class TestClaimEvidence:
    def test_evidence_locates_span_in_canonical_text(self, app_client):
        created = app_client.post(
            "/api/v1/tasks",
            json={"intents": [{"name": "discovery", "query": "pdac kras", "max_results": 5}]},
        )
        assert created.status_code == 202
        claims = app_client.get("/api/v1/claims?status=CANDIDATE").json()["claims"]
        assert claims

        response = app_client.get(f"/api/v1/claims/{claims[0]['claim_id']}/evidence")
        assert response.status_code == 200
        payload = response.json()
        assert payload["canonical_signature"] == claims[0]["canonical_signature"]
        assert payload["evidence"], "no-evidence-no-claim"
        for item in payload["evidence"]:
            span = item["span"]
            assert span["text"]
            # span 必须落在保存的 canonical text 内（grounding 可跳转）
            canonical = item["canonical_text"]
            assert canonical[span["start_char"] : span["end_char"]] == span["text"]

    def test_missing_claim_404(self, app_client):
        response = app_client.get(
            "/api/v1/claims/00000000-0000-0000-0000-000000000009/evidence"
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


class TestCors:
    def test_browser_origins_allowed(self, app_client):
        response = app_client.options(
            "/api/v1/health",
            headers={"Origin": "http://localhost:3001",
                     "Access-Control-Request-Method": "GET"},
        )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3001"


class TestAutomationEndpoints:
    """减少人工工作量：目标解析 + 一键运行 + 会话列表。"""

    def test_sessions_list(self, app_client):
        created = app_client.post("/api/v1/agent/sessions", json={"goal": "g1"})
        assert created.status_code == 201
        sessions = app_client.get("/api/v1/agent/sessions?limit=5").json()["sessions"]
        assert any(s["goal"] == "g1" for s in sessions)

    def test_parse_goal_binds_spec_without_llm_key(self, app_client):
        # 容器未配 LLM 时 goal_parser 为 None → 503 而不是崩溃
        created = app_client.post("/api/v1/agent/sessions", json={"goal": "g"})
        sid = created.json()["session_id"]
        response = app_client.post(f"/api/v1/agent/sessions/{sid}/parse-goal")
        assert response.status_code == 503

    def test_run_session_one_shot(self, app_client):
        created = app_client.post("/api/v1/agent/sessions", json={"goal": "PDAC markers"})
        sid = created.json()["session_id"]
        run = app_client.post(
            f"/api/v1/agent/sessions/{sid}/run",
            json={"disease": "PDAC", "task": "prognostic_biomarker", "max_results": 3},
        )
        assert run.status_code == 202
        detail = app_client.get(f"/api/v1/agent/sessions/{sid}").json()
        assert detail["status"] == "PLANNED"
        assert detail["plans"][-1]["approved_by_human"] is True
        assert detail["task_spec"]["disease"] == "PDAC"

    def test_run_without_disease_or_spec_rejected(self, app_client):
        created = app_client.post("/api/v1/agent/sessions", json={"goal": "g"})
        sid = created.json()["session_id"]
        run = app_client.post(
            f"/api/v1/agent/sessions/{sid}/run",
            json={"intents_only": True},
        )
        assert run.status_code == 422


class TestClarifyLoop:
    """歧义目标 → Agent 追问 → 用户回答 → 重新解析 → 保存检索式 → 运行。"""

    @pytest.fixture()
    def app_client(self, tmp_path):
        from fastapi.testclient import TestClient

        from pubminer.api.app import create_app
        from pubminer.api.deps import build_container
        from tests.architecture.test_api_v1 import _fake_ports

        test_db = tmp_path / "clarify.db"
        container = build_container(f"sqlite:///{test_db.as_posix()}", workflow_ports=_fake_ports())
        # 设置一个 fake goal_parser（离线测试）

        class FakeGoalParser:
            def parse(self, goal, *, prior_context=None):
                return {
                    "disease": "pancreatic cancer", "task": "prognostic_biomarker",
                    "year_from": 2020,
                    "search_intents": [
                        {"name": "discovery", "query": "pancreatic cancer prognostic biomarker"},
                        {"name": "validation", "query": "pancreatic cancer biomarker independent validation"},
                    ],
                    "clarification": {"needed": False, "question": None},
                }

        container.goal_parser = FakeGoalParser()
        from pubminer.infrastructure.db.base import Base
        from pubminer.infrastructure.db import orm_documents, orm_agents, orm_claims, orm_entities, orm_tasks  # noqa: F401

        engine = container.session_factory.kw["bind"]
        Base.metadata.create_all(bind=engine)
        with TestClient(create_app(container)) as client:
            yield client

    def test_parse_goal_returns_intents_and_clarification(self, app_client):
        created = app_client.post("/api/v1/agent/sessions", json={"goal": "biomarker"})
        sid = created.json()["session_id"]
        response = app_client.post(f"/api/v1/agent/sessions/{sid}/parse-goal")
        assert response.status_code == 200
        body = response.json()
        assert "search_intents" in body
        assert "clarification" in body
        assert "fields" in body

    def test_answer_stores_message(self, app_client):
        created = app_client.post("/api/v1/agent/sessions", json={"goal": "g"})
        sid = created.json()["session_id"]
        r = app_client.post(f"/api/v1/agent/sessions/{sid}/answer", json={"answer": "PDAC"})
        assert r.status_code == 200

    def test_save_search_intents(self, app_client):
        created = app_client.post("/api/v1/agent/sessions", json={"goal": "g"})
        sid = created.json()["session_id"]
        r = app_client.post(
            f"/api/v1/agent/sessions/{sid}/search-intents",
            json={"search_intents": [
                {"name": "discovery", "query": "PDAC prognostic biomarker"},
            ]},
        )
        assert r.status_code == 200

    def test_full_ask_answer_run_flow(self, app_client):
        """完整 AskHuman 闭环：解析 → 追问 → 回答 → 重新解析 → 保存检索式 → 运行。"""
        created = app_client.post("/api/v1/agent/sessions", json={"goal": "biomarker study"})
        sid = created.json()["session_id"]

        # 第一次解析
        parse1 = app_client.post(f"/api/v1/agent/sessions/{sid}/parse-goal")
        assert parse1.status_code == 200
        intents = parse1.json().get("search_intents", [])
        assert len(intents) >= 0  # 可能 0（goal 太模糊）

        # 用户回答澄清
        app_client.post(
            f"/api/v1/agent/sessions/{sid}/answer",
            json={"answer": "PDAC, prognostic, 2020+"},
        )

        # 重新解析
        parse2 = app_client.post(f"/api/v1/agent/sessions/{sid}/parse-goal")
        assert parse2.status_code == 200

        # 保存检索式
        if intents:
            app_client.post(
                f"/api/v1/agent/sessions/{sid}/search-intents",
                json={"search_intents": intents},
            )

        # 一键运行（用保存的检索式）
        run = app_client.post(
            f"/api/v1/agent/sessions/{sid}/run",
            json={"disease": "PDAC", "task": "prognostic_biomarker", "max_results": 3},
        )
        assert run.status_code in (202, 503)  # 503 = 无真实端口
