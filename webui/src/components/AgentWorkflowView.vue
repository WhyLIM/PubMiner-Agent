<template>
  <div class="space-y-4">
    <!-- Header Controls -->
    <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs flex flex-wrap items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-2">
          <h2 class="text-base font-bold text-slate-900">挖掘管线执行中心</h2>
          <span
            v-if="sessionStatus"
            :class="[
              'text-xs px-2 py-0.5 rounded font-mono font-medium',
              sessionStatus === 'COMPLETED' || sessionStatus === 'REVIEW_READY' ? 'bg-emerald-50 text-emerald-700' :
              sessionStatus === 'FAILED' ? 'bg-rose-50 text-rose-700' :
              sessionStatus === 'LIMITED' ? 'bg-amber-50 text-amber-700' :
              'bg-sky-50 text-sky-700'
            ]"
          >{{ sessionStatus }}</span>
        </div>
        <p class="text-xs text-slate-500 mt-0.5">
          检索 → 水合 → 筛选 → 抽取 → 归一化 → 验证 → 聚合；每步状态从后端实时获取。
        </p>
      </div>

      <div class="flex items-center gap-2">
        <el-button type="primary" @click="runPipeline" :loading="loading" :disabled="!hasSession">
          <el-icon class="mr-1"><CaretRight /></el-icon>
          {{ loading ? '执行中...' : hasSession ? '恢复/重跑管线' : '创建会话并运行' }}
        </el-button>
        <el-button size="default" @click="refreshSteps" :disabled="loading">
          <el-icon class="mr-1"><RefreshRight /></el-icon>
          刷新状态
        </el-button>
      </div>
    </div>

    <!-- Error -->
    <el-alert v-if="error" :title="error" type="error" :closable="true" />

    <!-- Pipeline Step Cards -->
    <div v-if="steps.length" class="grid grid-cols-1 md:grid-cols-5 lg:grid-cols-7 gap-3">
      <div
        v-for="(step, index) in steps"
        :key="step.index"
        @click="activeStepIndex = index"
        :class="[
          'p-3.5 rounded-lg border cursor-pointer transition-all flex flex-col justify-between',
          activeStepIndex === index
            ? 'border-sky-500 bg-sky-50/30 shadow-xs ring-1 ring-sky-500/20'
            : step.status === 'SUCCEEDED'
              ? 'border-emerald-200 bg-white'
              : step.status === 'FAILED_RETRYABLE' || step.status === 'FAILED_FINAL'
                ? 'border-rose-200 bg-rose-50/30'
                : 'border-slate-200 bg-white hover:border-slate-300'
        ]"
      >
        <div>
          <div class="flex items-center justify-between mb-2">
            <span class="text-[11px] font-mono font-bold text-slate-400">0{{ step.index + 1 }}</span>
            <span
              :class="[
                'text-[10px] px-1.5 py-0.5 rounded font-mono',
                step.status === 'SUCCEEDED' ? 'bg-emerald-50 text-emerald-700 font-medium' :
                step.status === 'RUNNING' ? 'bg-sky-50 text-sky-700 animate-pulse font-semibold' :
                step.status.includes('FAILED') ? 'bg-rose-50 text-rose-700' :
                'bg-slate-100 text-slate-500'
              ]"
            >
              {{ step.status === 'SUCCEEDED' ? '✓' : step.status.includes('FAILED') ? '✗' : step.status }}
            </span>
          </div>
          <h3 class="text-xs font-bold text-slate-800 leading-snug">{{ step.type }}</h3>
        </div>
      </div>
    </div>

    <el-empty v-else description="尚未运行挖掘管线；创建会话并点击上方按钮启动" :image-size="72" />

    <!-- Active Step Detail & Error -->
    <div v-if="activeStep" class="grid grid-cols-1 gap-4">
      <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-bold text-slate-800">
            {{ activeStep.type }} — {{ activeStep.status }}
          </h3>
          <el-button
            v-if="activeStep.status.includes('FAILED')"
            size="small" type="warning"
            :disabled="!taskId"
            @click="resumeTask"
          >从此步恢复</el-button>
        </div>
        <div v-if="activeStep.error" class="bg-rose-50 text-rose-700 text-xs rounded p-3 mb-3 font-mono">
          {{ activeStep.error }}
        </div>
        <div v-if="stepOutput" class="bg-slate-50 rounded p-3 text-xs font-mono text-slate-700 overflow-x-auto max-h-64 overflow-y-auto">
          <pre>{{ JSON.stringify(stepOutput, null, 2) }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { CaretRight, RefreshRight } from '@element-plus/icons-vue';
import { agentApi } from '@/api/client';
import { useResearch } from '@/composables/useResearch';

const { sessionId, tasks, loading, error, refreshClaims, refreshAggregations, refreshQueue } = useResearch();

const activeStepIndex = ref(0);
const steps = ref<Array<{ index: number; type: string; status: string; error: string | null }>>([]);
const taskId = ref<string | null>(null);
const stepOutput = ref<Record<string, unknown> | null>(null);
const runError = ref<string | null>(null);

const hasSession = computed(() => !!sessionId.value);
const sessionStatus = computed(() => {
  const latest = tasks.value[0];
  return latest?.status ?? null;
});
const activeStep = computed(() => steps.value[activeStepIndex.value] ?? null);

watch(tasks, (t) => {
  if (t.length && !taskId.value) {
    taskId.value = t[0].task_id;
  }
  void loadSteps();
}, { immediate: true, deep: true });

async function loadSteps() {
  if (!taskId.value) { return; }
  try {
    const detail = await agentApi.getTask(taskId.value);
    steps.value = detail.steps;
    if (detail.steps.length) {
      const failedIdx = detail.steps.findIndex(s => s.status.includes('FAILED') || s.status === 'RUNNING');
      activeStepIndex.value = failedIdx >= 0 ? failedIdx : 0;
    }
  } catch { /* 静默 */ }
}

async function refreshSteps() {
  await loadSteps();
  ElMessage.success('步骤状态已刷新');
}

async function runPipeline() {
  loading.value = true;
  runError.value = null;
  try {
    if (sessionId.value) {
      // 已有会话：直接运行
      const task = await agentApi.runSession(sessionId.value, { max_results: 50 });
      taskId.value = task.task_id;
    } else {
      // 无会话：先创建
      const created = await agentApi.createSession({
        goal: 'Collect colorectal cancer prognostic biomarkers with independent cohort validation',
        user_id: 'webui',
      });
      sessionId.value = created.session_id;
      localStorage.setItem('pubminer-session-id', created.session_id);
      await agentApi.parseGoal(created.session_id).catch(() => undefined);
      const plan = await agentApi.submitPlan(created.session_id, {
        rationale: 'auto',
        steps: [
          { id: 's1', action_type: 'SEARCH', status: 'pending' },
          { id: 's2', action_type: 'EXTRACT', status: 'pending' },
        ],
      });
      await agentApi.approvePlan(created.session_id, plan.plan_version);
      const task = await agentApi.runSession(created.session_id, { max_results: 50 });
      taskId.value = task.task_id;
    }
    await loadSteps();
    await Promise.all([refreshClaims(), refreshAggregations(), refreshQueue()]);
    ElMessage.success('管线执行完成');
  } catch (err) {
    runError.value = err instanceof Error ? err.message : String(err);
    await loadSteps();
  } finally {
    loading.value = false;
  }
}

async function resumeTask() {
  if (!taskId.value) { return; }
  try {
    loading.value = true;
    await agentApi.resumeTask(taskId.value);
    await loadSteps();
    await Promise.all([refreshClaims(), refreshAggregations()]);
    ElMessage.success('恢复完成');
  } catch (err) {
    runError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

const _ = stepOutput;
</script>
