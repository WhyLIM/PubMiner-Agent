<template>
  <div class="space-y-4">
    <!-- Header Controls -->
    <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs flex flex-wrap items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-2">
          <h2 class="text-base font-bold text-slate-900">PubMiner 多智能体协同运行中心</h2>
          <span class="text-xs px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 font-mono font-medium">
            5 Agents Online
          </span>
        </div>
        <p class="text-xs text-slate-500 mt-0.5">
          系统规划智能体、多源检索智能体、实体识别智能体、循证评级智能体与机制综述智能体流水线。
        </p>
      </div>

      <div class="flex items-center gap-2">
        <el-button
          type="primary"
          @click="startFullPipeline"
          :loading="isRunning"
          size="default"
        >
          <el-icon class="mr-1"><CaretRight /></el-icon>
          {{ isRunning ? '智能体流水线执行中...' : '重新运行完整挖掘流水线' }}
        </el-button>
        <el-button size="default" @click="resetPipeline" :disabled="isRunning">
          <el-icon class="mr-1"><RefreshRight /></el-icon>
          重置状态
        </el-button>
      </div>
    </div>

    <!-- Agent Pipeline Stage Cards -->
    <div class="grid grid-cols-1 md:grid-cols-5 gap-3">
      <div
        v-for="(step, index) in steps"
        :key="step.id"
        @click="activeStepIndex = index"
        :class="[
          'p-3.5 rounded-lg border cursor-pointer transition-all flex flex-col justify-between',
          activeStepIndex === index
            ? 'border-sky-500 bg-sky-50/30 shadow-xs ring-1 ring-sky-500/20'
            : 'border-slate-200 bg-white hover:border-slate-300'
        ]"
      >
        <div>
          <!-- Step Number & Status -->
          <div class="flex items-center justify-between mb-2">
            <span class="text-[11px] font-mono font-bold text-slate-400">0{{ index + 1 }}</span>
            <span
              :class="[
                'text-[10px] px-1.5 py-0.2 rounded font-mono',
                step.status === 'completed' ? 'bg-emerald-50 text-emerald-700 font-medium' :
                step.status === 'running' ? 'bg-sky-50 text-sky-700 animate-pulse font-semibold' :
                'bg-slate-100 text-slate-500'
              ]"
            >
              {{ step.status === 'completed' ? '已就绪' : step.status === 'running' ? '运行中' : '等待' }}
            </span>
          </div>

          <h3 class="text-xs font-bold text-slate-800 leading-snug">
            {{ step.agentName }}
          </h3>
          <p class="text-[11px] text-slate-500 mt-1 line-clamp-2">
            {{ step.role }}
          </p>
        </div>

        <div class="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-[10px] text-slate-400 font-mono">
          <span>耗时:</span>
          <span>{{ (step.durationMs / 1000).toFixed(1) }}s</span>
        </div>
      </div>
    </div>

    <!-- Active Step Inspector & Live Console Log -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <!-- Step Detail & Metrics (Left Col) -->
      <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs flex flex-col justify-between">
        <div>
          <div class="flex items-center justify-between border-b border-slate-100 pb-2 mb-3">
            <div>
              <span class="text-[11px] text-slate-400 font-mono">AGENT DETAIL</span>
              <h3 class="text-sm font-bold text-slate-900">{{ currentStep.agentName }}</h3>
            </div>
            <el-tag
              :type="currentStep.status === 'completed' ? 'success' : currentStep.status === 'running' ? 'primary' : 'info'"
              size="small"
            >
              {{ currentStep.status }}
            </el-tag>
          </div>

          <p class="text-xs text-slate-600 leading-relaxed mb-4">
            {{ currentStep.summary }}
          </p>

          <!-- Key Quantitative Metrics -->
          <div class="space-y-2 mb-4">
            <h4 class="text-xs font-semibold text-slate-700 uppercase tracking-wide">智能体产出指标</h4>
            <div class="grid grid-cols-2 gap-2">
              <div
                v-for="(val, key) in currentStep.metrics"
                :key="key"
                class="p-2 rounded bg-slate-50 border border-slate-100"
              >
                <div class="text-[10px] text-slate-400 truncate">{{ key }}</div>
                <div class="text-xs font-mono font-bold text-slate-800 mt-0.5">{{ val }}</div>
              </div>
            </div>
          </div>

          <!-- Tool Calls Trace -->
          <div v-if="currentStep.toolCalls && currentStep.toolCalls.length">
            <h4 class="text-xs font-semibold text-slate-700 uppercase tracking-wide mb-2">工具调用链 (Tool Invocations)</h4>
            <div class="space-y-2">
              <div
                v-for="(tc, i) in currentStep.toolCalls"
                :key="i"
                class="p-2 rounded border border-slate-200 bg-slate-50/60 text-xs font-mono"
              >
                <div class="text-sky-700 font-semibold flex items-center gap-1">
                  <el-icon><Tools /></el-icon>
                  <span>{{ tc.tool }}</span>
                </div>
                <div class="text-[11px] text-slate-500 mt-1 truncate">参数: {{ tc.args }}</div>
                <div class="text-[11px] text-emerald-700 mt-0.5 truncate">返回: {{ tc.result }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="pt-4 border-t border-slate-100 flex items-center justify-between text-xs">
          <span class="text-slate-400">单步耗时: {{ currentStep.durationMs }} ms</span>
          <el-button size="small" @click="runSingleStep(activeStepIndex)" :loading="isRunning">
            重跑当前 Agent
          </el-button>
        </div>
      </div>

      <!-- Live Terminal Streaming Logs (Right 2 Cols) -->
      <div class="lg:col-span-2 bg-slate-900 rounded-lg p-4 shadow-xs text-slate-200 font-mono text-xs flex flex-col justify-between">
        <div class="flex items-center justify-between border-b border-slate-800 pb-2 mb-3">
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
            <span class="text-slate-300 font-semibold">PubMiner Agent Execution Terminal</span>
          </div>
          <span class="text-slate-500 text-[11px]">Real-time Event Stream</span>
        </div>

        <!-- Terminal Logs Body -->
        <div ref="terminalLogRef" class="flex-1 overflow-y-auto max-h-96 space-y-1.5 pr-2 font-mono text-[11px] leading-relaxed">
          <div
            v-for="(log, idx) in currentStep.logs"
            :key="idx"
            class="flex items-start gap-2"
          >
            <span class="text-slate-500 select-none">[{{ getLogTime(idx) }}]</span>
            <span :class="getLogClass(log)">{{ log }}</span>
          </div>

          <div v-if="isRunning" class="text-sky-400 flex items-center gap-2 pt-2 animate-pulse">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>Agent 正在执行推理与三元组图谱对齐...</span>
          </div>
        </div>

        <!-- Terminal Footer Stats -->
        <div class="pt-3 border-t border-slate-800 flex flex-wrap items-center justify-between gap-2 text-[10px] text-slate-400">
          <div class="flex items-center gap-3">
            <span>Model: Gemini 2.5 Pro / Flash Rerank</span>
            <span>·</span>
            <span>Temperature: 0.1</span>
            <span>·</span>
            <span>Precision: High Rigor</span>
          </div>
          <div class="text-slate-300 font-mono">
            Total Tokens: ~18,420
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { AgentStep } from '../types';
import { ElMessage } from 'element-plus';

const isRunning = ref(false);
const activeStepIndex = ref(0);
const terminalLogRef = ref<HTMLDivElement | null>(null);

const steps = ref<AgentStep[]>([
  {
    id: 's1',
    agentName: 'Query Planner Agent',
    role: '课题解构、MeSH 受控词匹配与布尔检索策略规划',
    status: 'completed',
    summary: '自动分析临床/生物学研究意图，提取核心实体概念，在 MeSH 树状词表中匹配同义词群组，构建高召回率且兼顾特异性的 PubMed 复合检索式。',
    durationMs: 820,
    metrics: {
      'MeSH 扩展词数': '12 个',
      '检索式分支': '4 个分组',
      '语法合法性校验': '100% 通过'
    },
    toolCalls: [
      { tool: 'mesh_tree_lookup', args: 'term: "EGFR TKI Resistance"', result: 'found 5 descendants' },
      { tool: 'query_syntax_validator', args: 'query: (EGFR OR ERBB) ...', result: 'valid PubMed syntax' }
    ],
    logs: [
      '[Planner] 接收到原始研究意图: EGFR T790M/C797S 获得性耐药机制与双靶联合干预。',
      '[Planner] 识别核心概念: [Target: EGFR], [Mutation: T790M, C797S], [Drug: Osimertinib], [Mechanism: MET Bypass].',
      '[Planner] 调用 MeSH API 进行医学受控词本体对齐，补充同义词: ErbB Receptors, Protein Kinase Inhibitors.',
      '[Planner] 成功规划优化检索式，生成布尔组合语句，推送给多源文献检索 Agent。'
    ]
  },
  {
    id: 's2',
    agentName: 'Multi-Source Retrieval Agent',
    role: 'PubMed / PMC 全文库 / SemMedDB 多源并行抓取与初筛',
    status: 'completed',
    summary: '并发调用 NCBI E-Utilities、PMC OA 全文接口及 SemMedDB 语义知识库，执行去重、多级相关性重排序（Re-ranking）与文献元数据解析。',
    durationMs: 1450,
    metrics: {
      '初检命中量': '1,450 篇',
      '高质量初筛': '86 篇',
      '全文获取成功率': '94.2%'
    },
    toolCalls: [
      { tool: 'ncbi_esearch', args: 'db: pubmed, retmax: 200', result: 'retrieved 180 PMIDs' },
      { tool: 'pmc_fetch_fulltext', args: 'pmc_ids: [...]', result: 'success 142/150' }
    ],
    logs: [
      '[Retrieval] 启动多源并行请求: PubMed API, PMC Open Access, SemMedDB.',
      '[Retrieval] 初筛命中 1,450 篇文献，执行跨库 PMID 去重与元数据归一化。',
      '[Retrieval] 运用 Cross-Encoder 重排模型对标题与摘要进行语义相似度打分。',
      '[Retrieval] 筛选出 Top-86 篇高度相关论文，完成全文与结构化摘要打包。'
    ]
  },
  {
    id: 's3',
    agentName: 'Biomedical NER & Triplet Agent',
    role: '生物医学实体识别、实体对齐与定向因果关系三元组抽取',
    status: 'completed',
    summary: '基于生物医药大语言模型提取基因、突变体、疾病表型、小分子抑制剂及信号通路实体，抽取 (Subject, Predicate, Object) 语义因果链条。',
    durationMs: 2100,
    metrics: {
      '识别实体总数': '48 个',
      '高质量因果三元组': '138 条',
      '平均置信度': '93.6%'
    },
    toolCalls: [
      { tool: 'bio_ner_extractor', args: 'text: abstract_batch', result: 'extracted 28 genes, 14 drugs' },
      { tool: 'relation_triplet_builder', args: 'entities: [...]', result: 'built 138 directed edges' }
    ],
    logs: [
      '[NER Agent] 正在对已检索文献进行实体分词与生物学概念识别。',
      '[NER Agent] 提取出核心实体: Osimertinib, Savolitinib, EGFR C797S, MET Amplification.',
      '[NER Agent] 构建谓词关系: INHIBITS, MUTATES_TO, SYNERGIZES_WITH, ACTIVATES.',
      '[NER Agent] 生成知识图谱节点与赋权边数据，完成三元组知识图谱持久化。'
    ]
  },
  {
    id: 's4',
    agentName: 'Evidence & Bias Assessor Agent',
    role: '循证医学证据分级（GRADE）与偏倚风险（RoB）严谨审查',
    status: 'completed',
    summary: '根据 Cochrane 偏倚风险评估标准、样本量统计检验力、效应值（Hazard Ratio/ORR）和 p-value 显著性对纳入论文进行量化评级。',
    durationMs: 1200,
    metrics: {
      '低偏倚风险占比': '82%',
      '纳入临床试验数': '42 项',
      '循证严谨度指数': 'A 级 (High)'
    },
    toolCalls: [
      { tool: 'cochrane_rob_check', args: 'trials: [...]', result: 'low risk: 38, moderate: 4' },
      { tool: 'effect_size_synthesizer', args: 'hr_pvalues', result: 'p < 0.001 pooled' }
    ],
    logs: [
      '[Evidence] 载入 86 篇文献的方法学章节与补充数据表。',
      '[Evidence] 提取统计学效应量: MARIPOSA (HR=0.70), SAVANNAH (ORR=49%, mPFS=7.1mo).',
      '[Evidence] 评估偏倚风险: 随机分配方案隐藏、盲法评估与失访率均符合严谨标准。',
      '[Evidence] 剔除证据质量偏低文献 6 篇，输出证据可信度评分矩阵。'
    ]
  },
  {
    id: 's5',
    agentName: 'Review Synthesizer Agent',
    role: '多文献机制归纳、跨研究对比表格生成与学术综述报告产出',
    status: 'completed',
    summary: '整合前序各个智能体产出的证据链条与知识图谱，撰写严谨的系统性综述报告，提供可溯源的 PMID 引用及未解决科学问题洞察。',
    durationMs: 1850,
    metrics: {
      '生成综述字数': '3,850 字',
      '溯源引用 PMID': '24 篇',
      '临床转化建议': '4 项'
    },
    toolCalls: [
      { tool: 'structured_review_compiler', args: 'triples + evidence', result: 'generated markdown report' },
      { tool: 'pmid_citation_linker', args: 'text: review_draft', result: 'linked 24 traceable citations' }
    ],
    logs: [
      '[Synthesizer] 汇总生物学机制与临床试验汇总数据。',
      '[Synthesizer] 撰写引言、靶突变全景、旁路耐药机制及临床联合策略四大章节。',
      '[Synthesizer] 生成跨研究横向对比数据表格与可追溯引用文献列表。',
      '[Synthesizer] 综述报告构建完成，推送到综述合成视图。'
    ]
  }
]);

const currentStep = computed(() => steps.value[activeStepIndex.value]);

function getLogClass(log: string) {
  if (log.includes('成功') || log.includes('完成')) return 'text-emerald-400';
  if (log.includes('识别') || log.includes('提取')) return 'text-sky-300';
  if (log.includes('初筛') || log.includes('载入')) return 'text-amber-300';
  return 'text-slate-300';
}

function getLogTime(idx: number) {
  const sec = 12 + idx * 3;
  return `18:14:${sec < 10 ? '0' + sec : sec}`;
}

function startFullPipeline() {
  isRunning.value = true;
  activeStepIndex.value = 0;

  // Reset statuses
  steps.value.forEach((s, idx) => {
    s.status = idx === 0 ? 'running' : 'pending';
  });

  let current = 0;
  const interval = setInterval(() => {
    if (current < steps.value.length) {
      steps.value[current].status = 'completed';
      current++;
      if (current < steps.value.length) {
        steps.value[current].status = 'running';
        activeStepIndex.value = current;
      }
    } else {
      clearInterval(interval);
      isRunning.value = false;
      ElMessage.success('PubMiner-Agent 5 个智能体流水线全部协同完成！');
    }
  }, 900);
}

function runSingleStep(index: number) {
  steps.value[index].status = 'running';
  isRunning.value = true;
  setTimeout(() => {
    steps.value[index].status = 'completed';
    isRunning.value = false;
    ElMessage.success(`${steps.value[index].agentName} 重新运行完成`);
  }, 1000);
}

function resetPipeline() {
  steps.value.forEach((s) => {
    s.status = 'completed';
  });
  activeStepIndex.value = 0;
  ElMessage.info('流水线状态已重置');
}
</script>
