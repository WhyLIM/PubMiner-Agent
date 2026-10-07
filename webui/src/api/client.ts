/**
 * PubMiner Evidence Agent /api/v1 类型化客户端。
 *
 * 契约来源：后端 FastAPI 的 OpenAPI（openapi.json）；开发态经 Vite 代理
 * 同源访问 /api（无跨域），生产可用 VITE_API_BASE 指向独立后端。
 */

export const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export interface PlanStep {
  id: string;
  action_type: string;
  description?: string;
  search_intent?: string | null;
  status?: string;
}

export interface Plan {
  version: number;
  rationale: string;
  steps: PlanStep[];
  approved_by_human: boolean;
}

export interface ActionItem {
  id: string;
  turn: number;
  action_type: string;
  tool_name: string | null;
  status: string;
  result_summary: string;
}

export interface SessionResource {
  session_id: string;
  goal: string;
  status: string;
  turn: number;
  current_plan_version: number;
  plans: Plan[];
  task_spec: { schema_version: string; disease?: string | null; task?: string | null } | null;
  budget: Record<string, unknown>;
  budget_state: Record<string, unknown>;
  stop_reason: { kind: string; message?: string } | null;
  actions: ActionItem[];
}

export interface ClaimItem {
  claim_id: string;
  canonical_signature: string;
  status: string;
  predicate: string;
  direction: string;
  evidence_count: number;
  polarities: Record<string, number>;
}

export interface EvidenceSpanItem {
  evidence_id: string;
  polarity: string;
  span: {
    document_version_id: string;
    passage_id: string;
    section_path: string;
    start_char: number;
    end_char: number;
    text: string;
  };
  statistics?: Record<string, unknown> | null;
  study?: Record<string, unknown>;
  review_status: string;
  document_id?: string;
  document_version_id?: string;
  document_title?: string;
  canonical_text?: string;
}

export interface ClaimEvidence {
  claim_id: string;
  canonical_signature: string;
  evidence: EvidenceSpanItem[];
}

export interface ReviewQueueItem {
  claim_id: string;
  canonical_signature: string;
  status: string;
  version: number;
  priority: string;
  reasons: string[];
  evidence_count: number;
  polarities: Record<string, number>;
  cluster_key?: string;
  member_count?: number;
  members?: Array<{ claim_id: string; version: number; signature: string }>;
}

export interface TaskListItem {
  task_id: string;
  session_id: string | null;
  kind: string;
  status: string;
  created_at: string;
}

export interface AggregationItem {
  claim_id: string;
  canonical_signature: string;
  status: string;
  support_count: number;
  contradict_count: number;
  no_effect_count: number;
  uncertain_count: number;
  independent_validation: boolean;
  has_conflict: boolean;
  needs_review: boolean;
  distinct_documents: number;
  reasons: string[];
  subject_name?: string;
  subject_type?: string;
  member_count?: number;
}

export interface DomainEntityType {
  key: string;
  label: string;
}

export interface DomainInfo {
  name: string;
  display: string;
  default_task: string;
  object_label: string;
  entity_types: DomainEntityType[];
}

export interface DocumentClaimEntry {
  claim_id: string;
  canonical_signature: string;
  status: string;
  predicate: string;
  direction: string;
  support_count: number;
  contradict_count: number;
  no_effect_count: number;
  uncertain_count: number;
}

export interface DocumentItem {
  document_id: string;
  title: string;
  journal: string;
  year: number | null;
  authors: string[];
  abstract: string;
  pmid: string;
  pmcid: string;
  doi: string;
  source: string;
  evidence_count: number;
  support_count: number;
  contradict_count: number;
  no_effect_count: number;
  uncertain_count: number;
  claims: DocumentClaimEntry[];
}

export interface DocumentEvidenceEntry {
  evidence_id: string;
  claim_id: string;
  claim_signature: string;
  polarity: string;
  section_path: string;
  start_char: number;
  end_char: number;
  span_text: string;
  review_status: string;
  canonical_text: string;
}

export interface DocumentDetail extends DocumentItem {
  evidence: DocumentEvidenceEntry[];
}

export class AgentApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryable: boolean,
    readonly requestId: string,
  ) {
    super(`${code}: ${message}`);
    this.name = "AgentApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    let code = "HTTP_ERROR";
    let message = response.statusText;
    let retryable = response.status >= 500;
    let requestId = "";
    try {
      const body = (await response.json()) as {
        error?: { code?: string; message?: string; retryable?: boolean };
        request_id?: string;
      };
      code = body.error?.code ?? code;
      message = body.error?.message ?? message;
      retryable = body.error?.retryable ?? retryable;
      requestId = body.request_id ?? requestId;
    } catch {
      /* 非 JSON 错误体 */
    }
    throw new AgentApiError(response.status, code, message, retryable, requestId);
  }
  return response.json() as Promise<T>;
}

export const agentApi = {
  health: () => request<{ status: string }>("/api/v1/health"),

  listSessions: (limit = 20) =>
    request<{
      sessions: Array<{ session_id: string; goal: string; status: string; created_at: string }>;
    }>(`/api/v1/agent/sessions?limit=${limit}`),

  parseGoal: (sessionId: string) =>
    request<{
      bound: boolean;
      fields: Record<string, unknown>;
      search_intents: Array<{ name: string; query: string; explanation: string }>;
      clarification: { needed?: boolean; question?: string } & Record<string, unknown>;
      missing_required_fields: string[];
    }>(`/api/v1/agent/sessions/${sessionId}/parse-goal`, { method: "POST" }),

  answerClarification: (sessionId: string, answer: string) =>
    request<{ ok: boolean; hint: string }>(
      `/api/v1/agent/sessions/${sessionId}/answer`,
      { method: "POST", body: JSON.stringify({ answer }) },
    ),

  saveSearchIntents: (
    sessionId: string,
    searchIntents: Array<{ name: string; query: string; explanation?: string }>,
  ) =>
    request<{ ok: boolean; count: number }>(
      `/api/v1/agent/sessions/${sessionId}/search-intents`,
      { method: "POST", body: JSON.stringify({ search_intents: searchIntents }) },
    ),

  runSession: (sessionId: string, body: {
    disease?: string | null;
    task?: string;
    year_from?: number | null;
    max_results?: number;
    screen_criteria?: string | null;
    domain?: string;
  }) =>
    request<{ task_id: string; status: string; plan_version: number }>(
      `/api/v1/agent/sessions/${sessionId}/run`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  resumeTask: (taskId: string) =>
    request<{ task_id: string; status: string }>(
      `/api/v1/tasks/${taskId}/actions/resume`,
      { method: "POST" },
    ),

  createSession: (body: { goal: string; user_id?: string; limits?: Record<string, unknown> }) =>
    request<{ session_id: string; status: string; next: string }>("/api/v1/agent/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getSession: (sessionId: string) =>
    request<SessionResource>(`/api/v1/agent/sessions/${sessionId}`),

  postMessage: (sessionId: string, body: { role: string; content: string; kind?: string; payload?: Record<string, unknown> }) =>
    request<{ message_id: string; ok: boolean }>(
      `/api/v1/agent/sessions/${sessionId}/messages`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  bindTaskSpec: (
    sessionId: string,
    body: {
      disease?: string | null;
      task?: string | null;
      validation_requirement?: string | null;
      year_from?: number | null;
      year_to?: number | null;
      publication_types?: string[];
    },
  ) =>
    request<{ schema_version: string; missing_required_fields: string[] }>(
      `/api/v1/agent/sessions/${sessionId}/task-spec`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  submitPlan: (sessionId: string, body: { rationale?: string; steps: PlanStep[] }) =>
    request<{ plan_version: number; status: string }>(
      `/api/v1/agent/sessions/${sessionId}/plan`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  approvePlan: (sessionId: string, planVersion: number) =>
    request<{ approved: number }>(`/api/v1/agent/sessions/${sessionId}/plan/approve`, {
      method: "POST",
      body: JSON.stringify({ plan_version: planVersion }),
    }),

  pause: (sessionId: string) =>
    request<{ status: string }>(`/api/v1/agent/sessions/${sessionId}/actions/pause`, {
      method: "POST",
    }),

  fetchEvents: (sessionId: string, since: number) =>
    request<{
      events: Array<{
        seq: number;
        turn: number;
        action_type: string;
        tool_name: string | null;
        status: string;
        summary: string;
      }>;
      next_since: number;
    }>(`/api/v1/agent/sessions/${sessionId}/events?format=json&since=${since}`),

  createTask: (body: {
    session_id?: string | null;
    intents: Array<{ name: string; query: string; max_results?: number }>;
  }) =>
    request<{ task_id: string; status: string }>("/api/v1/tasks", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getTask: (taskId: string) =>
    request<{
      task_id: string;
      status: string;
      steps: Array<{
        index: number;
        type: string;
        status: string;
        error: string | null;
        output_summary?: Record<string, unknown> | null;
      }>;
    }>(`/api/v1/tasks/${taskId}`),

  listTasks: (limit = 20) =>
    request<{ tasks: TaskListItem[] }>(`/api/v1/tasks?limit=${limit}`),

  listClaims: (status = "CANDIDATE") =>
    request<{ claims: ClaimItem[] }>(`/api/v1/claims?status=${encodeURIComponent(status)}`),

  getClaimEvidence: (claimId: string) =>
    request<ClaimEvidence>(`/api/v1/claims/${claimId}/evidence`),

  getReviewQueue: (sessionId?: string) =>
    request<{ items: ReviewQueueItem[] }>(
      `/api/v1/reviews/queue${sessionId ? `?session_id=${sessionId}` : ''}`,
    ),

  submitReviewDecision: (body: {
    claim_id: string;
    decision: "ACCEPT" | "EDIT_ACCEPT" | "REJECT" | "NEEDS_REVIEW";
    reviewer_id: string;
    reason: string;
    expected_version: number;
    revision?: Record<string, unknown>;
  }) =>
    request<{ ok: boolean; claim_status: string; claim_version: number; review_id: string }>(
      "/api/v1/reviews/decision",
      { method: "POST", body: JSON.stringify(body) },
    ),

  getAggregations: (limit = 1000, sessionId?: string) =>
    request<{ aggregations: AggregationItem[] }>(
      `/api/v1/verification/aggregations?limit=${limit}${sessionId ? `&session_id=${sessionId}` : ''}`,
    ),

  listDomains: () =>
    request<{ domains: DomainInfo[] }>("/api/v1/domains"),

  listDocuments: (limit = 100, sessionId?: string) =>
    request<{ documents: DocumentItem[] }>(
      `/api/v1/documents?limit=${limit}${sessionId ? `&session_id=${sessionId}` : ''}`,
    ),

  getDocument: (documentId: string) =>
    request<DocumentDetail>(`/api/v1/documents/${documentId}`),

  listDomainSchemas: () =>
    request<{ schemas: Array<{ name: string; display: string; entity_label: string; default_task: string; object_label: string; file: string }> }>(
      "/api/v1/schemas",
    ),

  generateDomainSchema: (description: string) =>
    request<{ domain: Record<string, unknown> }>("/api/v1/schemas/generate", {
      method: "POST",
      body: JSON.stringify({ description }),
    }),

  calibrateDomainSchema: (domain: Record<string, unknown>) =>
    request<{ domain: Record<string, unknown> }>("/api/v1/schemas/calibrate", {
      method: "POST",
      body: JSON.stringify({ domain }),
    }),

  saveDomainSchema: (domain: Record<string, unknown>) =>
    request<{ ok: boolean; name: string; file: string }>("/api/v1/schemas/save", {
      method: "POST",
      body: JSON.stringify({ domain }),
    }),

  askEvidence: (sessionId: string, question: string) =>
    request<{
      answer: string;
      generated_by: string;
      citations: Array<{
        label: string;
        claim_signature: string;
        polarity: string;
        section_path: string;
        document_title: string;
      }>;
      matched_claims: Array<Record<string, unknown>>;
    }>(`/api/v1/agent/sessions/${sessionId}/qa`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),

  getCoverage: (sessionId: string) =>
    request<{
      session_id: string;
      questions: Array<{
        question: string;
        support_count: number;
        contradict_count: number;
        no_effect_count: number;
        uncertain_count: number;
        independent_validation_found: boolean;
        covered: boolean;
        note: string;
      }>;
      support_count: number;
      contradict_count: number;
      no_effect_count: number;
      independent_validation_found: boolean;
      unresolved_gaps: string[];
      recommended_next_action: string | null;
    }>(`/api/v1/agent/sessions/${sessionId}/coverage`),
};
