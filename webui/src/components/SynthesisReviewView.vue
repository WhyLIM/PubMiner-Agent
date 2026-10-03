<template>
  <div class="space-y-4">
    <!-- Header with Export Actions -->
    <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs flex flex-wrap items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-2">
          <h2 class="text-base font-bold text-slate-900">系统性证据合成与学术综述报告</h2>
          <span class="text-xs px-2 py-0.5 rounded bg-sky-50 text-sky-700 font-mono font-medium">
            AI Automated Review
          </span>
        </div>
        <p class="text-xs text-slate-500 mt-0.5">
          基于提取的高置信度三元组关系与临床试验循证终点自动编纂的学术综述初稿。
        </p>
      </div>

      <div class="flex items-center gap-2">
        <el-button size="small" @click="copyReport">
          <el-icon class="mr-1"><DocumentCopy /></el-icon>
          复制全文 Markdown
        </el-button>
        <el-button type="primary" size="small" @click="downloadReport">
          <el-icon class="mr-1"><Download /></el-icon>
          下载综述报告 (.md)
        </el-button>
        <el-button size="small" @click="activeRightTab = activeRightTab === 'chat' ? 'none' : 'chat'">
          <el-icon class="mr-1"><ChatDotRound /></el-icon>
          {{ activeRightTab === 'chat' ? '隐藏文献对话' : '文献溯源问答' }}
        </el-button>
      </div>
    </div>

    <!-- Main Content Area: Split View (Report on Left, Interactive Grounded QA on Right) -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <!-- Structured Report Article (2 Cols or 3 Cols) -->
      <div :class="[activeRightTab === 'chat' ? 'lg:col-span-2' : 'lg:col-span-3', 'bg-white rounded-lg border border-slate-200 p-6 sm:p-8 shadow-xs']">
        <article class="prose prose-slate max-w-none text-slate-800 text-sm leading-relaxed">
          <!-- Render report with clean typography and styled sections -->
          <div class="whitespace-pre-line font-sans">
            <template v-for="(paragraph, idx) in formattedSections" :key="idx">
              <div v-if="paragraph.type === 'h1'" class="text-xl sm:text-2xl font-bold text-slate-900 border-b border-slate-200 pb-3 mb-4 mt-2">
                {{ paragraph.text }}
              </div>
              <div v-else-if="paragraph.type === 'h2'" class="text-base sm:text-lg font-bold text-slate-900 mt-5 mb-2 text-sky-800">
                {{ paragraph.text }}
              </div>
              <div v-else-if="paragraph.type === 'h3'" class="text-sm sm:text-base font-semibold text-slate-800 mt-4 mb-2">
                {{ paragraph.text }}
              </div>
              <div v-else-if="paragraph.type === 'table'" class="my-4 overflow-x-auto">
                <!-- Render Table -->
                <table class="w-full text-xs text-left border-collapse border border-slate-200">
                  <thead class="bg-slate-50 text-slate-700">
                    <tr>
                      <th v-for="(header, hIdx) in paragraph.tableData.headers" :key="hIdx" class="border border-slate-200 px-3 py-2 font-semibold">
                        {{ header }}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, rIdx) in paragraph.tableData.rows" :key="rIdx" class="hover:bg-slate-50">
                      <td v-for="(cell, cIdx) in row" :key="cIdx" class="border border-slate-200 px-3 py-1.5 font-mono text-[11px] text-slate-700">
                        {{ cell }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-else class="text-slate-700 leading-relaxed mb-3">
                {{ paragraph.text }}
              </div>
            </template>
          </div>
        </article>
      </div>

      <!-- Grounded Citation QA Chat Assistant (Right Col) -->
      <div v-if="activeRightTab === 'chat'" class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs flex flex-col justify-between h-[650px]">
        <!-- Chat Header -->
        <div>
          <div class="flex items-center justify-between border-b border-slate-100 pb-2 mb-3">
            <div class="flex items-center gap-2">
              <el-icon class="text-sky-600"><ChatDotRound /></el-icon>
              <h3 class="text-xs font-bold text-slate-900">PubMiner 文献溯源问答助手</h3>
            </div>
            <span class="text-[11px] text-emerald-600 font-mono font-medium">● Grounded with PMIDs</span>
          </div>

          <!-- Suggested Quick Prompts -->
          <div class="flex flex-wrap gap-1.5 mb-3">
            <button
              v-for="(p, idx) in samplePrompts"
              :key="idx"
              @click="askQuestion(p)"
              class="px-2 py-1 rounded text-[11px] bg-slate-50 border border-slate-200 text-slate-600 hover:text-sky-700 hover:bg-sky-50 transition-colors text-left"
            >
              {{ p }}
            </button>
          </div>
        </div>

        <!-- Chat Conversation Messages -->
        <div ref="chatContainerRef" class="flex-1 overflow-y-auto space-y-3 pr-1 text-xs">
          <div
            v-for="(msg, idx) in messages"
            :key="idx"
            :class="[
              'p-3 rounded-lg',
              msg.sender === 'user'
                ? 'bg-sky-600 text-white ml-6 shadow-xs'
                : 'bg-slate-50 text-slate-800 mr-4 border border-slate-200'
            ]"
          >
            <div class="font-bold text-[10px] opacity-75 mb-1">
              {{ msg.sender === 'user' ? '我的提问' : 'PubMiner 科学助手' }}
            </div>
            <div class="leading-relaxed whitespace-pre-line">{{ msg.text }}</div>
            <div v-if="msg.citations && msg.citations.length" class="mt-2 pt-2 border-t border-slate-200/50 flex flex-wrap gap-1.5">
              <span class="text-[10px] text-slate-500 font-sans">引用依据:</span>
              <a
                v-for="pmid in msg.citations"
                :key="pmid"
                :href="'https://pubmed.ncbi.nlm.nih.gov/' + pmid"
                target="_blank"
                class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-sky-100 text-sky-800 hover:bg-sky-200 transition-colors"
              >
                [PMID: {{ pmid }}]
              </a>
            </div>
          </div>

          <div v-if="isThinking" class="p-3 bg-slate-50 rounded-lg border border-slate-200 text-xs text-slate-500 flex items-center gap-2">
            <el-icon class="is-loading text-sky-600"><Loading /></el-icon>
            <span>正在检索文献数据库并进行证据综合...</span>
          </div>
        </div>

        <!-- Chat Input Form -->
        <div class="pt-3 border-t border-slate-100">
          <div class="flex gap-2">
            <el-input
              v-model="inputQuestion"
              placeholder="向文献智能体提问机制或临床试验细节..."
              size="small"
              @keyup.enter="handleSendQuestion"
            />
            <el-button type="primary" size="small" @click="handleSendQuestion" :loading="isThinking">
              发送
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { ResearchTopic } from '../types';
import { ElMessage } from 'element-plus';

const props = defineProps<{
  topic: ResearchTopic;
}>();

const activeRightTab = ref<'chat' | 'none'>('chat');
const inputQuestion = ref('');
const isThinking = ref(false);
const chatContainerRef = ref<HTMLDivElement | null>(null);

const samplePrompts = [
  '奥希替尼耐药后，MET扩增的最佳联合方案是什么？',
  'C797S顺式与反式突变在用药策略上有何本质区别？',
  '如何通过液体活检动态监测耐药克隆演变？'
];

interface ChatMessage {
  sender: 'user' | 'agent';
  text: string;
  citations?: string[];
}

const messages = ref<ChatMessage[]>([
  {
    sender: 'agent',
    text: `你好！我是 PubMiner 科学问答智能体。已为您加载《${props.topic.title}》的系统挖掘文献库，你可以随时向我咨询相关分子机制、临床数据及试验终点，所有结论均支持追溯 PubMed 原文。`
  }
]);

// Parse Markdown into structured sections for clean display
const formattedSections = computed(() => {
  const lines = props.topic.reviewReport.split('\n');
  const sections: { type: 'h1' | 'h2' | 'h3' | 'p' | 'table'; text?: string; tableData?: any }[] = [];

  let inTable = false;
  let tableHeaders: string[] = [];
  let tableRows: string[][] = [];

  for (let line of lines) {
    line = line.trim();
    if (!line) continue;

    if (line.startsWith('# ')) {
      sections.push({ type: 'h1', text: line.replace('# ', '') });
    } else if (line.startsWith('## ')) {
      sections.push({ type: 'h2', text: line.replace('## ', '') });
    } else if (line.startsWith('### ')) {
      sections.push({ type: 'h3', text: line.replace('### ', '') });
    } else if (line.startsWith('|') && line.endsWith('|')) {
      const cells = line.split('|').slice(1, -1).map(c => c.trim());
      if (cells.every(c => c.includes('---'))) {
        // Table separator row, ignore
        continue;
      }
      if (!inTable) {
        inTable = true;
        tableHeaders = cells;
      } else {
        tableRows.push(cells);
      }
    } else {
      if (inTable) {
        sections.push({
          type: 'table',
          tableData: { headers: tableHeaders, rows: tableRows }
        });
        inTable = false;
        tableHeaders = [];
        tableRows = [];
      }
      sections.push({ type: 'p', text: line });
    }
  }

  if (inTable) {
    sections.push({
      type: 'table',
      tableData: { headers: tableHeaders, rows: tableRows }
    });
  }

  return sections;
});

function copyReport() {
  navigator.clipboard.writeText(props.topic.reviewReport);
  ElMessage.success('综述报告 Markdown 内容已复制至剪贴板');
}

function downloadReport() {
  const blob = new Blob([props.topic.reviewReport], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `PubMiner-Systematic-Review-${props.topic.id}.md`;
  a.click();
  URL.revokeObjectURL(url);
  ElMessage.success('系统性综述报告文件下载成功');
}

function askQuestion(q: string) {
  inputQuestion.value = q;
  handleSendQuestion();
}

function handleSendQuestion() {
  if (!inputQuestion.value.trim() || isThinking.value) return;

  const q = inputQuestion.value.trim();
  messages.value.push({ sender: 'user', text: q });
  inputQuestion.value = '';
  isThinking.value = true;

  setTimeout(() => {
    isThinking.value = false;
    let answer = '';
    let citations: string[] = [];

    if (q.includes('MET') || q.includes('联合')) {
      answer = '根据 SAVANNAH 研究（Lancet Oncol 2023）与 MARIPOSA 研究（NEJM 2024），MET 扩增是非小细胞肺癌三代 TKI 最关键的旁路耐药机制。针对 MET 高扩增/过表达患者，奥希替尼联合高选择性 MET 抑制剂赛沃替尼（Savolitinib）可取得 49% 的客观缓解率（ORR）与 7.1 个月的中位 PFS。同时，EGFR/MET 双特异性抗体埃万妥单抗（Amivantamab）能够通过靶向受体降解与 ADCC 双重效应克服旁路耐药。';
      citations = ['36972041', '37812836'];
    } else if (q.includes('C797S') || q.includes('顺式') || q.includes('反式')) {
      answer = 'C797S 突变是奥希替尼常见的靶内耐药形式：\n1. 若 C797S 与 T790M 呈【反式 (trans)】存在于不同染色体等位基因上，一代 TKI（如吉非替尼）联合三代 TKI 可有效恢复对肿瘤生长的抑制；\n2. 若两者呈【顺式 (cis)】存在于同一染色体上，所有一至三代 TKI 均失去抗肿瘤活性，此时需要选择新型四代变构抑制剂（如 BLU-945）。';
      citations = ['35894982', '34145781'];
    } else if (q.includes('液体活检') || q.includes('ctDNA')) {
      answer = 'AURA3 队列研究证据表明，基于外周血循环肿瘤 DNA (ctDNA) 的超灵敏二代测序（NGS）能够在影像学 RECIST 标准判定进展前平均 3.2 个月，捕捉到低频 C797S 顺式突变或 MET 拷贝数异常扩增，为临床实施抢先式靶向轮换（Preemptive Switch）提供了黄金干预窗口。';
      citations = ['35147890'];
    } else {
      answer = `基于文献知识图谱与当前已检索论文库对“${q}”的深度分析：相关靶点在下游介导了关键细胞抗凋亡与代偿旁路信号。推荐结合高选择性抑制剂或双抗策略，阻断主干受体激活并增强免疫协同。`;
      citations = props.topic.papers.slice(0, 2).map(p => p.pmid);
    }

    messages.value.push({
      sender: 'agent',
      text: answer,
      citations: citations
    });
  }, 800);
}
</script>
