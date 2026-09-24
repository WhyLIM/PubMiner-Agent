<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { agentApi, type EvidenceSpanItem, type ReviewQueueItem } from "@/api/client";
import SpanHighlight from "@/components/SpanHighlight.vue";

const queue = ref<ReviewQueueItem[]>([]);
const selected = ref<ReviewQueueItem | null>(null);
const spans = ref<EvidenceSpanItem[]>([]);
const revision = ref("");
const reason = ref("");
const message = ref<string | null>(null);
const submitting = ref(false);

const priorityTag = (priority: string) =>
  priority === "conflict" ? "danger" : priority === "needs_review" ? "warning" : "info";

async function loadQueue() {
  try {
    const { items } = await agentApi.getReviewQueue();
    queue.value = items;
  } catch (err) {
    message.value = err instanceof Error ? err.message : String(err);
  }
}

async function openClaim(item: ReviewQueueItem) {
  selected.value = item;
  spans.value = [];
  try {
    const evidence = await agentApi.getClaimEvidence(item.claim_id);
    spans.value = evidence.evidence ?? [];
  } catch (err) {
    message.value = err instanceof Error ? err.message : String(err);
  }
}

async function submit(decision: "ACCEPT" | "EDIT_ACCEPT" | "REJECT" | "NEEDS_REVIEW") {
  if (!selected.value) return;
  if (!reason.value.trim()) {
    message.value = "审核必须填写 reason（可追溯性要求）";
    return;
  }
  submitting.value = true;
  try {
    const result = await agentApi.submitReviewDecision({
      claim_id: selected.value.claim_id,
      decision,
      reviewer_id: "curator",
      reason: reason.value,
      expected_version: selected.value.version,
      revision:
        decision === "EDIT_ACCEPT" && revision.value.trim()
          ? { direction: revision.value.trim().toUpperCase() }
          : {},
    });
    ElMessage.success(`已提交 ${decision}：claim 现为 ${result.claim_status}（v${result.claim_version}）`);
    reason.value = "";
    revision.value = "";
    await loadQueue();
  } catch (err) {
    message.value = err instanceof Error ? err.message : String(err);
  } finally {
    submitting.value = false;
  }
}

onMounted(loadQueue);
</script>

<template>
  <div>
    <div class="pm-page-header">
      <h1>证据审核</h1>
      <p>左侧定位原文证据，右侧核定结论；所有决定可追溯，Agent 无法绕过此门禁</p>
    </div>

    <el-alert
      v-if="message"
      :title="message"
      type="info"
      :closable="true"
      class="page-alert"
      @close="message = null"
    />

    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>原文与证据定位</template>
          <el-empty v-if="!selected" description="从右侧选择一个待审结论" :image-size="72" />
          <el-empty
            v-else-if="spans.length === 0"
            description="该结论暂无已存储的 evidence span"
            :image-size="72"
          />
          <el-card
            v-for="item in spans"
            :key="item.evidence_id"
            shadow="never"
            class="evidence-card"
          >
            <p class="evidence-meta">
              {{ item.document_title || "（无标题）" }} · {{ item.span.section_path }}
              <el-tag
                size="small"
                :type="item.polarity === 'SUPPORT' ? 'success' : item.polarity === 'CONTRADICT' ? 'danger' : 'info'"
              >
                {{ item.polarity }}
              </el-tag>
              <span v-if="item.statistics?.effect_value" class="evidence-stat">
                {{ item.statistics.effect_measure }} = {{ item.statistics.effect_value }}
              </span>
            </p>
            <SpanHighlight
              :canonical-text="item.canonical_text ?? item.span.text"
              :start-char="item.span.start_char"
              :end-char="item.span.end_char"
            />
          </el-card>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never" class="queue-card">
          <template #header>
            <div class="card-header-row">
              <span>待审队列</span>
              <el-button text size="small" @click="loadQueue">刷新</el-button>
            </div>
          </template>
          <el-table
            :data="queue"
            size="small"
            highlight-current-row
            style="cursor: pointer"
            @row-click="openClaim"
          >
            <el-table-column label="优先级" width="110">
              <template #default="{ row }">
                <el-tag :type="priorityTag(row.priority)" size="small">{{ row.priority }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="结论" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="sig">{{ row.canonical_signature }}</span>
              </template>
            </el-table-column>
            <el-table-column label="支持/反对/无效应" width="150">
              <template #default="{ row }">
                {{ row.polarities?.SUPPORT ?? 0 }} / {{ row.polarities?.CONTRADICT ?? 0 }} /
                {{ row.polarities?.NO_EFFECT ?? 0 }}
              </template>
            </el-table-column>
            <el-table-column label="原因" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="queue-reason">{{ row.reasons?.join("；") }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card v-if="selected" shadow="never" class="editor-card">
          <template #header>
            <div class="card-header-row">
              <span>结论核定</span>
              <span class="sig">{{ selected.canonical_signature }}</span>
            </div>
          </template>
          <el-form label-width="90px" size="small">
            <el-form-item label="修订方向">
              <el-input
                v-model="revision"
                placeholder="HIGH / LOW / UNSPECIFIED（仅 Edit and Accept 使用）"
              />
            </el-form-item>
            <el-form-item label="审核理由" required>
              <el-input
                v-model="reason"
                type="textarea"
                :rows="2"
                placeholder="必填：说明判定依据，将随 before/after 一起存档"
              />
            </el-form-item>
          </el-form>
          <div class="decision-row">
            <el-button type="success" plain :disabled="submitting" @click="submit('ACCEPT')">Accept</el-button>
            <el-button type="primary" plain :disabled="submitting" @click="submit('EDIT_ACCEPT')">Edit & Accept</el-button>
            <el-button type="danger" plain :disabled="submitting" @click="submit('REJECT')">Reject</el-button>
            <el-button type="warning" plain :disabled="submitting" @click="submit('NEEDS_REVIEW')">Needs Review</el-button>
          </div>
          <p class="gate-note">
            Agent 只能产生 CANDIDATE；APPROVED / PUBLISHED 需要更高角色权限（发布门禁）。
          </p>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.page-alert {
  margin-bottom: 14px;
}

.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.evidence-card {
  margin-bottom: 10px;
  background: var(--pm-surface-2) !important;
}

.evidence-meta {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--pm-text-3);
}

.evidence-stat {
  margin-left: 8px;
  font-variant-numeric: tabular-nums;
  color: var(--pm-text-2);
}

.queue-card {
  margin-bottom: 16px;
}

.queue-reason {
  color: var(--pm-text-3);
  font-size: 12px;
}

.decision-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-top: 10px;
}

.gate-note {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--pm-text-3);
}
</style>
