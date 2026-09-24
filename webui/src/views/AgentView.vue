<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  agentApi,
  AgentApiError,
  type ClaimItem,
  type SessionResource,
} from "@/api/client";
import SpanHighlight from "@/components/SpanHighlight.vue";

const goalDraft = ref("");
const diseaseDraft = ref("");
const answerDraft = ref("");
const sessionId = ref<string | null>(null);
const session = ref<SessionResource | null>(null);
const phase = ref<"idle" | "creating" | "clarifying" | "planning" | "running" | "paused" | "completed" | "limited" | "failed">("idle");
const events = ref<Array<{ seq: number; turn: number; action_type: string; tool_name: string | null; status: string; summary: string }>>([]);
const claims = ref<ClaimItem[]>([]);
const spans = ref<import("@/api/client").EvidenceSpanItem[]>([]);
const selectedClaim = ref<string | null>(null);
const error = ref<string | null>(null);
let eventCursor = 0;
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
    error.value = describe(err);
  }
}

async function pollEvents() {
  if (!sessionId.value) return;
  try {
    const { events: fresh } = await agentApi.fetchEvents(sessionId.value, eventCursor);
    for (const e of fresh) {
      if (e.seq > eventCursor) {
        events.value.push(e);
        eventCursor = e.seq;
      }
    }
  } catch {
    /* 轮询失败静默重试 */
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

onMounted(() => {
  void agentApi.listClaims("CANDIDATE").then((r) => (claims.value = r.claims));
});
onBeforeUnmount(stopEventLoop);

async function createSession() {
  if (!goalDraft.value.trim()) return;
  phase.value = "creating";
  error.value = null;
  try {
    const created = await agentApi.createSession({ goal: goalDraft.value, user_id: "webui" });
    sessionId.value = created.session_id;
    phase.value = "clarifying";
    await refreshSession();
    startEventLoop();
  } catch (err) {
    error.value = describe(err);
    phase.value = "idle";
  }
}

async function confirmTaskSpec() {
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

async function sendClarification() {
  if (!sessionId.value || !answerDraft.value.trim()) return;
  try {
    await agentApi.postMessage(sessionId.value, { role: "user", content: answerDraft.value, kind: "text", payload: {} });
    answerDraft.value = "";
    ElMessage.success("已发送");
  } catch (err) {
    error.value = describe(err);
  }
}

async function submitAndApprovePlan() {
  if (!sessionId.value) return;
  try {
    const plan = await agentApi.submitPlan(sessionId.value, {
      rationale: "广撒网检索 → 生存证据 → 独立验证",
      steps: [
        { id: "s1", action_type: "SEARCH", description: "broad discovery", status: "pending" },
        { id: "s2", action_type: "EXTRACT", description: "biomarker extraction", status: "pending" },
      ],
    });
    await agentApi.approvePlan(sessionId.value, plan.plan_version);
    await refreshSession();
    ElMessage.success(`计划 v${plan.plan_version} 已批准`);
  } catch (err) {
    error.value = describe(err);
  }
}

async function runMiningTask() {
  if (!sessionId.value) return;
  phase.value = "running";
  try {
    const task = await agentApi.createTask({
      session_id: sessionId.value,
      intents: [{ name: "discovery", query: `${diseaseDraft.value || "pancreatic cancer"} prognostic biomarker`, max_results: 5 }],
    });
    const detail = await agentApi.getTask(task.task_id);
    if (detail.status === "FAILED") {
      error.value = "任务失败：可在总览页查看步骤详情后重试";
    }
    await Promise.all([refreshSession(), agentApi.listClaims("CANDIDATE").then((r) => (claims.value = r.claims))]);
    if (detail.status !== "FAILED") ElMessage.success("任务完成，结论已就绪");
  } catch (err) {
    error.value = describe(err);
  } finally {
    await refreshSession();
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

async function openClaim(claim: ClaimItem) {
  selectedClaim.value = claim.claim_id;
  try {
    const evidence = await agentApi.getClaimEvidence(claim.claim_id);
    spans.value = evidence.evidence ?? [];
  } catch (err) {
    error.value = describe(err);
  }
}

function claimRowClass({ row }: { row: ClaimItem }): string {
  return row.claim_id === selectedClaim.value ? "selected-row" : "";
}

const statusTag = (status: string) =>
  status === "COMPLETED" || status === "REVIEW_READY" ? "success"
  : status === "FAILED" ? "danger"
  : status === "LIMITED" ? "warning"
  : status === "WAITING_HUMAN" || status === "PAUSED" ? "warning"
  : "info";
</script>

<template>
  <div>
    <div class="pm-page-header">
      <h1>Agent 工作台</h1>
      <p>提出研究目标，Agent 澄清约束、制定计划并受控执行；每一步可追溯</p>
    </div>

    <el-row :gutter="16">
      <!-- 左：会话 -->
      <el-col :span="7">
        <el-card shadow="never">
          <template #header>研究目标</template>
          <el-input
            v-model="goalDraft" type="textarea" :rows="4"
            placeholder="例：寻找 2020 年以来胰腺癌预后 biomarker，并确认是否存在独立队列验证"
          />
          <el-button
            style="width: 100%; margin-top: 10px" type="primary"
            :disabled="phase !== 'idle' || !goalDraft.trim()" @click="createSession"
          >
            创建研究会话
          </el-button>

          <el-alert v-if="error" :title="error" type="error" :closable="false" style="margin-top: 10px" />

          <template v-if="session">
            <el-descriptions :column="1" size="small" style="margin-top: 14px">
              <el-descriptions-item label="状态">
                <el-tag :type="statusTag(session.status)" size="small">{{ session.status }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="轮次">{{ session.turn }}</el-descriptions-item>
              <el-descriptions-item v-if="session.stop_reason" label="停止原因">
                {{ session.stop_reason.kind }} — {{ session.stop_reason.message }}
              </el-descriptions-item>
            </el-descriptions>

            <el-divider style="margin: 12px 0" />
            <p style="margin: 0 0 6px; font-size: 13px; font-weight: 600">澄清约束（疾病）</p>
            <el-input v-model="diseaseDraft" placeholder="如 pancreatic cancer / PDAC" size="small" />
            <el-button style="width: 100%; margin-top: 8px" size="small" :disabled="!diseaseDraft.trim()" @click="confirmTaskSpec">
              绑定 TaskSpec
            </el-button>

            <p style="margin: 12px 0 6px; font-size: 13px; font-weight: 600">追问 / 补充</p>
            <el-input v-model="answerDraft" type="textarea" :rows="2" size="small" />
            <el-button style="width: 100%; margin-top: 8px" size="small" :disabled="!answerDraft.trim()" @click="sendClarification">
              发送给 Agent
            </el-button>
          </template>
        </el-card>
      </el-col>

      <!-- 中：计划与行动 -->
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>计划与行动</span>
              <div v-if="session" style="display: flex; gap: 8px">
                <el-button size="small" :disabled="phase === 'running'" @click="submitAndApprovePlan">批准计划</el-button>
                <el-button size="small" type="primary" :disabled="phase !== 'planning'" @click="runMiningTask">
                  执行检索任务
                </el-button>
                <el-button size="small" @click="pauseSession">暂停</el-button>
              </div>
            </div>
          </template>

          <template v-if="session">
            <el-collapse>
              <el-collapse-item
                v-for="plan in session.plans" :key="plan.version"
                :name="plan.version"
              >
                <template #title>
                  <span style="font-weight: 600">计划 v{{ plan.version }}</span>
                  <el-tag size="small" style="margin-left: 8px" :type="plan.approved_by_human ? 'success' : 'info'">
                    {{ plan.approved_by_human ? "已批准" : "待批准" }}
                  </el-tag>
                  <span style="color: #8a97ad; font-size: 12px; margin-left: 8px">{{ plan.rationale }}</span>
                </template>
                <el-tag
                  v-for="step in plan.steps" :key="step.id" size="small"
                  style="margin-right: 6px"
                >
                  {{ step.id }}: {{ step.action_type }}
                </el-tag>
              </el-collapse-item>
            </el-collapse>

            <p style="margin: 14px 0 6px; font-size: 13px; font-weight: 600">行动轨迹（真实 workflow 事件）</p>
            <el-timeline style="max-height: 320px; overflow-y: auto; padding-left: 4px">
              <el-timeline-item
                v-for="event in [...events].reverse()" :key="event.seq"
                :type="event.status === 'succeeded' ? 'success' : event.status === 'failed' ? 'danger' : 'info'"
                :timestamp="`#${event.seq} · turn ${event.turn}`"
              >
                <b>{{ event.action_type }}</b>
                <span v-if="event.tool_name" style="color: #8a97ad"> · {{ event.tool_name }}</span>
                <div v-if="event.summary" style="color: #6b7a90; font-size: 12px">{{ event.summary }}</div>
              </el-timeline-item>
              <el-timeline-item v-if="events.length === 0" timestamp="等待行动…" type="info" />
            </el-timeline>
          </template>
          <el-empty v-else description="先在左侧创建研究会话" :image-size="72" />
        </el-card>
      </el-col>

      <!-- 右：结论与证据 -->
      <el-col :span="7">
        <el-card shadow="never">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>Candidate Claims 与证据</span>
              <el-button text size="small" @click="agentApi.listClaims('CANDIDATE').then((r) => (claims = r.claims))">
                刷新
              </el-button>
            </div>
          </template>
          <el-table :data="claims" size="small" :show-header="false" style="cursor: pointer"
                    @row-click="openClaim"
                    :row-class-name="claimRowClass">
            <el-table-column>
              <template #default="{ row }">
                <span class="sig">{{ row.canonical_signature }}</span>
                <div style="margin-top: 4px; font-size: 12px; color: #6b7a90">
                  支持 {{ row.polarities?.SUPPORT ?? 0 }} · 反对 {{ row.polarities?.CONTRADICT ?? 0 }} ·
                  无效应 {{ row.polarities?.NO_EFFECT ?? 0 }}
                  <el-tag v-if="row.polarities?.CONTRADICT" type="danger" size="small" style="margin-left: 4px">冲突</el-tag>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="claims.length === 0" description="暂无候选结论，先执行一次检索任务" :image-size="60" />

          <template v-if="spans.length">
            <el-divider style="margin: 12px 0" />
            <p style="margin: 0 0 8px; font-size: 13px; font-weight: 600">原文证据（固定 offset 定位）</p>
            <el-card v-for="item in spans" :key="item.evidence_id" shadow="never" style="margin-bottom: 8px">
              <p style="margin: 0 0 6px; font-size: 12px; color: #8a97ad">
                {{ item.document_title || "（无标题）" }} · {{ item.span.section_path }} ·
                <el-tag size="small"
                        :type="item.polarity === 'SUPPORT' ? 'success' : item.polarity === 'CONTRADICT' ? 'danger' : 'info'">
                  {{ item.polarity }}
                </el-tag>
              </p>
              <SpanHighlight
                :canonical-text="item.canonical_text ?? item.span.text"
                :start-char="item.span.start_char" :end-char="item.span.end_char"
              />
            </el-card>
          </template>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
:deep(.selected-row) {
  --el-table-tr-bg-color: #f0f5ff;
}
</style>
