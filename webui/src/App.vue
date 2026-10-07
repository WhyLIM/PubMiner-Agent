<template>
  <div class="min-h-screen bg-slate-50 flex flex-col font-sans text-slate-800">
    <!-- Top Navigation Bar -->
    <TopNav
      :active-tab="activeTab"
      :topics="topics"
      current-topic-id="pubminer"
      :paper-count="currentTopic.papers.length"
      @update:active-tab="activeTab = $event"
      @select-topic="handleSelectTopic"
      @trigger-agent="handleTriggerAgent"
      @export-report="handleExportReport"
    />

    <!-- Sub-header: 真实会话上下文（状态 / 规模 / 课题） -->
    <section class="border-b border-slate-200 bg-white px-4 sm:px-6 py-3">
      <div class="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div class="min-w-0">
          <div class="flex items-center gap-2 text-xs flex-wrap">
            <span :class="['px-2 py-0.5 rounded font-mono text-[11px] font-medium', statusBadgeClass]">
              {{ sessionStatus ?? 'NO SESSION' }}
            </span>
            <span v-if="shortSessionId !== '—'" class="font-mono text-slate-400">会话 {{ shortSessionId }}</span>
            <span aria-hidden="true" class="text-slate-300">·</span>
            <span class="text-slate-500"><span class="font-mono font-semibold text-slate-700">{{ paperCount }}</span> 命题</span>
            <span aria-hidden="true" class="text-slate-300">·</span>
            <span class="text-slate-500"><span class="font-mono font-semibold text-slate-700">{{ docCount }}</span> 篇文献</span>
            <span aria-hidden="true" class="text-slate-300">·</span>
            <span class="text-slate-500"><span class="font-mono font-semibold text-slate-700">{{ totalEvidence }}</span> 条证据</span>
          </div>
          <h1 class="text-lg sm:text-xl font-bold text-slate-900 mt-1 tracking-tight truncate">
            {{ currentTopic.title }}
          </h1>
          <p class="text-xs text-slate-500 mt-0.5 truncate">
            {{ taskSpecLine }}
          </p>
        </div>

        <div class="flex items-center gap-2 shrink-0">
          <button
            @click="deleteCurrentTopic"
            class="px-3 py-1.5 rounded-md border border-rose-200 hover:bg-rose-50 text-rose-700 flex items-center gap-1.5 transition-colors font-medium text-xs"
            title="删除当前课题及其全部数据"
          >
            <el-icon><Delete /></el-icon>
            <span>删除课题</span>
          </button>
          <button
            @click="activeTab = 'synthesis'"
            class="px-3 py-1.5 rounded-md border border-sky-200 bg-sky-50/60 hover:bg-sky-50 text-sky-800 flex items-center gap-1.5 transition-colors font-medium text-xs"
          >
            <el-icon><Document /></el-icon>
            <span>综述报告 ({{ includedCount }} 条已批准)</span>
          </button>
        </div>
      </div>
    </section>

    <!-- Main Workspace Body -->
    <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-5">
      <!-- View 1: Literature Mining & Screening (self-contained via useResearch) -->
      <LiteratureView
        v-if="activeTab === 'literature'"
      />

      <!-- View 2: ECharts Interactive Knowledge Graph -->
      <KnowledgeGraphView
        v-else-if="activeTab === 'graph'"
        :nodes="currentTopic.graphNodes"
        :links="currentTopic.graphLinks"
        :categories="graphCategories"
      />

      <!-- View 3: ECharts Academic Analytics Dashboard -->
      <AnalyticsView
        v-else-if="activeTab === 'analytics'"
        :topic="currentTopic"
      />

      <!-- View 4: Systematic Review Synthesis & Grounded QA -->
      <SynthesisReviewView
        v-else-if="activeTab === 'synthesis'"
        :topic="currentTopic"
      />
    </main>

    <!-- Footer -->
    <footer class="border-t border-slate-200 bg-white py-4 px-6 text-xs text-slate-400">
      <div class="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <span class="font-bold text-slate-600">PubMiner-Agent</span>
          <span>·</span>
          <span>生物医药证据挖掘工作台</span>
        </div>
        <div class="flex items-center gap-3 font-mono text-[11px]">
          <span>Data Sources: PubMed · PMC OA</span>
        </div>
      </div>
    </footer>


  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue';
import TopNav from './components/TopNav.vue';
import LiteratureView from './components/LiteratureView.vue';
import KnowledgeGraphView from './components/KnowledgeGraphView.vue';
import AnalyticsView from './components/AnalyticsView.vue';
import SynthesisReviewView from './components/SynthesisReviewView.vue';
import { Paper } from './types';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useResearch } from './composables/useResearch';

const research = useResearch();
const activeTab = ref('literature');

/**
 * 响应式派生的活动课题：全部字段直接来自 research 的响应式状态，
 * 任何刷新/轮询更新都会自动传播到所有子视图（替代旧的手动快照 + watch）。
 */
const currentTopic = computed(() => ({
  id: research.sessionId.value || 'pubminer',
  title: research.session.value?.goal ?? 'PubMiner Evidence Agent',
  englishTitle: research.session.value?.session_id.slice(0, 8) ?? '',
  subtitle: 'Active mining session',
  query: '',
  meshTerms: [] as string[],
  papers: research.papers.value as Paper[],
  graphNodes: research.graphNodes.value,
  graphLinks: research.graphLinks.value,
  trendYears: [] as string[],
  pubCounts: [] as number[],
  citationAverages: [] as number[],
  cooccurrenceMatrix: { xLabels: [] as string[], yLabels: [] as string[], data: [] as [number, number, number][] },
  evidenceDistribution: [
    { name: 'SUPPORT', value: research.statCards.value.support },
    { name: 'CONTRADICT', value: research.statCards.value.contradict },
    { name: 'UNCERTAIN', value: research.statCards.value.uncertain },
  ],
  biomarkerRanking: research.aggregations.value
    .map(a => ({
      name: a.subject_name || a.canonical_signature.split(' | ')[0] || '',
      score: a.support_count,
      articles: a.distinct_documents,
    }))
    .filter(r => r.name)
    .sort((a, b) => b.score - a.score)
    .slice(0, 10),
  reviewReport: '',
}));

/** 课题下拉：全部历史会话（当前会话排最前），选择即切换 */
const topics = computed(() => {
  const list = research.sessions.value.map(s => ({
    id: s.session_id,
    title: s.goal || '(未命名课题)',
    meta: `${s.created_at.slice(0, 10)} · ${s.status}`,
    isCurrent: s.session_id === research.sessionId.value,
  }));
  // 当前会话可能尚未出现在清单（极新的），补到最前
  const currentId = research.sessionId.value;
  if (currentId && !list.some(t => t.id === currentId)) {
    list.unshift({
      id: currentId,
      title: currentTopic.value.title || '(未命名课题)',
      meta: '',
      isCurrent: true,
    });
  }
  return list.sort((a, b) => Number(b.isCurrent) - Number(a.isCurrent));
});

const shortSessionId = computed(() => (research.session.value?.session_id ?? '').slice(0, 8) || '—');
const sessionStatus = computed(() => research.session.value?.status ?? null);
const includedCount = computed(() => research.papers.value.filter(p => p.screeningStatus === 'included').length);
const graphCategories = computed(() => research.graphCategories.value);
const paperCount = computed(() => research.papers.value.length);
const docCount = computed(() => research.documents.value.length);
const totalEvidence = computed(() => research.papers.value.reduce((s, p) => s + (p.evidenceCount ?? 0), 0));
const statusBadgeClass = computed(() => {
  const s = sessionStatus.value;
  if (!s) { return 'bg-slate-100 text-slate-500'; }
  if (s === 'COMPLETED' || s === 'REVIEW_READY') { return 'bg-emerald-50 text-emerald-700'; }
  if (s === 'FAILED') { return 'bg-rose-50 text-rose-700'; }
  if (s === 'PARTIAL' || s === 'LIMITED') { return 'bg-amber-50 text-amber-700'; }
  return 'bg-sky-50 text-sky-700';
});
const taskSpecLine = computed(() => {
  const spec = research.session.value?.task_spec;
  if (spec && (spec.task || spec.disease)) {
    return `研究任务: ${spec.task ?? '—'} · 疾病: ${spec.disease ?? '—'}`;
  }
  return '确定性管线：检索 → 筛选 → 抽取 → 归一化 → 验证 → 聚合；结果以证据原文片段溯源。';
});

onMounted(() => {
  void research.init();
});

async function handleSelectTopic(topicId: string) {
  if (topicId === 'custom') {
    // 统一入口：新课题一律从文献页搜索框发起
    activeTab.value = 'literature';
    focusSearchInput();
    return;
  }
  try {
    await research.switchSession(topicId);
    ElMessage.success('已切换课题，数据已按该课题刷新');
  } catch {
    ElMessage.error(research.error.value ?? '课题切换失败');
  }
}

function handleTriggerAgent() {
  // 语义=查看执行进度（不创建任务）
  activeTab.value = 'literature';
  research.workflowPanelOpen.value = true;
}

/** 聚焦文献页搜索框（TopNav 课题下拉/新课题入口的统一去向） */
function focusSearchInput() {
  void nextTick(() => {
    const input = document.querySelector<HTMLInputElement>('input[placeholder*="输入研究问题"]');
    input?.focus();
  });
}

/** 删除当前课题：两次确认（概览 → 不可恢复警告），完成后切换到最近课题 */
async function deleteCurrentTopic() {
  const sid = research.sessionId.value;
  if (!sid) {
    ElMessage.warning('当前没有活动课题');
    return;
  }
  if (research.miningActive.value) {
    ElMessage.warning('挖掘正在执行，请等待完成后再删除课题');
    return;
  }
  const claims = research.papers.value.length;
  const docs = research.documents.value.length;

  const first = await ElMessageBox.confirm(
    `将删除课题「${currentTopic.value.title}」及其全部数据：${claims} 条命题、${docs} 篇文献、任务记录与对话。该操作不可撤销。`,
    '删除课题',
    { confirmButtonText: '继续', cancelButtonText: '取消', type: 'warning' },
  ).then(() => true).catch(() => false);
  if (!first) { return; }

  const second = await ElMessageBox.confirm(
    '再次确认：删除后数据无法恢复，确定要永久删除该课题吗？',
    '不可恢复操作',
    { confirmButtonText: '永久删除', cancelButtonText: '取消', type: 'error', confirmButtonClass: 'el-button--danger' },
  ).then(() => true).catch(() => false);
  if (!second) { return; }

  try {
    const res = await research.deleteSession(sid);
    const d = res.deleted;
    ElMessage.success(`课题已删除（命题 ${d.claims} · 证据 ${d.evidence} · 任务 ${d.tasks}）`);
    // 切换到最近保留的课题；全部删光则清空工作台
    localStorage.removeItem('pubminer-session-id');
    await research.refreshSessions();
    const next = research.sessions.value[0];
    if (next) {
      await research.switchSession(next.session_id);
    } else {
      research.clearActiveSession();
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  }
}

function downloadBlob(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function csvEscape(value: string | number | boolean): string {
  const s = String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function handleExportReport(format: 'markdown' | 'csv' | 'json' | 'cbd') {
  const aggs = research.aggregations.value;
  if (!aggs.length) {
    ElMessage.warning('暂无数据可导出：请先运行一次挖掘管线');
    return;
  }

  if (format === 'markdown') {
    const totalSupport = aggs.reduce((s, a) => s + a.support_count, 0);
    const totalContradict = aggs.reduce((s, a) => s + a.contradict_count, 0);
    const lines = [
      `# PubMiner 证据汇总：${currentTopic.value.title}`,
      '',
      `聚合命题 ${aggs.length} 条；支持 ${totalSupport} · 反驳 ${totalContradict}；独立验证命题 ${aggs.filter(a => a.independent_validation).length} 条。`,
      '',
      ...aggs.flatMap(a => [
        `## ${a.canonical_signature}`,
        '',
        `- 状态 ${a.status}；支持 ${a.support_count} / 反驳 ${a.contradict_count} / 无效应 ${a.no_effect_count} / 不确定 ${a.uncertain_count}；独立文献 ${a.distinct_documents} 篇。`,
        ...a.reasons.map(r => `- ${r}`),
        '',
      ]),
    ];
    downloadBlob(lines.join('\n'), 'PubMiner-Evidence-Summary.md', 'text/markdown');
    ElMessage.success('已导出 Markdown 证据汇总');
  } else if (format === 'csv') {
    const header = ['claim_id', 'canonical_signature', 'subject_name', 'status', 'support', 'contradict', 'no_effect', 'uncertain', 'distinct_documents', 'independent_validation'];
    const rows = aggs.map(a => [
      a.claim_id, a.canonical_signature, a.subject_name ?? '', a.status,
      a.support_count, a.contradict_count, a.no_effect_count, a.uncertain_count,
      a.distinct_documents, a.independent_validation,
    ].map(csvEscape).join(','));
    // \uFEFF BOM：保证 Excel 正确识别 UTF-8
    downloadBlob('\uFEFF' + [header.join(','), ...rows].join('\n'), 'PubMiner-Claims.csv', 'text/csv');
    ElMessage.success('已导出命题清单 CSV');
  } else if (format === 'cbd') {
    void (async () => {
      try {
        const res = await fetch('/api/v1/export/cbd?status=APPROVED&limit=500');
        if (!res.ok) { throw new Error(`导出失败（${res.status}）`); }
        const data = await res.json();
        if (!data.items?.length) {
          ElMessage.warning('没有已批准（APPROVED）的命题可导出；请先在文献页完成复核');
          return;
        }
        downloadBlob(JSON.stringify(data, null, 2), 'PubMiner-CBD.json', 'application/json');
        ElMessage.success(`已导出 CBD 格式 ${data.items.length} 条（仅含已批准命题）`);
      } catch (err) {
        ElMessage.error(err instanceof Error ? err.message : String(err));
      }
    })();
  } else {
    const data = JSON.stringify({
      topic: currentTopic.value.title,
      session_id: research.sessionId.value,
      nodes: currentTopic.value.graphNodes,
      links: currentTopic.value.graphLinks,
    }, null, 2);
    downloadBlob(data, 'PubMiner-KnowledgeGraph.json', 'application/json');
    ElMessage.success('已导出知识图谱三元组 JSON 数据');
  }
}
</script>
