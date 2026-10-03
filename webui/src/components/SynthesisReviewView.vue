<template>
  <div class="space-y-4">
    <!-- Header with Export Actions -->
    <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs flex flex-wrap items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-2">
          <h2 class="text-base font-bold text-slate-900">系统性证据合成与综述报告</h2>
          <span class="text-xs px-2 py-0.5 rounded bg-sky-50 text-sky-700 font-mono font-medium">
            Evidence-grounded Review
          </span>
        </div>
        <p class="text-xs text-slate-500 mt-0.5">
          报告与问答均由当前会话的真实聚合命题与证据原文片段生成；所有结论可溯源至文献原文片段。
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
          {{ activeRightTab === 'chat' ? '隐藏证据问答' : '证据溯源问答' }}
        </el-button>
      </div>
    </div>

    <!-- Main Content Area: Split View -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <!-- Structured Report Article -->
      <div :class="[activeRightTab === 'chat' ? 'lg:col-span-2' : 'lg:col-span-3', 'bg-white rounded-lg border border-slate-200 p-6 sm:p-8 shadow-xs']">
        <article class="prose prose-slate max-w-none text-slate-800 text-sm leading-relaxed">
          <div class="font-sans">
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

      <!-- Grounded Evidence QA (Right Col): local retrieval over real evidence -->
      <div v-if="activeRightTab === 'chat'" class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs flex flex-col justify-between h-[650px]">
        <div>
          <div class="flex items-center justify-between border-b border-slate-100 pb-2 mb-3">
            <div class="flex items-center gap-2">
              <el-icon class="text-sky-600"><ChatDotRound /></el-icon>
              <h3 class="text-xs font-bold text-slate-900">证据溯源问答</h3>
            </div>
            <span class="text-[11px] text-emerald-600 font-mono font-medium">● 本地证据检索 · 可溯源</span>
          </div>

          <!-- Suggested Quick Prompts (generated from real data) -->
          <div class="flex flex-wrap gap-1.5 mb-3">
            <button
              v-for="(p, idx) in samplePrompts"
              :key="idx"
              @click="askQuestion(p)"
              class="px-2 py-1 rounded text-[11px] bg-slate-50 border border-slate-200 text-slate-600 hover:text-sky-700 hover:bg-sky-50 transition-colors text-left line-clamp-1 max-w-full"
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
              {{ msg.sender === 'user' ? '我的提问' : 'PubMiner 证据助手' }}
            </div>
            <div class="leading-relaxed whitespace-pre-line">{{ msg.text }}</div>
            <div v-if="msg.citations && msg.citations.length" class="mt-2 pt-2 border-t border-slate-200/50 flex flex-wrap gap-1.5 items-center">
              <span class="text-[10px] text-slate-500 font-sans">依据片段:</span>
              <span
                v-for="cite in msg.citations"
                :key="cite"
                class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-sky-100 text-sky-800"
              >
                {{ cite }}
              </span>
            </div>
          </div>

          <div v-if="isThinking" class="p-3 bg-slate-50 rounded-lg border border-slate-200 text-xs text-slate-500 flex items-center gap-2">
            <el-icon class="is-loading text-sky-600"><Loading /></el-icon>
            <span>正在检索本地证据库并进行证据综合...</span>
          </div>
        </div>

        <!-- Chat Input Form -->
        <div class="pt-3 border-t border-slate-100">
          <div class="flex gap-2">
            <el-input
              v-model="inputQuestion"
              placeholder="输入关键词，检索证据库中的相关命题与原文片段..."
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
import { ref, computed, nextTick } from 'vue';
import { ResearchTopic } from '../types';
import { ElMessage } from 'element-plus';
import { agentApi, type EvidenceSpanItem } from '@/api/client';
import { useResearch } from '@/composables/useResearch';

const props = defineProps<{
  topic: ResearchTopic;
}>();

const { aggregations, session, coverage } = useResearch();

const activeRightTab = ref<'chat' | 'none'>('chat');
const inputQuestion = ref('');
const isThinking = ref(false);
const chatContainerRef = ref<HTMLDivElement | null>(null);

// ------------------------------------------------------------------ 报告生成（真实数据）

const report = computed(() => {
  const aggs = aggregations.value;
  if (!aggs.length) {
    return props.topic.reviewReport || '# 暂无数据\n\n请先在文献页或工作台运行一次挖掘管线。';
  }
  const totalSupport = aggs.reduce((s, a) => s + a.support_count, 0);
  const totalContradict = aggs.reduce((s, a) => s + a.contradict_count, 0);
  const totalNoEffect = aggs.reduce((s, a) => s + a.no_effect_count, 0);
  const totalUncertain = aggs.reduce((s, a) => s + a.uncertain_count, 0);
  const validated = aggs.filter(a => a.independent_validation);
  const conflicted = aggs.filter(a => a.has_conflict);
  const totalEvidence = totalSupport + totalContradict + totalNoEffect + totalUncertain;
  const lines: string[] = [];

  lines.push(`# 证据综述报告：${session.value?.goal ?? props.topic.title}`);
  lines.push('');
  lines.push(`> 会话 ${ (session.value?.session_id ?? '').slice(0, 8) || '—' } · 机器生成初稿，须经人工复核后采用。`);
  lines.push('');
  lines.push('## 一、证据总览');
  lines.push('');
  lines.push(`当前会话共聚合 ${aggs.length} 条命题，累计 ${totalEvidence} 条证据片段：支持 ${totalSupport}、反驳 ${totalContradict}、无效应 ${totalNoEffect}、不确定 ${totalUncertain}。`);
  lines.push(`其中 ${validated.length} 条命题达到独立验证标准（≥3 篇独立文献同向），${conflicted.length} 条命题存在反驳证据需要重点复核。`);
  lines.push('');

  // 汇总表（签名中的 | 会破坏 Markdown 表格，转义为全角竖线）
  const esc = (s: string) => s.replace(/\|/g, '｜');
  lines.push('| 命题 (规范签名) | 支持 | 反驳 | 无效应 | 不确定 | 独立文献 | 状态 |');
  lines.push('| --- | --- | --- | --- | --- | --- | --- |');
  for (const a of aggs.slice(0, 30)) {
    lines.push(`| ${esc(a.canonical_signature)} | ${a.support_count} | ${a.contradict_count} | ${a.no_effect_count} | ${a.uncertain_count} | ${a.distinct_documents} | ${a.status} |`);
  }
  if (aggs.length > 30) {
    lines.push(`| …其余 ${aggs.length - 30} 条见文献页 | | | | | | |`);
  }
  lines.push('');

  // 覆盖度（章节号动态，避免缺省时编号跳跃）
  let sectionNo = 2;
  if (coverage.value) {
    lines.push(`## ${sectionNo}、覆盖度评估 (COVERAGE)`);
    lines.push('');
    lines.push(`- 检索覆盖：支持 ${coverage.value.support_count} · 反驳 ${coverage.value.contradict_count}；独立验证${coverage.value.independent_validation_found ? '已达成' : '尚未达成'}。`);
    if (coverage.value.unresolved_gaps.length) {
      lines.push('- 未解决缺口：');
      for (const gap of coverage.value.unresolved_gaps) {
        lines.push(`  - ${gap}`);
      }
    }
    if (coverage.value.recommended_next_action) {
      lines.push(`- 推荐下一步：${coverage.value.recommended_next_action}`);
    }
    lines.push('');
    sectionNo += 1;
  }

  // 命题详情
  lines.push(`## ${sectionNo}、命题详情`);
  lines.push('');
  for (const a of aggs) {
    lines.push(`### ${a.canonical_signature}`);
    lines.push('');
    lines.push(`- 状态：${a.status}；独立文献 ${a.distinct_documents} 篇；${a.independent_validation ? '✅ 独立验证' : '未达独立验证'}${a.has_conflict ? '；⚠️ 存在冲突' : ''}。`);
    if (a.reasons.length) {
      lines.push('- 判定理由：');
      for (const r of a.reasons) {
        lines.push(`  - ${r}`);
      }
    }
    lines.push('');
  }

  lines.push(`## ${sectionNo + 1}、使用说明与局限`);
  lines.push('');
  lines.push('1. 本报告由 PubMiner Evidence Agent 基于检索、筛选、抽取、归一化、验证与聚合的确定性管线自动生成；');
  lines.push('2. 所有命题均可展开查看证据原文片段（含偏移定位），请在复核页面逐条确认后再写入下游数据库；');
  lines.push('3. 抽取与筛选依赖 LLM 与嵌入模型，可能存在漏检/误抽，人工复核是必要环节。');
  return lines.join('\n');
});

// Parse Markdown into structured sections for clean display
const formattedSections = computed(() => {
  const lines = report.value.split('\n');
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

// ------------------------------------------------------------------ 问答（本地证据检索）

interface ChatMessage {
  sender: 'user' | 'agent';
  text: string;
  citations?: string[];
}

const messages = ref<ChatMessage[]>([
  {
    sender: 'agent',
    text: `你好！我基于当前会话的真实证据库（${aggregations.value.length} 条聚合命题）回答问题。输入关键词（如基因名、药物名、表型），我会检索相关命题并给出可溯源的原文片段。`
  }
]);

/** 从真实命题数据生成推荐问题（去重） */
const samplePrompts = computed(() => {
  const prompts: string[] = ['当前证据库的总体结论与分歧点'];
  const seen = new Set<string>();
  const top = [...aggregations.value]
    .sort((a, b) => b.support_count - a.support_count)
    .slice(0, 4);
  for (const a of top) {
    const subject = a.subject_name || a.canonical_signature.split(' | ')[0] || '';
    if (!subject || subject === 'UNRESOLVED' || seen.has(subject)) { continue; }
    seen.add(subject);
    prompts.push(`${subject} 的证据支持情况如何？`);
    if (prompts.length >= 3) { break; }
  }
  const conflict = aggregations.value.find(a => a.has_conflict);
  if (conflict) {
    const subject = conflict.subject_name || conflict.canonical_signature.split(' | ')[0] || '';
    if (subject && subject !== 'UNRESOLVED' && !seen.has(subject)) {
      prompts.push(`${subject} 为什么存在冲突证据？`);
    }
  }
  return prompts.slice(0, 4);
});

/** 简易打分：问题词与签名/理由的重叠度 */
function scoreAgg(q: string, sig: string, reasons: string[]): number {
  const hay = (sig + ' ' + reasons.join(' ')).toLowerCase();
  const tokens = q.toLowerCase().split(/[\s,，?？。;；:：()（）]+/).filter(t => t.length >= 2);
  let score = 0;
  for (const t of tokens) {
    if (hay.includes(t)) { score += t.length; }
  }
  return score;
}

function bestSpan(evidence: EvidenceSpanItem[]): EvidenceSpanItem | null {
  return evidence.find(e => e.polarity === 'SUPPORT')
    ?? evidence.find(e => e.polarity === 'CONTRADICT')
    ?? evidence[0] ?? null;
}

async function answerFromEvidence(q: string): Promise<{ text: string; citations: string[] }> {
  const aggs = aggregations.value;
  if (!aggs.length) {
    return { text: '当前会话没有聚合命题。请先在文献页运行一次挖掘管线。', citations: [] };
  }

  if (q.includes('总体') || q.includes('总结') || q.includes('分歧')) {
    const validated = aggs.filter(a => a.independent_validation);
    const conflicted = aggs.filter(a => a.has_conflict);
    const totalSupport = aggs.reduce((s, a) => s + a.support_count, 0);
    const totalContradict = aggs.reduce((s, a) => s + a.contradict_count, 0);
    const lines = [
      `当前证据库共 ${aggs.length} 条命题：支持证据 ${totalSupport} 条、反驳证据 ${totalContradict} 条。`,
      validated.length ? `达到独立验证标准（≥3 篇同向）的命题 ${validated.length} 条，例如：${validated.slice(0, 3).map(a => a.canonical_signature).join('；')}。` : '尚无命题达到独立验证标准。',
      conflicted.length ? `存在反驳证据、需要重点复核的命题 ${conflicted.length} 条，例如：${conflicted.slice(0, 3).map(a => a.canonical_signature).join('；')}。` : '未检测到命题内冲突。',
    ];
    return { text: lines.join('\n'), citations: [] };
  }

  // 常规检索：打分取 top 3
  const scored = aggs
    .map(a => ({ a, score: scoreAgg(q, `${a.subject_name ?? ''} ${a.canonical_signature}`, a.reasons) }))
    .filter(x => x.score > 0)
    .sort((x, y) => y.score - x.score)
    .slice(0, 3);

  if (!scored.length) {
    return {
      text: `在当前证据库中未找到与"${q}"相关的命题。可尝试换用基因/药物/表型关键词，或先扩大检索范围重跑管线。`,
      citations: [],
    };
  }

  const parts: string[] = [];
  const citations: string[] = [];
  for (const { a } of scored) {
    const header = `【${a.canonical_signature}】支持 ${a.support_count} · 反驳 ${a.contradict_count} · 无效应 ${a.no_effect_count} · 不确定 ${a.uncertain_count}（${a.distinct_documents} 篇独立文献，${a.independent_validation ? '已独立验证' : '未达独立验证'}）`;
    let spanLine = '';
    try {
      const detail = await agentApi.getClaimEvidence(a.claim_id);
      const span = bestSpan(detail.evidence ?? []);
      if (span?.span?.text) {
        spanLine = `\n原文片段（${span.polarity}，${span.span.section_path || '正文'}）："${span.span.text}"`;
        citations.push(`doc ${span.span.document_version_id.slice(0, 8)} · ${span.span.section_path || 'span'}`);
      }
    } catch { /* 拉取失败时仅输出统计 */ }
    parts.push(header + spanLine);
  }

  return {
    text: `在证据库中检索到 ${scored.length} 条相关命题：\n\n` + parts.join('\n\n') + '\n\n以上结论均来自本地证据库原文片段，可在文献页展开复核。',
    citations,
  };
}

function askQuestion(q: string) {
  inputQuestion.value = q;
  void handleSendQuestion();
}

async function handleSendQuestion() {
  const q = inputQuestion.value.trim();
  if (!q || isThinking.value) return;

  messages.value.push({ sender: 'user', text: q });
  inputQuestion.value = '';
  isThinking.value = true;

  try {
    const { text, citations } = await answerFromEvidence(q);
    messages.value.push({ sender: 'agent', text, citations });
  } catch (err) {
    messages.value.push({
      sender: 'agent',
      text: `检索失败：${err instanceof Error ? err.message : String(err)}`,
    });
  } finally {
    isThinking.value = false;
    await nextTick();
    chatContainerRef.value?.scrollTo({ top: chatContainerRef.value.scrollHeight, behavior: 'smooth' });
  }
}

// ------------------------------------------------------------------ 导出

function copyReport() {
  navigator.clipboard.writeText(report.value);
  ElMessage.success('综述报告 Markdown 内容已复制至剪贴板');
}

function downloadReport() {
  const blob = new Blob([report.value], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `PubMiner-Systematic-Review-${props.topic.id}.md`;
  a.click();
  URL.revokeObjectURL(url);
  ElMessage.success('系统性综述报告文件下载成功');
}
</script>
