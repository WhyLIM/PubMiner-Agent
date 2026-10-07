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
          <div class="flex items-center gap-2 shrink-0">
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
            <label class="block text-slate-500 mb-1 font-medium">
              {{ displayDim === 'document' ? '最少证据条数' : '最少独立文献数' }}
            </label>
            <el-select v-model="minDocuments" placeholder="不限" size="small" class="w-full">
              <el-option label="不限" :value="0" />
              <el-option label="≥ 2" :value="2" />
              <el-option label="≥ 3 (独立验证阈值)" :value="3" />
              <el-option label="≥ 5" :value="5" />
            </el-select>
          </div>

          <div>
            <label class="block text-slate-500 mb-1 font-medium">证据倾向</label>
            <div class="pt-1.5 flex flex-wrap items-center gap-3">
              <el-checkbox v-model="onlyConflict" label="仅看存在反驳证据" size="small" />
              <el-checkbox v-if="displayDim === 'claim'" v-model="onlyValidated" label="仅看独立验证" size="small" />
            </div>
          </div>

          <div>
            <label class="block text-slate-500 mb-1 font-medium">排序方式</label>
            <el-select v-model="sortBy" size="small" class="w-full">
              <el-option label="证据总数 (多 → 少)" value="evidence" />
              <el-option label="支持证据 (多 → 少)" value="support" />
              <el-option label="反驳证据 (多 → 少)" value="contradict" />
              <el-option v-if="displayDim === 'claim'" label="独立文献数 (多 → 少)" value="documents" />
            </el-select>
          </div>
        </div>
      </div>
    </div>

    <!-- 研究目标确认（AskHuman 对话式澄清 + 检索式预览） -->
    <div v-if="setup" class="bg-white rounded-lg border border-sky-200 shadow-xs overflow-hidden">
      <div class="px-4 py-2.5 flex items-center justify-between bg-sky-50/70 border-b border-sky-100">
        <div class="flex items-center gap-2">
          <el-icon class="text-sky-600"><ChatDotRound /></el-icon>
          <span class="text-sm font-bold text-slate-800">研究目标确认</span>
          <span class="text-[11px] font-mono text-slate-400">{{ setupPhaseLabel }}</span>
        </div>
        <el-button size="small" text :disabled="setup.phase === 'running'" @click="closeSetup">取消</el-button>
      </div>

      <div class="flex flex-col h-[400px]">
        <!-- 对话区 -->
        <div ref="setupChatRef" class="flex-1 overflow-y-auto p-4 space-y-3 text-xs">
          <div
            v-for="(m, i) in setup.messages"
            :key="i"
            :class="[
              'p-3 rounded-lg leading-relaxed whitespace-pre-line',
              m.sender === 'user'
                ? 'ml-10 bg-sky-600 text-white'
                : 'mr-10 bg-slate-50 border border-slate-200 text-slate-800'
            ]"
          >{{ m.text }}</div>
          <div v-if="setup.phase === 'parsing'" class="text-slate-400 flex items-center gap-2 mr-10">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>解析中…</span>
          </div>
        </div>

        <!-- 检索式预览 / 编辑 + 主操作（无检索式时也可跳过/默认执行） -->
        <div v-if="setup.phase !== 'running' && setup.phase !== 'parsing'" class="border-t border-slate-100 p-3 space-y-2">
          <div v-if="setup.intents.length" class="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">检索式（可直接编辑）</div>
          <div v-else class="text-[11px] text-slate-400">尚未生成检索式；补充信息后会自动重新生成，也可按默认参数直接执行。</div>
          <div v-for="(si, i) in setup.intents" :key="i" class="space-y-0.5">
            <div class="flex items-center gap-2">
              <span class="text-[11px] text-slate-500 w-24 shrink-0 truncate" :title="si.name">{{ si.name }}</span>
              <el-input v-model="si.query" size="small" class="font-mono" />
            </div>
            <div v-if="si.explanation" class="text-[11px] text-slate-400 pl-[6.5rem]">{{ si.explanation }}</div>
          </div>
          <div class="flex items-center justify-between pt-1 gap-2">
            <span v-if="setup.phase === 'clarify'" class="text-[11px] text-amber-600">
              还有待确认的信息；可直接回答上方问题，或跳过追问。
            </span>
            <span v-else class="text-[11px] text-slate-400">确认无误即可开始挖掘。</span>
            <div class="ml-auto flex items-center gap-2 shrink-0">
              <el-button v-if="setup.phase === 'clarify'" size="small" @click="skipClarify">跳过追问</el-button>
              <el-button type="primary" size="small" @click="runSetup">开始挖掘</el-button>
            </div>
          </div>
        </div>

        <!-- 追问回答输入 -->
        <div v-if="setup.phase === 'clarify'" class="border-t border-slate-100 p-3 flex gap-2">
          <el-input
            v-model="setupInput"
            placeholder="用自然语言回答（如：胰腺癌，关注预后，2020 年以来）…"
            size="small"
            @keyup.enter="sendClar"
          />
          <el-button type="primary" size="small" @click="sendClar">发送</el-button>
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
        <span class="text-xs text-slate-500 font-medium">{{ displayDim === 'document' ? '检索文献' : '证据聚合命题' }}</span>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-2xl font-bold font-mono text-slate-900">{{ displayDim === 'document' ? documents.length : papers.length }}</span>
          <span class="text-xs text-slate-400 font-mono">{{ displayDim === 'document' ? '篇文献' : '条断言' }}</span>
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

    <!-- 管线执行监控（可展开面板，替代独立"智能体协同中心"页） -->
    <div class="bg-white rounded-lg border border-slate-200 shadow-xs overflow-hidden">
      <div
        class="px-4 py-2.5 flex items-center justify-between gap-3 bg-slate-50/70 cursor-pointer select-none hover:bg-slate-50 transition-colors"
        @click="workflowPanelOpen = !workflowPanelOpen"
      >
        <div class="flex items-center gap-2 min-w-0">
          <el-icon class="text-slate-400 transition-transform" :class="workflowPanelOpen ? 'rotate-180' : ''"><ArrowDown /></el-icon>
          <span class="text-sm font-bold text-slate-800 shrink-0">管线执行监控</span>
          <span v-if="miningActive" class="px-2 py-0.5 rounded bg-sky-50 text-sky-700 font-mono text-[11px] animate-pulse">执行中</span>
          <span v-else-if="wfLiveStatus" :class="['px-2 py-0.5 rounded font-mono text-[11px]', wfStatusClass]">{{ wfLiveStatus }}</span>
          <span v-if="taskSteps.length" class="font-mono text-[11px] text-slate-400">{{ wfSucceeded }}/{{ taskSteps.length }} 步完成</span>
        </div>
        <span class="text-[11px] text-slate-400 font-mono shrink-0">{{ workflowPanelOpen ? '收起' : '展开' }}</span>
      </div>
      <div v-show="workflowPanelOpen" class="p-4 border-t border-slate-100">
        <AgentWorkflowView />
      </div>
    </div>

    <!-- Evidence List & Screening Board -->
    <div class="bg-white rounded-lg border border-slate-200 shadow-xs overflow-hidden">
      <!-- Toolbar -->
      <div class="px-4 py-3 border-b border-slate-200 flex flex-nowrap items-center justify-between gap-3 bg-slate-50/70 overflow-x-auto">
        <div class="flex items-center gap-1 shrink-0">
          <template v-if="displayDim === 'claim'">
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
          </template>
          <span v-else class="text-xs text-slate-500 font-medium px-1">
            共 {{ filteredDocuments.length }} 篇文献（按证据数排序）
          </span>
        </div>

        <div class="flex items-center gap-3 shrink-0 flex-nowrap">
          <!-- 展示维度切换：按命题 / 按文献 -->
          <el-radio-group v-model="displayDim" size="small" class="shrink-0">
            <el-radio-button value="claim">按命题</el-radio-button>
            <el-radio-button value="document">按文献</el-radio-button>
          </el-radio-group>
          <el-input
            v-model="paperKeyword"
            :placeholder="displayDim === 'document' ? '过滤文献 (标题/期刊/PMID)...' : '在结果中快速过滤...'"
            prefix-icon="Search"
            size="small"
            clearable
            style="width: 11rem"
          />
          <!-- 视图切换：与维度切换同款分段样式 -->
          <el-radio-group v-if="displayDim === 'claim'" v-model="viewMode" size="small" class="shrink-0">
            <el-radio-button value="card">
              <span class="flex items-center gap-1"><el-icon><Menu /></el-icon>卡片</span>
            </el-radio-button>
            <el-radio-button value="table">
              <span class="flex items-center gap-1"><el-icon><Tickets /></el-icon>列表</span>
            </el-radio-button>
          </el-radio-group>
        </div>
      </div>

      <!-- ==================== 按命题 ==================== -->
      <template v-if="displayDim === 'claim'">
        <!-- Card Mode View -->
        <div v-if="viewMode === 'card'" class="p-3 space-y-3 bg-slate-50/60">
          <div
            v-for="paper in pagedPapers"
            :key="paper.id"
            class="p-4 sm:p-5 bg-white border border-slate-200 rounded-lg shadow-xs hover:border-sky-300 hover:shadow-sm transition-all flex flex-col gap-3 group"
          >
            <!-- Metadata Kicker Line -->
            <div class="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-mono text-slate-400">断言 {{ paper.id.slice(0, 8) }}</span>
                <span aria-hidden="true" class="text-slate-300">·</span>
                <span class="text-sky-700 font-medium">{{ statusLabel(paper.studyType) }}</span>
                <span
                  v-if="(paper.memberCount ?? 1) > 1"
                  class="px-1.5 py-0.5 rounded bg-violet-50 text-violet-700 border border-violet-200/60 font-medium"
                  title="同标志物的多条同义命题已合并，可整组复核"
                >合并 {{ paper.memberCount }} 条</span>
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
              <div class="flex items-center gap-1.5 shrink-0">
                <el-dropdown
                  v-if="paper.screeningStatus === 'flagged' && groupMembers(paper.id).length > 1"
                  @command="(cmd: string) => groupReview(paper, cmd === 'included' ? 'included' : 'excluded')"
                >
                  <button
                    class="px-2 py-1 text-xs font-medium rounded bg-violet-50 text-violet-700 hover:bg-violet-100 flex items-center gap-1"
                    title="对簇内全部同义命题执行同一判定"
                  >
                    <span>整组 ×{{ groupMembers(paper.id).length }}</span>
                    <el-icon :size="10"><ArrowDown /></el-icon>
                  </button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="included">整组批准</el-dropdown-item>
                      <el-dropdown-item command="excluded">整组否决</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
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

            <!-- Title -->
            <h3
              @click="openPaperDrawer(paper)"
              class="text-sm sm:text-base font-semibold text-sky-800 group-hover:text-sky-600 transition-colors cursor-pointer leading-snug font-mono"
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
          <el-table :data="pagedPapers" stripe style="width: 100%">
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

        <!-- Pagination -->
        <div v-if="filteredPapers.length > 0" class="px-4 py-3 border-t border-slate-100 flex items-center justify-between bg-slate-50/50">
          <span class="text-xs text-slate-400">共 {{ filteredPapers.length }} 条命题</span>
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :page-sizes="[10, 20, 50]"
            :total="filteredPapers.length"
            layout="sizes, prev, pager, next, jumper"
            background
          />
        </div>
      </template>

      <!-- ==================== 按文献 ==================== -->
      <template v-else>
        <div class="p-3 space-y-3 bg-slate-50/60">
          <div
            v-for="doc in pagedDocuments"
            :key="doc.document_id"
            class="p-4 sm:p-5 bg-white border border-slate-200 rounded-lg shadow-xs hover:border-sky-300 hover:shadow-sm transition-all flex flex-col gap-3 group"
          >
            <!-- Kicker: identifiers + journal -->
            <div class="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
              <div class="flex items-center gap-2 flex-wrap">
                <span v-if="doc.pmid" class="font-mono text-sky-700 font-medium">PMID: {{ doc.pmid }}</span>
                <span v-if="doc.pmcid" class="font-mono text-emerald-700">PMCID: {{ doc.pmcid }}</span>
                <span v-if="doc.journal" aria-hidden="true" class="text-slate-300">·</span>
                <span v-if="doc.journal" class="font-semibold text-slate-700 line-clamp-1">{{ doc.journal }}</span>
                <span v-if="doc.year" aria-hidden="true" class="text-slate-300">·</span>
                <span v-if="doc.year" class="font-mono">{{ doc.year }}</span>
                <span v-if="doc.source" class="px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 font-mono text-[10px]">{{ doc.source }}</span>
              </div>
              <span class="px-2 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200/60 font-mono text-[11px] shrink-0">
                {{ doc.evidence_count }} 条证据
              </span>
            </div>

            <!-- Real title -->
            <h3
              @click="openDocById(doc.document_id)"
              class="text-sm sm:text-base font-semibold text-sky-800 group-hover:text-sky-600 transition-colors cursor-pointer leading-snug"
            >
              {{ doc.title || '(无标题文献)' }}
            </h3>

            <!-- Authors -->
            <div v-if="doc.authors.length" class="text-xs text-slate-500 italic line-clamp-1">
              {{ doc.authors.slice(0, 6).join(', ') }}{{ doc.authors.length > 6 ? ' et al.' : '' }}
            </div>

            <!-- Abstract -->
            <p v-if="doc.abstract" class="text-xs sm:text-sm text-slate-600 leading-relaxed line-clamp-2">
              {{ doc.abstract }}
            </p>

            <!-- Footer: polarity counts + linked claims -->
            <div class="flex flex-wrap items-center justify-between gap-3 pt-1 text-xs border-t border-slate-100">
              <div class="flex flex-wrap items-center gap-3">
                <span class="text-slate-600">
                  <span class="text-slate-400">支持</span>
                  <span class="ml-1 font-mono font-semibold text-emerald-700">{{ doc.support_count }}</span>
                </span>
                <span class="text-slate-600">
                  <span class="text-slate-400">反驳</span>
                  <span class="ml-1 font-mono font-semibold text-rose-700">{{ doc.contradict_count }}</span>
                </span>
                <span class="text-slate-600">
                  <span class="text-slate-400">无效应</span>
                  <span class="ml-1 font-mono font-semibold text-slate-700">{{ doc.no_effect_count }}</span>
                </span>
                <span class="text-slate-600">
                  <span class="text-slate-400">不确定</span>
                  <span class="ml-1 font-mono font-semibold text-amber-700">{{ doc.uncertain_count }}</span>
                </span>
              </div>

              <div class="flex items-center gap-1.5 flex-wrap">
                <span
                  v-for="claim in doc.claims.slice(0, 2)"
                  :key="claim.claim_id"
                  class="px-2 py-0.5 rounded text-[11px] bg-slate-50 text-slate-600 border border-slate-200/60 font-mono max-w-[220px] truncate"
                  :title="claim.canonical_signature"
                >
                  {{ shortSignature(claim.canonical_signature) }}
                </span>
                <span v-if="doc.claims.length > 2" class="text-[11px] text-slate-400 font-mono">
                  +{{ doc.claims.length - 2 }}
                </span>
                <button
                  @click="openDocById(doc.document_id)"
                  class="text-xs text-sky-600 hover:text-sky-800 font-medium ml-1 flex items-center gap-0.5 shrink-0"
                >
                  <span>文献详情与证据</span>
                  <el-icon :size="12"><ArrowRight /></el-icon>
                </button>
              </div>
            </div>
          </div>

          <div v-if="filteredDocuments.length === 0" class="p-12 text-center text-slate-400 text-xs">
            {{ documents.length === 0 ? '暂无文献数据：请先启动一次挖掘管线。' : '没有匹配当前筛选条件的文献。' }}
          </div>
        </div>

        <!-- Pagination -->
        <div v-if="filteredDocuments.length > 0" class="px-4 py-3 border-t border-slate-100 flex items-center justify-between bg-slate-50/50">
          <span class="text-xs text-slate-400">共 {{ filteredDocuments.length }} 篇文献</span>
          <el-pagination
            v-model:current-page="docPage"
            v-model:page-size="docPageSize"
            :page-sizes="[10, 20, 50]"
            :total="filteredDocuments.length"
            layout="sizes, prev, pager, next, jumper"
            background
          />
        </div>
      </template>
    </div>

    <!-- ==================== 命题证据抽屉 ==================== -->
    <el-drawer
      v-model="drawerVisible"
      title="证据溯源与审查"
      size="640px"
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

        <!-- Grounded Evidence Spans with highlight -->
        <div>
          <div class="flex items-center justify-between mb-2">
            <h4 class="text-xs font-semibold text-slate-700 uppercase tracking-wide">证据原文片段（高亮定位）</h4>
            <span class="text-[11px] text-slate-400 font-mono">{{ evidenceSpans.length }} 条</span>
          </div>

          <div v-if="evidenceLoading" class="p-6 text-center text-xs text-slate-400 flex items-center justify-center gap-2">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>正在加载证据片段...</span>
          </div>

          <div v-else-if="evidenceSpans.length === 0" class="p-6 text-center text-xs text-slate-400">
            该断言暂无证据片段。
          </div>

          <div v-else class="space-y-3">
            <div
              v-for="ev in evidenceSpans"
              :key="ev.evidence_id"
              class="p-3 rounded-lg border bg-white"
              :class="polarityBorderClass(ev.polarity)"
            >
              <div class="flex flex-wrap items-center gap-1.5 mb-2 text-[11px]">
                <span :class="['px-1.5 py-0.5 rounded font-medium', polarityChipClass(ev.polarity)]">
                  {{ polarityLabel(ev.polarity) }}
                </span>
                <span class="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">{{ reviewLabel(ev.review_status) }}</span>
                <span v-if="ev.document_title" class="text-slate-500 line-clamp-1 max-w-[260px]" :title="ev.document_title">
                  {{ ev.document_title }}
                </span>
              </div>

              <!-- 原文 + span 高亮 -->
              <template v-if="ctxFor(ev)">
                <SpanHighlight
                  :canonical-text="ctxFor(ev)!.text"
                  :start-char="ctxFor(ev)!.start"
                  :end-char="ctxFor(ev)!.end"
                />
              </template>
              <p v-else class="text-xs text-slate-800 leading-relaxed">
                {{ ev.span?.text }}
              </p>

              <div class="mt-2 pt-2 border-t border-slate-100 flex flex-wrap items-center gap-1.5 text-[10px] font-mono text-slate-400">
                <span v-if="ev.span?.section_path">{{ ev.span.section_path }}</span>
                <span v-if="ev.span">[{{ ev.span.start_char }}:{{ ev.span.end_char }}]</span>
                <span v-if="ev.document_id">doc {{ ev.document_id.slice(0, 8) }}</span>
                <button
                  v-if="ev.document_id"
                  @click="openDocById(ev.document_id, { closeClaimDrawer: true })"
                  class="ml-auto text-sky-600 hover:text-sky-800 font-medium"
                >查看文献 →</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- ==================== 文献详情抽屉 ==================== -->
    <el-drawer
      v-model="docDrawerVisible"
      title="文献详情与证据溯源"
      size="720px"
      direction="rtl"
      :destroy-on-close="true"
    >
      <div v-if="docDetail" class="space-y-5 text-slate-800">
        <!-- Identifiers & links -->
        <div>
          <div class="flex flex-wrap items-center gap-2 text-xs mb-2">
            <a
              v-if="docDetail.pmid"
              :href="'https://pubmed.ncbi.nlm.nih.gov/' + docDetail.pmid"
              target="_blank"
              class="px-2 py-1 rounded border border-slate-300 hover:bg-slate-50 text-sky-700 font-mono flex items-center gap-1"
            >
              <el-icon><Link /></el-icon> PMID: {{ docDetail.pmid }}
            </a>
            <a
              v-if="docDetail.pmcid"
              :href="'https://www.ncbi.nlm.nih.gov/pmc/articles/' + docDetail.pmcid + '/'"
              target="_blank"
              class="px-2 py-1 rounded border border-slate-300 hover:bg-slate-50 text-emerald-700 font-mono flex items-center gap-1"
            >
              <el-icon><Document /></el-icon> {{ docDetail.pmcid }}
            </a>
            <a
              v-if="docDetail.doi"
              :href="'https://doi.org/' + docDetail.doi"
              target="_blank"
              class="px-2 py-1 rounded border border-slate-300 hover:bg-slate-50 text-slate-600 font-mono flex items-center gap-1"
            >
              <el-icon><Link /></el-icon> DOI
            </a>
            <span class="text-slate-400 font-mono ml-auto">{{ docDetail.source }}</span>
          </div>
          <h2 class="text-base font-bold text-slate-900 leading-snug">
            {{ docDetail.title || '(无标题文献)' }}
          </h2>
          <div class="text-xs text-slate-500 mt-1.5">
            <span v-if="docDetail.journal" class="font-semibold text-slate-700">{{ docDetail.journal }}</span>
            <span v-if="docDetail.year" class="ml-2 font-mono">{{ docDetail.year }}</span>
            <div v-if="docDetail.authors.length" class="italic mt-1 line-clamp-2">
              {{ docDetail.authors.join(', ') }}
            </div>
          </div>
        </div>

        <!-- Polarity summary -->
        <div class="bg-slate-50 rounded-lg p-3.5 border border-slate-200">
          <h4 class="text-xs font-semibold text-slate-700 uppercase tracking-wide mb-2">证据极性汇总</h4>
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span class="text-slate-400">证据总数:</span>
              <span class="ml-1 font-mono font-semibold text-slate-800">{{ docDetail.evidence_count }}</span>
            </div>
            <div>
              <span class="text-slate-400">关联命题:</span>
              <span class="ml-1 font-mono font-semibold text-slate-800">{{ docDetail.claims.length }}</span>
            </div>
            <div>
              <span class="text-slate-400">支持:</span>
              <span class="ml-1 font-mono font-semibold text-emerald-700">{{ docDetail.support_count }}</span>
            </div>
            <div>
              <span class="text-slate-400">反驳:</span>
              <span class="ml-1 font-mono font-semibold text-rose-700">{{ docDetail.contradict_count }}</span>
            </div>
          </div>
        </div>

        <!-- Abstract -->
        <div v-if="docDetail.abstract">
          <h4 class="text-xs font-semibold text-slate-700 uppercase tracking-wide mb-1.5">摘要 (Abstract)</h4>
          <div class="p-3 bg-slate-50/50 rounded-lg border border-slate-200 text-xs text-slate-700 leading-relaxed max-h-48 overflow-y-auto">
            {{ docDetail.abstract }}
          </div>
        </div>

        <!-- Linked claims -->
        <div v-if="docDetail.claims.length">
          <h4 class="text-xs font-semibold text-slate-700 uppercase tracking-wide mb-2">关联命题 ({{ docDetail.claims.length }})</h4>
          <div class="space-y-1.5">
            <div
              v-for="claim in docDetail.claims"
              :key="claim.claim_id"
              class="p-2.5 rounded-lg border border-slate-200 bg-white text-xs flex items-center justify-between gap-2"
            >
              <span class="font-mono text-slate-700 line-clamp-1" :title="claim.canonical_signature">
                {{ shortSignature(claim.canonical_signature) }}
              </span>
              <span class="flex items-center gap-2 font-mono text-[11px] shrink-0">
                <span class="text-emerald-700">S{{ claim.support_count }}</span>
                <span class="text-rose-700">C{{ claim.contradict_count }}</span>
                <span class="text-amber-700">U{{ claim.uncertain_count }}</span>
                <el-tag size="small" type="info" effect="plain">{{ statusLabel(claim.status) }}</el-tag>
              </span>
            </div>
          </div>
        </div>

        <!-- Evidence spans with highlight -->
        <div>
          <h4 class="text-xs font-semibold text-slate-700 uppercase tracking-wide mb-2">
            证据原文片段（高亮定位，{{ docDetail.evidence.length }} 条）
          </h4>
          <div class="space-y-3">
            <div
              v-for="ev in docDetail.evidence"
              :key="ev.evidence_id"
              class="p-3 rounded-lg border bg-white"
              :class="polarityBorderClass(ev.polarity)"
            >
              <div class="flex flex-wrap items-center gap-1.5 mb-2 text-[11px]">
                <span :class="['px-1.5 py-0.5 rounded font-medium', polarityChipClass(ev.polarity)]">
                  {{ polarityLabel(ev.polarity) }}
                </span>
                <span class="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">{{ reviewLabel(ev.review_status) }}</span>
                <span v-if="ev.section_path" class="font-mono text-slate-400">{{ ev.section_path }}</span>
              </div>
              <!-- 原文窗口 + span 高亮（全文文献只展示 span 前后各 ~200 字符） -->
              <SpanHighlight
                v-if="docCtx(ev)"
                :canonical-text="docCtx(ev)!.text"
                :start-char="docCtx(ev)!.start"
                :end-char="docCtx(ev)!.end"
              />
              <p v-else class="text-xs text-slate-800 leading-relaxed">
                {{ ev.span_text }}
              </p>
              <div class="mt-2 pt-2 border-t border-slate-100 flex items-center gap-2 text-[10px] font-mono text-slate-400">
                <span class="line-clamp-1" :title="ev.claim_signature">{{ shortSignature(ev.claim_signature) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="p-12 text-center text-xs text-slate-400 flex items-center justify-center gap-2">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在加载文献详情...</span>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue';
import { ElMessage } from 'element-plus';
import SpanHighlight from './SpanHighlight.vue';
import AgentWorkflowView from './AgentWorkflowView.vue';
import { agentApi, type DocumentDetail, type DocumentEvidenceEntry, type EvidenceSpanItem } from '@/api/client';
import { useResearch } from '@/composables/useResearch';

const {
  papers, documents, miningActive, error: researchError,
  selectClaim, evidenceSpans, clearError, refreshQueue, claimVersions,
  submitReviewDecision,
  workflowPanelOpen, taskStatus, taskSteps,
  setup, startGoalSetup, sendClarification, confirmAndRun, closeSetup,
  reviewQueue, refreshClaims, refreshAggregations,
} = useResearch();

const searchQuery = ref('');
const filterExpanded = ref(false);
const viewMode = ref<'card' | 'table'>('card');
const paperKeyword = ref('');
const activeScreeningFilter = ref<'all' | 'included' | 'flagged' | 'excluded'>('all');
/** 展示维度：按命题（claim 聚合） / 按文献（document） */
const displayDim = ref<'claim' | 'document'>('claim');

// Claim Drawer State
const drawerVisible = ref(false);
const selectedPaper = ref<(typeof papers.value)[0] | null>(null);
const evidenceLoading = ref(false);

// Document Drawer State
const docDrawerVisible = ref(false);
const docDetail = ref<DocumentDetail | null>(null);

// Advanced filters (operate on real fields)
const minDocuments = ref(0);
const onlyConflict = ref(false);
const onlyValidated = ref(false);
const sortBy = ref<'evidence' | 'support' | 'contradict' | 'documents'>('evidence');

/** isSearching 仅在挖掘管线真正运行时为 true（而非任何接口加载） */
const isSearching = computed(() => miningActive.value);

// ---- 管线执行监控面板 ----
const wfLiveStatus = computed(() => taskStatus.value);
const wfSucceeded = computed(() => taskSteps.value.filter(s => s.status === 'SUCCEEDED').length);
const wfStatusClass = computed(() => {
  const s = wfLiveStatus.value;
  if (!s) { return 'bg-slate-100 text-slate-600'; }
  if (s === 'COMPLETED' || s === 'REVIEW_READY') { return 'bg-emerald-50 text-emerald-700'; }
  if (s === 'FAILED' || s === 'CANCELLED') { return 'bg-rose-50 text-rose-700'; }
  if (s === 'PARTIAL') { return 'bg-amber-50 text-amber-700'; }
  return 'bg-sky-50 text-sky-700';
});
// 挖掘启动时自动展开面板，进度一目了然
watch(miningActive, (v) => {
  if (v) { workflowPanelOpen.value = true; }
});

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

// ---- 命题列表分页（依赖 filteredPapers，必须声明在其后） ----
const currentPage = ref(1);
const pageSize = ref(10);
const pagedPapers = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return filteredPapers.value.slice(start, start + pageSize.value);
});
// 任一筛选条件变化时回到第一页
watch([paperKeyword, activeScreeningFilter, minDocuments, onlyConflict, onlyValidated, sortBy, displayDim], () => {
  currentPage.value = 1;
});
// 数据刷新（复核提交/新挖掘）导致列表变短时，防止当前页超出范围出现空页
watch(() => filteredPapers.value.length, (len) => {
  const maxPage = Math.max(1, Math.ceil(len / pageSize.value));
  if (currentPage.value > maxPage) { currentPage.value = 1; }
});

const filteredDocuments = computed(() => {
  const list = documents.value.filter(doc => {
    if (minDocuments.value > 0 && doc.evidence_count < minDocuments.value) {
      return false;
    }
    if (onlyConflict.value && doc.contradict_count === 0) {
      return false;
    }
    if (paperKeyword.value) {
      const q = paperKeyword.value.toLowerCase();
      const match = doc.title.toLowerCase().includes(q) ||
        doc.journal.toLowerCase().includes(q) ||
        doc.abstract.toLowerCase().includes(q) ||
        doc.pmid.includes(q) ||
        doc.authors.join(' ').toLowerCase().includes(q);
      if (!match) return false;
    }
    return true;
  });
  const sorted = [...list];
  sorted.sort((a, b) => {
    switch (sortBy.value) {
      case 'support': return b.support_count - a.support_count;
      case 'contradict': return b.contradict_count - a.contradict_count;
      case 'documents': return b.claims.length - a.claims.length;
      default: return b.evidence_count - a.evidence_count;
    }
  });
  return sorted;
});

// ---- 文献列表分页（依赖 filteredDocuments，必须声明在其后） ----
const docPage = ref(1);
const docPageSize = ref(10);
const pagedDocuments = computed(() => {
  const start = (docPage.value - 1) * docPageSize.value;
  return filteredDocuments.value.slice(start, start + docPageSize.value);
});
watch([paperKeyword, minDocuments, onlyConflict, sortBy, displayDim], () => {
  docPage.value = 1;
});
watch(() => filteredDocuments.value.length, (len) => {
  const maxPage = Math.max(1, Math.ceil(len / docPageSize.value));
  if (docPage.value > maxPage) { docPage.value = 1; }
});

type PaperRow = (typeof papers.value)[0];

/** 规范签名缩短为 "Subject → Object" 形式用于窄容器展示 */
function shortSignature(sig: string): string {
  const parts = sig.split(' | ');
  if (parts.length >= 3) {
    const subj = parts[0].length > 24 ? parts[0].slice(0, 24) + '…' : parts[0];
    return `${subj} → ${parts[2]}`;
  }
  return sig.length > 40 ? sig.slice(0, 40) + '…' : sig;
}

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
    pending: '待复核',
    ACCEPTED: '已接受',
    EDIT_ACCEPT: '修订后接受',
    REJECTED: '已否决',
    NEEDS_REVIEW: '需人工',
  };
  return map[status] ?? status;
}

/**
 * 计算 span 高亮窗口：原文过长时只取 span 前后各 ~200 字符，
 * 返回窗口文本及 span 在窗口内的相对偏移。
 */
function highlightWindow(text: string, start: number, end: number, pad = 200): { text: string; start: number; end: number } | null {
  if (!text) { return null; }
  if (text.length <= pad * 2 + (end - start)) {
    return { text, start, end };
  }
  const ws = Math.max(0, start - pad);
  const we = Math.min(text.length, end + pad);
  const prefix = ws > 0 ? '… ' : '';
  const suffix = we < text.length ? ' …' : '';
  return {
    text: prefix + text.slice(ws, we) + suffix,
    start: start - ws + prefix.length,
    end: end - ws + prefix.length,
  };
}

/** 命题抽屉：为每条证据计算高亮窗口（canonical_text 完整时窗口即全文） */
function ctxFor(ev: EvidenceSpanItem) {
  const text = ev.canonical_text ?? '';
  if (!text || !ev.span) { return null; }
  return highlightWindow(text, ev.span.start_char, ev.span.end_char);
}

/** 文献抽屉：同上，避免 PMC 全文逐条渲染整篇论文 */
function docCtx(ev: DocumentEvidenceEntry) {
  const text = ev.canonical_text || '';
  if (!text) { return null; }
  return highlightWindow(text, ev.start_char, ev.end_char);
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
    // 两段式启动：解析目标（+ AskHuman 澄清）→ 确认检索式后开跑
    await startGoalSetup(q);
    await nextTick();
    scrollSetupChat();
  } catch {
    ElMessage.error(researchError.value ?? '会话创建失败');
  }
}

// ---- 研究目标确认对话 ----
const setupInput = ref('');
const setupChatRef = ref<HTMLDivElement | null>(null);
const setupPhaseLabel = computed(() => {
  switch (setup.value?.phase) {
    case 'parsing': return '解析中';
    case 'clarify': return '等待你的回答';
    case 'ready': return '待确认';
    case 'running': return '挖掘执行中';
    default: return '';
  }
});

function scrollSetupChat() {
  const el = setupChatRef.value;
  if (el) { el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' }); }
}

async function sendClar() {
  const t = setupInput.value.trim();
  if (!t) { return; }
  setupInput.value = '';
  await sendClarification(t);
  await nextTick();
  scrollSetupChat();
}

function skipClarify() {
  if (!setup.value) { return; }
  setup.value.rounds = 99;
  setup.value.phase = 'ready';
  setup.value.messages.push({ sender: 'ai', text: '已跳过追问，将按当前解析结果执行（缺失字段使用默认值）。' });
  void nextTick(scrollSetupChat);
}

async function runSetup() {
  workflowPanelOpen.value = true; // 启动即展开监控，进度可见
  try {
    await confirmAndRun();
    ElMessage.success(`挖掘完成: 产出 ${papers.value.length} 条命题、${documents.value.length} 篇文献`);
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

// ---- 同义命题簇整组复核 ----
function groupMembers(claimId: string): Array<{ claim_id: string; version: number; signature: string }> {
  const item = reviewQueue.value.find(i => i.claim_id === claimId);
  return item?.members ?? [];
}

async function groupReview(paper: PaperRow, status: 'included' | 'excluded') {
  const members = groupMembers(paper.id);
  if (members.length <= 1) { return; }
  const decision = status === 'included' ? 'ACCEPT' as const : 'REJECT' as const;
  let ok = 0;
  let fail = 0;
  for (const m of members) {
    try {
      // 直调 API：整组结束后统一刷新，避免逐成员 3 请求
      await agentApi.submitReviewDecision({
        claim_id: m.claim_id, decision, reviewer_id: 'curator',
        reason: `Group review: ${status}`, expected_version: m.version,
      });
      ok += 1;
    } catch {
      fail += 1; // 单个成员失败（如已被终审）不阻断整组
    }
  }
  await Promise.all([refreshQueue(), refreshClaims(), refreshAggregations()]);
  if (fail) {
    ElMessage.warning(`整组操作完成：成功 ${ok} 条，失败 ${fail} 条（可能已被终审）`);
  } else {
    ElMessage.success(`整组操作完成：${ok} 条命题已${status === 'included' ? '批准' : '否决'}`);
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

/** 打开文献抽屉（文献列表点击、命题抽屉内跳转共用；传入时关闭命题抽屉） */
async function openDocById(documentId: string, { closeClaimDrawer = false } = {}) {
  if (closeClaimDrawer) { drawerVisible.value = false; }
  docDrawerVisible.value = true;
  docDetail.value = null;
  try {
    docDetail.value = await agentApi.getDocument(documentId);
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  }
}
</script>
