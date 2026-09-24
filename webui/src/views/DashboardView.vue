<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  agentApi,
  type AggregationItem,
  type ClaimItem,
  type ReviewQueueItem,
  type TaskListItem,
} from "@/api/client";
import { useChart } from "@/composables/useChart";

const router = useRouter();
const loading = ref(false);
const claims = ref<ClaimItem[]>([]);
const aggregations = ref<AggregationItem[]>([]);
const queue = ref<ReviewQueueItem[]>([]);
const tasks = ref<TaskListItem[]>([]);

const polarityTotals = computed(() => {
  const totals = { SUPPORT: 0, CONTRADICT: 0, NO_EFFECT: 0, UNCERTAIN: 0 };
  for (const agg of aggregations.value) {
    totals.SUPPORT += agg.support_count;
    totals.CONTRADICT += agg.contradict_count;
    totals.NO_EFFECT += agg.no_effect_count;
    totals.UNCERTAIN += agg.uncertain_count;
  }
  return totals;
});

const priorityCounts = computed(() => {
  const counts: Record<string, number> = {};
  for (const item of queue.value) {
    counts[item.priority] = (counts[item.priority] ?? 0) + 1;
  }
  return Object.entries(counts).map(([name, value]) => ({ name, value }));
});

const polarityChartEl = ref<HTMLElement>();
const polarityOption = computed(() => ({
  grid: { left: 8, right: 16, top: 28, bottom: 0, containLabel: true },
  tooltip: { trigger: "axis" as const },
  xAxis: { type: "category" as const, data: ["支持", "反对", "无效应", "不确定"] },
  yAxis: { type: "value" as const, minInterval: 1 },
  series: [
    {
      type: "bar" as const,
      barWidth: 42,
      itemStyle: { borderRadius: [6, 6, 0, 0] },
      data: [
        polarityTotals.value.SUPPORT,
        polarityTotals.value.CONTRADICT,
        polarityTotals.value.NO_EFFECT,
        polarityTotals.value.UNCERTAIN,
      ],
      color: "#4f7cff",
    },
  ],
}));
useChart(polarityChartEl, () => polarityOption.value);

const priorityChartEl = ref<HTMLElement>();
const priorityOption = computed(() => ({
  tooltip: { trigger: "item" as const },
  legend: { bottom: 0, itemWidth: 10, itemHeight: 10 },
  series: [
    {
      type: "pie" as const,
      radius: ["45%", "70%"],
      itemStyle: { borderRadius: 6 },
      label: { show: false },
      data: priorityCounts.value.map((d, i) => ({
        ...d,
        itemStyle: { color: ["#e2545c", "#e6a23c", "#8a97ad"][i % 3] },
      })),
    },
  ],
}));
useChart(priorityChartEl, () => priorityOption.value);

async function load() {
  loading.value = true;
  try {
    const [agg, q, c, t] = await Promise.all([
      agentApi.getAggregations(),
      agentApi.getReviewQueue(),
      agentApi.listClaims("CANDIDATE"),
      agentApi.listTasks(10),
    ]);
    aggregations.value = agg.aggregations;
    queue.value = q.items;
    claims.value = c.claims;
    tasks.value = t.tasks;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div v-loading="loading">
    <div class="pm-page-header">
      <h1>总览</h1>
      <p>证据库现状、跨论文验证聚合与待审队列</p>
    </div>

    <el-row :gutter="16">
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="pm-stat-value">{{ aggregations.length }}</div>
          <div class="pm-stat-label">结论聚类（含全部状态）</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="pm-stat-value">{{ claims.length }}</div>
          <div class="pm-stat-label">CANDIDATE 结论</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="pm-stat-value">{{ polarityTotals.SUPPORT }}</div>
          <div class="pm-stat-label">支持证据</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="pm-stat-value">{{ queue.length }}</div>
          <div class="pm-stat-label">待审核队列</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>证据极性分布（跨论文聚合）</template>
          <div ref="polarityChartEl" style="height: 260px" />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>审核队列优先级</template>
          <div ref="priorityChartEl" style="height: 260px" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>最近挖掘任务</span>
              <el-button text size="small" @click="router.push('/agent')">去工作台 →</el-button>
            </div>
          </template>
          <el-table :data="tasks" size="small" :show-header="true">
            <el-table-column prop="task_id" label="Task" width="120">
              <template #default="{ row }">
                <span class="sig">{{ row.task_id.slice(0, 8) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="kind" label="类型" width="90" />
            <el-table-column prop="status" label="状态" width="130">
              <template #default="{ row }">
                <el-tag :type="row.status === 'REVIEW_READY' ? 'success' : row.status === 'FAILED' ? 'danger' : 'info'" size="small">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间">
              <template #default="{ row }">
                {{ new Date(row.created_at).toLocaleString() }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>待审 TOP（冲突优先）</template>
          <el-table
            :data="queue.slice(0, 6)"
            size="small"
            @row-click="(row: ReviewQueueItem) => router.push('/review')"
            style="cursor: pointer"
          >
            <el-table-column label="结论" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="sig">{{ row.canonical_signature }}</span>
              </template>
            </el-table-column>
            <el-table-column label="优先级" width="110">
              <template #default="{ row }">
                <el-tag :type="row.priority === 'conflict' ? 'danger' : row.priority === 'needs_review' ? 'warning' : 'info'" size="small">
                  {{ row.priority }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="evidence_count" label="证据" width="70" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>
