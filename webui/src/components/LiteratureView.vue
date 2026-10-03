<template>
  <div class="space-y-4">
    <!-- Search & Filter Console -->
    <div class="bg-white rounded-lg border border-slate-200 p-4 sm:p-5 shadow-xs">
      <div class="flex flex-col gap-3">
        <!-- Natural Language / Boolean Search Bar -->
        <div class="flex flex-col sm:flex-row gap-2">
          <div class="relative flex-1">
            <el-input
              v-model="searchQuery"
              placeholder="输入研究问题、MeSH 术语或 Boolean 检索式 (例如: (EGFR OR MET) AND Osimertinib AND Resistance)..."
              clearable
              size="large"
              @keyup.enter="handleSearch"
            >
              <template #prefix>
                <el-icon class="text-slate-400"><Search /></el-icon>
              </template>
            </el-input>
          </div>
          <div class="flex items-center gap-2">
            <el-button type="primary" size="large" @click="handleSearch" :loading="isSearching">
              <el-icon class="mr-1"><Search /></el-icon>
              检索文献
            </el-button>
            <el-button size="large" @click="toggleFilterExpanded">
              <el-icon class="mr-1"><Filter /></el-icon>
              {{ filterExpanded ? '收起筛选' : '高级过滤' }}
            </el-button>
          </div>
        </div>

        <!-- MeSH Controlled Vocabulary & Sources Bar -->
        <div class="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500 pt-1 border-t border-slate-100">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-slate-400 font-medium">检索数据源:</span>
            <el-checkbox v-model="sources.pubmed" label="PubMed" size="small" />
            <el-checkbox v-model="sources.pmc" label="PMC 全文" size="small" />
            <el-checkbox v-model="sources.semmed" label="SemMedDB" size="small" />
            <el-checkbox v-model="sources.biogrid" label="BioGRID" size="small" />
          </div>

          <div class="flex items-center gap-3">
            <div class="flex items-center gap-1.5">
              <el-switch v-model="enableMeSHExpansion" size="small" />
              <span class="text-slate-600">MeSH 同义词扩展</span>
            </div>
            <div class="flex items-center gap-1.5">
              <el-switch v-model="enableAIExtraction" size="small" />
              <span class="text-slate-600">实时 NER 实体抽取</span>
            </div>
          </div>
        </div>

        <!-- Advanced Filter Row (Collapsible) -->
        <div v-if="filterExpanded" class="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-4 gap-3 pt-3 border-t border-slate-100 text-xs">
          <div>
            <label class="block text-slate-500 mb-1 font-medium">研究类型 (Study Design)</label>
            <el-select v-model="selectedStudyType" placeholder="全部类型" clearable size="small" class="w-full">
              <el-option label="全部类型" value="" />
              <el-option label="临床三期试验 (Phase III)" value="Clinical Trial Phase III" />
              <el-option label="早期临床试验 (Phase I/II)" value="Clinical Trial Phase I/II" />
              <el-option label="系统综述 / Meta 分析" value="Systematic Review" />
              <el-option label="前瞻性队列研究" value="Prospective Cohort" />
              <el-option label="基础 / 临床前体外模型" value="Preclinical / In Vitro" />
            </el-select>
          </div>

          <div>
            <label class="block text-slate-500 mb-1 font-medium">文献年份跨度 (Publication Year)</label>
            <el-select v-model="selectedYearRange" placeholder="全部年份" size="small" class="w-full">
              <el-option label="近 3 年 (2023 - 2026)" value="recent3" />
              <el-option label="近 5 年 (2021 - 2026)" value="recent5" />
              <el-option label="近 10 年 (2016 - 2026)" value="recent10" />
              <el-option label="全部年份" value="all" />
            </el-select>
          </div>

          <div>
            <label class="block text-slate-500 mb-1 font-medium">偏倚风险 (Risk of Bias)</label>
            <el-select v-model="selectedBias" placeholder="不限" clearable size="small" class="w-full">
              <el-option label="全部" value="" />
              <el-option label="低偏倚风险 (Low Risk)" value="Low" />
              <el-option label="中度风险 (Moderate)" value="Moderate" />
            </el-select>
          </div>

          <div>
            <label class="block text-slate-500 mb-1 font-medium">全文获取权限</label>
            <div class="pt-1">
              <el-checkbox v-model="onlyOpenAccess" label="仅显示 Open Access 全文" size="small" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Quantitative Metrics Strip -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
      <div class="bg-white border border-slate-200 rounded-lg p-3.5 flex flex-col justify-between">
        <span class="text-xs text-slate-500 font-medium">检索总文献量</span>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-2xl font-bold font-mono text-slate-900">{{ papers.length }}</span>
          <span class="text-xs text-slate-400 font-mono">篇记录</span>
        </div>
      </div>

      <div class="bg-white border border-slate-200 rounded-lg p-3.5 flex flex-col justify-between">
        <span class="text-xs text-slate-500 font-medium">已纳入系统综述</span>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-2xl font-bold font-mono text-emerald-600">{{ includedCount }}</span>
          <span class="text-xs text-slate-400 font-mono">/ {{ papers.length }} 纳入</span>
        </div>
      </div>

      <div class="bg-white border border-slate-200 rounded-lg p-3.5 flex flex-col justify-between">
        <span class="text-xs text-slate-500 font-medium">生物实体三元组</span>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-2xl font-bold font-mono text-sky-600">{{ totalTriplesCount }}</span>
          <span class="text-xs text-slate-400 font-mono">条语义关系</span>
        </div>
      </div>

      <div class="bg-white border border-slate-200 rounded-lg p-3.5 flex flex-col justify-between">
        <span class="text-xs text-slate-500 font-medium">平均影响因子 / 被引</span>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-2xl font-bold font-mono text-slate-900">{{ averageCitations }}</span>
          <span class="text-xs text-slate-400 font-mono">次 / 篇</span>
        </div>
      </div>
    </div>

    <!-- Literature List & Screening Board -->
    <div class="bg-white rounded-lg border border-slate-200 shadow-xs overflow-hidden">
      <!-- Toolbar -->
      <div class="px-4 py-3 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3 bg-slate-50/70">
        <div class="flex items-center gap-1">
          <button
            v-for="tab in screeningTabs"
            :key="tab.key"
            @click="activeScreeningFilter = tab.key"
            :class="[
              'px-3 py-1 text-xs font-medium rounded-md transition-colors flex items-center gap-1.5',
              activeScreeningFilter === tab.key
                ? 'bg-white text-slate-900 shadow-xs border border-slate-200'
                : 'text-slate-600 hover:text-slate-900'
            ]"
          >
            <span>{{ tab.label }}</span>
            <span class="font-mono text-[11px] px-1.5 py-0.2 rounded bg-slate-100 text-slate-600">
              {{ tab.count }}
            </span>
          </button>
        </div>

        <div class="flex items-center gap-2">
          <el-input
            v-model="paperKeyword"
            placeholder="在已检索结果中快速过滤..."
            prefix-icon="Search"
            size="small"
            clearable
            class="w-48 sm:w-60"
          />
          <el-button-group size="small">
            <el-button :type="viewMode === 'card' ? 'primary' : 'default'" @click="viewMode = 'card'">
              <el-icon><Menu /></el-icon>
            </el-button>
            <el-button :type="viewMode === 'table' ? 'primary' : 'default'" @click="viewMode = 'table'">
              <el-icon><Tickets /></el-icon>
            </el-button>
          </el-button-group>
        </div>
      </div>

      <!-- Card Mode View -->
      <div v-if="viewMode === 'card'" class="divide-y divide-slate-100">
        <div
          v-for="paper in filteredPapers"
          :key="paper.id"
          class="p-4 sm:p-5 hover:bg-slate-50/60 transition-colors flex flex-col gap-3 group"
        >
          <!-- Metadata Kicker Line (Zero-Pill Rule) -->
          <div class="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500 font-sans">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-semibold text-slate-700">{{ paper.journal }}</span>
              <span aria-hidden="true" class="text-slate-300">·</span>
              <span class="font-mono">{{ paper.year }}</span>
              <span aria-hidden="true" class="text-slate-300">·</span>
              <span class="text-sky-700 font-medium">{{ paper.studyType }}</span>
              <span aria-hidden="true" class="text-slate-300">·</span>
              <span class="font-mono">PMID: {{ paper.pmid }}</span>
              <span v-if="paper.openAccess" class="text-emerald-600 font-medium">OA 全文</span>
            </div>

            <!-- Quick Screening Actions -->
            <div class="flex items-center gap-1.5">
              <button
                @click="updatePaperStatus(paper.id, 'included')"
                :class="[
                  'px-2.5 py-1 text-xs font-medium rounded transition-colors flex items-center gap-1',
                  paper.screeningStatus === 'included'
                    ? 'bg-emerald-600 text-white shadow-xs'
                    : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                ]"
                title="纳入系统综述"
              >
                <el-icon><Check /></el-icon>
                <span>纳入</span>
              </button>

              <button
                @click="updatePaperStatus(paper.id, 'flagged')"
                :class="[
                  'px-2 py-1 text-xs font-medium rounded transition-colors flex items-center gap-1',
                  paper.screeningStatus === 'flagged'
                    ? 'bg-amber-500 text-white shadow-xs'
                    : 'bg-amber-50 text-amber-700 hover:bg-amber-100'
                ]"
                title="待核实/存疑"
              >
                <el-icon><Warning /></el-icon>
                <span>待定</span>
              </button>

              <button
                @click="updatePaperStatus(paper.id, 'excluded')"
                :class="[
                  'px-2 py-1 text-xs font-medium rounded transition-colors flex items-center gap-1',
                  paper.screeningStatus === 'excluded'
                    ? 'bg-rose-600 text-white shadow-xs'
                    : 'bg-rose-50 text-rose-700 hover:bg-rose-100'
                ]"
                title="排除本条文献"
              >
                <el-icon><Close /></el-icon>
                <span>排除</span>
              </button>
            </div>
          </div>

          <!-- Paper Title -->
          <h3
            @click="openPaperDrawer(paper)"
            class="text-base font-semibold text-slate-900 group-hover:text-sky-700 transition-colors cursor-pointer leading-snug"
          >
            {{ paper.title }}
          </h3>

          <!-- Authors -->
          <div class="text-xs text-slate-500 italic">
            {{ paper.authors }}
          </div>

          <!-- Abstract Snippet -->
          <p class="text-xs sm:text-sm text-slate-600 leading-relaxed line-clamp-2">
            {{ paper.abstract }}
          </p>

          <!-- Key Extracted Statistical Findings & Entities (Clean unboxed tokens) -->
          <div class="flex flex-wrap items-center justify-between gap-3 pt-1 text-xs border-t border-slate-100">
            <div class="flex flex-wrap items-center gap-3">
              <div v-if="paper.sampleSize" class="text-slate-600">
                <span class="text-slate-400">样本量:</span>
                <span class="ml-1 font-mono font-medium">N = {{ paper.sampleSize }}</span>
              </div>
              <div v-if="paper.hazardRatio" class="text-slate-600">
                <span class="text-slate-400">效应量:</span>
                <span class="ml-1 font-mono font-semibold text-slate-800">{{ paper.hazardRatio }}</span>
              </div>
              <div v-if="paper.pValue" class="text-slate-600">
                <span class="text-slate-400">显著性:</span>
                <span class="ml-1 font-mono text-emerald-700">{{ paper.pValue }}</span>
              </div>
            </div>

            <!-- Extracted entities chips -->
            <div class="flex items-center gap-1.5 flex-wrap">
              <span
                v-for="gene in paper.entities.genes.slice(0, 3)"
                :key="gene"
                class="px-2 py-0.5 rounded text-[11px] bg-sky-50 text-sky-700 border border-sky-200/60 font-mono"
              >
                {{ gene }}
              </span>
              <span
                v-for="drug in paper.entities.drugs.slice(0, 2)"
                :key="drug"
                class="px-2 py-0.5 rounded text-[11px] bg-emerald-50 text-emerald-700 border border-emerald-200/60 font-mono"
              >
                {{ drug }}
              </span>
              <button
                @click="openPaperDrawer(paper)"
                class="text-xs text-sky-600 hover:text-sky-800 font-medium ml-1 flex items-center gap-0.5"
              >
                <span>抽取详情</span>
                <el-icon :size="12"><ArrowRight /></el-icon>
              </button>
            </div>
          </div>
        </div>

        <div v-if="filteredPapers.length === 0" class="p-12 text-center text-slate-400 text-xs">
          没有匹配当前筛选条件的文献记录。
        </div>
      </div>

      <!-- Table Mode View -->
      <div v-else class="overflow-x-auto">
        <el-table :data="filteredPapers" stripe style="width: 100%">
          <el-table-column prop="pmid" label="PMID" width="100">
            <template #default="{ row }">
              <span class="font-mono text-xs text-sky-700 font-medium">{{ row.pmid }}</span>
            </template>
          </el-table-column>

          <el-table-column label="文献标题与期刊" min-width="280">
            <template #default="{ row }">
              <div class="py-1">
                <div
                  @click="openPaperDrawer(row)"
                  class="font-medium text-xs text-slate-800 hover:text-sky-600 cursor-pointer line-clamp-1"
                >
                  {{ row.title }}
                </div>
                <div class="text-[11px] text-slate-400 mt-0.5">
                  {{ row.journal }} ({{ row.year }}) · {{ row.authors.split(',')[0] }} et al.
                </div>
              </div>
            </template>
          </el-table-column>

          <el-table-column prop="studyType" label="研究类型" width="160">
            <template #default="{ row }">
              <span class="text-xs text-slate-600">{{ row.studyType }}</span>
            </template>
          </el-table-column>

          <el-table-column label="样本量 / 效应值" width="160">
            <template #default="{ row }">
              <div class="text-xs font-mono">
                <span v-if="row.sampleSize">N={{ row.sampleSize }}</span>
                <span v-if="row.hazardRatio" class="text-slate-500 block text-[11px]">{{ row.hazardRatio }}</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="抽取实体" width="180">
            <template #default="{ row }">
              <div class="flex items-center gap-1 flex-wrap">
                <span
                  v-for="gene in row.entities.genes.slice(0, 2)"
                  :key="gene"
                  class="text-[10px] font-mono px-1 rounded bg-slate-100 text-slate-700"
                >
                  {{ gene }}
                </span>
                <span
                  v-for="drug in row.entities.drugs.slice(0, 1)"
                  :key="drug"
                  class="text-[10px] font-mono px-1 rounded bg-emerald-50 text-emerald-700"
                >
                  {{ drug }}
                </span>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="筛选状态" width="120" align="center">
            <template #default="{ row }">
              <el-tag
                :type="row.screeningStatus === 'included' ? 'success' : row.screeningStatus === 'flagged' ? 'warning' : 'info'"
                size="small"
              >
                {{ row.screeningStatus === 'included' ? '纳入' : row.screeningStatus === 'flagged' ? '待定' : '已排除' }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="操作" width="140" align="right">
            <template #default="{ row }">
              <div class="flex items-center justify-end gap-1">
                <el-button link type="primary" size="small" @click="openPaperDrawer(row)">
                  详情
                </el-button>
                <el-button
                  link
                  :type="row.screeningStatus === 'included' ? 'danger' : 'success'"
                  size="small"
                  @click="updatePaperStatus(row.id, row.screeningStatus === 'included' ? 'excluded' : 'included')"
                >
                  {{ row.screeningStatus === 'included' ? '排除' : '纳入' }}
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- Paper Details & Extraction Drawer -->
    <el-drawer
      v-model="drawerVisible"
      title="文献深度抽取与证据审查"
      size="540px"
      direction="rtl"
      :destroy-on-close="true"
    >
      <div v-if="selectedPaper" class="space-y-5 text-slate-800">
        <!-- Title and Citation Links -->
        <div>
          <div class="flex items-center gap-2 text-xs text-slate-500 mb-1">
            <span class="font-mono text-sky-700 font-semibold">PMID: {{ selectedPaper.pmid }}</span>
            <span aria-hidden="true">·</span>
            <span>DOI: {{ selectedPaper.doi }}</span>
            <span aria-hidden="true">·</span>
            <span class="font-mono">{{ selectedPaper.year }}</span>
          </div>
          <h2 class="text-base font-bold text-slate-900 leading-snug">
            {{ selectedPaper.title }}
          </h2>
          <div class="text-xs text-slate-500 mt-1 italic">
            {{ selectedPaper.authors }}
          </div>
          <div class="flex items-center gap-3 mt-3">
            <a
              :href="'https://pubmed.ncbi.nlm.nih.gov/' + selectedPaper.pmid"
              target="_blank"
              class="px-3 py-1 text-xs rounded border border-slate-300 hover:bg-slate-50 text-slate-700 flex items-center gap-1"
            >
              <el-icon><Link /></el-icon>
              <span>在 PubMed 中打开</span>
            </a>
            <a
              :href="'https://doi.org/' + selectedPaper.doi"
              target="_blank"
              class="px-3 py-1 text-xs rounded border border-slate-300 hover:bg-slate-50 text-slate-700 flex items-center gap-1"
            >
              <el-icon><Document /></el-icon>
              <span>访问出版商原文</span>
            </a>
          </div>
        </div>

        <!-- Evidence & Quantitative Synthesis -->
        <div class="bg-slate-50 rounded-lg p-3.5 border border-slate-200">
          <h4 class="text-xs font-semibold text-slate-700 uppercase tracking-wide mb-2">研究特征与循证指标</h4>
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span class="text-slate-400">研究设计:</span>
              <span class="ml-1 font-medium text-slate-800">{{ selectedPaper.studyType }}</span>
            </div>
            <div>
              <span class="text-slate-400">偏倚风险:</span>
              <span class="ml-1 font-medium text-emerald-700">{{ selectedPaper.biasRisk }}</span>
            </div>
            <div>
              <span class="text-slate-400">样本规模:</span>
              <span class="ml-1 font-mono text-slate-800">{{ selectedPaper.sampleSize ? 'N = ' + selectedPaper.sampleSize : 'N/A' }}</span>
            </div>
            <div>
              <span class="text-slate-400">被引频次:</span>
              <span class="ml-1 font-mono text-slate-800">{{ selectedPaper.citations }} 次</span>
            </div>
            <div class="col-span-2">
              <span class="text-slate-400">统计效应量:</span>
              <span class="ml-1 font-mono font-semibold text-sky-800">{{ selectedPaper.hazardRatio || '显著有效 (p < 0.05)' }}</span>
            </div>
          </div>
        </div>

        <!-- Abstract with semantic structure -->
        <div>
          <h4 class="text-xs font-semibold text-slate-700 uppercase tracking-wide mb-1.5">摘要文本 (Abstract)</h4>
          <div class="p-3 bg-slate-50/50 rounded-lg border border-slate-200 text-xs sm:text-sm text-slate-700 leading-relaxed font-sans">
            {{ selectedPaper.abstract }}
          </div>
        </div>

        <!-- Extracted Knowledge Triples -->
        <div>
          <div class="flex items-center justify-between mb-2">
            <h4 class="text-xs font-semibold text-slate-700 uppercase tracking-wide">抽取实体关系三元组 (Triples)</h4>
            <span class="text-[11px] text-slate-400 font-mono">{{ selectedPaper.triples.length }} 个断言</span>
          </div>

          <div class="space-y-2">
            <div
              v-for="(triple, idx) in selectedPaper.triples"
              :key="idx"
              class="p-2.5 rounded-lg border border-slate-200 bg-white flex items-center justify-between text-xs"
            >
              <div class="flex items-center gap-1.5 flex-wrap">
                <span class="font-mono font-semibold text-sky-700 bg-sky-50 px-2 py-0.5 rounded">{{ triple.subject }}</span>
                <span class="text-[11px] font-mono text-slate-400 font-medium">--[{{ triple.predicate }}]--></span>
                <span class="font-mono font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">{{ triple.object }}</span>
              </div>
              <span class="text-[11px] font-mono text-slate-400">{{ (triple.confidence * 100).toFixed(0) }}% 置信</span>
            </div>
          </div>
        </div>

        <!-- MeSH Terms -->
        <div>
          <h4 class="text-xs font-semibold text-slate-700 uppercase tracking-wide mb-1.5">MeSH 医学主题词</h4>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="term in selectedPaper.meshTerms"
              :key="term"
              class="px-2 py-1 rounded text-xs bg-slate-100 text-slate-700 font-mono text-[11px]"
            >
              {{ term }}
            </span>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { Paper } from '../types';
import { ElMessage } from 'element-plus';

const props = defineProps<{
  papers: Paper[];
  initialQuery: string;
}>();

const emit = defineEmits<{
  (e: 'search-query', query: string): void;
  (e: 'update-status', payload: { id: string; status: Paper['screeningStatus'] }): void;
}>();

const searchQuery = ref(props.initialQuery);
const isSearching = ref(false);
const filterExpanded = ref(false);
const viewMode = ref<'card' | 'table'>('card');
const paperKeyword = ref('');
const activeScreeningFilter = ref<'all' | 'included' | 'flagged' | 'excluded'>('all');

// Drawer State
const drawerVisible = ref(false);
const selectedPaper = ref<Paper | null>(null);

// Filters
const selectedStudyType = ref('');
const selectedYearRange = ref('all');
const selectedBias = ref('');
const onlyOpenAccess = ref(false);

const sources = ref({
  pubmed: true,
  pmc: true,
  semmed: true,
  biogrid: false,
});

const enableMeSHExpansion = ref(true);
const enableAIExtraction = ref(true);

const includedCount = computed(() => props.papers.filter(p => p.screeningStatus === 'included').length);
const totalTriplesCount = computed(() => props.papers.reduce((sum, p) => sum + p.triples.length, 0));
const averageCitations = computed(() => {
  if (!props.papers.length) return 0;
  const sum = props.papers.reduce((acc, p) => acc + p.citations, 0);
  return (sum / props.papers.length).toFixed(1);
});

const screeningTabs = computed(() => [
  { key: 'all' as const, label: '全部文献', count: props.papers.length },
  { key: 'included' as const, label: '已纳入', count: props.papers.filter(p => p.screeningStatus === 'included').length },
  { key: 'flagged' as const, label: '待复核', count: props.papers.filter(p => p.screeningStatus === 'flagged').length },
  { key: 'excluded' as const, label: '已排除', count: props.papers.filter(p => p.screeningStatus === 'excluded').length },
]);

const filteredPapers = computed(() => {
  return props.papers.filter(paper => {
    // Tab filter
    if (activeScreeningFilter.value !== 'all' && paper.screeningStatus !== activeScreeningFilter.value) {
      return false;
    }
    // Study Type
    if (selectedStudyType.value && paper.studyType !== selectedStudyType.value) {
      return false;
    }
    // Bias
    if (selectedBias.value && paper.biasRisk !== selectedBias.value) {
      return false;
    }
    // OA
    if (onlyOpenAccess.value && !paper.openAccess) {
      return false;
    }
    // Search keyword in title or abstract
    if (paperKeyword.value) {
      const q = paperKeyword.value.toLowerCase();
      const match = paper.title.toLowerCase().includes(q) ||
        paper.abstract.toLowerCase().includes(q) ||
        paper.pmid.includes(q) ||
        paper.journal.toLowerCase().includes(q);
      if (!match) return false;
    }
    return true;
  });
});

function toggleFilterExpanded() {
  filterExpanded.value = !filterExpanded.value;
}

function handleSearch() {
  if (!searchQuery.value.trim()) {
    ElMessage.warning('请输入检索关键词或研究问题');
    return;
  }
  isSearching.value = true;
  setTimeout(() => {
    emit('search-query', searchQuery.value);
    isSearching.value = false;
    ElMessage.success(`检索完成: 找到 ${props.papers.length} 篇相关生物医药文献`);
  }, 600);
}

function updatePaperStatus(id: string, status: Paper['screeningStatus']) {
  emit('update-status', { id, status });
  ElMessage.success({
    message: status === 'included' ? '已标记为纳入' : status === 'flagged' ? '已标记为待核实' : '已标记为排除',
    duration: 1500
  });
}

function openPaperDrawer(paper: Paper) {
  selectedPaper.value = paper;
  drawerVisible.value = true;
}
</script>
