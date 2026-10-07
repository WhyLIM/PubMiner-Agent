<template>
  <header class="h-14 border-b border-slate-200 bg-white/95 backdrop-blur-md px-4 sm:px-6 flex items-center justify-between sticky top-0 z-50">
    <!-- Zone 1: Single text element wordmark -->
    <div class="flex items-center gap-3 shrink-0">
      <div class="w-8 h-8 rounded-lg bg-sky-700 flex items-center justify-center text-white shadow-sm">
        <el-icon :size="18"><Opportunity /></el-icon>
      </div>
      <div class="flex items-baseline gap-2">
        <span class="text-base font-bold tracking-tight text-slate-900 font-sans">
          PubMiner<span class="text-sky-600 font-normal">-Agent</span>
        </span>
        <span class="hidden md:inline text-xs text-slate-400 font-mono">v{{ appVersion }}</span>
      </div>
    </div>

    <!-- Zone 2: 4-6 clean text navigation links -->
    <nav class="hidden lg:flex items-center gap-1">
      <button
        v-for="item in navItems"
        :key="item.key"
        @click="$emit('update:activeTab', item.key)"
        :class="[
          'px-3 py-1.5 text-xs font-medium rounded-md transition-colors flex items-center gap-1.5 whitespace-nowrap',
          activeTab === item.key
            ? 'bg-sky-50 text-sky-700 font-semibold'
            : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
        ]"
      >
        <el-icon :size="14"><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
        <span v-if="item.badge" class="ml-1 px-1.5 py-0.5 text-[10px] leading-none rounded bg-slate-200/70 text-slate-600 font-mono">
          {{ item.badge }}
        </span>
      </button>
    </nav>

    <!-- Zone 3: 1-2 primary actions -->
    <div class="flex items-center gap-2.5 shrink-0">
      <!-- Scenario Selector -->
      <el-dropdown trigger="click" @command="handleSelectTopic">
        <button class="px-2.5 py-1.5 text-xs border border-slate-200 rounded-md bg-white hover:bg-slate-50 text-slate-700 flex items-center gap-1.5 transition-colors">
          <el-icon :size="13" class="text-sky-600"><Collection /></el-icon>
          <span class="max-w-[140px] sm:max-w-[180px] truncate">{{ currentTopicTitle }}</span>
          <el-icon :size="12" class="text-slate-400"><ArrowDown /></el-icon>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="t in topics"
              :key="t.id"
              :command="t.id"
              :disabled="t.id === currentTopicId"
            >
              <div class="py-0.5">
                <div class="font-medium text-xs text-slate-800 max-w-[300px] truncate">{{ t.title }}</div>
                <div v-if="t.meta" class="text-[11px] text-slate-400 font-mono">{{ t.meta }}</div>
              </div>
            </el-dropdown-item>
            <el-dropdown-item divided command="custom">
              <div class="flex items-center gap-1.5 text-sky-600 text-xs py-0.5 font-medium">
                <el-icon><Plus /></el-icon>
                <span>新建课题（前往文献页搜索框）...</span>
              </div>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <!-- Execution Monitor Button（不创建任务，仅查看进度） -->
      <button
        @click="$emit('trigger-agent')"
        class="px-3 py-1.5 text-xs font-medium text-white bg-sky-700 hover:bg-sky-800 rounded-md transition-colors flex items-center gap-1.5 shadow-sm whitespace-nowrap"
      >
        <el-icon :size="13"><Monitor /></el-icon>
        <span>执行监控</span>
      </button>

      <!-- Export Data Action -->
      <el-dropdown trigger="click" @command="handleExport">
        <button class="p-1.5 text-slate-600 hover:text-slate-900 border border-slate-200 rounded-md bg-white hover:bg-slate-50 transition-colors" title="导出数据报告">
          <el-icon :size="15"><Download /></el-icon>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="markdown">导出综述报告 (.md)</el-dropdown-item>
            <el-dropdown-item command="csv">导出命题清单 (.csv)</el-dropdown-item>
            <el-dropdown-item command="json">导出三元组图谱 (.json)</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>

  <!-- Mobile Secondary Tab Bar (only visible on small screens) -->
  <div class="lg:hidden flex items-center gap-1 overflow-x-auto px-4 py-2 border-b border-slate-200 bg-slate-50 text-xs">
    <button
      v-for="item in navItems"
      :key="item.key"
      @click="$emit('update:activeTab', item.key)"
      :class="[
        'px-2.5 py-1 rounded text-xs whitespace-nowrap flex items-center gap-1 transition-colors',
        activeTab === item.key ? 'bg-sky-600 text-white font-medium' : 'text-slate-600 hover:text-slate-900'
      ]"
    >
      <el-icon :size="12"><component :is="item.icon" /></el-icon>
      <span>{{ item.label }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

/** 构建时注入的版本号（单一来源：package.json，与后端 pyproject.toml 对齐） */
const appVersion = __APP_VERSION__;

const props = defineProps<{
  activeTab: string;
  topics: Array<{ id: string; title: string; meta?: string }>;
  currentTopicId: string;
  paperCount: number;
}>();

const emit = defineEmits<{
  (e: 'update:activeTab', tab: string): void;
  (e: 'select-topic', topicId: string): void;
  (e: 'trigger-agent'): void;
  (e: 'export-report', format: 'markdown' | 'csv' | 'json'): void;
}>();

const navItems = computed(() => [
  { key: 'literature', label: '文献检索挖掘', icon: 'Search', badge: `${props.paperCount}` },
  { key: 'graph', label: '知识图谱', icon: 'Share' },
  { key: 'analytics', label: '多维学术分析', icon: 'DataAnalysis' },
  { key: 'synthesis', label: '证据合成综述', icon: 'Document' },
]);

const currentTopicTitle = computed(() => {
  const t = props.topics.find(item => item.id === props.currentTopicId);
  if (!t) { return '研究课题'; }
  const first = t.title.split(' ')[0] ?? t.title;
  return first.length > 24 ? first.slice(0, 24) + '…' : first;
});

function handleSelectTopic(command: string) {
  emit('select-topic', command);
}

function handleExport(command: string) {
  emit('export-report', command as 'markdown' | 'csv' | 'json');
}
</script>
