"""MiningWorkflow：SEARCH→HYDRATE→SCREEN→EXTRACT→NORMALIZE→VERIFY→AGGREGATE 竖切。

确定性状态机（ADR-005）：每步输入输出落库（run_steps.output_summary），
失败标记 FAILED_RETRYABLE 可从失败步恢复（resume）；不依赖 Agent 决策。
"""
from __future__ import annotations

import logging
from uuid import UUID, uuid4

from pubminer.domain.claims import (
    Claim,
    ClaimContext,
    Direction,
    Predicate,
)
from pubminer.domain.documents import Document
from pubminer.domain.entities import Entity, EntityAlias, EntityIdentifier, EntityType, IdentifierSource
from pubminer.domain.evidence import Evidence, EvidencePolarity, StudyAttributes
from pubminer.domain.screening import ScreeningLabel
from pubminer.domain.tasks import Task, TaskStatus
from pubminer.infrastructure.db.repositories.entities import EntityRepository
from pubminer.infrastructure.db.repositories.workflow import TaskRepository
from pubminer.workflows.ports import HydratedDocument, MiningPorts, SearchIntent

logger = logging.getLogger("pubminer.workflow")

_STEP_SEQUENCE = ["SEARCH", "HYDRATE", "SCREEN", "EXTRACT", "NORMALIZE", "VERIFY", "AGGREGATE"]
_STATUS_BY_STEP = {
    "SEARCH": TaskStatus.SEARCHING,
    "HYDRATE": TaskStatus.SEARCHING,
    "SCREEN": TaskStatus.SCREENING,
    "EXTRACT": TaskStatus.EXTRACTING,
    "NORMALIZE": TaskStatus.NORMALIZING,
    "VERIFY": TaskStatus.VERIFYING,
    "AGGREGATE": TaskStatus.REVIEW_READY,
}

_ROLE_TO_PREDICATE = {
    "prognostic": Predicate.PROGNOSTIC,
    "diagnostic": Predicate.DIAGNOSTIC,
    "predictive": Predicate.PREDICTIVE,
}


class WorkflowStepError(RuntimeError):
    """可重试的步骤失败（来源瞬断、限流等）。"""

    retryable = True


class WorkflowFatalError(RuntimeError):
    """不可恢复的步骤失败（schema 无法满足等）。"""

    retryable = False


class MiningWorkflow:
    """对一篇查询的最小竖切：意图 → grounded candidate claims。"""

    def __init__(
        self,
        ports: MiningPorts,
        *,
        document_repo_factory,
        claim_repo_factory,
        entity_repo_factory,
        task_repo: TaskRepository,
        pipeline_release: str = "mvp-0.1:fake",
        max_step_attempts: int = 2,
    ) -> None:
        """
        repo_factory(session) -> repository；由 API/worker 装配层注入。
        """
        self.ports = ports
        self.document_repo_factory = document_repo_factory
        self.claim_repo_factory = claim_repo_factory
        self.entity_repo_factory = entity_repo_factory
        self.task_repo = task_repo
        self.pipeline_release = pipeline_release
        self.max_step_attempts = max_step_attempts

    # ------------------------------------------------------------------ entry

    def start(
        self,
        *,
        session_id: UUID | None,
        intents: list[SearchIntent],
        task_id: UUID | None = None,
        screen_criteria: str | None = None,
    ) -> UUID:
        """创建任务并立即执行；返回 task_id。"""
        task = Task(
            id=task_id or uuid4(),
            session_id=session_id,
            kind="mining",
            request={
                "intents": [i.__dict__ for i in intents],
                "screen_criteria": screen_criteria,
            },
        )
        self.task_repo.create(task)
        return self._execute(task, resume_from=0)

    def resume(self, task_id: UUID) -> UUID:
        """从最后一个未成功步骤恢复。"""
        task = self.task_repo.get(task_id)
        if task is None:
            raise LookupError(f"task {task_id} not found")
        failed_index = self.task_repo.first_failed_step_index(task_id)
        return self._execute(task, resume_from=max(failed_index, 0))

    # ------------------------------------------------------------------ engine

    def _execute(self, task: Task, *, resume_from: int) -> UUID:
        state: dict = {}
        for index, step_name in enumerate(_STEP_SEQUENCE):
            if index < resume_from:
                output = self.task_repo.step_output(task.id, index)
                if output is not None:
                    state.update(output)
                continue

            self.task_repo.set_step(task.id, index, step_name, "RUNNING")
            self.task_repo.update_status(task.id, _STATUS_BY_STEP[step_name])
            try:
                output = self._run_step(step_name, state, task)
            except WorkflowFatalError as exc:
                self.task_repo.fail_step(task.id, index, str(exc), retryable=False)
                self.task_repo.update_status(task.id, TaskStatus.FAILED)
                raise
            except Exception as exc:
                logger.warning("step %s failed: %s", step_name, exc)
                self.task_repo.fail_step(task.id, index, str(exc), retryable=True)
                self.task_repo.update_status(task.id, TaskStatus.FAILED)
                return task.id  # 可恢复失败：保持 task 可 resume

            self.task_repo.succeed_step(task.id, index, output)
            state.update(output)

        self.task_repo.update_status(task.id, TaskStatus.REVIEW_READY)
        return task.id

    def _run_step(self, step_name: str, state: dict, task: Task) -> dict:
        handler = getattr(self, f"_step_{step_name.lower()}")
        return handler(state, task)

    # ------------------------------------------------------------------ steps

    def _step_search(self, state: dict, task: Task) -> dict:
        intents = [
            SearchIntent(**i) if isinstance(i, dict) else i
            for i in task.request.get("intents", [])
        ]
        pmids: list[str] = list(state.get("pmids", []))
        for intent in intents:
            try:
                records = self.ports.search.search(intent)
            except Exception as exc:
                raise WorkflowStepError(f"search failed for intent {intent.name}: {exc}") from exc
            for record in records:
                pmid = str(record.get("pmid", "")).strip()
                if pmid and pmid not in pmids:
                    pmids.append(pmid)
        return {"pmids": pmids}

    def _step_hydrate(self, state: dict, task: Task) -> dict:
        """水合即落库：document/version/passages 持久化，保证后续 evidence FK 有效。"""
        doc_repo = self.document_repo_factory(self.task_repo.session)
        hydrated: list[dict] = list(state.get("hydrated", []))
        known = {h["pmid"] for h in hydrated}
        for pmid in state.get("pmids", []):
            if pmid in known:
                continue
            try:
                doc = self.ports.hydrate.hydrate(pmid)
            except Exception as exc:
                raise WorkflowStepError(f"hydrate failed for {pmid}: {exc}") from exc
            if doc is None:
                continue
            stored = doc_repo.upsert_document(doc.document)
            version_id = doc_repo.get_or_add_version(stored.id, doc.version, doc.section_spans)
            version_data = doc.version.model_dump(mode="json")
            version_data["id"] = str(version_id)
            version_data["document_id"] = str(stored.id)
            document_data = stored.model_dump(mode="json")
            hydrated.append(
                {
                    "pmid": pmid,
                    "document": document_data,
                    "version": version_data,
                    "section_spans": doc.section_spans,
                    "fulltext_available": doc.fulltext_available,
                }
            )
        return {"hydrated": hydrated}

    def _step_screen(self, state: dict, task: Task) -> dict:
        criteria = task.request.get("screen_criteria")
        decisions: list[dict] = []
        for item in state.get("hydrated", []):
            document = Document.model_validate(item["document"])
            try:
                decision = self.ports.screen.screen(document, criteria)
            except Exception as exc:
                raise WorkflowStepError(f"screen failed for {item['pmid']}: {exc}") from exc
            decisions.append(decision.model_dump(mode="json"))
        return {"decisions": decisions}

    def _step_extract(self, state: dict, task: Task) -> dict:
        relevant = {
            d["document_id"]
            for d in state.get("decisions", [])
            if d["label"] in (ScreeningLabel.RELEVANT.value, ScreeningLabel.UNCERTAIN.value)
        }
        extractions: list[dict] = []
        for item in state.get("hydrated", []):
            if str(item["document"]["id"]) not in relevant:
                continue
            hydrated = HydratedDocument(
                document=Document.model_validate(item["document"]),
                version=item["version"],
                section_spans=item["section_spans"],
                fulltext_available=item["fulltext_available"],
            )
            try:
                evidence_items = self.ports.extract.extract(hydrated)
            except Exception as exc:
                raise WorkflowStepError(f"extract failed for {item['pmid']}: {exc}") from exc
            for evidence in evidence_items:
                extractions.append(evidence.model_dump(mode="json"))
        return {"extractions": extractions}

    def _step_normalize(self, state: dict, task: Task) -> dict:
        resolutions: list[dict] = []
        cache: dict[str, dict] = {}
        for extraction in state.get("extractions", []):
            mention = extraction["biomarker_mention"]
            if mention not in cache:
                try:
                    candidates, needs_review = self.ports.normalize.resolve(mention, "GENE")
                except Exception as exc:
                    raise WorkflowStepError(f"normalize failed for {mention}: {exc}") from exc
                cache[mention] = {
                    "mention": mention,
                    "candidates": [c.__dict__ for c in candidates],
                    "needs_review": needs_review,
                }
            resolutions.append(dict(cache[mention]))
        return {"resolutions": resolutions}

    def _step_verify(self, state: dict, task: Task) -> dict:
        verified: list[dict] = []
        for extraction in state.get("extractions", []):
            evidence = _extraction_model(extraction)
            signature = _provisional_signature(evidence, state)
            try:
                result = self.ports.verify.verify(signature, evidence)
            except Exception as exc:
                raise WorkflowStepError(f"verify failed: {exc}") from exc
            verified.append(
                {
                    "biomarker_mention": extraction["biomarker_mention"],
                    "polarity": result.polarity.value,
                    "statistically_significant": result.statistically_significant,
                    "independent_validation": result.independent_validation,
                    "needs_human_review": result.needs_human_review,
                    "reasons": result.reasons,
                }
            )
        return {"verified": verified}

    def _step_aggregate(self, state: dict, task: Task) -> dict:
        """按 canonical signature 聚类并落库 CANDIDATE claims + evidence。"""
        created: list[dict] = []
        claims_repo = self.claim_repo_factory(self.task_repo.session)
        entity_repo = self.entity_repo_factory(self.task_repo.session)
        doc_repo = self.document_repo_factory(self.task_repo.session)

        clusters: dict[str, list[dict]] = {}
        for extraction in state.get("extractions", []):
            evidence = _extraction_model(extraction)
            resolution = self._resolution_for(state, extraction["biomarker_mention"])
            signature = _provisional_signature(evidence, state, resolution)
            clusters.setdefault(signature, []).append((extraction, resolution))

        for signature, members in clusters.items():
            first_extraction, first_resolution = members[0]
            evidence_model = _extraction_model(first_extraction)
            subject_entity = self._ensure_entity(entity_repo, first_resolution, evidence_model)
            polarity = self._polarity_for(state, first_extraction["biomarker_mention"])
            claim = self._build_claim(signature, subject_entity, evidence_model, state)
            evidence_rows = []
            for extraction, resolution in members:
                ev = _extraction_model(extraction)
                span = ev.evidence_span
                pmid = self._pmid_for(state, span)
                hydrated_item = self._hydrated_for_pmid(state, pmid)
                domain_evidence = Evidence(
                    claim_id=claim.id,
                    document_id=UUID(hydrated_item["document"]["id"]),
                    document_version_id=span.document_version_id,
                    passage_id=span.passage_id,
                    span=span,
                    polarity=polarity,
                    study=StudyAttributes(
                        design=ev.study_design,
                        independent_validation=self._independent(state, ev.biomarker_mention),
                    ),
                    statistics=ev.statistics,
                )
                evidence_rows.append(domain_evidence)
            stored = claims_repo.create_candidate_claim(claim, evidence_rows)
            created.append(
                {
                    "claim_id": str(stored.id),
                    "signature": stored.canonical_signature,
                    "evidence_count": len(members),
                }
            )
        return {"claims": created}

    # ------------------------------------------------------------------ helpers

    def _resolution_for(self, state: dict, mention: str) -> dict | None:
        for resolution in state.get("resolutions", []):
            if resolution["mention"] == mention:
                return resolution
        return None

    def _polarity_for(self, state: dict, mention: str) -> EvidencePolarity:
        for item in state.get("verified", []):
            if item["biomarker_mention"] == mention:
                return EvidencePolarity(item["polarity"])
        return EvidencePolarity.UNCERTAIN

    def _independent(self, state: dict, mention: str) -> bool | None:
        for item in state.get("verified", []):
            if item["biomarker_mention"] == mention:
                return item.get("independent_validation")
        return None

    def _hydrated_for_pmid(self, state: dict, pmid: str) -> dict:
        for item in state.get("hydrated", []):
            if item["pmid"] == pmid:
                return item
        raise WorkflowFatalError(f"evidence span without hydrated document (pmid={pmid})")

    def _pmid_for(self, state: dict, span) -> str:
        target = str(span.document_version_id)
        for item in state.get("hydrated", []):
            if str(item["version"]["id"]) == target:
                return item["pmid"]
        raise WorkflowFatalError("no hydrated document for evidence span")

    def _ensure_entity(self, entity_repo: EntityRepository, resolution: dict | None, evidence) -> Entity:
        """把 resolver 的 top 候选落成实体行；无 resolver 候选 → 致命错误（禁止猜 ID）。"""
        if not resolution or not resolution.get("candidates"):
            raise WorkflowFatalError("no resolver candidates; refusing to invent identifier (ADR-006)")
        top = resolution["candidates"][0]
        identifier = top.get("identifier")
        if not identifier or ":" not in identifier:
            raise WorkflowFatalError("resolver candidate without identifier")
        namespace, value = identifier.split(":", 1)
        ontology_version = "mvp-2026"
        existing = entity_repo.find_by_identifier(namespace, value, ontology_version)
        if existing is not None:
            return existing
        return entity_repo.create_entity(
            Entity(
                type=EntityType.GENE,
                canonical_name=top.get("name") or evidence.biomarker_mention,
                ontology_version=ontology_version,
                aliases=[EntityAlias(alias=evidence.biomarker_mention)],
                identifiers=[
                    EntityIdentifier(
                        entity_id=uuid4(),
                        namespace=namespace,
                        value=value,
                        ontology_version=ontology_version,
                        source=IdentifierSource.PUBTATOR
                        if namespace == "PUBTATOR"
                        else IdentifierSource.NCBI_GENE_RESOLVER,
                        score=top.get("score"),
                    )
                ],
            )
        )

    def _build_claim(
        self, signature: str, subject_entity: Entity, evidence, state: dict
    ) -> Claim:
        direction = Direction.UNSPECIFIED
        if evidence.direction:
            for candidate in Direction:
                if candidate.value == evidence.direction.upper():
                    direction = candidate
                    break
        predicate = _ROLE_TO_PREDICATE.get(evidence.role, Predicate.ASSOCIATED)
        claim = Claim(
            subject_entity_id=subject_entity.id,
            predicate=predicate,
            object_value=evidence.disease_mention or "UNSPECIFIED",
            direction=direction,
            context=ClaimContext(disease_name=evidence.disease_mention or ""),
        )
        claim.canonical_signature = signature
        return claim


def _extraction_model(payload: dict):
    from pubminer.domain.evidence import BiomarkerEvidence

    return BiomarkerEvidence.model_validate(payload)


def _provisional_signature(
    evidence, state: dict, resolution: dict | None = None
) -> str:
    """聚类键：resolver identifier（可用时）+ role + disease + direction。"""
    subject = "UNRESOLVED"
    if resolution and resolution.get("candidates"):
        identifier = resolution["candidates"][0].get("identifier")
        if identifier:
            subject = identifier.upper()
    direction = (evidence.direction or "UNSPECIFIED").upper()
    predicate = _ROLE_TO_PREDICATE.get(evidence.role, Predicate.ASSOCIATED).value
    disease = (evidence.disease_mention or "UNSPECIFIED").upper().replace(" ", "_")
    return f"{subject} | {predicate} | {disease} | {direction}"
