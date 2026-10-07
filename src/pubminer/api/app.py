"""FastAPI 应用工厂：/api/v1 路由、错误模型、SSE 事件流。"""
from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from pubminer.infrastructure.db.base import session_scope

from pubminer.api import schemas
from pubminer.api.deps import Container
from pubminer.application.ports import LLMError
from pubminer.infrastructure.db.orm_agents import AgentMessageRow as AgentMessageRow_
from pubminer.domain.tasks import TaskStatus
from pubminer.workflows import MiningWorkflow, SearchIntent
from pubminer.integrations.adapters.pubmed_tags import validate_query
from pubminer.workflows.mining import WorkflowFatalError


def create_app(container: Container) -> FastAPI:
    app = FastAPI(title="PubMiner Evidence Agent API", version="v1")

    # webui 默认跑在 localhost:3000/3001；可用 PUBMINER_CORS_ORIGINS 覆盖
    import os

    origins = os.environ.get(
        "PUBMINER_CORS_ORIGINS", "http://localhost:3000,http://localhost:3001"
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------ 错误模型 §10.2

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        payload = {
            "error": {
                "code": _code_for_status(exc.status_code),
                "message": str(exc.detail),
                "retryable": exc.status_code >= 500,
                "details": getattr(exc, "details", {}) or {},
            },
            "request_id": container.next_request_id(),
        }
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL",
                    "message": "internal error; see server logs",
                    "retryable": True,
                    "details": {},
                },
                "request_id": container.next_request_id(),
            },
        )

    # ------------------------------------------------------------ helpers

    def _parse_uuid(value: str, what: str) -> UUID:
        try:
            return UUID(value)
        except ValueError:
            raise HTTPException(404, f"{what} not found")

    def _require_session(session_id: str):
        with session_scope(container.session_factory) as session:
            found = container.session_service(session).load_for_replay(_parse_uuid(session_id, "session"))
            return found.model_dump(mode="json")

    # ------------------------------------------------------------ health

    @app.get("/api/v1/tasks")
    def list_tasks(limit: int = 20) -> schemas.TaskListResponse:
        from sqlalchemy import select

        from pubminer.infrastructure.db.orm_tasks import TaskRow

        with session_scope(container.session_factory) as session:
            rows = session.execute(
                select(TaskRow).order_by(TaskRow.created_at.desc()).limit(min(limit, 100))
            ).scalars().all()
            return schemas.TaskListResponse(
                tasks=[
                    schemas.TaskListItem(
                        task_id=str(r.id),
                        session_id=str(r.session_id) if r.session_id else None,
                        kind=r.kind,
                        status=r.status,
                        created_at=r.created_at.isoformat(),
                    )
                    for r in rows
                ]
            )

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "version": "v1"}

    @app.get("/api/v1/schemas")
    def list_schemas():
        """真实领域清单（schemas/domains/ 目录扫描）。"""
        from pubminer.workflows.domain_schema import discover_domains, load_domain

        domains = []
        for name, path in discover_domains().items():
            try:
                d = load_domain(path)
                domains.append({
                    "name": d.name, "display": d.display,
                    "entity_label": d.entity_label, "default_task": d.default_task,
                    "object_label": d.object_label, "file": path.name,
                })
            except Exception:
                continue
        return {"schemas": domains}

    # ------------------------------------------------------------ agent sessions

    @app.post("/api/v1/agent/sessions", status_code=201, response_model=schemas.CreateSessionResponse)
    def create_session(body: schemas.CreateSessionRequest):
        with session_scope(container.session_factory) as session:
            service = container.session_service(session)
            created = service.create_session(
                schemas.CreateSessionRequest(
                    goal=body.goal, user_id=body.user_id, limits=body.limits
                )
            )
            return schemas.CreateSessionResponse(
                session_id=str(created.id), status=created.status.value, next="ASK_HUMAN"
            )

    @app.post("/api/v1/agent/sessions/{session_id}/messages", status_code=201)
    def post_message(session_id: str, body: schemas.PostMessageRequest):
        with session_scope(container.session_factory) as session:
            service = container.session_service(session)
            message = service.post_message(
                _parse_uuid(session_id, "session"), body.role, body.content, body.kind, body.payload
            )
            return {"message_id": str(message.id), "ok": True}

    @app.post("/api/v1/agent/sessions/{session_id}/task-spec", status_code=200)
    def bind_task_spec(session_id: str, body: schemas.BindTaskSpecRequest):
        with session_scope(container.session_factory) as session:
            service = container.session_service(session)
            try:
                spec = service.bind_task_spec(_parse_uuid(session_id, "session"), body, goal_text=body.disease or "")
            except LookupError as exc:
                raise HTTPException(404, str(exc))
            return {
                "schema_version": spec.schema_version,
                "missing_required_fields": spec.missing_required_fields(),
            }

    @app.post("/api/v1/agent/sessions/{session_id}/plan", status_code=202)
    def submit_plan(session_id: str, body: schemas.SubmitPlanRequest):
        from pubminer.domain.agents import Plan, PlanStep

        with session_scope(container.session_factory) as session:
            service = container.session_service(session)
            current = service.load_for_replay(_parse_uuid(session_id, "session"))
            plan = Plan(
                version=current.current_plan_version + 1,
                rationale=body.rationale,
                steps=[PlanStep.model_validate(s.model_dump()) for s in body.steps],
            )
            service.submit_plan(_parse_uuid(session_id, "session"), plan)
            return {"plan_version": plan.version, "status": "PLANNED"}

    @app.post("/api/v1/agent/sessions/{session_id}/plan/approve", status_code=200)
    def approve_plan(session_id: str, body: schemas.ApprovePlanRequest):
        with session_scope(container.session_factory) as session:
            service = container.session_service(session)
            try:
                service.approve_plan(_parse_uuid(session_id, "session"), body.plan_version)
            except ValueError as exc:
                raise HTTPException(409, str(exc))
            except LookupError as exc:
                raise HTTPException(404, str(exc))
            return {"approved": body.plan_version}

    @app.get("/api/v1/agent/sessions/{session_id}", response_model_exclude_none=True)
    def get_session(session_id: str) -> schemas.SessionResponse:
        try:
            data = _require_session(session_id)
        except (LookupError, ValueError):
            raise HTTPException(404, f"session {session_id} not found")
        data["session_id"] = data.pop("id")
        return data

    @app.post("/api/v1/agent/sessions/{session_id}/actions/pause", status_code=200)
    def pause_session(session_id: str):
        with session_scope(container.session_factory) as session:
            service = container.session_service(session)
            try:
                service.repository.update_status(_parse_uuid(session_id, "session"), "PAUSED")
            except LookupError as exc:
                raise HTTPException(404, str(exc))
            return {"status": "PAUSED"}

    @app.get("/api/v1/agent/sessions/{session_id}/events")
    def session_events(session_id: str, since: int = 0, format: str = "sse", max_events: int = 100) -> schemas.SessionEventsResponse:
        """行动事件流：SSE（默认）或 JSON（format=json，供测试/降级）。"""
        try:
            data = _require_session(session_id)
        except (LookupError, ValueError):
            raise HTTPException(404, f"session {session_id} not found")

        actions = data.get("actions", [])
        events = [
            {
                "seq": index + 1,
                "type": "action",
                "action_id": action["id"],
                "turn": action["turn"],
                "action_type": action["action_type"],
                "tool_name": action.get("tool_name"),
                "status": action["status"],
                "summary": action.get("result_summary", ""),
            }
            for index, action in enumerate(actions)
            if index + 1 > since
        ][:max_events]

        if format == "json":
            return schemas.SessionEventsResponse(events=events, next_since=since + len(events))

        def stream():
            for event in events:
                yield f"id: {event['seq']}\nevent: action\ndata: {json.dumps(event)}\n\n"

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    # ------------------------------------------------------------ mining tasks

    @app.post("/api/v1/tasks", status_code=202)
    def create_task(body: schemas.CreateTaskRequest):
        if container.workflow_ports is None:
            raise HTTPException(503, "workflow ports not configured")
        intents = [
            SearchIntent(
                name=i.get("name", "discovery"),
                query=i.get("query", ""),
                max_results=int(i.get("max_results", 50)),
            )
            for i in body.intents
        ]
        session_id = UUID(body.session_id) if body.session_id else None
        with session_scope(container.session_factory) as session:
            workflow = MiningWorkflow(
                container.workflow_ports,
                document_repo_factory=DocumentRepositoryOf,
                claim_repo_factory=ClaimRepositoryOf,
                entity_repo_factory=EntityRepositoryOf,
                task_repo=container.task_repository(session),
                pipeline_release=container.pipeline_release,
            )
            try:
                task_id = workflow.start(session_id=session_id, intents=intents)
            except WorkflowFatalError as exc:
                raise HTTPException(422, str(exc))
            task = container.task_repository(session).get(task_id)
            return {"task_id": str(task_id), "status": task.status.value if task else "CREATED"}

    @app.get("/api/v1/tasks/{task_id}")
    def get_task(task_id: str) -> schemas.TaskResponse:
        with session_scope(container.session_factory) as session:
            repo = container.task_repository(session)
            task = repo.get(_parse_uuid(task_id, "task"))
            if task is None:
                raise HTTPException(404, f"task {task_id} not found")
            return schemas.TaskResponse(
                task_id=str(task.id),
                session_id=str(task.session_id) if task.session_id else None,
                status=task.status.value,
                steps=[schemas.TaskStepResponse(**step) for step in repo.list_steps(task.id)],
            )

    @app.post("/api/v1/tasks/{task_id}/actions/resume", status_code=202)
    def resume_task(task_id: str):
        if container.workflow_ports is None:
            raise HTTPException(503, "workflow ports not configured")
        with session_scope(container.session_factory) as session:
            workflow = MiningWorkflow(
                container.workflow_ports,
                document_repo_factory=DocumentRepositoryOf,
                claim_repo_factory=ClaimRepositoryOf,
                entity_repo_factory=EntityRepositoryOf,
                task_repo=container.task_repository(session),
                pipeline_release=container.pipeline_release,
            )
            try:
                workflow.resume(_parse_uuid(task_id, "task"))
            except LookupError as exc:
                raise HTTPException(404, str(exc))
            task = container.task_repository(session).get(_parse_uuid(task_id, "task"))
            return {"task_id": task_id, "status": task.status.value}

    @app.post("/api/v1/tasks/{task_id}/actions/cancel", status_code=200)
    def cancel_task(task_id: str):
        with session_scope(container.session_factory) as session:
            repo = container.task_repository(session)
            try:
                repo.update_status(_parse_uuid(task_id, "task"), TaskStatus.CANCELLED)
            except LookupError as exc:
                raise HTTPException(404, str(exc))
            return {"task_id": task_id, "status": "CANCELLED"}

    # ------------------------------------------------------------ claims

    @app.get("/api/v1/claims")
    def list_claims(status: str = "CANDIDATE", limit: int = 50) -> schemas.ClaimsResponse:
        from sqlalchemy import select

        from pubminer.infrastructure.db.orm_claims import ClaimRow

        with session_scope(container.session_factory) as session:
            rows = session.execute(
                select(ClaimRow).where(ClaimRow.status == status).limit(min(limit, 200))
            ).scalars().all()
            claims = []
            for row in rows:
                polarities: dict[str, int] = {}
                for ev in row.evidence_items:
                    polarities[ev.polarity] = polarities.get(ev.polarity, 0) + 1
                claims.append(
                    schemas.ClaimResponse(
                        claim_id=str(row.id),
                        canonical_signature=row.canonical_signature,
                        status=row.status,
                        predicate=row.predicate,
                        direction=row.direction,
                        evidence_count=len(row.evidence_items),
                        polarities=polarities,
                    )
                )
            return schemas.ClaimsResponse(claims=claims)

    # ------------------------------------------------------------ claim evidence（PR-012）

    @app.get("/api/v1/claims/{claim_id}/evidence")
    def get_claim_evidence(claim_id: str) -> schemas.ClaimEvidenceResponse:
        cid = _parse_uuid(claim_id, "claim")
        with session_scope(container.session_factory) as session:
            claim_repo = container.claim_repository(session)
            claim = claim_repo.get(cid)
            if claim is None:
                raise HTTPException(404, f"claim {claim_id} not found")
            evidences = claim_repo.get_evidence(cid)
            items: list[schemas.ClaimEvidenceItem] = []
            from pubminer.infrastructure.db.orm_documents import DocumentVersionRow

            for ev in evidences:
                version_row = session.get(DocumentVersionRow, ev.document_version_id)
                items.append(
                    schemas.ClaimEvidenceItem(
                        evidence_id=str(ev.id),
                        polarity=ev.polarity.value,
                        span=schemas.ClaimEvidenceSpan(
                            document_version_id=str(ev.document_version_id),
                            passage_id=str(ev.passage_id),
                            section_path=ev.span.section_path,
                            start_char=ev.span.start_char,
                            end_char=ev.span.end_char,
                            text=ev.span.text,
                        ),
                        study=ev.study.model_dump(mode="json"),
                        statistics=ev.statistics.model_dump(mode="json") if ev.statistics else None,
                        review_status=ev.review_status,
                        document_id=str(ev.document_id),
                        document_version_id=str(ev.document_version_id),
                        document_title=version_row.title if version_row else "",
                        canonical_text=version_row.canonical_text if version_row else "",
                    )
                )
            return schemas.ClaimEvidenceResponse(
                claim_id=str(cid),
                canonical_signature=claim.canonical_signature,
                evidence=items,
            )

    # ------------------------------------------------------------ 跨论文验证 / 覆盖 / 审核（PR-013）

    @app.get("/api/v1/domains")
    def list_domains() -> schemas.DomainsResponse:
        """领域 schema 清单：图谱图例/分类标签由前端按活跃领域动态生成。"""
        from pubminer.workflows.domain_schema import discover_domains, load_domain

        domains: list[schemas.DomainInfo] = []
        for _name, path in discover_domains().items():
            d = load_domain(path)
            domains.append(
                schemas.DomainInfo(
                    name=d.name,
                    display=d.display,
                    default_task=d.default_task,
                    object_label=d.object_label,
                    entity_types=[schemas.DomainEntityType(key=k, label=v) for k, v in d.entity_types.items()],
                )
            )
        return schemas.DomainsResponse(domains=domains)

    @app.get("/api/v1/documents")
    def list_documents(limit: int = 100, session_id: str | None = None) -> schemas.DocumentsResponse:
        with session_scope(container.session_factory) as session:
            repo = container.document_repository(session)
            return schemas.DocumentsResponse(
                documents=[schemas.DocumentItem(**d) for d in repo.list_documents_with_evidence(
                    limit=limit,
                    session_id=_parse_uuid(session_id, "session_id") if session_id else None,
                )]
            )

    @app.get("/api/v1/documents/{document_id}")
    def get_document(document_id: str) -> schemas.DocumentDetail:
        with session_scope(container.session_factory) as session:
            repo = container.document_repository(session)
            detail = repo.get_document_detail(_parse_uuid(document_id, "document"))
            if detail is None:
                raise HTTPException(404, f"document {document_id} not found")
            return schemas.DocumentDetail(**detail)

    @app.get("/api/v1/verification/aggregations")
    def verification_aggregations(limit: int = 200, session_id: str | None = None) -> schemas.AggregationsResponse:
        from pubminer.workflows.verification import CrossPaperVerifier

        with session_scope(container.session_factory) as session:
            claim_repo = container.claim_repository(session)
            entity_repo = container.entity_repository(session)
            verifier = CrossPaperVerifier(claim_repo)
            aggregations = verifier.aggregate(
                session, limit=limit,
                session_id=_parse_uuid(session_id, "session_id") if session_id else None,
            )
            # 批量解析 subject 实体名（签名中只有本体编号，图谱/卡片需要可读名称）
            items: list[schemas.AggregationItem] = []
            for agg in aggregations:
                payload = agg.to_dict()
                claim = claim_repo.get(agg.claim_id)
                if claim is not None and claim.subject_entity_id:
                    entity = entity_repo.get(claim.subject_entity_id)
                    if entity is not None:
                        payload["subject_name"] = entity.canonical_name
                        etype = getattr(entity.type, "value", entity.type)
                        payload["subject_type"] = str(etype).upper()
                items.append(schemas.AggregationItem(**payload))
            return schemas.AggregationsResponse(aggregations=items)

    @app.get("/api/v1/agent/sessions/{session_id}/coverage")
    def session_coverage(session_id: str) -> schemas.CoverageResponse:
        from pubminer.workflows.verification import CrossPaperVerifier

        sid = _parse_uuid(session_id, "session")
        with session_scope(container.session_factory) as session:
            verifier = CrossPaperVerifier(container.claim_repository(session))
            snapshot = verifier.coverage_snapshot(session, sid)
            return schemas.CoverageResponse(
                session_id=str(snapshot.session_id),
                questions=[q.model_dump() for q in snapshot.questions],
                support_count=snapshot.support_count,
                contradict_count=snapshot.contradict_count,
                no_effect_count=snapshot.no_effect_count,
                independent_validation_found=snapshot.independent_validation_found,
                unresolved_gaps=snapshot.unresolved_gaps,
                recommended_next_action=snapshot.recommended_next_action,
            )

    @app.get("/api/v1/reviews/queue")
    def review_queue(session_id: str | None = None) -> schemas.ReviewQueueResponse:
        from collections import Counter

        with session_scope(container.session_factory) as session:
            claim_repo = container.claim_repository(session)
            from pubminer.workflows.verification import CrossPaperVerifier, claim_cluster_key

            verifier = CrossPaperVerifier(claim_repo)
            # 簇成员清单：整组批量复核用（同簇 claim 的 id/version/签名）
            members_map: dict[tuple, list[dict]] = {}
            for c in claim_repo.list_claims(limit=1000):
                members_map.setdefault(claim_cluster_key(c), []).append(
                    {"claim_id": str(c.id), "version": c.version, "signature": c.canonical_signature}
                )
            items: list[schemas.ReviewQueueItem] = []
            for agg in verifier.aggregate(
                session, limit=1000,
                session_id=_parse_uuid(session_id, "session_id") if session_id else None,
            ):
                if agg.status not in ("CANDIDATE", "REVIEWED"):
                    continue
                claim = claim_repo.get(agg.claim_id)
                assert claim is not None
                key = claim_cluster_key(claim)
                evidences = claim_repo.get_evidence(agg.claim_id)
                polarities = Counter(e.polarity.value for e in evidences)
                priority = "conflict" if agg.has_conflict else (
                    "needs_review" if agg.needs_review else "normal"
                )
                items.append(
                    schemas.ReviewQueueItem(
                        claim_id=str(agg.claim_id),
                        canonical_signature=agg.canonical_signature,
                        status=agg.status,
                        version=claim.version,
                        priority=priority,
                        reasons=agg.reasons,
                        evidence_count=len(evidences),
                        polarities=dict(polarities),
                        cluster_key="|".join(key),
                        member_count=agg.member_count,
                        members=members_map.get(key, []),
                    )
                )
            # 冲突 > 需复核 > 普通
            order = {"conflict": 0, "needs_review": 1, "normal": 2}
            items.sort(key=lambda i: order[i.priority])
            return schemas.ReviewQueueResponse(items=items)

    @app.post("/api/v1/reviews/decision", status_code=201)
    def submit_review_decision(body: schemas.ReviewDecisionRequest) -> schemas.ReviewDecisionResponse:
        from pubminer.domain.claims import ClaimStatus
        from pubminer.domain.reviews import Review, ReviewDecision, ReviewTarget, ReviewTargetType
        from pubminer.infrastructure.db.repositories.reviews import ReviewRepository

        decision = ReviewDecision(body.decision)
        with session_scope(container.session_factory) as session:
            claim_repo = container.claim_repository(session)
            review_repo = ReviewRepository(session)
            claim = claim_repo.get(_parse_uuid(body.claim_id, "claim"))
            if claim is None:
                raise HTTPException(404, f"claim {body.claim_id} not found")
            if claim.status not in (ClaimStatus.CANDIDATE, ClaimStatus.REVIEWED):
                raise HTTPException(409, f"claim in status {claim.status.value} is not reviewable")
            if claim.version != body.expected_version:
                raise HTTPException(409, "stale review: claim version changed (optimistic lock)")

            before = claim.model_dump(mode="json", exclude={"id", "created_at", "updated_at"})

            if decision == ReviewDecision.ACCEPT:
                claim.transition(ClaimStatus.REVIEWED, actor=body.reviewer_id)
            elif decision == ReviewDecision.REJECT:
                claim.transition(ClaimStatus.REJECTED, actor=body.reviewer_id)
            elif decision == ReviewDecision.EDIT_ACCEPT:
                from pubminer.domain.claims import Direction, Predicate

                for field_name, value in body.revision.items():
                    if field_name == "direction" and value:
                        claim.direction = Direction(str(value).upper())
                    elif field_name == "object_value" and value:
                        claim.object_value = str(value)
                    elif field_name == "predicate" and value:
                        claim.predicate = Predicate(str(value).upper())
                    # 其他字段暂不开放修改；identifier 类修改必须走 resolver（ADR-006）
                claim.version += 1
                claim.transition(ClaimStatus.REVIEWED, actor=body.reviewer_id)
            elif decision == ReviewDecision.NEEDS_REVIEW:
                pass  # 保持 CANDIDATE，仅记录审核轨迹

            # 把决定写回 DB（领域对象不会自动同步 ORM 行）
            from pubminer.infrastructure.db.orm_claims import ClaimRow

            row = session.get(ClaimRow, claim.id)
            if row is None:
                raise HTTPException(404, f"claim {body.claim_id} not found")
            row.status = claim.status.value
            row.version = claim.version
            row.direction = claim.direction.value
            row.predicate = claim.predicate.value
            row.object_value = claim.object_value
            row.canonical_signature = claim.canonical_signature
            row.updated_at = claim.updated_at
            session.flush()

            review = review_repo.add(
                Review(
                    target=ReviewTarget(type=ReviewTargetType.CLAIM, id=claim.id),
                    decision=decision,
                    reviewer_id=body.reviewer_id,
                    before=before,
                    after=body.revision or None,
                    reason=body.reason,
                )
            )
            return schemas.ReviewDecisionResponse(
                ok=True,
                claim_status=claim.status.value,
                claim_version=claim.version,
                review_id=str(review.id),
            )

    @app.post("/api/v1/schemas/generate")
    def generate_schema(body: schemas.GenerateSchemaRequest) -> schemas.SchemaGeneratedResponse:
        """自然语言描述 → LLM 生成领域定义 + 抽取字段（强校验）。"""
        if container.schema_generator is None:
            raise HTTPException(503, "schema generator requires an LLM key (PUBMINER_LLM_API_KEY)")
        try:
            domain, extraction_fields = container.schema_generator.generate(body.description)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return schemas.SchemaGeneratedResponse(domain=domain, extraction_fields=extraction_fields)

    @app.post("/api/v1/schemas/calibrate")
    def calibrate_schema(body: schemas.CalibrateSchemaRequest) -> schemas.SchemaGeneratedResponse:
        """用户粘贴的领域 JSON → LLM 解析校准补齐 → 强校验格式。"""
        if container.schema_generator is None:
            raise HTTPException(503, "schema generator requires an LLM key (PUBMINER_LLM_API_KEY)")
        try:
            domain, extraction_fields = container.schema_generator.calibrate(body.domain)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return schemas.SchemaGeneratedResponse(domain=domain, extraction_fields=extraction_fields)

    @app.post("/api/v1/schemas/save")
    def save_schema(body: schemas.SaveSchemaRequest) -> dict:
        """校验后写入 schemas/domains/{name}.json；抽取字段（若有）一并保存并关联。"""
        from pubminer.workflows.domain_schema import DEFAULT_DOMAINS_DIR, load_domain
        from pubminer.workflows.schema_validation import DomainSchemaModel, ExtractionFieldsModel

        try:
            model = DomainSchemaModel(**body.domain)
        except ValidationError as exc:
            raise HTTPException(422, f"领域定义校验失败：{exc}")
        target_dir = Path(body.target_dir) if body.target_dir else DEFAULT_DOMAINS_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{model.name}.json"
        payload = dict(body.domain)
        if payload.get("object_label") is None:
            payload.pop("object_label", None)
        # 抽取字段（可选）：保存到 schemas/extraction_fields/ 并自动关联到领域
        ef = body.extraction_fields
        if ef and ef.get("name"):
            ExtractionFieldsModel(**ef)
            ef_dir = target_dir.parent / "extraction_fields"
            ef_dir.mkdir(parents=True, exist_ok=True)
            (ef_dir / f"{ef['name']}.json").write_text(
                json.dumps(ef, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            payload["extraction_fields_schema"] = ef["name"]
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        load_domain(target)  # 写入后回读校验
        return {"ok": True, "name": model.name, "file": str(target)}

    @app.delete("/api/v1/agent/sessions/{session_id}")
    def delete_session(session_id: str) -> dict:
        """删除课题及其全部数据：命题/证据/审核记录/任务/步骤/消息/会话。

        documents 为全局去重语料，不随课题删除（重跑可复用水合结果）。
        """
        from sqlalchemy import delete as sa_delete, select

        from pubminer.domain.reviews import ReviewTargetType
        from pubminer.infrastructure.db.orm_agents import AgentMessageRow, AgentSessionRow
        from pubminer.infrastructure.db.orm_claims import ClaimRow, EvidenceRow
        from pubminer.infrastructure.db.orm_reviews import ReviewRow
        from pubminer.infrastructure.db.orm_tasks import RunStepRow, TaskRow

        sid = _parse_uuid(session_id, "session")
        with session_scope(container.session_factory) as session:
            claim_ids = select(ClaimRow.id).where(ClaimRow.session_id == sid)
            task_ids = select(TaskRow.id).where(TaskRow.session_id == sid)
            evidence_n = session.execute(
                sa_delete(EvidenceRow).where(EvidenceRow.claim_id.in_(claim_ids))
            ).rowcount
            review_n = session.execute(
                sa_delete(ReviewRow).where(
                    ReviewRow.target_type == ReviewTargetType.CLAIM.value,
                    ReviewRow.target_id.in_(claim_ids),
                )
            ).rowcount
            claims_n = session.execute(sa_delete(ClaimRow).where(ClaimRow.session_id == sid)).rowcount
            steps_n = session.execute(sa_delete(RunStepRow).where(RunStepRow.task_id.in_(task_ids))).rowcount
            tasks_n = session.execute(sa_delete(TaskRow).where(TaskRow.session_id == sid)).rowcount
            msgs_n = session.execute(sa_delete(AgentMessageRow).where(AgentMessageRow.session_id == sid)).rowcount
            sess_row = session.get(AgentSessionRow, sid)
            if sess_row is None:
                raise HTTPException(404, f"session {session_id} not found")
            session.delete(sess_row)
            return {
                "ok": True,
                "deleted": {"claims": claims_n, "evidence": evidence_n, "reviews": review_n,
                            "tasks": tasks_n, "run_steps": steps_n, "messages": msgs_n},
            }

    @app.get("/api/v1/agent/sessions")
    def list_sessions(limit: int = 20) -> schemas.SessionListResponse:
        from sqlalchemy import select

        from pubminer.infrastructure.db.orm_agents import AgentSessionRow

        with session_scope(container.session_factory) as session:
            rows = session.execute(
                select(AgentSessionRow)
                .order_by(AgentSessionRow.created_at.desc())
                .limit(min(limit, 100))
            ).scalars().all()
            return schemas.SessionListResponse(
                sessions=[
                    schemas.SessionListItem(
                        session_id=str(r.id),
                        goal=r.goal,
                        status=r.status,
                        created_at=r.created_at.isoformat(),
                    )
                    for r in rows
                ]
            )

    @app.post("/api/v1/agent/sessions/{session_id}/parse-goal")
    def parse_goal(session_id: str) -> schemas.ParseGoalResponse:
        """LLM 解析自然语言目标：提取字段 + 生成检索式 + 歧义检测。"""
        if container.goal_parser is None:
            raise HTTPException(503, "goal parser requires an LLM key (PUBMINER_LLM_API_KEY)")
        sid = _parse_uuid(session_id, "session")
        with session_scope(container.session_factory) as session:
            service = container.session_service(session)
            current = service.load_for_replay(sid)

            # 收集先验上下文（此前的澄清问答）
            prior = "\n".join(
                f"Q: {m.content}" if m.role == "agent" else f"A: {m.content}"
                for m in session.query(AgentMessageRow_)
                .filter(AgentMessageRow_.session_id == sid)
                .order_by(AgentMessageRow_.created_at)
                .all()
            ) or None

            try:
                result = container.goal_parser.parse(current.goal, prior_context=prior)
            except LLMError as exc:
                raise HTTPException(502, f"goal parse failed: {exc}")

            # 绑定 TaskSpec 字段
            spec_fields = {k: v for k, v in result.items()
                           if k in ("disease", "task", "year_from", "year_to", "validation_requirement")}
            spec = service.bind_task_spec(sid, schemas.BindTaskSpecRequest(**spec_fields), goal_text=current.goal)

            # 存储检索式
            intents = result.get("search_intents", [])
            if intents:
                service.post_message(sid, "agent", json.dumps(intents), kind="search_intents")

            clarification = result.get("clarification", {})
            needs_clarification = clarification.get("needed", False)
            if needs_clarification and clarification.get("question"):
                service.post_message(sid, "agent", clarification["question"], kind="clarification")

            return schemas.ParseGoalResponse(
                bound=bool(spec_fields),
                fields=spec_fields,
                search_intents=[schemas.SearchIntentItem(**si) for si in intents],
                clarification=clarification,
                missing_required_fields=spec.missing_required_fields() if spec else [],
            )

    @app.post("/api/v1/agent/sessions/{session_id}/answer")
    def answer_clarification(session_id: str, body: schemas.AnswerRequest):
        """用户回答澄清问题：存储回答。前端收到 200 后重新调 parse-goal。"""
        sid = _parse_uuid(session_id, "session")
        with session_scope(container.session_factory) as session:
            service = container.session_service(session)
            service.post_message(sid, "user", body.answer, kind="clarification_answer")
            # 触发前端重新调 parse-goal（后端只存消息）
            return {"ok": True, "hint": "call parse-goal again to re-parse with new context"}

    @app.post("/api/v1/agent/sessions/{session_id}/search-intents")
    def save_search_intents(session_id: str, body: schemas.SaveSearchIntentsRequest):
        """保存最终检索式（用户确认或编辑后）。"""
        sid = _parse_uuid(session_id, "session")
        with session_scope(container.session_factory) as session:
            service = container.session_service(session)
            service.post_message(
                sid, "user",
                json.dumps([si.model_dump() for si in body.search_intents]),
                kind="search_intents_final",
            )
            return {"ok": True, "count": len(body.search_intents)}

    @app.post("/api/v1/agent/sessions/{session_id}/qa")
    def session_qa(session_id: str, body: schemas.QaRequest) -> schemas.QaResponse:
        """RAG 式证据问答：混合检索（embedding + 关键词）→ 证据片段 → LLM 生成。

        LLM 或 embedding 不可用时降级为模板拼装，接口始终可用。
        """
        sid = _parse_uuid(session_id, "session")
        if container.embedding_service is None:
            raise HTTPException(503, "embedding service not configured (PUBMINER_EMBEDDING_MODEL)")
        from pubminer.workflows.qa import EvidenceQA

        with session_scope(container.session_factory) as session:
            qa = EvidenceQA(
                session=session,
                claim_repo=container.claim_repository(session),
                entity_repo=container.entity_repository(session),
                embedding_service=container.embedding_service,
                llm=container.llm,
                prompt_registry=container.prompt_registry,
                session_id=sid,
            )
            result = qa.answer(body.question)
            return schemas.QaResponse(
                answer=result.answer,
                generated_by=result.generated_by,
                citations=[schemas.QaCitationItem(**vars(c)) for c in result.citations],
                matched_claims=result.matched_claims,
            )

    @app.post("/api/v1/agent/sessions/{session_id}/run", status_code=202)
    def run_session(session_id: str, body: schemas.RunSessionRequest) -> schemas.RunSessionResponse:
        """一键运行：绑定约束（可选）→ 生成并批准计划 → 启动挖掘管线。"""
        from pubminer.domain.agents import Plan, PlanStep

        if container.workflow_ports is None:
            raise HTTPException(503, "workflow ports not configured")
        sid = _parse_uuid(session_id, "session")
        with session_scope(container.session_factory) as session:
            service = container.session_service(session)
            current = service.load_for_replay(sid)

            if body.disease:
                service.bind_task_spec(
                    sid,
                    schemas.BindTaskSpecRequest(
                        disease=body.disease, task=body.task, year_from=body.year_from
                    ),
                    goal_text=current.goal,
                )
            elif current.task_spec is None:
                raise HTTPException(
                    422, "no TaskSpec bound; provide disease via request body or bind first"
                )

            plan = service.submit_plan(
                sid,
                Plan(
                    version=current.current_plan_version + 1,
                    rationale="auto: discovery search -> extract -> verify",
                    steps=[
                        PlanStep(id="s1", action_type="SEARCH"),
                        PlanStep(id="s2", action_type="EXTRACT"),
                    ],
                ),
            )
            service.approve_plan(sid, plan.version)

            disease = current.task_spec.disease if current.task_spec else body.disease
            task_word = current.task_spec.task if current.task_spec else body.task
            query = f"{disease or ''} {task_word or ''} biomarker".strip()
            query, _stripped = validate_query(query)
            screen_criteria = body.screen_criteria or (
                f"{disease or 'the target disease'} / {task_word or 'biomarker'} / "
                "independent cohort validation preferred"
            )

            workflow = MiningWorkflow(
                container.workflow_ports,
                document_repo_factory=DocumentRepositoryOf,
                claim_repo_factory=ClaimRepositoryOf,
                entity_repo_factory=EntityRepositoryOf,
                task_repo=container.task_repository(session),
                pipeline_release=container.pipeline_release,
            )
            try:
                task_id = workflow.start(
                    session_id=sid,
                    intents=[SearchIntent(name="discovery", query=query, max_results=body.max_results)],
                    screen_criteria=screen_criteria,
                    domain=body.domain,
                )
            except WorkflowFatalError as exc:
                raise HTTPException(422, str(exc))
            task = container.task_repository(session).get(task_id)
            return schemas.RunSessionResponse(
                task_id=str(task_id), status=task.status.value if task else "CREATED",
                plan_version=plan.version,
            )

    @app.get("/api/v1/export/cbd")
    def export_cbd_format(status: str = "APPROVED", limit: int = 200):
        """导出 CBD 格式（Colorectal Cancer Biomarker Database 兼容）。"""
        from sqlalchemy import select

        from pubminer.infrastructure.db.orm_claims import ClaimRow, EvidenceRow
        with session_scope(container.session_factory) as session:
            rows = session.execute(
                select(ClaimRow).where(ClaimRow.status == status).limit(min(limit, 500))
            ).scalars().all()
            items = []
            for row in rows:
                evidence_list = session.execute(
                    select(EvidenceRow).where(EvidenceRow.claim_id == row.id)
                ).scalars().all()
                for ev in evidence_list:
                    stats = ev.statistics or {}
                    items.append({
                        "biomarker": _extract_biomarker_name(row.canonical_signature),
                        "category": ev.study.get("design", "unknown") if ev.study else "unknown",
                        "application": _predicate_to_application(row.predicate),
                        "description": ev.span_text[:500],
                        "conclusion": row.direction + " expression associated with outcome",
                        "statistics": f"{stats.get('effect_measure', '')} {stats.get('effect_value', '')}, p {stats.get('p_value', '')}".strip(),
                        "pmid": int(ev.document_id) if str(ev.document_id).isdigit() else None,
                        "location": "Colorectal",
                        "evidence_source": ev.study.get("evidence_source", "abstract") if ev.study else "abstract",
                        "effect_measure": stats.get("effect_measure"),
                        "effect_value": stats.get("effect_value"),
                        "p_value": stats.get("p_value"),
                        "confidence_interval": stats.get("confidence_interval"),
                        "independent_validation": ev.study.get("independent_validation", False) if ev.study else False,
                        "signature": row.canonical_signature,
                        "claim_id": str(row.id),
                        "evidence_id": str(ev.id),
                    })
            return {"total": len(items), "data": items}

    def _extract_biomarker_name(signature: str) -> str:
        """从 canonical signature 提取 biomarker 名（第一段 | 前部分）。"""
        return signature.split(" | ")[0] if " | " in signature else signature

    def _predicate_to_application(predicate: str) -> str:
        return {
            "PROGNOSTIC": "Prognosis",
            "DIAGNOSTIC": "Diagnosis",
            "PREDICTIVE": "Prediction",
            "THERAPEUTIC": "Treatment",
        }.get(predicate, predicate)

    return app

def DocumentRepositoryOf(session):
    from pubminer.infrastructure.db.repositories.documents import DocumentRepository

    return DocumentRepository(session)


def ClaimRepositoryOf(session):
    from pubminer.infrastructure.db.repositories.claims import ClaimRepository

    return ClaimRepository(session)


def EntityRepositoryOf(session):
    from pubminer.infrastructure.db.repositories.entities import EntityRepository

    return EntityRepository(session)


def _code_for_status(status: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "PERMISSION_DENIED",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "SCHEMA_UNSATISFIABLE",
        429: "RATE_LIMITED",
        503: "SOURCE_UNAVAILABLE",
    }.get(status, "INTERNAL" if status >= 500 else "BAD_REQUEST")
