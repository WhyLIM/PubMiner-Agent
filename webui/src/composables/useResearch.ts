/**
 * 全局研究状态管理：连接后端 /api/v1，在五个视图间共享数据。
 *
 * 生命周期：App.vue 挂载时调 init() 加载已有 session 和 claims。
 * 各视图通过 computed 消费状态，通过 actions 触发管线。
 */
import { computed, ref } from 'vue';
import {
  agentApi,
  type ClaimItem,
  type EvidenceSpanItem,
  type SessionResource,
  type AggregationItem,
  type ReviewQueueItem,
  type TaskListItem,
} from '@/api/client';

const SESSION_KEY = 'pubminer-session-id';

const sessionId = ref<string | null>(localStorage.getItem(SESSION_KEY));
const session = ref<SessionResource | null>(null);
const claims = ref<ClaimItem[]>([]);
const aggregations = ref<AggregationItem[]>([]);
const reviewQueue = ref<ReviewQueueItem[]>([]);
const tasks = ref<TaskListItem[]>([]);
const evidenceSpans = ref<EvidenceSpanItem[]>([]);
const selectedClaimId = ref<string | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);
const events = ref<Array<{ seq: number; turn: number; action_type: string; tool_name: string | null; status: string; summary: string }>>([]);
const coverage = ref<{
  support_count: number;
  contradict_count: number;
  no_effect_count: number;
  independent_validation_found: boolean;
  unresolved_gaps: string[];
} | null>(null);

const activeTab = ref('literature');

/** 将后端 claims + aggregations 转换为 UI 展示用的文献卡片数据 */
const papers = computed(() => {
  return aggregations.value.map(agg => {
    const claim = claims.value.find(c => c.claim_id === agg.claim_id);
    return {
      id: agg.claim_id,
      pmid: agg.claim_id.slice(0, 8),
      doi: '',
      title: agg.canonical_signature,
      journal: '',
      year: 0,
      authors: '',
      abstract: agg.reasons.join('；') || '',
      studyType: agg.status,
      confidenceScore: agg.support_count / Math.max(1, agg.support_count + agg.contradict_count + agg.uncertain_count),
      screeningStatus: agg.has_conflict ? 'flagged' as const :
        agg.needs_review ? 'flagged' as const :
        agg.status === 'APPROVED' ? 'included' as const :
        agg.status === 'REJECTED' ? 'excluded' as const : 'unscreened' as const,
      entities: { genes: [], diseases: [], drugs: [], pathways: [] },
      triples: [],
      citations: agg.distinct_documents,
      openAccess: false,
      meshTerms: [],
      biasRisk: agg.has_conflict ? 'High' as const : 'Low' as const,
      // 扩展字段
      signature: agg.canonical_signature,
      supportCount: agg.support_count,
      contradictCount: agg.contradict_count,
      noEffectCount: agg.no_effect_count,
      uncertainCount: agg.uncertain_count,
      independentValidation: agg.independent_validation,
      evidenceCount: agg.support_count + agg.contradict_count + agg.no_effect_count + agg.uncertain_count,
      sampleSize: agg.distinct_documents,
      hazardRatio: '' as string,
      pValue: '' as string,
    };
  });
});

const graphNodes = computed(() => {
  const nodes: Array<{ id: string; name: string; category: 0 | 1 | 2 | 3; symbolSize: number; value: number }> = [];
  const seen = new Set<string>();
  for (const agg of aggregations.value) {
    const parts = agg.canonical_signature.split(' | ');
    const subject = parts[0]?.replace(/^NCBIGENE:/, 'Gene:').replace(/^UNRESOLVED$/, 'Unresolved') ?? 'Unknown';
    const object = parts[2] ?? 'Unknown';
    for (const name of [subject, object]) {
      if (seen.has(name)) { continue; }
      seen.add(name);
      nodes.push({
        id: name,
        name,
        category: name.startsWith('Gene:') ? 0 as const : 1 as const,
        symbolSize: Math.min(60, 15 + (agg.support_count + agg.contradict_count + agg.no_effect_count + agg.uncertain_count) * 4),
        value: (agg.support_count + agg.contradict_count + agg.no_effect_count + agg.uncertain_count),
      });
    }
  }
  return nodes;
});

const graphLinks = computed(() => {
  return aggregations.value.map(agg => {
    const parts = agg.canonical_signature.split(' | ');
    return {
      source: parts[0]?.replace(/^NCBIGENE:/, 'Gene:') ?? 'Unknown',
      target: parts[2] ?? 'Unknown',
      relation: parts[1] ?? 'ASSOCIATED',
      weight: (agg.support_count + agg.contradict_count + agg.no_effect_count + agg.uncertain_count),
      evidenceCount: (agg.support_count + agg.contradict_count + agg.no_effect_count + agg.uncertain_count),
    };
  });
});

const statCards = computed(() => {
  const totalSupport = aggregations.value.reduce((s, a) => s + a.support_count, 0);
  const totalContradict = aggregations.value.reduce((s, a) => s + a.contradict_count, 0);
  const totalUncertain = aggregations.value.reduce((s, a) => s + a.uncertain_count, 0);
  return {
    claims: aggregations.value.length,
    candidates: claims.value.length,
    support: totalSupport,
    queue: reviewQueue.value.length,
    contradict: totalContradict,
    uncertain: totalUncertain,
  };
});

function describe(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

async function init() {
  loading.value = true;
  try {
    await Promise.all([
      refreshClaims(),
      refreshAggregations(),
      refreshQueue(),
      refreshTasks(),
    ]);
    if (sessionId.value) {
      await refreshSession();
    }
  } catch (err) {
    error.value = describe(err);
  } finally {
    loading.value = false;
  }
}

async function refreshClaims() {
  claims.value = (await agentApi.listClaims('CANDIDATE')).claims;
}

async function refreshAggregations() {
  aggregations.value = (await agentApi.getAggregations()).aggregations;
}

async function refreshQueue() {
  reviewQueue.value = (await agentApi.getReviewQueue()).items;
}

async function refreshTasks() {
  tasks.value = (await agentApi.listTasks(10)).tasks;
}

async function refreshSession() {
  if (!sessionId.value) { return; }
  try {
    session.value = await agentApi.getSession(sessionId.value);
  } catch {
    localStorage.removeItem(SESSION_KEY);
    sessionId.value = null;
  }
}

async function refreshCoverage() {
  if (!sessionId.value) { return; }
  try {
    coverage.value = await agentApi.getCoverage(sessionId.value);
  } catch { /* ignore */ }
}

async function createAndRunSession(goal: string, disease?: string) {
  loading.value = true;
  error.value = null;
  try {
    const created = await agentApi.createSession({ goal, user_id: 'webui' });
    sessionId.value = created.session_id;
    localStorage.setItem(SESSION_KEY, created.session_id);

    // Parse goal (LLM)
    let specFields: Record<string, unknown> = {};
    try {
      specFields = (await agentApi.parseGoal(created.session_id)).fields;
    } catch { /* LLM 不可用时跳过 */ }

    // Approve plan
    const plan = await agentApi.submitPlan(created.session_id, {
      rationale: 'auto: discovery -> extract -> verify',
      steps: [
        { id: 's1', action_type: 'SEARCH', status: 'pending' },
        { id: 's2', action_type: 'EXTRACT', status: 'pending' },
      ],
    });
    await agentApi.approvePlan(created.session_id, plan.plan_version);

    // Run mining
    const task = await agentApi.runSession(created.session_id, {
      disease: disease || (specFields.disease as string) || null,
      task: 'prognostic_biomarker',
      max_results: 50,
    });

    // Wait and refresh all data
    await agentApi.getTask(task.task_id);
    await Promise.all([
      refreshSession(),
      refreshClaims(),
      refreshAggregations(),
      refreshQueue(),
      refreshTasks(),
      refreshCoverage(),
    ]);
    return task;
  } catch (err) {
    error.value = describe(err);
    throw err;
  } finally {
    loading.value = false;
  }
}

async function selectClaim(claimId: string) {
  selectedClaimId.value = claimId;
  try {
    const evidence = await agentApi.getClaimEvidence(claimId);
    evidenceSpans.value = evidence.evidence ?? [];
  } catch (err) {
    error.value = describe(err);
  }
}

async function submitReviewDecision(claimId: string, decision: 'ACCEPT' | 'EDIT_ACCEPT' | 'REJECT' | 'NEEDS_REVIEW', reason: string, version: number, revision?: Record<string, unknown>) {
  const result = await agentApi.submitReviewDecision({
    claim_id: claimId,
    decision,
    reviewer_id: 'curator',
    reason,
    expected_version: version,
    revision: revision ?? {},
  });
  await Promise.all([refreshClaims(), refreshAggregations(), refreshQueue()]);
  return result;
}

export function useResearch() {
  return {
    sessionId, session, claims, aggregations, reviewQueue, tasks,
    evidenceSpans, selectedClaimId, loading, error, events, coverage,
    activeTab,
    papers, graphNodes, graphLinks, statCards,
    init, createAndRunSession, selectClaim, submitReviewDecision,
    refreshClaims, refreshAggregations, refreshQueue, refreshTasks,
    refreshSession, refreshCoverage,
  };
}
