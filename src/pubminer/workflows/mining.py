"""MiningWorkflow：SEARCH→HYDRATE→SCREEN→EXTRACT→NORMALIZE→VERIFY→AGGREGATE 竖切。

确定性状态机（ADR-005）：每步输入输出落库（run_steps.output_summary），
失败标记 FAILED_RETRYABLE 可从失败步恢复（resume）；不依赖 Agent 决策。
"""
from __future__ import annotations

import logging
from uuid import UUID, uuid4

from pubminer.domain.claims import (
    Claim,
    build_canonical_signature,
    ClaimContext,
    Direction,
    Predicate,
)
from pubminer.domain.documents import Document
from pubminer.domain.entities import Entity, EntityAlias, EntityIdentifier, EntityType, IdentifierSource
from pubminer.domain.evidence import Evidence, EvidencePolarity, StudyAttributes
from pubminer.domain.screening import ScreeningLabel
from pubminer.domain.tasks import Task, TaskStatus
from pubminer.integrations.adapters.pubmed_tags import validate_query
from pubminer.infrastructure.db.repositories.entities import EntityRepository
from pubminer.infrastructure.db.repositories.workflow import TaskRepository
from pubminer.workflows.ports import HydratedDocument, MiningPorts, SearchIntent

logger = logging.getLogger("pubminer.workflow")

_STEP_SEQUENCE = ["SEARCH", "HYDRATE", "SCREEN", "EXTRACT", "NORMALIZE", "VERIFY", "AGGREGATE"]
_STATUS_BY_STEP = {
    "SEARCH": TaskStatus.SEARCHING,
    "HYDRATE": TaskStatus.SEARCHING,
    "HYDRATE2": TaskStatus.SEARCHING,
    "SCREEN": TaskStatus.SCREENING,
    "SCREEN2": TaskStatus.SCREENING,
    "EXTRACT": TaskStatus.EXTRACTING,
    "EXTRACT2": TaskStatus.EXTRACTING,
    "NORMALIZE": TaskStatus.NORMALIZING,
    "NORMALIZE2": TaskStatus.NORMALIZING,
    "VERIFY": TaskStatus.VERIFYING,
    "VERIFY2": TaskStatus.VERIFYING,
    "COVERAGE": TaskStatus.VERIFYING,
    "EXPAND": TaskStatus.SEARCHING,
    "AGGREGATE": TaskStatus.REVIEW_READY,
}

_SOURCE_BY_NAMESPACE = {
    "NCBIGene": IdentifierSource.NCBI_GENE_RESOLVER,
    "MESH": IdentifierSource.MESH_RESOLVER,
    "PUBTATOR": IdentifierSource.PUBTATOR,
}


def _source_for_namespace(namespace: str) -> IdentifierSource:
    return _SOURCE_BY_NAMESPACE.get(namespace, IdentifierSource.PUBTATOR)


class WorkflowStepError(RuntimeError):
    """可重试的步骤失败（来源瞬断、限流等）。"""

    retryable = True


class WorkflowFatalError(RuntimeError):
    """不可恢复的步骤失败（schema 无法满足等）。"""

    retryable = False


class MiningWorkflow:
    """对一篇查询的竖切：意图 → 迭代扩展 → grounded candidate claims。

    支持覆盖驱动的迭代扩展：VERIFY 之后评估覆盖缺口（如独立验证未发现），
    满足条件时经引文扩展（相关文献的 cited-by/参考文献）拉入第二波文献，
    重复 水合→筛选→抽取→验证，再统一聚合。
    """

    BASE_STEPS = ["SEARCH", "HYDRATE", "SCREEN", "EXTRACT", "NORMALIZE", "VERIFY"]
    EXPANSION_STEPS = ["COVERAGE", "EXPAND", "HYDRATE2", "SCREEN2", "EXTRACT2", "NORMALIZE2", "VERIFY2"]

    def __init__(
        self,
        ports: MiningPorts,
        *,
        document_repo_factory,
        claim_repo_factory,
        entity_repo_factory,
        task_repo: TaskRepository,
        domain=None,
        pipeline_release: str = "mvp-0.1:fake",
        max_step_attempts: int = 2,
    ) -> None:
        """
        repo_factory(session) -> repository；由 API/worker 装配层注入。
        domain 定义研究领域（谓词/方向/签名模板等），缺省为 biomarker。
        """
        from pubminer.workflows.domain_schema import load_domain_by_name

        self.ports = ports
        self.document_repo_factory = document_repo_factory
        self.claim_repo_factory = claim_repo_factory
        self.entity_repo_factory = entity_repo_factory
        self.task_repo = task_repo
        self.domain = domain or load_domain_by_name("biomarker")
        self.pipeline_release = pipeline_release
        self.max_step_attempts = max_step_attempts

    def _sequence(self, task: Task) -> list[str]:
        steps = list(self.BASE_STEPS)
        if task.request.get("citation_expansion", True) and getattr(self.ports, "citations", None):
            steps += self.EXPANSION_STEPS
        steps.append("AGGREGATE")
        return steps

    # ------------------------------------------------------------------ entry

    def start(
        self,
        *,
        session_id: UUID | None,
        intents: list[SearchIntent],
        task_id: UUID | None = None,
        screen_criteria: str | None = None,
        citation_expansion: bool = True,
    ) -> UUID:
        """创建任务并立即执行；返回 task_id。"""
        task_citation_expansion = citation_expansion and getattr(self.ports, "citations", None) is not None
        task = Task(
            id=task_id or uuid4(),
            session_id=session_id,
            kind="mining",
            request={
                "intents": [i.__dict__ for i in intents],
                "screen_criteria": screen_criteria,
                "citation_expansion": task_citation_expansion,
            },
        )
        self.task_repo.create(task)
        return self._execute(task, resume_from=0)

    def resume(self, task_id: UUID) -> UUID:
        """从最后一个未成功步骤恢复；全部完成时空操作。"""
        task = self.task_repo.get(task_id)
        if task is None:
            raise LookupError(f"task {task_id} not found")
        failed_index = self.task_repo.first_failed_step_index(task_id)
        if failed_index is None:
            return task.id
        return self._execute(task, resume_from=failed_index)

    # ------------------------------------------------------------------ engine

    def _execute(self, task: Task, *, resume_from: int) -> UUID:
        state: dict = {}
        sequence = self._sequence(task)
        for index, step_name in enumerate(sequence):
            if index < resume_from:
                output = self.task_repo.step_output(task.id, index)
                if output is not None:
                    state.update(output)
                continue

            self.task_repo.set_step(task.id, index, step_name, "RUNNING")
            self.task_repo.update_status(task.id, _STATUS_BY_STEP.get(step_name, _STATUS_BY_STEP["AGGREGATE"]))
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
            cleaned, removed = validate_query(intent.query)
            if removed:
                logger.warning("stripped invalid PubMed tags %s from query %r", removed, intent.query)
                intent = SearchIntent(name=intent.name, query=cleaned, max_results=intent.max_results, date_range=intent.date_range)
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
        failed_hydrations: list[str] = []
        known = {h["pmid"] for h in hydrated}
        todo = [p for p in state.get("pmids", []) if p not in known]
        # 批量优先（元数据一次 efetch + PMC 全文有限并发）；fake 端口回退逐篇
        hydrate_many = getattr(self.ports.hydrate, "hydrate_many", None)
        results: list[HydratedDocument | None]
        if hydrate_many is not None and todo:
            try:
                results = hydrate_many(todo)
            except Exception as exc:
                raise WorkflowStepError(f"hydrate failed: {exc}") from exc
        else:
            results = []
            for pmid in todo:
                try:
                    results.append(self.ports.hydrate.hydrate(pmid))
                except Exception as exc:
                    logger.warning("hydrate failed for %s (skipped): %s", pmid, exc)
                    results.append(None)
        for pmid, doc in zip(todo, results):
            if doc is None:
                failed_hydrations.append(pmid)
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
        output = {"hydrated": hydrated}
        if failed_hydrations:
            output["failed_hydrations"] = failed_hydrations
            logger.warning("hydrate skipped %d/%d PMIDs due to errors", len(failed_hydrations), len(failed_hydrations) + len(hydrated))
        return output

    def _step_screen(self, state: dict, task: Task) -> dict:
        criteria = task.request.get("screen_criteria")
        decisions: list[dict] = list(state.get("decisions", []))
        seen_docs = {d["document_id"] for d in decisions}
        embedding_service = getattr(self.ports, "embedding_service", None)

        # 第一级：embedding 预筛（万级文献时跳过明显不相关的，节省 LLM 调用）
        to_screen: list[dict] = []
        for item in state.get("hydrated", []):
            doc_id = str(item["document"]["id"])
            if doc_id in seen_docs:
                continue
            to_screen.append(item)

        if embedding_service and len(to_screen) > 20:
            profile = embedding_service.build_profile(
                criteria or task.request.get("screen_criteria", "biomarker evidence")
            )
            candidates = [
                {"pmid": item["pmid"], "doc_id": doc_id,
                 "abstract": item["document"].get("abstract", "")}
                for item, doc_id in ((item, str(item["document"]["id"])) for item in to_screen)
                for item in [item]
            ]
            texts = [c["abstract"] for c in candidates]
            scores = embedding_service.similarity_to_profile(
                profile, texts, session=self.task_repo.session
            )
            threshold = embedding_service.adaptive_threshold(scores)
            passed_ids = {
                c["doc_id"] for c, score in zip(candidates, scores) if score >= threshold
            }
            pre_filter_count = len(to_screen)
            to_screen = [item for item in to_screen if str(item["document"]["id"]) in passed_ids]
            logger.info(
                "embedding prefilter: %d/%d passed (threshold=%.2f)",
                len(to_screen), pre_filter_count, threshold,
            )

        # 第二级：LLM 筛选 + 全文级联升级
        for item in to_screen:
            doc_id = str(item["document"]["id"])
            document = Document.model_validate(item["document"])
            try:
                decision = self.ports.screen.screen(document, criteria)
            except Exception as exc:
                raise WorkflowStepError(f"screen failed for {item['pmid']}: {exc}") from exc
            # 第三级：摘要判 UNCERTAIN 且有全文时用全文重筛
            if (
                decision.label == ScreeningLabel.UNCERTAIN
                and item.get("fulltext_available")
            ):
                try:
                    decision = self.ports.screen.screen(
                        document, criteria, fulltext_upgrade=item["version"]["canonical_text"]
                    )
                except Exception:
                    pass
            decisions.append(decision.model_dump(mode="json"))
        return {"decisions": decisions}

    def _step_extract(self, state: dict, task: Task) -> dict:
        relevant = {
            d["document_id"]
            for d in state.get("decisions", [])
            if d["label"] in (ScreeningLabel.RELEVANT.value, ScreeningLabel.UNCERTAIN.value)
        }
        extractions: list[dict] = []
        study_contexts: list[dict] = list(state.get("study_contexts", []))
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
                _result = self.ports.extract.extract(hydrated, session=self.task_repo.session)
                if isinstance(_result, tuple):
                    evidence_items, study_ctx = _result
                else:
                    evidence_items, study_ctx = _result, None
            except Exception as exc:
                raise WorkflowStepError(f"extract failed for {item['pmid']}: {exc}") from exc
            source = "fulltext" if item.get("fulltext_available") else "abstract"
            for evidence in evidence_items:
                if hasattr(evidence, "evidence_source"):
                    evidence.evidence_source = source
                dump = evidence.model_dump(mode="json")
                dump["_pmid"] = item["pmid"]
                extractions.append(dump)
            if study_ctx:
                ctx = dict(study_ctx) if isinstance(study_ctx, dict) else study_ctx.model_dump(mode="json")
                ctx["_pmid"] = item["pmid"]
                study_contexts.append(ctx)
        output = {"extractions": extractions}
        if study_contexts:
            output["study_contexts"] = study_contexts
        return output

    def _step_normalize(self, state: dict, task: Task) -> dict:
        resolutions: list[dict] = []
        cache: dict[str, dict] = {}
        for extraction in state.get("extractions", []):
            mention = extraction["biomarker_mention"]
            mention_type = (extraction.get("biomarker_type") or "GENE").upper()
            entity_type = self.domain.entity_types.get(mention_type, "OTHER")
            if mention not in cache:
                try:
                    candidates, needs_review = self.ports.normalize.resolve(mention, entity_type, session=self.task_repo.session)
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
        verified: list[dict] = list(state.get("verified", []))
        done = {v["biomarker_mention"] for v in verified}
        for extraction in state.get("extractions", []):
            mention = extraction["biomarker_mention"]
            if mention in done:
                continue
            evidence = _extraction_model(extraction)
            signature = _provisional_signature(evidence, state, domain=self.domain)
            try:
                result = self.ports.verify.verify(signature, evidence, session=self.task_repo.session)
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

    def _step_coverage(self, state: dict, task: Task) -> dict:
        """覆盖门控：独立验证未发现且有相关文献时触发引文扩展。"""
        if not getattr(self.ports, "citations", None):
            return {"expand": False}
        relevant_pmids = [item["pmid"] for item in state.get("hydrated", []) if self._pmid_relevant(state, item["pmid"])]
        if not relevant_pmids:
            return {"expand": False}
        iv_found = any(v.get("independent_validation") for v in state.get("verified", []))
        return {"expand": not iv_found, "candidate_pmids": relevant_pmids}

    def _pmid_relevant(self, state: dict, pmid: str) -> bool:
        for decision in state.get("decisions", []):
            for item in state.get("hydrated", []):
                if item["document"]["id"] == decision["document_id"] and item["pmid"] == pmid:
                    if decision["label"] in (ScreeningLabel.RELEVANT.value, ScreeningLabel.UNCERTAIN.value):
                        return True
        return False

    def _step_expand(self, state: dict, task: Task) -> dict:
        """引文扩展：相关文献的 cited-by + references 中未见过的新 PMID。"""
        if not state.get("expand"):
            return {}
        candidate_pmids = state.get("candidate_pmids", [])
        seen = set(state.get("pmids", []))
        try:
            citation_map = self.ports.citations.fetch_citations(candidate_pmids)
        except Exception as exc:
            raise WorkflowStepError(f"citation fetch failed: {exc}") from exc

        new_pmids: list[str] = []
        for pmid in candidate_pmids:
            entry = citation_map.get(pmid)
            linked: list[str] = []
            if entry is not None:
                linked = [str(x) for x in (getattr(entry, "cited_by", []) or [])]
                linked += [str(x) for x in (getattr(entry, "references", []) or [])]
            for ref in linked:
                ref = ref.strip()
                if ref and ref not in seen and ref not in new_pmids:
                    new_pmids.append(ref)
        new_pmids = new_pmids[:10]  # 扩展上限：控制成本
        return {
            "pmids": list(state.get("pmids", [])) + new_pmids,
            "expand_pmids": new_pmids,
        }

    def _step_hydrate2(self, state: dict, task: Task) -> dict:
        expand_pmids = state.get("expand_pmids", [])
        todo = [p for p in expand_pmids if p not in {h["pmid"] for h in state.get("hydrated", [])}]
        if not todo:
            return {}
        return self._step_hydrate({**state, "pmids": todo}, task)

    def _step_screen2(self, state: dict, task: Task) -> dict:
        expand_pmids = set(state.get("expand_pmids", []))
        if not expand_pmids:
            return {}
        fresh = [item for item in state.get("hydrated", []) if item["pmid"] in expand_pmids]
        decisions: list[dict] = list(state.get("decisions", []))
        criteria = task.request.get("screen_criteria")
        for item in fresh:
            document = Document.model_validate(item["document"])
            try:
                decision = self.ports.screen.screen(document, criteria)
            except Exception as exc:
                raise WorkflowStepError(f"screen failed for {item['pmid']}: {exc}") from exc
            decisions.append(decision.model_dump(mode="json"))
        return {"decisions": decisions}

    def _step_extract2(self, state: dict, task: Task) -> dict:
        expand_pmids = set(state.get("expand_pmids", []))
        relevant = {
            d["document_id"]
            for d in state.get("decisions", [])
            if d["label"] in (ScreeningLabel.RELEVANT.value, ScreeningLabel.UNCERTAIN.value)
        }
        extractions: list[dict] = list(state.get("extractions", []))
        for item in state.get("hydrated", []):
            if item["pmid"] not in expand_pmids:
                continue
            if str(item["document"]["id"]) not in relevant:
                continue
            hydrated = HydratedDocument(
                document=Document.model_validate(item["document"]),
                version=item["version"],
                section_spans=item["section_spans"],
                fulltext_available=item["fulltext_available"],
            )
            try:
                _result = self.ports.extract.extract(hydrated, session=self.task_repo.session)
                if isinstance(_result, tuple):
                    evidence_items, study_context = _result
                else:
                    evidence_items, study_context = _result, None
            except Exception as exc:
                raise WorkflowStepError(f"extract failed for {item['pmid']}: {exc}") from exc
            source = "fulltext" if item.get("fulltext_available") else "abstract"
            for evidence in evidence_items:
                evidence.evidence_source = source
                dump = evidence.model_dump(mode="json")
                dump["_pmid"] = item["pmid"]
                extractions.append(dump)
            if study_context:
                ctx = dict(study_context) if isinstance(study_context, dict) else study_context.model_dump(mode="json")
                ctx["pmid"] = item["pmid"]
                state.setdefault("study_contexts", []).append(ctx)
        output = {"extractions": extractions}
        if state.get("study_contexts"):
            output["study_contexts"] = state["study_contexts"]
        return output

    def _step_normalize2(self, state: dict, task: Task) -> dict:
        known = {r["mention"] for r in state.get("resolutions", [])}
        resolutions: list[dict] = list(state.get("resolutions", []))
        for extraction in state.get("extractions", []):
            mention = extraction["biomarker_mention"]
            if mention in known:
                continue
            known.add(mention)
            try:
                candidates, needs_review = self.ports.normalize.resolve(
                    mention, (extraction.get("biomarker_type") or "GENE").upper()
                )
            except Exception as exc:
                raise WorkflowStepError(f"normalize failed for {mention}: {exc}") from exc
            resolutions.append({
                "mention": mention,
                "candidates": [c.__dict__ for c in candidates],
                "needs_review": needs_review,
            })
        return {"resolutions": resolutions}

    def _step_verify2(self, state: dict, task: Task) -> dict:
        verified_mentions = {v["biomarker_mention"] for v in state.get("verified", [])}
        verified: list[dict] = list(state.get("verified", []))
        for extraction in state.get("extractions", []):
            mention = extraction["biomarker_mention"]
            if mention in verified_mentions:
                continue
            verified_mentions.add(mention)
            evidence = _extraction_model(extraction)
            signature = _provisional_signature(evidence, state, domain=self.domain)
            try:
                result = self.ports.verify.verify(signature, evidence, session=self.task_repo.session)
            except Exception as exc:
                raise WorkflowStepError(f"verify failed: {exc}") from exc
            verified.append({
                "biomarker_mention": mention,
                "polarity": result.polarity.value,
                "statistically_significant": result.statistically_significant,
                "independent_validation": result.independent_validation,
                "needs_human_review": result.needs_human_review,
                "reasons": result.reasons,
            })
        return {"verified": verified}

    def _step_aggregate(self, state: dict, task: Task) -> dict:
        """按 canonical signature 聚类并落库 CANDIDATE claims + evidence。"""
        created: list[dict] = []
        claims_repo = self.claim_repo_factory(self.task_repo.session)
        entity_repo = self.entity_repo_factory(self.task_repo.session)

        clusters: dict[str, list[dict]] = {}
        for extraction in state.get("extractions", []):
            evidence = _extraction_model(extraction)
            resolution = self._resolution_for(state, extraction["biomarker_mention"])
            signature = _provisional_signature(evidence, state, resolution, domain=self.domain)
            clusters.setdefault(signature, []).append((extraction, resolution))

        # 疾病归一化：将 disease mention 解析为 MeSH，聚合同一疾病的不同写法
        disease_resolutions: dict[str, dict | None] = {}
        for extraction in state.get("extractions", []):
            disease = extraction.get("disease_mention")
            if disease and disease not in disease_resolutions:
                try:
                    candidates, _review = self.ports.normalize.resolve(disease, "DISEASE", session=self.task_repo.session)
                except Exception as exc:
                    logger.warning("disease normalize failed for %r: %s", disease, exc)
                    disease_resolutions[disease] = None
                    continue
                disease_resolutions[disease] = (
                    {"candidates": [c.__dict__ for c in candidates]}
                    if candidates else None
                )

        for signature, members in clusters.items():
            first_extraction, first_resolution = members[0]
            evidence_model = _extraction_model(first_extraction)
            subject_entity, unresolved = self._ensure_entity(
                entity_repo, first_resolution, evidence_model
            )
            polarity = self._polarity_for(state, first_extraction["biomarker_mention"])
            claim = self._build_claim(signature, subject_entity, evidence_model, state)
            disease_mesh = self._disease_mesh_id(state, evidence_model.disease_mention, disease_resolutions)
            if disease_mesh:
                claim.context.disease_mesh_id = disease_mesh
                claim.canonical_signature = build_canonical_signature(
                    subject_identifier=signature.split(" | ")[0],
                    predicate=claim.predicate,
                    object_identifier=f"MESH:{disease_mesh}",
                    direction=claim.direction,
                    context=claim.context,
                )
                # 疾病侧实体化：MeSH 解析结果落 Entity(type=DISEASE)，object_entity_id 可用于聚簇/图谱/导出
                disease_entity, _dr = self._ensure_disease_entity(
                    entity_repo, disease_mesh, evidence_model.disease_mention or "UNSPECIFIED"
                )
                claim.object_entity_id = disease_entity.id
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
                        evidence_source=ev.evidence_source,
                    ),
                    statistics=ev.statistics,
                )
                evidence_rows.append(domain_evidence)
            # 独立验证自动检测：同一结论在 ≥2 篇不同文献中同向成立
            distinct_docs = {e.document_id for e in evidence_rows}
            if len(distinct_docs) >= self.domain.iv_min_documents:
                for e in evidence_rows:
                    e.study.independent_validation = True
            stored = claims_repo.create_candidate_claim(claim, evidence_rows)
            if unresolved:
                claims_repo.mark_evidence_needs_review(stored.id)
            created.append(
                {
                    "claim_id": str(stored.id),
                    "signature": stored.canonical_signature,
                    "evidence_count": len(members),
                    "needs_review": unresolved,
                }
            )
        return {"claims": created}

    # ------------------------------------------------------------------ helpers

    def _disease_mesh_id(self, state: dict, disease: str | None, disease_resolutions: dict) -> str | None:
        if not disease:
            return None
        resolution = disease_resolutions.get(disease)
        if not resolution or not resolution.get("candidates"):
            return None
        identifier = resolution["candidates"][0].get("identifier") or ""
        return identifier.split(":", 1)[1] if identifier.upper().startswith("MESH:") else None

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

    def _ensure_entity(
        self, entity_repo: EntityRepository, resolution: dict | None, evidence
    ) -> tuple[Entity, bool]:
        """把 resolver 的 top 候选落成实体行。

        返回 (entity, unresolved)：unresolved=True 表示 resolver 没有给出
        identifier（如非基因类临床指标）——此时创建无 identifier 的占位
        实体并把证据标记 needs_review，绝不编造 identifier（ADR-006）。
        """
        mention_type = (evidence.biomarker_type or "GENE").upper()
        entity_type_enum = EntityType.__members__.get(mention_type, EntityType.OTHER)
        if not resolution or not resolution.get("candidates"):
            placeholder = entity_repo.find_by_canonical_name(
                evidence.biomarker_mention, entity_type=entity_type_enum.value
            ) or entity_repo.create_entity(
                Entity(
                    type=entity_type_enum,
                    canonical_name=evidence.biomarker_mention,
                    ontology_version="mvp-2026",
                    aliases=[EntityAlias(alias=evidence.biomarker_mention, is_canonical=True)],
                    identifiers=[],  # 无 resolver 候选：不编造 identifier，等 curator 补
                )
            )
            return placeholder, True
        top = resolution["candidates"][0]
        identifier = top.get("identifier")
        if not identifier or ":" not in identifier:
            raise WorkflowFatalError("resolver candidate without identifier")
        namespace, value = identifier.split(":", 1)
        ontology_version = "mvp-2026"
        existing = entity_repo.find_by_identifier(namespace, value, ontology_version)
        if existing is not None:
            return existing, False
        return entity_repo.create_entity(
            Entity(
                type=entity_type_enum,
                canonical_name=top.get("name") or evidence.biomarker_mention,
                ontology_version=ontology_version,
                aliases=[EntityAlias(alias=evidence.biomarker_mention)],
                identifiers=[
                    EntityIdentifier(
                        entity_id=uuid4(),
                        namespace=namespace,
                        value=value,
                        ontology_version=ontology_version,
                        source=_source_for_namespace(namespace),
                        score=top.get("score"),
                    )
                ],
            )
        ), resolution.get("needs_review", False)

    def _ensure_disease_entity(
        self, entity_repo: EntityRepository, mesh_id: str, mention: str
    ) -> tuple[Entity, bool]:
        """按 MeSH 标识符查找或创建疾病实体（type=DISEASE）。"""
        namespace, value = "MESH", mesh_id
        ontology_version = "mvp-2026"
        existing = entity_repo.find_by_identifier(namespace, value, ontology_version)
        if existing is not None:
            return existing, False
        return entity_repo.create_entity(
            Entity(
                type=EntityType.DISEASE,
                canonical_name=mention,
                ontology_version=ontology_version,
                aliases=[EntityAlias(alias=mention)],
                identifiers=[
                    EntityIdentifier(
                        entity_id=uuid4(),
                        namespace=namespace,
                        value=value,
                        ontology_version=ontology_version,
                        source=_source_for_namespace(namespace),
                        score=None,
                    )
                ],
            )
        ), False

    def _build_claim(
        self, signature: str, subject_entity: Entity, evidence, state: dict
    ) -> Claim:
        direction = Direction.UNSPECIFIED
        if evidence.direction:
            for candidate in Direction:
                if candidate.value == evidence.direction.upper():
                    direction = candidate
                    break
        predicate_str = self.domain.predicate_for_role(evidence.role)
        predicate = Predicate(predicate_str)
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
    evidence, state: dict, resolution: dict | None = None,
    domain=None,
) -> str:
    """聚类键：resolver identifier（可用时）+ role + disease + direction。"""
    subject = "UNRESOLVED"
    if resolution and resolution.get("candidates"):
        identifier = resolution["candidates"][0].get("identifier")
        if identifier:
            subject = identifier.upper()
    direction = (evidence.direction or "UNSPECIFIED").upper()
    if domain is not None:
        predicate_str = domain.predicate_for_role(evidence.role)
    else:
        predicate_str = evidence.role.upper() if evidence.role else "ASSOCIATED"
    disease = (evidence.disease_mention or "UNSPECIFIED").upper().replace(" ", "_")
    return f"{subject} | {predicate_str} | {disease} | {direction}"
