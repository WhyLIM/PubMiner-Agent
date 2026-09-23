/**
 * Agent Workspace feature store（PR-011：feature-local store 拆分第一步）。
 *
 * 服务端资源（session/claims/tasks）由 client 拉取，本 store 只持有
 * Agent Workspace 的工作状态，不与 legacy lib/store.ts 共享形状。
 */
import { create } from "zustand";

import {
  agentApi,
  AgentApiError,
  type ClaimItem,
  type SessionResource,
} from "@/shared/api/agent-client";

export type AgentPhase =
  | "idle"
  | "creating"
  | "clarifying"
  | "planning"
  | "running"
  | "paused"
  | "completed"
  | "limited"
  | "failed";

export type AgentEventItem = {
  seq: number;
  turn: number;
  action_type: string;
  tool_name: string | null;
  status: string;
  summary: string;
  receivedAt: number;
};

type AgentWorkspaceState = {
  sessionId: string | null;
  session: SessionResource | null;
  phase: AgentPhase;
  goalDraft: string;
  diseaseDraft: string;
  events: AgentEventItem[];
  claims: ClaimItem[];
  error: string | null;

  setGoalDraft: (value: string) => void;
  setDiseaseDraft: (value: string) => void;
  setError: (message: string | null) => void;

  createSession: () => Promise<void>;
  answerClarification: (answer: string) => Promise<void>;
  confirmTaskSpec: () => Promise<void>;
  submitAndApprovePlan: () => Promise<void>;
  runMiningTask: () => Promise<void>;
  pauseSession: () => Promise<void>;
  refreshSession: () => Promise<void>;
  refreshClaims: () => Promise<void>;
  appendEvents: (events: Omit<AgentEventItem, "receivedAt">[]) => void;
  reset: () => void;
};

function phaseOf(status: string): AgentPhase {
  switch (status) {
    case "CLARIFYING":
      return "clarifying";
    case "PLANNED":
      return "planning";
    case "RUNNING":
    case "SYNTHESIZING":
      return "running";
    case "WAITING_HUMAN":
      return "paused";
    case "PAUSED":
      return "paused";
    case "COMPLETED":
      return "completed";
    case "LIMITED":
      return "limited";
    case "FAILED":
    case "CANCELLED":
      return "failed";
    default:
      return "idle";
  }
}

export const useAgentWorkspace = create<AgentWorkspaceState>((set, get) => ({
  sessionId: null,
  session: null,
  phase: "idle",
  goalDraft: "",
  diseaseDraft: "",
  events: [],
  claims: [],
  error: null,

  setGoalDraft: (value) => set({ goalDraft: value }),
  setDiseaseDraft: (value) => set({ diseaseDraft: value }),
  setError: (message) => set({ error: message }),

  createSession: async () => {
    const { goalDraft } = get();
    if (!goalDraft.trim()) return;
    set({ phase: "creating", error: null });
    try {
      const created = await agentApi.createSession({ goal: goalDraft, user_id: "webui" });
      set({ sessionId: created.session_id, phase: "clarifying" });
      await get().refreshSession();
    } catch (error) {
      set({ error: describe(error) });
      set({ phase: "idle" });
    }
  },

  answerClarification: async (answer) => {
    const { sessionId } = get();
    if (!sessionId || !answer.trim()) return;
    try {
      await agentApi.postMessage(sessionId, { role: "user", content: answer, kind: "text", payload: {} });
      await get().refreshSession();
    } catch (error) {
      set({ error: describe(error) });
    }
  },

  confirmTaskSpec: async () => {
    const { sessionId, diseaseDraft } = get();
    if (!sessionId) return;
    try {
      await agentApi.bindTaskSpec(sessionId, {
        disease: diseaseDraft || null,
        task: "prognostic_biomarker",
        validation_requirement: "independent_validation",
        year_from: 2020,
      });
      await get().refreshSession();
    } catch (error) {
      set({ error: describe(error) });
    }
  },

  submitAndApprovePlan: async () => {
    const { sessionId } = get();
    if (!sessionId) return;
    try {
      const plan = await agentApi.submitPlan(sessionId, {
        rationale: "broad discovery then survival evidence",
        steps: [
          { id: "s1", action_type: "SEARCH", description: "broad discovery search", status: "pending" },
          { id: "s2", action_type: "EXTRACT", description: "biomarker extraction", status: "pending" },
        ],
      });
      await agentApi.approvePlan(sessionId, plan.plan_version);
      await get().refreshSession();
    } catch (error) {
      set({ error: describe(error) });
    }
  },

  runMiningTask: async () => {
    const { sessionId, diseaseDraft } = get();
    if (!sessionId) return;
    try {
      const task = await agentApi.createTask({
        session_id: sessionId,
        intents: [
          {
            name: "discovery",
            query: `${diseaseDraft || "pancreatic cancer"} prognostic biomarker`,
            max_results: 50,
          },
        ],
      });
      set({ phase: "running" });
      // MVP：任务同步执行，完成后拉取状态与 claims
      await agentApi.getTask(task.task_id);
      await Promise.all([get().refreshSession(), get().refreshClaims()]);
    } catch (error) {
      set({ error: describe(error) });
    }
  },

  pauseSession: async () => {
    const { sessionId } = get();
    if (!sessionId) return;
    try {
      await agentApi.pause(sessionId);
      await get().refreshSession();
    } catch (error) {
      set({ error: describe(error) });
    }
  },

  refreshSession: async () => {
    const { sessionId } = get();
    if (!sessionId) return;
    try {
      const session = await agentApi.getSession(sessionId);
      set({ session, phase: phaseOf(session.status) });
    } catch (error) {
      set({ error: describe(error) });
    }
  },

  refreshClaims: async () => {
    try {
      const { claims } = await agentApi.listClaims("CANDIDATE");
      set({ claims });
    } catch (error) {
      set({ error: describe(error) });
    }
  },

  appendEvents: (incoming) =>
    set((state) => {
      const known = new Set(state.events.map((e) => e.seq));
      const fresh = incoming
        .filter((e) => !known.has(e.seq))
        .map((e) => ({ ...e, receivedAt: Date.now() }));
      return fresh.length > 0 ? { events: [...state.events, ...fresh] } : {};
    }),

  reset: () =>
    set({
      sessionId: null,
      session: null,
      phase: "idle",
      events: [],
      claims: [],
      error: null,
    }),
}));

function describe(error: unknown): string {
  if (error instanceof AgentApiError) {
    return error.retryable ? `${error.message}（可重试）` : error.message;
  }
  return error instanceof Error ? error.message : String(error);
}
