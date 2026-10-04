/**
 * 全局研究状态管理：连接后端 /api/v1，在五个视图间共享数据。
 *
 * 生命周期：App.vue 挂载时调 init() 加载已有 session 和 claims。
 * 各视图通过 computed 消费状态，通过 actions 触发管线。
 *
 * 运行期：startGoalSetup（含 AskHuman 澄清）→ confirmAndRun 启动管线后进入轮询
 * （3s 间隔拉取 task 步骤状态 + 事件流），直至终态后刷新全部数据。
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
  type DocumentItem,
  type DomainInfo,
} from '@/api/client';

const SESSION_KEY = 'pubminer-session-id';

/** 轮询间隔 (ms) */
const POLL_INTERVAL = 3000;
/** 管线终态：到达即停止轮询 */
const TERMINAL_STATUSES = new Set(['COMPLETED', 'PARTIAL', 'REVIEW_READY', 'FAILED', 'CANCELLED']);

const sessionId = ref<string | null>(localStorage.getItem(SESSION_KEY));
const session = ref<SessionResource | null>(null);
const claims = ref<ClaimItem[]>([]);
const aggregations = ref<AggregationItem[]>([]);
const documents = ref<DocumentItem[]>([]);
const domains = ref<DomainInfo[]>([]);
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
  recommended_next_action?: string | null;
} | null>(null);

// ---- 运行期轮询状态（跨视图共享，AgentWorkflowView 直接消费） ----
const runningTaskId = ref<string | null>(null);
const taskStatus = ref<string | null>(null);
const taskSteps = ref<Array<{ index: number; type: string; status: string; error: string | null; output_summary?: Record<string, unknown> | null }>>([]);
const lastEventSeq = ref(0);
/** 挖掘管线真正在执行（轮询进行中）；与通用 loading 区分，避免页面初始化时误显示"执行中" */
const miningActive = ref(false);
/** 文献页内"管线执行监控"面板是否展开（跨组件共享，顶栏"运行 Agent"也能展开它） */
const workflowPanelOpen = ref(false);

// ---- 研究准备（AskHuman 对话式澄清 + 检索式确认） ----
export interface SetupChatMessage {
  sender: 'ai' | 'user';
  text: string;
}
export interface SetupState {
  open: boolean;
  /** parsing: LLM 解析中 | clarify: 等待用户回答追问 | ready: 可确认开跑 | running: 已启动 */
  phase: 'parsing' | 'clarify' | 'ready' | 'running';
  goal: string;
  messages: SetupChatMessage[];
  fields: Record<string, unknown>;
  intents: Array<{ name: string; query: string; explanation: string }>;
  /** 已进行的追问轮数（上限 3，避免循环） */
  rounds: number;
}
const setup = ref<SetupState | null>(null);

let pollHandle: ReturnType<typeof setInterval> | null = null;
let pollInFlight = false;
/** 连续失败计数：达到上限后停止轮询，避免后端不可用时无限静默重试 */
let pollFailures = 0;
const MAX_POLL_FAILURES = 8;

/** 规范签名格式: "MESH:C024903 | PROGNOSTIC | COLORECTAL_CANCER | HIGH" */
function parseSignature(sig: string) {
  const parts = sig.split(' | ');
  return {
    subject: parts[0] ?? 'Unknown',
    predicate: parts[1] ?? 'ASSOCIATED',
    object: parts[2] ?? 'Unknown',
    direction: parts[3] ?? '',
  };
}

/** subject 优先使用后端解析出的实体名；否则保留本体编号前缀 */
function prettySubject(subject: string, subjectName?: string): string {
  if (subjectName) { return subjectName; }
  return subject.replace(/^MESH:/, 'MeSH:').replace(/^NCBIGENE:/, 'Gene:').replace(/^UNRESOLVED$/, 'Unresolved');
}

function directionSuffix(direction: string): string {
  return direction && direction !== 'UNSPECIFIED' ? ` (${direction})` : '';
}

/** 将后端 claims + aggregations 转换为 UI 展示用的文献卡片数据 */
const papers = computed(() => {
  return aggregations.value.map(agg => {
    const sig = parseSignature(agg.canonical_signature);
    const subjectLabel = prettySubject(sig.subject, agg.subject_name);
    const claim = claims.value.find(c => c.claim_id === agg.claim_id);
    return {
      id: agg.claim_id,
      pmid: agg.claim_id.slice(0, 8),
      doi: '',
      title: `${subjectLabel} — ${sig.predicate}${directionSuffix(sig.direction)} — ${sig.object}`,
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
      // 复核乐观锁需要的真实 claim 版本（reviewQueue 提供）
      claimVersion: claimVersions.value.get(agg.claim_id) ?? 1,
    };
  });
});

/** claim_id → 当前版本号（来自复核队列；用于乐观锁提交） */
const claimVersions = computed(() => {
  const map = new Map<string, number>();
  for (const item of reviewQueue.value) {
    map.set(item.claim_id, item.version);
  }
  return map;
});

// ---- 图谱分类：跟随领域 schema 动态生成（subject 按实体类型细分，object 固定末位） ----
const OBJECT_CATEGORY_KEY = '__OBJECT__';
const DEFAULT_SUBJECT_TYPES = ['GENE', 'PROTEIN', 'CLINICAL_MARKER', 'METABOLITE', 'OTHER'];
const TYPE_LABELS_ZH: Record<string, string> = {
  GENE: '基因',
  PROTEIN: '蛋白质',
  CLINICAL_MARKER: '临床标志物',
  METABOLITE: '代谢物',
  DRUG: '药物',
  TARGET: '靶点蛋白',
  PATHWAY: '通路',
  VARIANT: '变异',
  PROCESS: '生物过程',
  SPECIES: '物种',
  OTHER: '其他',
};
const CATEGORY_PALETTE = ['#0284c7', '#0d9488', '#8b5cf6', '#d97706', '#0ea5e9', '#64748b', '#7c3aed', '#f59e0b'];

/** 活跃领域：按会话任务匹配 schema 的 default_task，回退 biomarker，再回退首个 */
const activeDomain = computed<DomainInfo | null>(() => {
  if (!domains.value.length) { return null; }
  const task = session.value?.task_spec?.task;
  if (task) {
    const byTask = domains.value.find(d => d.default_task === task);
    if (byTask) { return byTask; }
  }
  return domains.value.find(d => d.name === 'biomarker') ?? domains.value[0];
});

const graphCategories = computed(() => {
  const domain = activeDomain.value;
  const subjectTypes = domain && domain.entity_types.length
    ? domain.entity_types
    : DEFAULT_SUBJECT_TYPES.map(key => ({ key, label: key.toLowerCase() }));
  const cats = subjectTypes.map((t, i) => ({
    key: t.key.toUpperCase(),
    label: TYPE_LABELS_ZH[t.key.toUpperCase()] ?? t.label,
    color: CATEGORY_PALETTE[i % CATEGORY_PALETTE.length],
  }));
  cats.push({
    key: OBJECT_CATEGORY_KEY,
    label: domain?.object_label || '疾病/临床结局',
    color: '#e11d48',
  });
  return cats;
});

const graphNodes = computed(() => {
  const typeIdx = new Map<string, number>();
  graphCategories.value.forEach((c, i) => {
    if (c.key !== OBJECT_CATEGORY_KEY) { typeIdx.set(c.key, i); }
  });
  const otherIdx = typeIdx.get('OTHER') ?? 0;
  const objectIdx = graphCategories.value.length - 1;

  const valueOf = new Map<string, number>();
  const nameOf = new Map<string, { name: string; category: number }>();
  for (const agg of aggregations.value) {
    const sig = parseSignature(agg.canonical_signature);
    const subject = prettySubject(sig.subject, agg.subject_name);
    const object = sig.object;
    const weight = agg.support_count + agg.contradict_count + agg.no_effect_count + agg.uncertain_count;
    const st = (agg.subject_type ?? '').toUpperCase();
    nameOf.set(subject, { name: subject, category: typeIdx.get(st) ?? otherIdx });
    nameOf.set(object, { name: object, category: objectIdx });
    valueOf.set(subject, (valueOf.get(subject) ?? 0) + weight);
    valueOf.set(object, (valueOf.get(object) ?? 0) + weight);
  }
  return [...nameOf.values()].map(({ name, category }) => ({
    id: name,
    name,
    category,
    symbolSize: Math.min(60, 15 + (valueOf.get(name) ?? 0) * 2),
    value: valueOf.get(name) ?? 0,
  }));
});

const graphLinks = computed(() => {
  return aggregations.value.map(agg => {
    const sig = parseSignature(agg.canonical_signature);
    return {
      source: prettySubject(sig.subject, agg.subject_name),
      target: sig.object,
      relation: `${sig.predicate}${directionSuffix(sig.direction)}`,
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

function clearError() {
  error.value = null;
}

async function init() {
  loading.value = true;
  try {
    await Promise.all([
      refreshClaims(),
      refreshAggregations(),
      refreshQueue(),
      refreshTasks(),
      refreshDocuments(),
      refreshDomains(),
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
  aggregations.value = (await agentApi.getAggregations(1000)).aggregations;
}

async function refreshDocuments() {
  documents.value = (await agentApi.listDocuments(1000)).documents;
}

async function refreshDomains() {
  try {
    domains.value = (await agentApi.listDomains()).domains;
  } catch { /* 领域信息不可用时使用前端默认分类 */ }
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

async function refreshAll() {
  await Promise.all([
    refreshSession(),
    refreshClaims(),
    refreshAggregations(),
    refreshQueue(),
    refreshTasks(),
    refreshDocuments(),
    refreshCoverage(),
  ]);
}

// ------------------------------------------------------------------ 轮询

async function pollOnce(taskId: string): Promise<boolean> {
  // 返回 true 表示已到终态（或已停止轮询）
  if (pollInFlight) { return false; }
  pollInFlight = true;
  try {
    const detail = await agentApi.getTask(taskId);
    pollFailures = 0;
    taskStatus.value = detail.status;
    taskSteps.value = detail.steps;
    if (sessionId.value) {
      const res = await agentApi.fetchEvents(sessionId.value, lastEventSeq.value);
      if (res.events.length) {
        events.value = [...events.value, ...res.events].slice(-500);
        lastEventSeq.value = res.next_since;
      }
    }
    if (TERMINAL_STATUSES.has(detail.status)) {
      stopPolling();
      await refreshAll();
      return true;
    }
    return false;
  } catch {
    pollFailures += 1;
    if (pollFailures >= MAX_POLL_FAILURES) {
      stopPolling();
      error.value = `任务状态轮询连续失败 ${pollFailures} 次，已停止自动刷新；请检查后端服务后手动重试`;
      return true;
    }
    return false; // 单次失败不中断轮询
  } finally {
    pollInFlight = false;
  }
}

function startPolling(taskId: string) {
  stopPolling();
  pollFailures = 0;
  runningTaskId.value = taskId;
  lastEventSeq.value = 0;
  events.value = [];
  miningActive.value = true;
  void pollOnce(taskId);
  pollHandle = setInterval(() => { void pollOnce(taskId); }, POLL_INTERVAL);
}

function stopPolling() {
  if (pollHandle !== null) {
    clearInterval(pollHandle);
    pollHandle = null;
  }
  miningActive.value = false;
}

/** 运行指定会话并轮询至终态（不负责创建/批准计划） */
async function runAndWait(sessionIdValue: string, body: Parameters<typeof agentApi.runSession>[1]) {
  const task = await agentApi.runSession(sessionIdValue, body);
  startPolling(task.task_id);
  // 等待轮询至终态（pollOnce 内部到终态会 stopPolling + refreshAll）
  while (pollHandle !== null && runningTaskId.value === task.task_id) {
    await new Promise(r => setTimeout(r, POLL_INTERVAL));
  }
  return task;
}

// ------------------------------------------------------------------ 动作

// ------------------------------------------------------------------ 研究准备（AskHuman）

const MAX_CLARIFY_ROUNDS = 3;
const FIELD_LABELS: Record<string, string> = {
  disease: '研究对象疾病/主题',
  task: '研究任务类型（预后 / 诊断 / 预测等）',
  year_from: '起始年份',
  year_to: '截止年份',
  validation_requirement: '验证要求',
};

function buildGoalSummary(fields: Record<string, unknown>, intents: Array<{ name: string; query: string; explanation: string }>): string {
  const lines: string[] = [];
  const parts: string[] = [];
  if (fields.disease) { parts.push(`疾病：${fields.disease}`); }
  if (fields.task) { parts.push(`任务类型：${fields.task}`); }
  if (fields.year_from) { parts.push(`起始年份：${fields.year_from}`); }
  if (fields.year_to) { parts.push(`截止年份：${fields.year_to}`); }
  lines.push(parts.length ? `已解析你的研究目标：\n- ${parts.join('\n- ')}` : '已解析你的研究目标（未识别出结构化字段，将按默认参数执行）。');
  if (intents.length) {
    lines.push('');
    lines.push('生成的检索式：');
    intents.forEach((si, i) => {
      lines.push(`${i + 1}. ${si.query}${si.explanation ? ` —— ${si.explanation}` : ''}`);
    });
    lines.push('检索式可在下方直接修改。');
  }
  return lines.join('\n');
}

/** 启动研究准备：创建会话并解析目标；需要澄清时进入对话追问 */
async function startGoalSetup(goal: string): Promise<void> {
  setup.value = {
    open: true,
    phase: 'parsing',
    goal,
    messages: [{ sender: 'ai', text: '正在解析你的研究目标…' }],
    fields: {},
    intents: [],
    rounds: 0,
  };
  workflowPanelOpen.value = false;
  try {
    const created = await agentApi.createSession({ goal, user_id: 'webui' });
    sessionId.value = created.session_id;
    localStorage.setItem(SESSION_KEY, created.session_id);
    await applyParse();
  } catch (err) {
    setup.value = null;
    error.value = describe(err);
    throw err;
  }
}

/** 调 parse-goal 并把解析结果 / 追问转成对话消息 */
async function applyParse() {
  const s = setup.value;
  if (!s || !sessionId.value) { return; }
  s.phase = 'parsing';
  try {
    const res = await agentApi.parseGoal(sessionId.value);
    s.fields = res.fields ?? {};
    s.intents = res.search_intents ?? [];
    s.messages.push({ sender: 'ai', text: buildGoalSummary(s.fields, s.intents) });
    // 追问触发：LLM 判定需要澄清，或存在缺失的必填字段（确定性信号）
    const clarification = res.clarification ?? {};
    const missing = res.missing_required_fields ?? [];
    const llmWantsClarify = clarification.needed && clarification.question;
    const missingFields = missing.filter(f => !(f in s.fields));
    if ((llmWantsClarify || missingFields.length > 0) && s.rounds < MAX_CLARIFY_ROUNDS) {
      s.rounds += 1;
      s.phase = 'clarify';
      const question = llmWantsClarify
        ? String(clarification.question)
        : '请补充以下信息，以便生成有效的检索式：\n- ' + missingFields.map(f => FIELD_LABELS[f] ?? f).join('\n- ');
      s.messages.push({ sender: 'ai', text: question });
    } else {
      s.phase = 'ready';
      if (s.rounds >= MAX_CLARIFY_ROUNDS) {
        s.messages.push({ sender: 'ai', text: '已达追问上限，将按当前解析结果执行。' });
      }
    }
  } catch {
    // LLM 不可用：不阻断流程，走默认参数
    s.phase = 'ready';
    s.messages.push({ sender: 'ai', text: '目标解析服务暂不可用（未配置 LLM 或服务异常）。可直接用默认参数开始挖掘，或检查 .env 中的 LLM 配置后重试。' });
  }
}

/** 用户在对话中回答追问：存入会话后重新解析 */
async function sendClarification(text: string): Promise<void> {
  const s = setup.value;
  if (!s || !sessionId.value || !text.trim() || s.phase !== 'clarify') { return; }
  s.messages.push({ sender: 'user', text: text.trim() });
  s.phase = 'parsing';
  try {
    await agentApi.answerClarification(sessionId.value, text.trim());
  } catch { /* 存储失败不阻断重解析 */ }
  await applyParse();
}

/** 确认检索式并开始挖掘：保存检索式 → 批准计划 → 运行管线至终态 */
async function confirmAndRun(): Promise<void> {
  const s = setup.value;
  if (!s || !sessionId.value) { return; }
  s.phase = 'running';
  loading.value = true;
  error.value = null;
  try {
    if (s.intents.length) {
      await agentApi.saveSearchIntents(sessionId.value, s.intents).catch(() => undefined);
    }
    const plan = await agentApi.submitPlan(sessionId.value, {
      rationale: 'auto: discovery -> extract -> verify',
      steps: [
        { id: 's1', action_type: 'SEARCH', status: 'pending' },
        { id: 's2', action_type: 'EXTRACT', status: 'pending' },
      ],
    });
    await agentApi.approvePlan(sessionId.value, plan.plan_version);
    await runAndWait(sessionId.value, {
      disease: (s.fields.disease as string) || null,
      task: (s.fields.task as string) || 'prognostic_biomarker',
      max_results: 50,
    });
    setup.value = null;
  } catch (err) {
    error.value = describe(err);
    s.phase = 'ready';
    throw err;
  } finally {
    loading.value = false;
  }
}

function closeSetup() {
  setup.value = null;
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
    documents,
    domains, graphCategories,
    papers, graphNodes, graphLinks, statCards, claimVersions,
    runningTaskId, taskStatus, taskSteps, miningActive, workflowPanelOpen,
    setup,
    init, selectClaim, submitReviewDecision,
    refreshClaims, refreshAggregations, refreshQueue, refreshTasks,
    refreshDocuments, refreshSession, refreshCoverage, refreshAll,
    startPolling, runAndWait, clearError,
    startGoalSetup, sendClarification, confirmAndRun, closeSetup,
  };
}
