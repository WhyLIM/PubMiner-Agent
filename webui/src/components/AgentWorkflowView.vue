<template>
  <div class="space-y-4">
    <!-- Compact Toolbar（嵌入文献页面板，标题由外层面板提供） -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <p class="text-xs text-slate-500 min-w-0">
        检索 → 水合 → 筛选 → 抽取 → 归一化 → 验证 → 覆盖门控 → (引文扩展循环) → 聚合；运行期间每 3 秒自动刷新。
      </p>
      <div class="flex items-center gap-2 shrink-0">
        <el-button type="primary" size="small" @click="runPipeline" :loading="isRunning" :disabled="isRunning && !!runningTaskId">
          <el-icon class="mr-1"><CaretRight /></el-icon>
          {{ isRunning ? '执行中...' : hasSession ? '恢复/重跑管线' : '创建会话并运行' }}
        </el-button>
        <el-button size="small" @click="refreshSteps" :disabled="isRunning">
          <el-icon class="mr-1"><RefreshRight /></el-icon>
          刷新状态
        </el-button>
      </div>
    </div>

    <!-- Error -->
    <el-alert v-if="displayError" :title="displayError" type="error" :closable="true" @close="runError = null" />

    <!-- Pipeline Step Cards -->
    <div v-if="steps.length" class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
      <div
        v-for="(step, index) in steps"
        :key="step.index"
        @click="selectStep(index)"
        :class="[
          'p-3.5 rounded-lg border cursor-pointer transition-all flex flex-col justify-between',
          activeStepIndex === index
            ? 'border-sky-500 bg-sky-50/30 shadow-xs ring-1 ring-sky-500/20'
            : step.status === 'SUCCEEDED'
              ? 'border-emerald-200 bg-white'
              : step.status.includes('FAILED')
                ? 'border-rose-200 bg-rose-50/30'
                : 'border-slate-200 bg-white hover:border-slate-300'
        ]"
      >
        <div>
          <div class="flex items-center justify-between mb-2">
            <span class="text-[11px] font-mono font-bold text-slate-400">{{ String(step.index + 1).padStart(2, '0') }}</span>
            <span
              :class="[
                'text-[10px] px-1.5 py-0.5 rounded font-mono',
                step.status === 'SUCCEEDED' ? 'bg-emerald-50 text-emerald-700 font-medium' :
                step.status === 'RUNNING' ? 'bg-sky-50 text-sky-700 animate-pulse font-semibold' :
                step.status.includes('FAILED') ? 'bg-rose-50 text-rose-700' :
                'bg-slate-100 text-slate-500'
              ]"
            >
              {{ step.status === 'SUCCEEDED' ? '✓' : step.status === 'RUNNING' ? '⟳' : step.status.includes('FAILED') ? '✗' : '…' }}
            </span>
          </div>
          <h3 class="text-xs font-bold text-slate-800 leading-snug">{{ stepLabel(step.type) }}</h3>
          <p class="text-[10px] font-mono text-slate-400 mt-0.5">{{ step.type }}</p>
        </div>
      </div>
    </div>

    <el-empty v-else description="尚未运行挖掘管线；创建会话并点击上方按钮启动" :image-size="72" />

    <!-- Active Step Detail & Live Log -->
    <div v-if="steps.length" class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <!-- Step Detail -->
      <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-bold text-slate-800">
            {{ stepLabel(activeStep?.type ?? '') }}
            <span class="ml-2 text-xs font-mono text-slate-400">{{ activeStep?.status }}</span>
          </h3>
          <el-button
            v-if="activeStep?.status.includes('FAILED')"
            size="small" type="warning"
            :disabled="!taskId"
            @click="resumeTask"
          >从此步恢复</el-button>
        </div>
        <div v-if="activeStep?.error" class="bg-rose-50 text-rose-700 text-xs rounded p-3 mb-3 font-mono break-all">
          {{ activeStep.error }}
        </div>
        <template v-if="stepOutput">
          <div class="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1.5">步骤输出摘要 (output_summary)</div>
          <div class="bg-slate-50 rounded p-3 text-xs font-mono text-slate-700 overflow-x-auto max-h-64 overflow-y-auto">
            <pre class="whitespace-pre-wrap">{{ stepOutputDisplay }}</pre>
          </div>
          <div v-if="stepOutputTruncated" class="mt-1.5">
            <el-button size="small" link type="primary" @click="showFullOutput = !showFullOutput">
              {{ showFullOutput ? '收起，仅显示摘要' : `显示完整输出（共 ${stepOutputText.length.toLocaleString()} 字符）` }}
            </el-button>
          </div>
        </template>
        <div v-else-if="activeStep && activeStep.status === 'SUCCEEDED'" class="text-xs text-slate-400">
          该步骤无输出摘要。
        </div>
        <div v-else-if="activeStep && activeStep.status === 'RUNNING'" class="text-xs text-sky-600 flex items-center gap-1.5">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>步骤执行中，输出将在完成后显示...</span>
        </div>
      </div>

      <!-- Live Event Log -->
      <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs flex flex-col">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-bold text-slate-800">运行事件流</h3>
          <span class="text-[11px] font-mono text-slate-400">最近 {{ events.length }} 条</span>
        </div>
        <div class="flex-1 overflow-y-auto max-h-72 space-y-1.5 text-xs font-mono">
          <div v-if="!events.length" class="text-slate-400 text-center py-6">
            {{ isRunning ? '等待事件...' : '暂无事件；运行管线后此处实时显示进度。' }}
          </div>
          <div
            v-for="ev in events"
            :key="ev.seq"
            class="flex items-start gap-2 py-1 border-b border-slate-50 last:border-0"
          >
            <span class="text-slate-300 shrink-0">#{{ ev.seq }}</span>
            <span
              :class="[
                'shrink-0 px-1 rounded',
                ev.status === 'SUCCEEDED' ? 'text-emerald-600' : ev.status === 'FAILED' ? 'text-rose-600' : 'text-sky-600'
              ]"
            >{{ ev.action_type }}</span>
            <span class="text-slate-600 break-all">{{ ev.summary }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { agentApi } from '@/api/client';
import { useResearch } from '@/composables/useResearch';

const {
  sessionId, tasks, loading, error,
  runningTaskId, taskSteps, events,
  refreshTasks, startPolling, runAndWait, clearError,
} = useResearch();

const activeStepIndex = ref(0);
/** 用户手动点选步骤后，轮询不再自动跳到 RUNNING 步（新开一轮运行时重置） */
const stepPinned = ref(false);
/** 本地兜底步骤（无运行时轮询数据时展示最近一次任务） */
const localSteps = ref<Array<{ index: number; type: string; status: string; error: string | null; output_summary?: Record<string, unknown> | null }>>([]);
const taskId = ref<string | null>(null);
const runError = ref<string | null>(null);

const hasSession = computed(() => !!sessionId.value);
const isRunning = computed(() => loading.value || !!runningTaskId.value);
const steps = computed(() => (taskSteps.value.length ? taskSteps.value : localSteps.value));
const activeStep = computed(() => steps.value[activeStepIndex.value] ?? null);
/** W1 修复：从后端 run_steps.output_summary 直接获取步骤输出 */
const stepOutput = computed(() => activeStep.value?.output_summary ?? null);
const displayError = computed(() => runError.value ?? error.value);

// ---- 步骤输出渲染性能优化 ----
// 大输出（如 200 条筛选决策）整段渲染会导致卡顿：序列化结果用 computed 缓存，
// 默认只显示前 N 字符，完整输出按需渲染。
const STEP_OUTPUT_LIMIT = 5000;
const showFullOutput = ref(false);
const stepOutputText = computed(() => (stepOutput.value ? JSON.stringify(stepOutput.value, null, 2) : ''));
const stepOutputTruncated = computed(() => stepOutputText.value.length > STEP_OUTPUT_LIMIT);
const stepOutputDisplay = computed(() => {
  if (!stepOutputTruncated.value || showFullOutput.value) { return stepOutputText.value; }
  return stepOutputText.value.slice(0, STEP_OUTPUT_LIMIT) + '\n…（已截断）';
});
// 切换步骤时回到摘要视图，避免上一手点的"完整输出"渲染新步骤的大对象
watch(() => activeStepIndex.value, () => {
  showFullOutput.value = false;
});

/** W3：中文步骤名（HYDRATE2 等第二轮步骤去尾号后映射） */
function stepLabel(type: string): string {
  const map: Record<string, string> = {
    SEARCH: '文献检索',
    HYDRATE: '全文水合',
    SCREEN: '三层筛选',
    EXTRACT: '断言抽取',
    NORMALIZE: '实体归一化',
    VERIFY: '跨文献验证',
    COVERAGE: '覆盖度门控',
    EXPAND: '引文扩展',
    AGGREGATE: '证据聚合',
  };
  return map[type.replace(/\d+$/, '')] ?? type;
}

async function loadLatestTask() {
  try {
    await refreshTasks();
    const latest = tasks.value[0];
    if (!latest) { return; }
    taskId.value = latest.task_id;
    if (latest.status === 'RUNNING' || latest.status === 'CREATED') {
      // 页面打开时已有任务在跑：接管轮询（W2：与其它视图共享同一 taskId）
      sessionId.value = latest.session_id ?? sessionId.value;
      startPolling(latest.task_id);
      return;
    }
    const detail = await agentApi.getTask(latest.task_id);
    localSteps.value = detail.steps;
    if (detail.steps.length) {
      const idx = detail.steps.findIndex(s => s.status.includes('FAILED') || s.status === 'RUNNING');
      activeStepIndex.value = idx >= 0 ? idx : 0;
    }
  } catch { /* 静默 */ }
}

async function refreshSteps() {
  await loadLatestTask();
  ElMessage.success('步骤状态已刷新');
}

async function runPipeline() {
  loading.value = true;
  runError.value = null;
  stepPinned.value = false;
  clearError();
  try {
    if (!sessionId.value) {
      const created = await agentApi.createSession({
        goal: 'Collect prognostic biomarkers with independent cohort validation',
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
    }
    // runAndWait 内部 startPolling + 等待终态 + refreshAll（W2: taskId 写入共享状态）
    const task = await runAndWait(sessionId.value!, { max_results: 50 });
    taskId.value = task.task_id;
    localSteps.value = taskSteps.value;
    ElMessage.success('管线执行完成');
  } catch (err) {
    runError.value = err instanceof Error ? err.message : String(err);
    await loadLatestTask();
  } finally {
    loading.value = false;
  }
}

async function resumeTask() {
  if (!taskId.value) { return; }
  try {
    loading.value = true;
    await agentApi.resumeTask(taskId.value);
    startPolling(taskId.value);
  } catch (err) {
    runError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

// 轮询期间自动跟随 RUNNING 步（用户手动点选后停止跟随）；到终态后 composable 已 refreshAll
watch(taskSteps, (s) => {
  if (s.length && runningTaskId.value && !stepPinned.value) {
    const idx = s.findIndex(x => x.status === 'RUNNING');
    if (idx >= 0) { activeStepIndex.value = idx; }
  }
});

function selectStep(index: number) {
  stepPinned.value = true;
  activeStepIndex.value = index;
}

onMounted(() => {
  void loadLatestTask();
});
</script>
