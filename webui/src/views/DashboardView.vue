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
import { isDark } from "@/composables/useTheme";

const router = useRouter();
const loading = ref(true);
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

// 图表颜色跟随明暗主题（useChart 对 option 深度监听，主题切换即重绘）
const axisText = computed(() => (isDark.value ? "#8ea3c4" : "#8592a8"));
const gridLine = computed(() => (isDark.value ? "rgba(142, 163, 196, 0.16)" : "rgba(133, 146, 168, 0.18)"));
const barColor = computed(() => (isDark.value ? "#6b93ff" : "#3d6fed"));

const polarityChartEl = ref<HTMLElement>();
const polarityOption = computed(() => ({
  grid: { left: 8, right: 16, top: 28, bottom: 0, containLabel: true },
  tooltip: { trigger: "axis" as const },
  xAxis: {
    type: "category" as const,
    data: ["支持", "反对", "无效应", "不确定"],
    axisLabel: { color: axisText.value },
    axisLine: { lineStyle: { color: gridLine.value } },
  },
  yAxis: {
    type: "value" as const,
    minInterval: 1,
    axisLabel: { color: axisText.value },
    splitLine: { lineStyle: { color: gridLine.value } },
  },
  series: [
    {
      type: "bar" as const,
      barWidth: 42,
      itemStyle: { borderRadius: [6, 6, 0, 0], color: barColor.value },
      data: [
        polarityTotals.value.SUPPORT,
        polarityTotals.value.CONTRADICT,
        polarityTotals.value.NO_EFFECT,
        polarityTotals.value.UNCERTAIN,
      ],
    },
  ],
}));
useChart(polarityChartEl, () => polarityOption.value);

const donutPalette = computed(() =>
  isDark.value ? ["#e06c74", "#d9a44e", "#6e7d99"] : ["#cf5058", "#c98a2d", "#8592a8"],
);

const priorityChartEl = ref<HTMLElement>();
const priorityOption = computed(() => ({
  tooltip: { trigger: "item" as const },
  legend: { bottom: 0, itemWidth: 10, itemHeight: 10, textStyle: { color: axisText.value } },
  series: [
    {
      type: "pie" as const,
      radius: ["45%", "70%"],
      itemStyle: { borderRadius: 6 },
      label: { show: false },
      data: priorityCounts.value.map((d, i) => ({
        ...d,
        itemStyle: { color: donutPalette.value[i % donutPalette.value.length] },
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

const statusTag = (status: string) =>
  status === "REVIEW_READY" ? "success" : status === "FAILED" ? "danger" : "info";
</script>

<template>
  <div>
    <div class="pm-page-header">
      <h1>总览</h1>
      <p>证据库现状、跨论文验证聚合与待审队列</p>
    </div>

    <!-- 加载骨架：与最终布局同形，不用转圈 -->
    <template v-if="loading">
      <el-row :gutter="16">
        <el-col v-for="i in 4" :key="i" :span="6">
          <el-skeleton animated style="padding: 18px">
            <template #template>
              <el-skeleton-item variant="rect" style="height: 44px; width: 60%" />
              <el-skeleton-item variant="text" style="margin-top: 10px; width: 40%" />
            </template>
          </el-skeleton>
        </el-col>
      </el-row>
      <el-row :gutter="16" style="margin-top: 16px">
        <el-col v-for="i in 2" :key="i" :span="12">
          <el-skeleton animated style="padding: 18px; height: 300px" />
        </el-col>
      </el-row>
    </template>

    <template v-else>
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
                <el-button text size="small" @click="router.push('/agent')">去工作台</el-button>
              </div>
            </template>
            <el-table :data="tasks" size="small">
              <el-table-column prop="task_id" label="Task" width="120">
                <template #default="{ row }">
                  <span class="sig">{{ row.task_id.slice(0, 8) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="kind" label="类型" width="90" />
              <el-table-column prop="status" label="状态" width="140">
                <template #default="{ row }">
                  <el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag>
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
            <template #header>
              <div style="display: flex; justify-content: space-between; align-items: center">
                <span>待审 TOP（冲突优先）</span>
                <el-button text size="small" @click="router.push('/review')">去审核</el-button>
              </div>
            </template>
            <el-table
              :data="queue.slice(0, 6)"
              size="small"
              style="cursor: pointer"
              @row-click="() => router.push('/review')"
            >
              <el-table-column label="结论" show-overflow-tooltip>
                <template #default="{ row }">
                  <span class="sig">{{ row.canonical_signature }}</span>
                </template>
              </el-table-column>
              <el-table-column label="优先级" width="110">
                <template #default="{ row }">
                  <el-tag
                    :type="row.priority === 'conflict' ? 'danger' : row.priority === 'needs_review' ? 'warning' : 'info'"
                    size="small"
                  >
                    {{ row.priority }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="evidence_count" label="证据" width="70" />
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>
