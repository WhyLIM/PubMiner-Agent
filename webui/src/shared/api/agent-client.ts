/**
 * Typed client for the PubMiner Evidence Agent API (/api/v1).
 *
 * Contract source: src/shared/api/openapi.json (exported from the FastAPI app;
 * regenerate with `pnpm gen:api`). Types come from the generated schema.d.ts —
 * hand-written duplicates of backend models are not allowed (PR-011).
 */
import type { operations, paths } from "./schema";

export const API_V1_BASE_URL =
  process.env.NEXT_PUBLIC_AGENT_API_URL ?? "http://localhost:8001";

type ResponsesOf<Op> = Op extends { responses: infer R } ? R : never;
type JsonBody<Resp> = Resp extends { content: { "application/json": infer Body } } ? Body : never;
type SuccessJson<Op> =
  Op extends { responses: infer R }
    ? R extends { 200: infer A }
      ? JsonBody<A>
      : R extends { 201: infer B }
        ? JsonBody<B>
        : R extends { 202: infer C }
          ? JsonBody<C>
          : unknown
    : unknown;
type OkBody<Op> = SuccessJson<Op>;

export type SessionResource = OkBody<operations["get_session_api_v1_agent_sessions__session_id__get"]>;
export type CreateSessionBody = operations["create_session_api_v1_agent_sessions_post"]["requestBody"]["content"]["application/json"];
export type PostMessageBody = operations["post_message_api_v1_agent_sessions__session_id__messages_post"]["requestBody"]["content"]["application/json"];
export type BindTaskSpecBody = operations["bind_task_spec_api_v1_agent_sessions__session_id__task_spec_post"]["requestBody"]["content"]["application/json"];
export type SubmitPlanBody = operations["submit_plan_api_v1_agent_sessions__session_id__plan_post"]["requestBody"]["content"]["application/json"];
export type CreateTaskBody = operations["create_task_api_v1_tasks_post"]["requestBody"]["content"]["application/json"];
export type ClaimItem = NonNullable<OkBody<operations["list_claims_api_v1_claims_get"]>["claims"]>[number];
export type ClaimEvidence = OkBody<operations["get_claim_evidence_api_v1_claims__claim_id__evidence_get"]>;
export type EvidenceSpanItem = NonNullable<ClaimEvidence["evidence"]>[number];
export type ReviewQueueItem = NonNullable<OkBody<operations["review_queue_api_v1_reviews_queue_get"]>["items"]>[number];
export type ReviewDecisionBody = operations["submit_review_decision_api_v1_reviews_decision_post"]["requestBody"]["content"]["application/json"];
export type ReviewDecisionResult = OkBody<operations["submit_review_decision_api_v1_reviews_decision_post"]>;
export type AggregationItem = NonNullable<
  OkBody<operations["verification_aggregations_api_v1_verification_aggregations_get"]>["aggregations"]
>[number];
export type CoverageResource = OkBody<operations["session_coverage_api_v1_agent_sessions__session_id__coverage_get"]>;

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

async function request<Path extends keyof paths>(
  path: Path,
  init?: RequestInit,
): Promise<unknown> {
  const response = await fetch(`${API_V1_BASE_URL}${path as string}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    let code = "HTTP_ERROR";
    let message = response.statusText;
    let retryable = response.status >= 500;
    let requestId = "";
    try {
      const body = (await response.json()) as { error?: { code?: string; message?: string; retryable?: boolean }; request_id?: string };
      code = body.error?.code ?? code;
      message = body.error?.message ?? message;
      retryable = body.error?.retryable ?? retryable;
      requestId = body.request_id ?? requestId;
    } catch {
      // 非 JSON 错误体，保留默认值
    }
    throw new AgentApiError(response.status, code, message, retryable, requestId);
  }
  return response.json();
}

export const agentApi = {
  async createSession(body: CreateSessionBody): Promise<{ session_id: string; status: string; next: string }> {
    return (await request("/api/v1/agent/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    })) as { session_id: string; status: string; next: string };
  },

  async getSession(sessionId: string): Promise<SessionResource> {
    return (await request(
      `/api/v1/agent/sessions/${sessionId}` as keyof paths,
    )) as SessionResource;
  },

  async postMessage(sessionId: string, body: PostMessageBody): Promise<void> {
    await request(`/api/v1/agent/sessions/${sessionId}/messages` as keyof paths, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async bindTaskSpec(sessionId: string, body: BindTaskSpecBody): Promise<{ schema_version: string; missing_required_fields: string[] }> {
    return (await request(
      `/api/v1/agent/sessions/${sessionId}/task-spec` as keyof paths,
      { method: "POST", body: JSON.stringify(body) },
    )) as { schema_version: string; missing_required_fields: string[] };
  },

  async submitPlan(sessionId: string, body: SubmitPlanBody): Promise<{ plan_version: number; status: string }> {
    return (await request(
      `/api/v1/agent/sessions/${sessionId}/plan` as keyof paths,
      { method: "POST", body: JSON.stringify(body) },
    )) as { plan_version: number; status: string };
  },

  async approvePlan(sessionId: string, planVersion: number): Promise<void> {
    await request(
      `/api/v1/agent/sessions/${sessionId}/plan/approve` as keyof paths,
      { method: "POST", body: JSON.stringify({ plan_version: planVersion }) },
    );
  },

  async pause(sessionId: string): Promise<void> {
    await request(
      `/api/v1/agent/sessions/${sessionId}/actions/pause` as keyof paths,
      { method: "POST" },
    );
  },

  /** 事件恢复：按游标拉取错过的行动事件（SSE 重连前先补齐）。 */
  async fetchEvents(sessionId: string, since: number): Promise<{ events: Array<{ seq: number; turn: number; action_type: string; tool_name: string | null; status: string; summary: string }>; next_since: number }> {
    return (await request(
      `/api/v1/agent/sessions/${sessionId}/events?format=json&since=${since}` as keyof paths,
    )) as { events: Array<{ seq: number; turn: number; action_type: string; tool_name: string | null; status: string; summary: string }>; next_since: number };
  },

  async createTask(body: CreateTaskBody): Promise<{ task_id: string; status: string }> {
    return (await request("/api/v1/tasks", {
      method: "POST",
      body: JSON.stringify(body),
    })) as { task_id: string; status: string };
  },

  async getTask(taskId: string): Promise<{ task_id: string; status: string; steps: Array<{ index: number; type: string; status: string; error: string | null }> }> {
    return (await request(`/api/v1/tasks/${taskId}` as keyof paths)) as {
      task_id: string;
      status: string;
      steps: Array<{ index: number; type: string; status: string; error: string | null }>;
    };
  },

  async getClaimEvidence(claimId: string): Promise<ClaimEvidence> {
    return (await request(
      `/api/v1/claims/${claimId}/evidence` as keyof paths,
    )) as ClaimEvidence;
  },

  async getReviewQueue(): Promise<{ items: ReviewQueueItem[] }> {
    return (await request("/api/v1/reviews/queue" as keyof paths)) as {
      items: ReviewQueueItem[];
    };
  },

  async submitReviewDecision(body: ReviewDecisionBody): Promise<ReviewDecisionResult> {
    return (await request("/api/v1/reviews/decision" as keyof paths, {
      method: "POST",
      body: JSON.stringify(body),
    })) as ReviewDecisionResult;
  },

  async getAggregations(): Promise<{ aggregations: AggregationItem[] }> {
    return (await request(
      "/api/v1/verification/aggregations" as keyof paths,
    )) as { aggregations: AggregationItem[] };
  },

  async getCoverage(sessionId: string): Promise<CoverageResource> {
    return (await request(
      `/api/v1/agent/sessions/${sessionId}/coverage` as keyof paths,
    )) as CoverageResource;
  },

  async listClaims(status: string = "CANDIDATE"): Promise<{ claims: ClaimItem[] }> {
    return (await request(
      `/api/v1/claims?status=${encodeURIComponent(status)}` as keyof paths,
    )) as { claims: ClaimItem[] };
  },
};
