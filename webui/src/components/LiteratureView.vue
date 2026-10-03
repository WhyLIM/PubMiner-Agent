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
              placeholder="输入研究问题启动新一轮挖掘 (例如: KRAS G12D inhibitor resistance in colorectal cancer)..."
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
              {{ isSearching ? '管线执行中...' : '启动挖掘' }}
            </el-button>
            <el-button size="large" @click="toggleFilterExpanded">
              <el-icon class="mr-1"><Filter /></el-icon>
              {{ filterExpanded ? '收起筛选' : '高级过滤' }}
            </el-button>
          </div>
        </div>

        <!-- Data source note (real sources only) -->
        <div class="flex flex-wrap items-center gap-2 text-xs text-slate-500 pt-1 border-t border-slate-100">
          <span class="text-slate-400 font-medium">数据源:</span>
          <span class="px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-medium">PubMed E-utilities</span>
          <span class="px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-medium">PMC OA 全文 (BioC)</span>
          <span class="text-slate-400 ml-2">证据原文片段均含偏移定位，支持原文溯源。</span>
        </div>

        <!-- Advanced Filter Row (Collapsible, operates on real fields) -->
        <div v-if="filterExpanded" class="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-3 border-t border-slate-100 text-xs">
          <div>
            <label class="block text-slate-500 mb-1 font-medium">最少独立文献数</label>
            <el-select v-model="minDocuments" placeholder="不限" size="small" class="w-full">
              <el-option label="不限" :value="0" />
              <el-option label="≥ 2 篇独立文献" :value="2" />
              <el-option label="≥ 3 篇独立文献 (独立验证阈值)" :value="3" />
              <el-option label="≥ 5 篇独立文献" :value="5" />
            </el-select>
          </div>

          <div>
            <label class="block text-slate-500 mb-1 font-medium">证据倾向</label>
            <div class="pt-1.5 flex flex-wrap items-center gap-3">
              <el-checkbox v-model="onlyConflict" label="仅看存在反驳证据" size="small" />
              <el-checkbox v-model="onlyValidated" label="仅看独立验证" size="small" />
            </div>
          </div>

          <div>
            <label class="block text-slate-500 mb-1 font-medium">排序方式</label>
            <el-select v-model="sortBy" size="small" class="w-full">
              <el-option label="证据总数 (多 → 少)" value="evidence" />
              <el-option label="支持证据 (多 → 少)" value="support" />
              <el-option label="反驳证据 (多 → 少)" value="contradict" />
              <el-option label="独立文献数 (多 → 少)" value="documents" />
            </el-select>
          </div>
        </div>
      </div>
    </div>

    <!-- Error from composable -->
    <el-alert
      v-if="researchError"
      :title="researchError"
      type="error"
      show-icon
      closable
      @close="clearError()"
    />

    <!-- Quantitative Metrics Strip (all real) -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
      <div class="bg-white border border-slate-200 rounded-lg p-3.5 flex flex-col justify-between">
        <span class="text-xs text-slate-500 font-medium">证据聚合命题</span>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-2xl font-bold font-mono text-slate-900">{{ papers.length }}</span>
          <span class="text-xs text-slate-400 font-mono">条断言</span>
        </div>
      </div>

      <div class="bg-white border border-slate-200 rounded-lg p-3.5 flex flex-col justify-between">
        <span class="text-xs text-slate-500 font-medium">已批准纳入</span>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-2xl font-bold font-mono text-emerald-600">{{ includedCount }}</span>
          <span class="text-xs text-slate-400 font-mono">/ {{ papers.length }} 命题</span>
        </div>
      </div>

      <div class="bg-white border border-slate-200 rounded-lg p-3.5 flex flex-col justify-between">
        <span class="text-xs text-slate-500 font-medium">待复核 / 冲突命题</span>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-2xl font-bold font-mono text-amber-600">{{ flaggedCount }}</span>
          <span class="text-xs text-slate-400 font-mono">条命题</span>
        </div>
      </div>

      <div class="bg-white border border-slate-200 rounded-lg p-3.5 flex flex-col justify-between">
        <span class="text-xs text-slate-500 font-medium">独立验证命题</span>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-2xl font-bold font-mono text-sky-600">{{ validatedCount }}</span>
          <span class="text-xs text-slate-400 font-mono">≥3 篇同向</span>
        </div>
      </div>
    </div>

    <!-- Evidence List & Screening Board -->
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
            <span class="font-mono text-[11px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
              {{ tab.count }}
            </span>
          </button>
        </div>

        <div class="flex items-center gap-2">
          <el-input
            v-model="paperKeyword"
            placeholder="在结果中快速过滤..."
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
          <!-- Metadata Kicker Line -->
          <div class="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500 font-sans">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-mono text-slate-400">断言 {{ paper.id.slice(0, 8) }}</span>
              <span aria-hidden="true" class="text-slate-300">·</span>
              <span class="text-sky-700 font-medium">{{ statusLabel(paper.studyType) }}</span>
              <span
                v-if="paper.independentValidation"
                class="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200/60 font-medium"
              >独立验证</span>
              <span
                v-if="(paper.contradictCount ?? 0) > 0"
                class="px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200/60 font-medium"
              >存在反驳</span>
            </div>

            <!-- Quick Screening Actions -->
            <div class="flex items-center gap-1.5">
              <button
                @click="updatePaperStatus(paper, 'included')"
                :class="[
                  'px-2.5 py-1 text-xs font-medium rounded transition-colors flex items-center gap-1',
                  paper.screeningStatus === 'included'
                    ? 'bg-emerald-600 text-white shadow-xs'
                    : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                ]"
                title="批准该断言 (ACCEPT)"
              >
                <el-icon><Check /></el-icon>
                <span>批准</span>
              </button>

              <button
                @click="updatePaperStatus(paper, 'flagged')"
                :class="[
                  'px-2 py-1 text-xs font-medium rounded transition-colors flex items-center gap-1',
                  paper.screeningStatus === 'flagged'
                    ? 'bg-amber-500 text-white shadow-xs'
                    : 'bg-amber-50 text-amber-700 hover:bg-amber-100'
                ]"
                title="转人工复核 (NEEDS_REVIEW)"
              >
                <el-icon><Warning /></el-icon>
                <span>待定</span>
              </button>

              <button
                @click="updatePaperStatus(paper, 'excluded')"
                :class="[
                  'px-2 py-1 text-xs font-medium rounded transition-colors flex items-center gap-1',
                  paper.screeningStatus === 'excluded'
                    ? 'bg-rose-600 text-white shadow-xs'
                    : 'bg-rose-50 text-rose-700 hover:bg-rose-100'
                ]"
                title="否决该断言 (REJECT)"
              >
                <el-icon><Close /></el-icon>
                <span>否决</span>
              </button>
            </div>
          </div>

          <!-- Canonical Signature as Title -->
          <h3
            @click="openPaperDrawer(paper)"
            class="text-sm sm:text-base font-semibold text-slate-900 group-hover:text-sky-700 transition-colors cursor-pointer leading-snug font-mono"
          >
            {{ paper.title }}
          </h3>

          <!-- Aggregation reasons snippet -->
          <p class="text-xs sm:text-sm text-slate-600 leading-relaxed line-clamp-2">
            {{ paper.abstract }}
          </p>

          <!-- Polarity counts (real data) -->
          <div class="flex flex-wrap items-center justify-between gap-3 pt-1 text-xs border-t border-slate-100">
            <div class="flex flex-wrap items-center gap-3">
              <span class="text-slate-600">
                <span class="text-slate-400">支持</span>
                <span class="ml-1 font-mono font-semibold text-emerald-700">{{ paper.supportCount ?? 0 }}</span>
              </span>
              <span class="text-slate-600">
                <span class="text-slate-400">反驳</span>
                <span class="ml-1 font-mono font-semibold text-rose-700">{{ paper.contradictCount ?? 0 }}</span>
              </span>
              <span class="text-slate-600">
                <span class="text-slate-400">无效应</span>
                <span class="ml-1 font-mono font-semibold text-slate-700">{{ paper.noEffectCount ?? 0 }}</span>
              </span>
              <span class="text-slate-600">
                <span class="text-slate-400">不确定</span>
                <span class="ml-1 font-mono font-semibold text-amber-700">{{ paper.uncertainCount ?? 0 }}</span>
              </span>
            </div>

            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="px-2 py-0.5 rounded text-[11px] bg-slate-50 text-slate-600 border border-slate-200/60 font-mono">
                {{ paper.sampleSize ?? 0 }} 篇独立文献
              </span>
              <button
                @click="openPaperDrawer(paper)"
                class="text-xs text-sky-600 hover:text-sky-800 font-medium ml-1 flex items-center gap-0.5"
              >
                <span>查看证据原文</span>
                <el-icon :size="12"><ArrowRight /></el-icon>
              </button>
            </div>
          </div>
        </div>

        <div v-if="filteredPapers.length === 0" class="p-12 text-center text-slate-400 text-xs">
          {{ papers.length === 0 ? '暂无数据：请先启动一次挖掘管线。' : '没有匹配当前筛选条件的命题。' }}
        </div>
      </div>

      <!-- Table Mode View -->
      <div v-else class="overflow-x-auto">
        <el-table :data="filteredPapers" stripe style="width: 100%">
          <el-table-column label="断言 ID" width="110">
            <template #default="{ row }">
              <span class="font-mono text-xs text-sky-700 font-medium">{{ row.id.slice(0, 8) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="规范签名 (Subject | Predicate | Object)" min-width="280">
            <template #default="{ row }">
              <div
                @click="openPaperDrawer(row)"
                class="font-mono text-xs text-slate-800 hover:text-sky-600 cursor-pointer line-clamp-1"
              >
                {{ row.title }}
              </div>
              <div class="text-[11px] text-slate-400 mt-0.5 line-clamp-1">
                {{ row.abstract }}
              </div>
            </template>
          </el-table-column>

          <el-table-column label="状态" width="110" align="center">
            <template #default="{ row }">
              <el-tag
                :type="row.screeningStatus === 'included' ? 'success' : row.screeningStatus === 'flagged' ? 'warning' : row.screeningStatus === 'excluded' ? 'danger' : 'info'"
                size="small"
              >
                {{ statusLabel(row.studyType) }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="支持/反驳" width="100" align="center">
            <template #default="{ row }">
              <span class="text-xs font-mono">
                <span class="text-emerald-700">{{ row.supportCount ?? 0 }}</span>
                /
                <span class="text-rose-700">{{ row.contradictCount ?? 0 }}</span>
              </span>
            </template>
          </el-table-column>

          <el-table-column label="独立文献" width="90" align="center">
            <template #default="{ row }">
              <span class="text-xs font-mono text-slate-700">{{ row.sampleSize ?? 0 }}</span>
            </template>
          </el-table-column>

          <el-table-column label="标记" width="150" align="center">
            <template #default="{ row }">
              <div class="flex items-center justify-center gap-1">
                <el-tag v-if="row.independentValidation" type="success" size="small" effect="plain">独立验证</el-tag>
                <el-tag v-if="(row.contradictCount ?? 0) > 0" type="danger" size="small" effect="plain">反驳</el-tag>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="操作" width="140" align="right">
            <template #default="{ row }">
              <div class="flex items-center justify-end gap-1">
                <el-button link type="primary" size="small" @click="openPaperDrawer(row)">
                  证据
                </el-button>
                <el-button
                  link
                  :type="row.screeningStatus === 'included' ? 'danger' : 'success'"
                  size="small"
                  @click="updatePaperStatus(row, row.screeningStatus === 'included' ? 'excluded' : 'included')"
                >
                  {{ row.screeningStatus === 'included' ? '否决' : '批准' }}
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- Evidence Detail Drawer -->
    <el-drawer
      v-model="drawerVisible"
      title="证据溯源与审查"
      size="600px"
      direction="rtl"
      :destroy-on-close="true"
    >
      <div v-if="selectedPaper" class="space-y-5 text-slate-800">
        <!-- Signature & Status -->
        <div>
          <div class="flex items-center gap-2 text-xs text-slate-500 mb-1 flex-wrap">
            <span class="font-mono text-sky-700 font-semibold">断言 {{ selectedPaper.id.slice(0, 8) }}</span>
            <span aria-hidden="true">·</span>
            <span>版本 v{{ selectedPaper.claimVersion ?? '—' }}</span>
            <span aria-hidden="true">·</span>
            <span>{{ statusLabel(selectedPaper.studyType) }}</span>
            <span
              v-if="selectedPaper.independentValidation"
              class="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200/60"
            >独立验证</span>
          </div>
          <h2 class="text-sm font-bold text-slate-900 leading-snug font-mono break-all">
            {{ selectedPaper.title }}
          </h2>
        </div>

        <!-- Polarity Summary -->
        <div class="bg-slate-50 rounded-lg p-3.5 border border-slate-200">
          <h4 class="text-xs font-semibold text-slate-700 uppercase tracking-wide mb-2">证据极性汇总</h4>
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span class="text-slate-400">支持 (SUPPORT):</span>
              <span class="ml-1 font-mono font-semibold text-emerald-700">{{ selectedPaper.supportCount ?? 0 }}</span>
            </div>
            <div>
              <span class="text-slate-400">反驳 (CONTRADICT):</span>
              <span class="ml-1 font-mono font-semibold text-rose-700">{{ selectedPaper.contradictCount ?? 0 }}</span>
            </div>
            <div>
              <span class="text-slate-400">无效应 (NO_EFFECT):</span>
              <span class="ml-1 font-mono font-semibold text-slate-700">{{ selectedPaper.noEffectCount ?? 0 }}</span>
            </div>
            <div>
              <span class="text-slate-400">不确定 (UNCERTAIN):</span>
              <span class="ml-1 font-mono font-semibold text-amber-700">{{ selectedPaper.uncertainCount ?? 0 }}</span>
            </div>
            <div>
              <span class="text-slate-400">独立文献数:</span>
              <span class="ml-1 font-mono text-slate-800">{{ selectedPaper.sampleSize ?? 0 }}</span>
            </div>
            <div>
              <span class="text-slate-400">是否存在冲突:</span>
              <span class="ml-1 font-medium" :class="(selectedPaper.contradictCount ?? 0) > 0 ? 'text-rose-700' : 'text-emerald-700'">
                {{ (selectedPaper.contradictCount ?? 0) > 0 ? '是' : '否' }}
              </span>
            </div>
          </div>
        </div>

        <!-- Aggregation reasons -->
        <div v-if="selectedPaper.abstract">
          <h4 class="text-xs font-semibold text-slate-700 uppercase tracking-wide mb-1.5">聚合判定理由</h4>
          <div class="p-3 bg-slate-50/50 rounded-lg border border-slate-200 text-xs sm:text-sm text-slate-700 leading-relaxed">
            {{ selectedPaper.abstract }}
          </div>
        </div>

        <!-- Grounded Evidence Spans (real, loaded on open) -->
        <div>
          <div class="flex items-center justify-between mb-2">
            <h4 class="text-xs font-semibold text-slate-700 uppercase tracking-wide">证据原文片段</h4>
            <span class="text-[11px] text-slate-400 font-mono">{{ evidenceSpans.length }} 条</span>
          </div>

          <div v-if="evidenceLoading" class="p-6 text-center text-xs text-slate-400 flex items-center justify-center gap-2">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>正在加载证据片段...</span>
          </div>

          <div v-else-if="evidenceSpans.length === 0" class="p-6 text-center text-xs text-slate-400">
            该断言暂无证据片段。
          </div>

          <div v-else class="space-y-2.5">
            <div
              v-for="ev in evidenceSpans"
              :key="ev.evidence_id"
              class="p-3 rounded-lg border bg-white"
              :class="polarityBorderClass(ev.polarity)"
            >
              <div class="flex flex-wrap items-center gap-1.5 mb-1.5 text-[11px]">
                <span
                  :class="['px-1.5 py-0.5 rounded font-medium', polarityChipClass(ev.polarity)]"
                >{{ polarityLabel(ev.polarity) }}</span>
                <span class="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">{{ reviewLabel(ev.review_status) }}</span>
                <span v-if="ev.span?.section_path" class="font-mono text-slate-400">{{ ev.span.section_path }}</span>
                <span v-if="ev.span" class="font-mono text-slate-400">[{{ ev.span.start_char }}:{{ ev.span.end_char }}]</span>
              </div>
              <p class="text-xs text-slate-800 leading-relaxed">
                <span class="text-slate-400">"</span>{{ ev.span?.text }}<span class="text-slate-400">"</span>
              </p>
              <div v-if="ev.statistics && Object.keys(ev.statistics).length" class="mt-2 pt-2 border-t border-slate-100 flex flex-wrap gap-2">
                <span
                  v-for="(val, key) in ev.statistics"
                  :key="key"
                  class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-sky-50 text-sky-800"
                >{{ key }}: {{ typeof val === 'object' ? JSON.stringify(val) : val }}</span>
              </div>
              <div class="mt-2 text-[10px] font-mono text-slate-400">
                doc {{ (ev.span?.document_version_id ?? '').slice(0, 8) }} · passage {{ ev.span?.passage_id?.slice(0, 8) }} · 偏移定位可溯源
              </div>
            </div>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { ElMessage } from 'element-plus';
import { useResearch } from '@/composables/useResearch';

const {
  papers, createAndRunSession, loading: researchLoading, error: researchError,
  selectClaim, evidenceSpans, clearError, refreshQueue, claimVersions,
  submitReviewDecision,
} = useResearch();

const searchQuery = ref('');
const filterExpanded = ref(false);
const viewMode = ref<'card' | 'table'>('card');
const paperKeyword = ref('');
const activeScreeningFilter = ref<'all' | 'included' | 'flagged' | 'excluded'>('all');

// Drawer State
const drawerVisible = ref(false);
const selectedPaper = ref<(typeof papers.value)[0] | null>(null);
const evidenceLoading = ref(false);

// Advanced filters (operate on real fields)
const minDocuments = ref(0);
const onlyConflict = ref(false);
const onlyValidated = ref(false);
const sortBy = ref<'evidence' | 'support' | 'contradict' | 'documents'>('evidence');

/** isSearching 与全局管线 loading 保持同步（不再持有过期 ref 引用） */
const isSearching = computed(() => researchLoading.value);

const includedCount = computed(() => papers.value.filter(p => p.screeningStatus === 'included').length);
const flaggedCount = computed(() => papers.value.filter(p => p.screeningStatus === 'flagged').length);
const validatedCount = computed(() => papers.value.filter(p => p.independentValidation).length);

const screeningTabs = computed(() => [
  { key: 'all' as const, label: '全部命题', count: papers.value.length },
  { key: 'included' as const, label: '已批准', count: papers.value.filter(p => p.screeningStatus === 'included').length },
  { key: 'flagged' as const, label: '待复核', count: papers.value.filter(p => p.screeningStatus === 'flagged').length },
  { key: 'excluded' as const, label: '已否决', count: papers.value.filter(p => p.screeningStatus === 'excluded').length },
]);

const filteredPapers = computed(() => {
  const list = papers.value.filter(paper => {
    if (activeScreeningFilter.value !== 'all' && paper.screeningStatus !== activeScreeningFilter.value) {
      return false;
    }
    if (minDocuments.value > 0 && (paper.sampleSize ?? 0) < minDocuments.value) {
      return false;
    }
    if (onlyConflict.value && (paper.contradictCount ?? 0) === 0) {
      return false;
    }
    if (onlyValidated.value && !paper.independentValidation) {
      return false;
    }
    if (paperKeyword.value) {
      const q = paperKeyword.value.toLowerCase();
      const match = paper.title.toLowerCase().includes(q) ||
        paper.abstract.toLowerCase().includes(q) ||
        paper.id.toLowerCase().includes(q);
      if (!match) return false;
    }
    return true;
  });

  const sorted = [...list];
  sorted.sort((a, b) => {
    switch (sortBy.value) {
      case 'support': return (b.supportCount ?? 0) - (a.supportCount ?? 0);
      case 'contradict': return (b.contradictCount ?? 0) - (a.contradictCount ?? 0);
      case 'documents': return (b.sampleSize ?? 0) - (a.sampleSize ?? 0);
      default: return (b.evidenceCount ?? 0) - (a.evidenceCount ?? 0);
    }
  });
  return sorted;
});

type PaperRow = (typeof papers.value)[0];

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    CANDIDATE: '候选',
    APPROVED: '已批准',
    REJECTED: '已否决',
    REVIEWED: '已复核',
    SUPERSEDED: '已废弃',
  };
  return map[status] ?? status;
}

function polarityLabel(polarity: string): string {
  const map: Record<string, string> = {
    SUPPORT: '支持',
    CONTRADICT: '反驳',
    NO_EFFECT: '无效应',
    UNCERTAIN: '不确定',
  };
  return map[polarity] ?? polarity;
}

function polarityChipClass(polarity: string): string {
  switch (polarity) {
    case 'SUPPORT': return 'bg-emerald-50 text-emerald-700 border border-emerald-200/60';
    case 'CONTRADICT': return 'bg-rose-50 text-rose-700 border border-rose-200/60';
    case 'UNCERTAIN': return 'bg-amber-50 text-amber-700 border border-amber-200/60';
    default: return 'bg-slate-100 text-slate-600 border border-slate-200';
  }
}

function polarityBorderClass(polarity: string): string {
  switch (polarity) {
    case 'SUPPORT': return 'border-emerald-200';
    case 'CONTRADICT': return 'border-rose-200';
    case 'UNCERTAIN': return 'border-amber-200';
    default: return 'border-slate-200';
  }
}

function reviewLabel(status: string): string {
  const map: Record<string, string> = {
    PENDING: '待复核',
    ACCEPTED: '已接受',
    EDIT_ACCEPT: '修订后接受',
    REJECTED: '已否决',
    NEEDS_REVIEW: '需人工',
  };
  return map[status] ?? status;
}

function toggleFilterExpanded() {
  filterExpanded.value = !filterExpanded.value;
}

async function handleSearch() {
  const q = searchQuery.value.trim();
  if (!q) {
    ElMessage.warning('请输入研究问题或检索关键词');
    return;
  }
  try {
    await createAndRunSession(q);
    ElMessage.success(`挖掘完成: 产出 ${papers.value.length} 条证据聚合命题`);
  } catch {
    ElMessage.error(researchError.value ?? '挖掘管线执行失败');
  }
}

/** 使用复核队列提供的真实 claim 版本做乐观锁提交（替代硬编码 version=1） */
async function submitReviewForStatus(paper: PaperRow, status: 'included' | 'flagged' | 'excluded') {
  const decisionMap = {
    included: 'ACCEPT',
    excluded: 'REJECT',
    flagged: 'NEEDS_REVIEW',
  } as const;
  const decision = decisionMap[status];

  let version = paper.claimVersion ?? 0;
  if (version < 1) {
    // 版本号缺失：刷新复核队列后重取
    await refreshQueue();
    version = claimVersions.value.get(paper.id) ?? 0;
  }
  if (version < 1) {
    ElMessage.error('无法获取该断言的当前版本号（可能已终审，不在待复核队列中）');
    return;
  }

  await submitReviewDecision(
    paper.id,
    decision,
    `Literature view: marked as ${status}`,
    version,
  );
  ElMessage.success(`已${status === 'included' ? '批准纳入' : status === 'excluded' ? '否决' : '转人工复核'}`);
}

async function updatePaperStatus(paper: PaperRow, status: 'included' | 'flagged' | 'excluded') {
  try {
    await submitReviewForStatus(paper, status);
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  }
}

async function openPaperDrawer(paper: PaperRow) {
  selectedPaper.value = paper;
  drawerVisible.value = true;
  evidenceLoading.value = true;
  try {
    await selectClaim(paper.id);
  } finally {
    evidenceLoading.value = false;
  }
}
</script>
