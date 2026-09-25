<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  agentApi,
  AgentApiError,
  type ClaimItem,
  type EvidenceSpanItem,
  type SessionResource,
} from "@/api/client";
import SpanHighlight from "@/components/SpanHighlight.vue";

const SESSION_KEY = "pubminer-session-id";

const goalDraft = ref("");
const diseaseDraft = ref("");
const answerDraft = ref("");
const sessionId = ref<string | null>(localStorage.getItem(SESSION_KEY));
const session = ref<SessionResource | null>(null);
const phase = ref<"idle" | "working" | "clarifying" | "planning" | "running" | "paused" | "completed" | "limited" | "failed">(
  sessionId.value ? "working" : "idle",
);
const events = ref<Array<{ seq: number; turn: number; action_type: string; tool_name: string | null; status: string; summary: string }>>([]);
const claims = ref<ClaimItem[]>([]);
const spans = ref<EvidenceSpanItem[]>([]);
const selectedClaim = ref<string | null>(null);
const coverage = ref<{
  support_count: number;
  contradict_count: number;
  no_effect_count: number;
  independent_validation_found: boolean;
  unresolved_gaps: string[];
} | null>(null);
const error = ref<string | null>(null);
const lastTaskId = ref<string | null>(null);
const recentSessions = ref<Array<{ session_id: string; goal: string; status: string }>>([]);
const runStep = ref("");
let pollTimer: ReturnType<typeof setInterval> | null = null;

function describe(err: unknown): string {
  if (err instanceof AgentApiError) return err.retryable ? `${err.message}（可重试）` : err.message;
  return err instanceof Error ? err.message : String(err);
}

function phaseOf(status: string): typeof phase.value {
  const map: Record<string, typeof phase.value> = {
    CLARIFYING: "clarifying", PLANNED: "planning", RUNNING: "running",
    SYNTHESIZING: "running", WAITING_HUMAN: "paused", PAUSED: "paused",
    COMPLETED: "completed", LIMITED: "limited", FAILED: "failed", CANCELLED: "failed",
  };
  return map[status] ?? "idle";
}

async function refreshSession() {
  if (!sessionId.value) return;
  try {
    session.value = await agentApi.getSession(sessionId.value);
    phase.value = phaseOf(session.value.status);
  } catch (err) {
    if (err instanceof AgentApiError && err.status === 404) {
      localStorage.removeItem(SESSION_KEY);
      sessionId.value = null;
      session.value = null;
    } else {
      error.value = describe(err);
    }
  }
}

async function pollEvents() {
  if (!sessionId.value) return;
  try {
    const { events: fresh } = await agentApi.fetchEvents(sessionId.value, events.value.length);
    for (const e of fresh) events.value.push(e);
  } catch {
    /* 静默重试 */
  }
}

function startEventLoop() {
  stopEventLoop();
  pollTimer = setInterval(pollEvents, 2500);
  void pollEvents();
}

function stopEventLoop() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

async function refreshClaims() {
  try {
    claims.value = (await agentApi.listClaims("CANDIDATE")).claims;
  } catch { /* 静默 */ }
}

async function refreshCoverage() {
  if (!sessionId.value) return;
  try {
    coverage.value = await agentApi.getCoverage(sessionId.value);
  } catch { /* 静默 */ }
}

async function loadRecentSessions() {
  try {
    recentSessions.value = (await agentApi.listSessions(10)).sessions;
  } catch { /* 静默 */ }
}

function switchSession(id: string) {
  sessionId.value = id;
  localStorage.setItem(SESSION_KEY, id);
  session.value = null;
  events.value = [];
  claims.value = [];
  spans.value = [];
  coverage.value = null;
  phase.value = "working";
  void refreshSession().then(() => {
    phase.value = phaseOf(session.value?.status ?? "idle");
    startEventLoop();
  });
}

function newSession() {
  stopEventLoop();
  localStorage.removeItem(SESSION_KEY);
  sessionId.value = null;
  session.value = null;
  events.value = [];
  claims.value = [];
  spans.value = [];
  coverage.value = null;
  lastTaskId.value = null;
  selectedClaim.value = null;
  phase.value = "idle";
  error.value = null;
}

/** 一键研究：创建会话 → LLM 解析目标绑定约束 → 自动批准计划 → 执行检索 → 轮询完成。 */
async function startResearch() {
  if (!goalDraft.value.trim()) return;
  error.value = null;
  phase.value = "working";
  const setStep = (s: string) => (runStep.value = s);
  try {
    setStep("创建会话");
    const created = await agentApi.createSession({ goal: goalDraft.value, user_id: "webui" });
    sessionId.value = created.session_id;
    localStorage.setItem(SESSION_KEY, created.session_id);
    startEventLoop();

    setStep("解析目标（LLM 绑定约束）");
    let specFields: Record<string, unknown> = {};
    try {
      specFields = (await agentApi.parseGoal(created.session_id)).fields;
    } catch (err) {
      if (err instanceof AgentApiError && err.status === 503) {
        throw new Error("未配置 LLM，无法自动解析目标；请在「手动控制」中填写约束");
      }
      throw err;
    }
    diseaseDraft.value = String(specFields.disease ?? "");

    setStep("批准计划");
    await refreshSession();
    const plan = await agentApi.submitPlan(created.session_id, {
      rationale: "auto: discovery search -> extract -> verify",
      steps: [
        { id: "s1", action_type: "SEARCH", description: "discovery search", status: "pending" },
        { id: "s2", action_type: "EXTRACT", description: "biomarker extraction", status: "pending" },
      ],
    });
    await agentApi.approvePlan(created.session_id, plan.plan_version);

    setStep("检索与抽取");
    const task = await agentApi.runSession(created.session_id, {
      disease: (specFields.disease as string) ?? null,
      task: (specFields.task as string) ?? "prognostic_biomarker",
      year_from: (specFields.year_from as number) ?? null,
      max_results: 5,
    });
    lastTaskId.value = task.task_id;

    setStep("汇总证据");
    const detail = await agentApi.getTask(task.task_id);
    if (detail.status === "FAILED") {
      throw new Error("任务失败：可点击「从失败步恢复」重试");
    }
    await Promise.all([refreshSession(), refreshClaims(), refreshCoverage()]);
    phase.value = phaseOf(session.value?.status ?? "COMPLETED");
    runStep.value = "";
    ElMessage.success("研究完成，结论已生成");
  } catch (err) {
    runStep.value = "";
    error.value = describe(err);
    phase.value = "failed";
    await refreshSession().catch(() => undefined);
  }
}

async function resumeTask() {
  if (!lastTaskId.value) return;
  try {
    phase.value = "running";
    await agentApi.resumeTask(lastTaskId.value);
    const detail = await agentApi.getTask(lastTaskId.value);
    await Promise.all([refreshSession(), refreshClaims(), refreshCoverage()]);
    if (detail.status === "FAILED") throw new Error("仍失败，请检查 LLM/网络配置");
    ElMessage.success("恢复成功");
  } catch (err) {
    error.value = describe(err);
  } finally {
    await refreshSession();
  }
}

async function openClaim(claim: ClaimItem) {
  selectedClaim.value = claim.claim_id;
  try {
    spans.value = (await agentApi.getClaimEvidence(claim.claim_id)).evidence ?? [];
  } catch (err) {
    error.value = describe(err);
  }
}

function claimRowClass({ row }: { row: ClaimItem }): string {
  return row.claim_id === selectedClaim.value ? "selected-row" : "";
}

async function sendClarification() {
  if (!sessionId.value || !answerDraft.value.trim()) return;
  try {
    await agentApi.postMessage(sessionId.value, {
      role: "user", content: answerDraft.value, kind: "text", payload: {},
    });
    answerDraft.value = "";
  } catch (err) {
    error.value = describe(err);
  }
}

async function bindManualSpec() {
  if (!sessionId.value || !diseaseDraft.value.trim()) return;
  try {
    await agentApi.bindTaskSpec(sessionId.value, {
      disease: diseaseDraft.value, task: "prognostic_biomarker",
      validation_requirement: "independent_validation", year_from: 2020,
    });
    await refreshSession();
    ElMessage.success("TaskSpec 已绑定");
  } catch (err) {
    error.value = describe(err);
  }
}

async function pauseSession() {
  if (!sessionId.value) return;
  try {
    await agentApi.pause(sessionId.value);
    await refreshSession();
  } catch (err) {
    error.value = describe(err);
  }
}

onMounted(async () => {
  if (sessionId.value) {
    await refreshSession();
    if (session.value) {
      phase.value = phaseOf(session.value.status);
      startEventLoop();
      void refreshClaims();
    } else {
      sessionId.value = null;
      phase.value = "idle";
    }
  }
  void loadRecentSessions();
});
onBeforeUnmount(stopEventLoop);

const statusTag = (status: string) =>
  status === "COMPLETED" || status === "REVIEW_READY" ? "success"
  : status === "FAILED" ? "danger"
  : status === "LIMITED" || status === "WAITING_HUMAN" || status === "PAUSED" ? "warning"
  : "info";
</script>

<template>
  <div>
    <div class="pm-page-header">
      <h1>Agent 工作台</h1>
      <p>一句话目标，Agent 自动完成 澄清 → 计划 → 检索 → 抽取 → 验证 → 结论</p>
    </div>

    <!-- 一键研究 -->
    <el-card shadow="never" class="start-card">
      <el-input
        v-model="goalDraft"
        type="textarea"
        :rows="3"
        placeholder="输入研究目标，例如：寻找 2020 年以来胰腺癌预后 biomarker，并确认是否存在独立队列验证"
      />
      <div class="start-row">
        <el-button
          type="primary"
          :disabled="phase !== 'idle' || !goalDraft.trim()"
          @click="startResearch"
        >
          开始研究
        </el-button>
        <span v-if="runStep" class="run-step">{{ runStep }}…</span>
        <el-button v-if="sessionId" size="small" text @click="newSession">新建会话</el-button>
        <el-select
          v-if="recentSessions.length"
          v-model="sessionId"
          size="small"
          style="margin-left: auto; width: 280px"
          placeholder="继续历史会话"
          @change="(id: string) => switchSession(id)"
        >
          <el-option
            v-for="s in recentSessions"
            :key="s.session_id"
            :label="`${s.goal.slice(0, 28)}（${s.status}）`"
            :value="s.session_id"
          />
        </el-select>
      </div>
      <el-alert v-if="error" :title="error" type="error" :closable="false" style="margin-top: 10px" />
      <div v-if="error && lastTaskId" style="margin-top: 8px">
        <el-button size="small" type="warning" @click="resumeTask">从失败步恢复</el-button>
      </div>
    </el-card>

    <el-row :gutter="16">
      <!-- 左：会话状态 + 覆盖 -->
      <el-col :span="7">
        <el-card shadow="never">
          <template #header>
            <div class="card-header-row">
              <span>会话状态</span>
              <el-tag v-if="session" :type="statusTag(session.status)" size="small">{{ session.status }}</el-tag>
            </div>
          </template>
          <template v-if="session">
            <el-descriptions :column="1" size="small">
              <el-descriptions-item label="目标">{{ session.goal }}</el-descriptions-item>
              <el-descriptions-item v-if="session.task_spec" label="疾病">
                {{ session.task_spec.disease }}
              </el-descriptions-item>
              <el-descriptions-item v-if="session.stop_reason" label="停止原因">
                {{ session.stop_reason.kind }} — {{ session.stop_reason.message }}
              </el-descriptions-item>
            </el-descriptions>

            <el-collapse style="margin-top: 10px">
              <el-collapse-item title="手动控制（高级）" name="manual">
                <el-input v-model="diseaseDraft" size="small" placeholder="疾病（如 pancreatic cancer）" />
                <el-button
                  style="width: 100%; margin-top: 6px" size="small"
                  :disabled="!diseaseDraft.trim()" @click="bindManualSpec"
                >
                  手动绑定 TaskSpec
                </el-button>
                <el-input v-model="answerDraft" type="textarea" :rows="2" size="small" style="margin-top: 10px" />
                <el-button
                  style="width: 100%; margin-top: 6px" size="small"
                  :disabled="!answerDraft.trim()" @click="sendClarification"
                >
                  发送澄清说明
                </el-button>
                <el-button style="width: 100%; margin-top: 6px" size="small" @click="pauseSession">
                  暂停会话
                </el-button>
              </el-collapse-item>
            </el-collapse>
          </template>
          <el-empty v-else description="尚无活动会话" :image-size="60" />
        </el-card>

        <el-card v-if="coverage" shadow="never" style="margin-top: 16px">
          <template #header>覆盖矩阵</template>
          <div class="pm-mini-stats" style="font-size: 13px">
            <span class="s-up">支持 {{ coverage.support_count }}</span>
            <span class="s-down">反对 {{ coverage.contradict_count }}</span>
            <span class="s-flat">无效应 {{ coverage.no_effect_count }}</span>
          </div>
          <p style="margin: 8px 0 0; font-size: 12px; color: var(--pm-text-3)">
            独立队列验证：
            <el-tag size="small" :type="coverage.independent_validation_found ? 'success' : 'warning'">
              {{ coverage.independent_validation_found ? "已发现" : "未发现" }}
            </el-tag>
          </p>
          <ul
            v-if="coverage.unresolved_gaps.length"
            style="margin: 8px 0 0; padding-left: 18px; font-size: 12px; color: var(--pm-text-3)"
          >
            <li v-for="gap in coverage.unresolved_gaps" :key="gap">{{ gap }}</li>
          </ul>
        </el-card>
      </el-col>

      <!-- 中：计划与行动 -->
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>计划与行动（真实 workflow 事件）</template>
          <template v-if="session">
            <el-collapse>
              <el-collapse-item v-for="plan in session.plans" :key="plan.version" :name="plan.version">
                <template #title>
                  <span class="plan-title">计划 v{{ plan.version }}</span>
                  <el-tag size="small" class="plan-tag" :type="plan.approved_by_human ? 'success' : 'info'">
                    {{ plan.approved_by_human ? "已批准" : "待批准" }}
                  </el-tag>
                  <span class="plan-rationale">{{ plan.rationale }}</span>
                </template>
                <el-tag v-for="step in plan.steps" :key="step.id" size="small" style="margin-right: 6px">
                  {{ step.id }}: {{ step.action_type }}
                </el-tag>
              </el-collapse-item>
            </el-collapse>

            <p class="section-label" style="margin-top: 14px">行动轨迹</p>
            <el-timeline class="event-timeline">
              <el-timeline-item
                v-for="event in [...events].reverse()"
                :key="event.seq"
                :type="event.status === 'succeeded' ? 'success' : event.status === 'failed' ? 'danger' : 'info'"
                :timestamp="`#${event.seq} · turn ${event.turn}`"
              >
                <b>{{ event.action_type }}</b>
                <span v-if="event.tool_name" class="event-tool">{{ event.tool_name }}</span>
                <div v-if="event.summary" class="event-summary">{{ event.summary }}</div>
              </el-timeline-item>
              <el-timeline-item v-if="events.length === 0" timestamp="等待行动…" type="info" />
            </el-timeline>
          </template>
          <el-empty v-else description="开始研究后此处展示真实事件流" :image-size="72" />
        </el-card>
      </el-col>

      <!-- 右：结论与证据 -->
      <el-col :span="7">
        <el-card shadow="never">
          <template #header>
            <div class="card-header-row">
              <span>Candidate Claims 与证据</span>
              <el-button text size="small" @click="refreshClaims">刷新</el-button>
            </div>
          </template>
          <el-table
            :data="claims"
            size="small"
            :show-header="false"
            style="cursor: pointer"
            :row-class-name="claimRowClass"
            @row-click="openClaim"
          >
            <el-table-column>
              <template #default="{ row }">
                <span class="sig">{{ row.canonical_signature }}</span>
                <div class="pm-mini-stats" style="margin-top: 4px">
                  <span class="s-up">支持 {{ row.polarities?.SUPPORT ?? 0 }}</span>
                  <span class="s-down">反对 {{ row.polarities?.CONTRADICT ?? 0 }}</span>
                  <span class="s-flat">无效应 {{ row.polarities?.NO_EFFECT ?? 0 }}</span>
                  <el-tag v-if="row.polarities?.CONTRADICT" type="danger" size="small">冲突</el-tag>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="claims.length === 0" description="尚无候选结论" :image-size="60" />

          <template v-if="spans.length">
            <el-divider style="margin: 12px 0" />
            <p class="section-label">原文证据（固定 offset 定位）</p>
            <el-card v-for="item in spans" :key="item.evidence_id" shadow="never" class="evidence-card">
              <p class="evidence-meta">
                {{ item.document_title || "（无标题）" }} · {{ item.span.section_path }}
                <el-tag
                  size="small"
                  :type="item.polarity === 'SUPPORT' ? 'success' : item.polarity === 'CONTRADICT' ? 'danger' : 'info'"
                >
                  {{ item.polarity }}
                </el-tag>
              </p>
              <SpanHighlight
                :canonical-text="item.canonical_text ?? item.span.text"
                :start-char="item.span.start_char"
                :end-char="item.span.end_char"
              />
            </el-card>
          </template>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.start-card {
  margin-bottom: 16px;
}

.start-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
}

.run-step {
  font-size: 13px;
  color: var(--pm-accent);
  font-weight: 500;
}

.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.section-label {
  margin: 14px 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--pm-text-1);
}

.plan-title {
  font-weight: 600;
}

.plan-tag {
  margin-left: 8px;
}

.plan-rationale {
  color: var(--pm-text-3);
  font-size: 12px;
  margin-left: 8px;
}

.event-timeline {
  max-height: 320px;
  overflow-y: auto;
  padding-left: 4px;
}

.event-tool {
  color: var(--pm-text-3);
}

.event-summary {
  color: var(--pm-text-2);
  font-size: 12px;
}

.evidence-card {
  margin-bottom: 8px;
  background: var(--pm-surface-2) !important;
}

.evidence-meta {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--pm-text-3);
}

:deep(.selected-row) {
  --el-table-tr-bg-color: var(--pm-accent-soft);
}
</style>
