<template>
  <div class="min-h-screen bg-slate-50 flex flex-col font-sans text-slate-800">
    <!-- Top Navigation Bar -->
    <TopNav
      :active-tab="activeTab"
      :topics="topics"
      :current-topic-id="currentTopic.id"
      :paper-count="currentTopic.papers.length"
      @update:active-tab="activeTab = $event"
      @select-topic="handleSelectTopic"
      @trigger-agent="handleTriggerAgent"
      @export-report="handleExportReport"
    />

    <!-- Sub-header Breadcrumb & Topic Hero Banner -->
    <section class="border-b border-slate-200 bg-white px-4 sm:px-6 py-3">
      <div class="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div>
          <div class="flex items-center gap-2 text-xs text-slate-400 font-mono">
            <span>PROJECT WORKSPACE</span>
            <span aria-hidden="true">/</span>
            <span class="text-sky-700 font-semibold">{{ currentTopic.id.toUpperCase() }}</span>
            <span aria-hidden="true">/</span>
            <span class="text-slate-500 font-sans">PubMed & PMC Active Session</span>
          </div>
          <h1 class="text-lg sm:text-xl font-bold text-slate-900 mt-0.5 tracking-tight flex items-center gap-2">
            <span>{{ currentTopic.title }}</span>
          </h1>
          <p class="text-xs text-slate-500 mt-0.5 max-w-4xl line-clamp-1 font-sans">
            {{ currentTopic.subtitle }}
          </p>
        </div>

        <div class="flex items-center gap-3 shrink-0 text-xs">
          <!-- Active MeSH Terms Summary -->
          <div class="hidden xl:flex items-center gap-1.5 text-slate-400">
            <span>MeSH 词:</span>
            <span
              v-for="mesh in currentTopic.meshTerms.slice(0, 2)"
              :key="mesh"
              class="px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-mono text-[11px]"
            >
              {{ mesh.split('/')[0] }}
            </span>
          </div>

          <!-- Quick Action: Switch to Review -->
          <button
            @click="activeTab = 'synthesis'"
            class="px-3 py-1.5 rounded-md border border-slate-200 hover:bg-slate-50 text-slate-700 flex items-center gap-1.5 transition-colors font-medium text-xs"
          >
            <el-icon class="text-sky-600"><Document /></el-icon>
            <span>综述报告 ({{ currentTopic.papers.filter(p => p.screeningStatus === 'included').length }} 篇纳入)</span>
          </button>
        </div>
      </div>
    </section>

    <!-- Main Workspace Body -->
    <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-5">
      <!-- View 1: Literature Mining & Screening -->
      <LiteratureView
        v-if="activeTab === 'literature'"
        :papers="currentTopic.papers"
        :initial-query="currentTopic.query"
        @search-query="handleCustomSearch"
        @update-status="handlePaperStatusChange"
      />

      <!-- View 2: ECharts Interactive Knowledge Graph -->
      <KnowledgeGraphView
        v-else-if="activeTab === 'graph'"
        :nodes="currentTopic.graphNodes"
        :links="currentTopic.graphLinks"
      />

      <!-- View 3: ECharts Academic Analytics Dashboard -->
      <AnalyticsView
        v-else-if="activeTab === 'analytics'"
        :topic="currentTopic"
      />

      <!-- View 4: Multi-Agent Workflow Console -->
      <AgentWorkflowView
        v-else-if="activeTab === 'workflow'"
      />

      <!-- View 5: Systematic Review Synthesis & Grounded Chat -->
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
          <span>Vue 3 + Element Plus + ECharts 生物医药文献智能挖掘工作台</span>
        </div>
        <div class="flex items-center gap-3 font-mono text-[11px]">
          <span>Data Sources: PubMed · PMC · SemMedDB</span>
          <span>·</span>
          <span>NCBI E-Utilities Grounded</span>
        </div>
      </div>
    </footer>

    <!-- Custom Topic Modal Dialog -->
    <el-dialog
      v-model="customDialogVisible"
      title="创建新文献挖掘课题 (PubMiner Custom Mining)"
      width="560px"
      :destroy-on-close="true"
    >
      <div class="space-y-4">
        <p class="text-xs text-slate-500">
          输入您要探索的生物医学研究问题、疾病靶点或候选药物，PubMiner-Agent 将自动解析 MeSH 概念树、多源检索相关文献并构建知识图谱。
        </p>

        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1">研究课题 / 检索式</label>
          <el-input
            v-model="customInputQuery"
            placeholder="例如: KRAS G12D inhibitor resistance, Alzheimer Tau phosphorylation, Metformin longevity"
            clearable
            @keyup.enter="submitCustomTopic"
          />
        </div>

        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1">推荐示例检索</label>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="sample in samplePresetQueries"
              :key="sample"
              @click="customInputQuery = sample"
              class="px-2 py-1 rounded text-xs bg-slate-100 hover:bg-sky-50 hover:text-sky-700 transition-colors text-slate-600 text-left"
            >
              {{ sample }}
            </button>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="flex justify-end gap-2">
          <el-button @click="customDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitCustomTopic" :loading="isCreatingTopic">
            启动 Agent 挖掘
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import TopNav from './components/TopNav.vue';
import LiteratureView from './components/LiteratureView.vue';
import KnowledgeGraphView from './components/KnowledgeGraphView.vue';
import AnalyticsView from './components/AnalyticsView.vue';
import AgentWorkflowView from './components/AgentWorkflowView.vue';
import SynthesisReviewView from './components/SynthesisReviewView.vue';
import { RESEARCH_TOPICS, createCustomTopic } from './data/researchTopics';
import { ResearchTopic, Paper } from './types';
import { ElMessage } from 'element-plus';

const activeTab = ref('literature');
const topics = ref<ResearchTopic[]>([...RESEARCH_TOPICS]);
const currentTopic = ref<ResearchTopic>(topics.value[0]);

// Custom Topic Modal
const customDialogVisible = ref(false);
const customInputQuery = ref('');
const isCreatingTopic = ref(false);

const samplePresetQueries = [
  'KRAS G12D mutation and MRTX1133 resistance',
  'Metformin longevity AMPK mTOR signaling',
  'Tertiary lymphoid structures and immunotherapy in melanoma'
];

function handleSelectTopic(topicId: string) {
  if (topicId === 'custom') {
    customDialogVisible.value = true;
    return;
  }
  const found = topics.value.find(t => t.id === topicId);
  if (found) {
    currentTopic.value = found;
    ElMessage.success(`已切换至课题: ${found.title}`);
  }
}

function handleTriggerAgent() {
  activeTab.value = 'workflow';
  ElMessage.info('已切换至智能体协同运行中心');
}

function handleCustomSearch(query: string) {
  // If user searched in LiteratureView
  if (query.length > 2) {
    const newTopic = createCustomTopic(query);
    topics.value.unshift(newTopic);
    currentTopic.value = newTopic;
  }
}

function handlePaperStatusChange(payload: { id: string; status: Paper['screeningStatus'] }) {
  const paper = currentTopic.value.papers.find(p => p.id === payload.id);
  if (paper) {
    paper.screeningStatus = payload.status;
  }
}

function submitCustomTopic() {
  if (!customInputQuery.value.trim()) {
    ElMessage.warning('请输入有效的课题关键词');
    return;
  }

  isCreatingTopic.value = true;
  setTimeout(() => {
    const newTopic = createCustomTopic(customInputQuery.value.trim());
    topics.value.unshift(newTopic);
    currentTopic.value = newTopic;
    isCreatingTopic.value = false;
    customDialogVisible.value = false;
    customInputQuery.value = '';
    activeTab.value = 'workflow';
    ElMessage.success(`已成功创建课题并启动 Agent 挖掘: ${newTopic.title}`);
  }, 700);
}

function handleExportReport(format: 'markdown' | 'bibtex' | 'json') {
  if (format === 'markdown') {
    const blob = new Blob([currentTopic.value.reviewReport], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `PubMiner-${currentTopic.value.id}.md`;
    a.click();
    URL.revokeObjectURL(url);
    ElMessage.success('已导出 Markdown 综述报告');
  } else if (format === 'bibtex') {
    const bibtex = currentTopic.value.papers.map(p => `@article{pmid${p.pmid},
  title = {${p.title}},
  author = {${p.authors}},
  journal = {${p.journal}},
  year = {${p.year}},
  doi = {${p.doi}},
  pmid = {${p.pmid}}
}`).join('\n\n');
    const blob = new Blob([bibtex], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `PubMiner-Citations-${currentTopic.value.id}.bib`;
    a.click();
    URL.revokeObjectURL(url);
    ElMessage.success('已导出 BibTeX 文献数据库');
  } else if (format === 'json') {
    const data = JSON.stringify({
      topic: currentTopic.value.title,
      nodes: currentTopic.value.graphNodes,
      links: currentTopic.value.graphLinks,
      triples: currentTopic.value.papers.flatMap(p => p.triples)
    }, null, 2);
    const blob = new Blob([data], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `PubMiner-KnowledgeGraph-${currentTopic.value.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
    ElMessage.success('已导出知识图谱三元组 JSON 数据');
  }
}
</script>
