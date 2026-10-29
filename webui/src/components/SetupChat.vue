<template>
  <div v-if="setup" class="bg-white rounded-lg border border-sky-200 shadow-xs overflow-hidden">
    <!-- 面板头 -->
    <div class="px-4 py-2.5 flex items-center justify-between bg-sky-50/70 border-b border-sky-100">
      <div class="flex items-center gap-2">
        <el-icon class="text-sky-600"><ChatDotRound /></el-icon>
        <span class="text-sm font-bold text-slate-800">研究目标确认</span>
        <span class="px-2 py-0.5 rounded bg-white/80 border border-sky-100 text-[11px] font-mono text-sky-700">{{ setupPhaseLabel }}</span>
      </div>
      <el-button size="small" text :disabled="setup.phase === 'running'" @click="closeSetup">取消</el-button>
    </div>

    <!-- XProvider: 把 antd 组件主色对齐全站的 sky-600 -->
    <XProvider :theme="xTheme">
      <div class="flex flex-col h-[520px]">
        <!-- 对话流 -->
        <div ref="setupChatRef" class="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          <template v-for="(m, i) in setup.messages" :key="i">
            <!-- 消息气泡：AI 左侧无边框纯文本，用户右侧 sky 实底 -->
            <Bubble
              v-if="m.text"
              :placement="m.sender === 'user' ? 'end' : 'start'"
              :variant="m.sender === 'user' ? 'filled' : 'borderless'"
              :content="m.text"
              :styles="m.sender === 'user' ? userBubbleStyles : undefined"
              class="setup-msg"
            >
              <template #avatar>
                <el-avatar
                  :size="26"
                  :style="m.sender === 'user' ? 'background:#0284c7;color:#fff' : 'background:#e0f2fe;color:#0284c7'"
                >
                  <el-icon :size="14"><User v-if="m.sender === 'user'" /><ChatDotRound v-else /></el-icon>
                </el-avatar>
              </template>
            </Bubble>

            <!-- dsh 式问题卡片（内联在追问消息下） -->
            <div v-if="m.questions?.length" class="pl-10 space-y-2 max-w-[92%]">
              <div
                v-for="q in m.questions"
                :key="q.id"
                class="p-2.5 rounded-lg border border-sky-100 bg-sky-50/40 space-y-2"
              >
                <div class="flex items-baseline gap-2">
                  <span v-if="q.header" class="text-[11px] font-semibold text-sky-800 shrink-0">{{ q.header }}</span>
                  <span class="text-xs text-slate-700">{{ q.question }}</span>
                </div>
                <div v-if="q.options.length" class="flex flex-wrap gap-1.5">
                  <button
                    v-for="opt in q.options"
                    :key="opt.label"
                    :title="opt.description"
                    :class="[
                      'px-2.5 py-1 rounded-full text-xs border transition-colors text-left',
                      (questionAnswers[q.id]?.selected ?? []).includes(opt.label)
                        ? 'bg-sky-600 text-white border-sky-600 shadow-xs'
                        : 'bg-white text-slate-600 border-slate-300 hover:border-sky-400 hover:text-sky-700',
                    ]"
                    @click="toggleOption(q, opt.label)"
                  >
                    {{ opt.label }}
                  </button>
                </div>
                <el-input
                  :model-value="questionAnswers[q.id]?.custom ?? ''"
                  size="small"
                  placeholder="或输入自定义答案…"
                  @update:model-value="(v: string) => setCustom(q.id, v)"
                />
              </div>
              <!-- 追问动作（仅最后一条追问消息 + clarify 阶段） -->
              <div v-if="i === lastQuestionMsgIdx && setup.phase === 'clarify'" class="flex items-center gap-2">
                <el-button size="small" @click="skipClarify">跳过追问</el-button>
                <el-button type="primary" size="small" :disabled="!hasAnyAnswer" @click="submitAnswers()">提交回答</el-button>
                <span class="text-[11px] text-slate-400">也可以在下方输入框中补充后直接发送</span>
              </div>
            </div>

            <!-- 第一问：检索式审批（多选形态，默认不勾选，末尾可补充自定义） -->
            <div
              v-if="m.intents && i === lastParseMsgIdx && setup.phase === 'queries'"
              class="pl-10 max-w-[92%]"
            >
              <div class="p-3 rounded-lg border border-slate-200 bg-white space-y-2">
                <div class="text-xs text-slate-700">
                  我为这个目标生成了 {{ setup.intents.length }} 条检索式，请确认参与本次检索的条目（可直接编辑）：
                </div>
                <div v-if="!setup.intents.length" class="text-[11px] text-slate-400">
                  尚未生成检索式；可在「其它」中自行补充，或按默认参数直接执行。
                </div>
                <div v-for="(si, siIdx) in setup.intents" :key="siIdx" class="space-y-0.5">
                  <div class="flex items-start gap-2">
                    <el-checkbox
                      v-model="si.enabled"
                      size="small"
                      class="shrink-0 !h-6"
                      :title="si.enabled ? '参与本次挖掘；取消则跳过该检索式' : '已禁用，不参与本次挖掘'"
                    />
                    <div class="min-w-0 flex-1">
                      <div class="text-[11px] text-slate-500">{{ si.name }}</div>
                      <el-input v-model="si.query" size="small" class="font-mono mt-0.5" :disabled="!si.enabled" />
                      <div v-if="si.explanation" class="text-[11px] text-slate-400 mt-0.5">{{ si.explanation }}</div>
                    </div>
                  </div>
                </div>
                <!-- 第四项：其它，请补充（免勾选直接输入） -->
                <div class="flex items-center gap-2 pt-1 border-t border-slate-100">
                  <span class="text-xs text-slate-600 shrink-0">其它，请补充</span>
                  <el-input
                    v-model="customQuery"
                    size="small"
                    class="font-mono"
                    placeholder="输入自定义检索式（PubMed 语法）…"
                  />
                </div>
                <div class="flex items-center justify-between pt-1">
                  <span class="text-[11px] text-slate-400">确认后我们再选择研究领域。</span>
                  <el-button type="primary" size="small" @click="confirmQueries">确认检索式，继续</el-button>
                </div>
              </div>
            </div>

            <!-- 第二问：研究领域选择（默认 / 默认+自定义 / 仅自定义，默认为合并） -->
            <div v-if="setup.phase === 'domain' && i === setup.messages.length - 1" class="pl-10 max-w-[92%]">
              <div class="p-3 rounded-lg border border-slate-200 bg-white space-y-2.5">
                <div class="flex items-center justify-between gap-2 flex-wrap">
                  <div class="flex items-center gap-2 text-[11px]">
                    <span class="font-semibold text-slate-500 uppercase tracking-wide">研究领域</span>
                    <span class="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-mono">
                      {{ domainBadgeText }}
                    </span>
                  </div>
                  <el-radio-group v-model="setup.domainMode" size="small">
                    <el-radio-button value="default">仅默认</el-radio-button>
                    <el-radio-button value="merge">默认＋自定义</el-radio-button>
                    <el-radio-button value="replace">仅自定义</el-radio-button>
                  </el-radio-group>
                </div>

                <div class="text-[11px] text-slate-500 leading-relaxed">
                  {{ domainModeHint }}
                </div>

                <template v-if="setup.domainMode !== 'default'">
                  <div class="flex items-center gap-1.5 pt-0.5 border-t border-slate-100">
                    <span class="text-[11px] text-slate-400 shrink-0">定义自定义领域</span>
                    <el-button size="small" @click="domainTab = domainTab === 'paste' ? '' : 'paste'">粘贴 JSON</el-button>
                    <el-button size="small" @click="domainTab = domainTab === 'generate' ? '' : 'generate'">AI 生成</el-button>
                    <span v-if="setup.domainName" class="text-[11px] text-emerald-600 ml-auto">
                      已保存：{{ setup.domainName }}
                    </span>
                  </div>

                  <div v-if="domainTab" class="space-y-2">
                    <el-input
                      v-if="domainTab === 'generate'"
                      v-model="domainDescription"
                      size="small"
                      placeholder="描述研究领域（如：阿尔茨海默病脑脊液蛋白标志物，关注预后）…"
                    />
                    <el-input
                      v-else
                      v-model="domainJsonText"
                      type="textarea"
                      :rows="6"
                      placeholder="粘贴领域定义 JSON。粘贴后点解析校准，AI 会补齐缺失字段并规范化格式。"
                    />
                    <div class="flex items-center gap-2">
                      <el-button
                        size="small"
                        type="primary"
                        :loading="domainBusy"
                        @click="domainTab === 'generate' ? runGenerate() : runCalibrate()"
                      >
                        {{ domainTab === 'generate' ? 'AI 生成领域' : '解析校准' }}
                      </el-button>
                    </div>
                  </div>

                  <div v-if="domainPreview" class="space-y-2">
                    <div class="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
                      领域预览（name: {{ domainPreview.name }}）— 可编辑后保存
                    </div>
                    <el-input v-model="domainPreviewText" type="textarea" :rows="8" class="font-mono" />
                    <template v-if="domainPreviewFields">
                      <div class="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
                        抽取字段预览（{{ domainPreviewFields.name }}）
                      </div>
                      <el-input v-model="domainPreviewFieldsText" type="textarea" :rows="5" class="font-mono" />
                    </template>
                    <div class="flex items-center gap-2">
                      <el-button size="small" type="success" :loading="domainBusy" @click="saveDomain">保存并使用此领域</el-button>
                      <el-button size="small" text @click="domainPreview = null">放弃</el-button>
                    </div>
                  </div>
                </template>

                <div class="flex items-center justify-between pt-1">
                  <span v-if="setup.domainMode === 'replace' && !setup.domainName" class="text-[11px] text-amber-600">
                    仅自定义模式需先保存一个自定义领域（上方粘贴或 AI 生成）
                  </span>
                  <span v-else class="text-[11px] text-slate-400">点击开始后将按管线执行：检索 → 抽取 → 验证 → 聚合</span>
                  <el-button type="primary" size="small" :disabled="!canRunFromDomain" @click="runSetup">
                    {{ runButtonText }}
                  </el-button>
                </div>
              </div>
            </div>
          </template>

          <!-- 解析中：打字点动画气泡 -->
          <Bubble
            v-if="setup.phase === 'parsing'"
            placement="start"
            :loading="true"
            content="正在解析"
          >
            <template #avatar>
              <el-avatar :size="26" style="background:#e0f2fe;color:#0284c7">
                <el-icon :size="14"><ChatDotRound /></el-icon>
              </el-avatar>
            </template>
          </Bubble>
        </div>

        <!-- 底部输入区：Sender 仅在 clarify 阶段可用 -->
        <div class="border-t border-slate-100 p-3">
          <Sender
            v-model:value="setupInput"
            :placeholder="senderPlaceholder"
            :disabled="setup.phase !== 'clarify'"
            :loading="setup.phase === 'parsing'"
            :send-disabled="!hasAnyAnswer"
            submit-type="enter"
            :auto-size="{ minRows: 1, maxRows: 4 }"
            @submit="onSenderSubmit"
          />
        </div>
      </div>
    </XProvider>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue';
import { ElMessage } from 'element-plus';
import { Bubble, Sender, XProvider } from 'ant-design-x-vue';
// 样式由组件内置 cssinjs 运行时注入（包内 dist/style.css 导出项指向的文件并不存在）
import { agentApi } from '@/api/client';
import { useResearch, type SetupQuestion } from '@/composables/useResearch';

const {
  setup, customQuery, papers, documents, miningActive, workflowPanelOpen,
  sendClarification, confirmQueries, confirmAndRun, closeSetup,
} = useResearch();

/** antd 主色对齐 Tailwind sky-600，发送按钮/气泡与全站视觉一致 */
const xTheme = { token: { colorPrimary: '#0284c7', borderRadius: 8 } };
/** 用户气泡：sky 实底白字（filled 变体默认为浅灰，这里显式覆盖） */
const userBubbleStyles = { content: { background: '#0284c7', color: '#ffffff' } };

const setupInput = ref('');
const setupChatRef = ref<HTMLDivElement | null>(null);

const setupPhaseLabel = computed(() => {
  switch (setup.value?.phase) {
    case 'parsing': return '解析中';
    case 'clarify': return '等待你的回答';
    case 'queries': return '确认检索式';
    case 'domain': return '选择研究领域';
    case 'running': return '挖掘执行中';
    default: return '';
  }
});

const senderPlaceholder = computed(() => {
  switch (setup.value?.phase) {
    case 'parsing': return '正在解析你的回答…';
    case 'clarify': return '用自然语言回答（如：胰腺癌，关注预后，2020 年以来）…';
    case 'queries': return '请在上方卡片中确认检索式，然后点「确认检索式，继续」';
    case 'domain': return '请选择研究领域后开始挖掘';
    case 'running': return '管线执行中，可在下方监控面板查看进度…';
    default: return '';
  }
});

/** 新消息 / 阶段变化时滚动到底部 */
async function scrollSetupChat() {
  await nextTick();
  const el = setupChatRef.value;
  if (el) { el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' }); }
}
watch(
  () => [setup.value?.messages.length, setup.value?.phase],
  () => { void scrollSetupChat(); },
);

// ---- dsh 式问题卡片：答案收集与提交 ----
const questionAnswers = ref<Record<string, { selected: string[]; custom: string }>>({});

const pendingQuestions = computed<SetupQuestion[]>(() => {
  if (setup.value?.phase !== 'clarify') { return []; }
  const last = [...setup.value.messages].reverse().find(m => m.questions?.length);
  return last?.questions ?? [];
});
/** 最后一条追问消息（内联动作只挂在这里） */
const lastQuestionMsgIdx = computed(() => {
  const msgs = setup.value?.messages ?? [];
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].questions?.length) { return i; }
  }
  return -1;
});
const lastParseMsgIdx = computed(() => {
  const msgs = setup.value?.messages ?? [];
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].intents) { return i; }
  }
  return -1;
});

const hasAnyAnswer = computed(() => {
  if (setupInput.value.trim()) { return true; }
  return Object.values(questionAnswers.value).some(a => a.selected.length || a.custom.trim());
});

function toggleOption(q: SetupQuestion, label: string) {
  const cur = questionAnswers.value[q.id] ?? { selected: [], custom: '' };
  if (q.multi_select) {
    const sel = cur.selected.includes(label) ? cur.selected.filter(x => x !== label) : [...cur.selected, label];
    questionAnswers.value[q.id] = { ...cur, selected: sel };
  } else {
    // 单选：再次点击取消选择
    questionAnswers.value[q.id] = { ...cur, selected: cur.selected.includes(label) ? [] : [label] };
  }
}

function setCustom(qid: string, text: string) {
  const cur = questionAnswers.value[qid] ?? { selected: [], custom: '' };
  questionAnswers.value[qid] = { ...cur, custom: text };
}

/** 提交追问回答：卡片选项 + 自由文本合并为一条用户消息。
 *  phase 切换与消息推送由 sendClarification 统一负责（提前改 phase 会触发其 'clarify' 守卫空转）。 */
async function submitAnswers(senderText?: string) {
  const s = setup.value;
  if (!s || s.phase !== 'clarify') { return; }
  const parts: string[] = [];
  for (const q of pendingQuestions.value) {
    const a = questionAnswers.value[q.id];
    if (!a) { continue; }
    const merged = [a.selected.join('、'), a.custom].filter(Boolean).join('；');
    if (merged) { parts.push(`${q.question} → ${merged}`); }
  }
  const free = (senderText ?? setupInput.value).trim();
  if (free) { parts.push(free); }
  if (!parts.length) {
    ElMessage.warning('请先点选选项或输入回答；如无需补充可点「跳过追问」');
    return;
  }
  setupInput.value = '';
  questionAnswers.value = {};
  await sendClarification(parts.join('\n'));
  await scrollSetupChat();
}

/** Sender 提交（Enter / 发送按钮）：与卡片提交共用一条路径 */
function onSenderSubmit(message: string) {
  void submitAnswers(message);
}

function skipClarify() {
  if (!setup.value || setup.value.phase !== 'clarify') { return; }
  // 跳过追问 → 进入检索式确认（检索式可能为空，使用默认参数执行）
  setup.value.rounds = 99;
  setup.value.phase = 'queries';
}

// ---- 研究领域（AskHuman 扩展：默认/合并/仅自定义 + 粘贴/生成/校准/保存） ----
const domainTab = ref<'' | 'paste' | 'generate'>('');
const domainDescription = ref('');
const domainJsonText = ref('');
const domainPreview = ref<Record<string, unknown> | null>(null);
const domainPreviewText = ref('');
const domainPreviewFields = ref<Record<string, unknown> | null>(null);
const domainPreviewFieldsText = ref('');
const domainBusy = ref(false);

const domainBadgeText = computed(() => {
  const name = setup.value?.domainName;
  switch (setup.value?.domainMode) {
    case 'default': return '默认（按任务自动匹配）';
    case 'replace': return name ? `仅自定义：${name}` : '自定义（未定义）';
    default: return name ? `默认＋${name}` : '默认（未定义自定义，等同仅默认）';
  }
});

const domainModeHint = computed(() => {
  switch (setup.value?.domainMode) {
    case 'default':
      return '使用内置领域定义（按研究任务自动匹配生物标志物等领域），不做任何自定义扩展。';
    case 'replace':
      return '完全使用你定义的自定义领域，替换内置定义（谓词、实体类型、抽取字段均以自定义为准）。';
    default:
      return '推荐：自定义领域将并入默认领域——实体类型、谓词与抽取字段取并集，验证阈值等安全红线保持默认，兼顾覆盖面与稳定性。';
  }
});

const canRunFromDomain = computed(() => {
  const s = setup.value;
  if (!s) { return false; }
  if (s.domainMode === 'replace') { return !!s.domainName; }
  return true;
});

const runButtonText = computed(() => {
  const s = setup.value;
  if (!s) { return '开始挖掘'; }
  if (s.domainMode === 'default') { return '开始挖掘（使用默认领域）'; }
  if (s.domainMode === 'replace') { return s.domainName ? `开始挖掘（仅使用 ${s.domainName}）` : '开始挖掘（需先保存自定义领域）'; }
  return s.domainName ? `开始挖掘（默认＋${s.domainName}）` : '开始挖掘（使用默认领域）';
});

function setDomainPreview(domain: Record<string, unknown>, extractionFields: Record<string, unknown> | null) {
  domainPreview.value = domain;
  domainPreviewText.value = JSON.stringify(domain, null, 2);
  domainPreviewFields.value = extractionFields;
  domainPreviewFieldsText.value = extractionFields ? JSON.stringify(extractionFields, null, 2) : '';
}

async function runGenerate() {
  if (!domainDescription.value.trim()) {
    ElMessage.warning('请先描述研究领域');
    return;
  }
  domainBusy.value = true;
  try {
    const res = await agentApi.generateDomainSchema(domainDescription.value.trim());
    setDomainPreview(res.domain, res.extraction_fields);
    ElMessage.success('领域定义已生成，请检查预览');
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  } finally {
    domainBusy.value = false;
  }
}

async function runCalibrate() {
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(domainJsonText.value);
  } catch {
    ElMessage.error('JSON 解析失败，请检查格式');
    return;
  }
  domainBusy.value = true;
  try {
    const res = await agentApi.calibrateDomainSchema(payload);
    setDomainPreview(res.domain, res.extraction_fields);
    ElMessage.success('AI 已校准格式并补齐缺失字段，请检查预览');
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  } finally {
    domainBusy.value = false;
  }
}

async function saveDomain() {
  let payload: Record<string, unknown>;
  let efPayload: Record<string, unknown> | null = null;
  try {
    payload = JSON.parse(domainPreviewText.value);
    if (domainPreviewFields.value) {
      efPayload = JSON.parse(domainPreviewFieldsText.value);
    }
  } catch {
    ElMessage.error('JSON 解析失败，请检查格式');
    return;
  }
  domainBusy.value = true;
  try {
    const res = await agentApi.saveDomainSchema(payload, efPayload);
    if (setup.value) { setup.value.domainName = res.name; }
    domainPreview.value = null;
    domainPreviewFields.value = null;
    domainTab.value = '';
    domainJsonText.value = '';
    domainDescription.value = '';
    ElMessage.success(`领域「${res.name}」已保存，本次挖掘将使用该领域`);
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  } finally {
    domainBusy.value = false;
  }
}

async function runSetup() {
  workflowPanelOpen.value = true; // 启动即展开监控，进度可见
  try {
    await confirmAndRun();
    ElMessage.success(`挖掘完成: 产出 ${papers.value.length} 条命题、${documents.value.length} 篇文献`);
  } catch {
    ElMessage.error('挖掘管线执行失败');
  }
}
</script>

<style scoped>
/* 气泡正文行高与字号贴近全站 13px 文本 */
:deep(.setup-msg .ant-bubble-content) {
  font-size: 13px;
  line-height: 1.65;
}
/* AI 无边框气泡保留可选中复制的外观，不抢卡片焦点 */
:deep(.ant-bubble-content-borderless) {
  color: #1e293b;
}
</style>
