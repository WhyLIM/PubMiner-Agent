<template>
  <div class="space-y-4">
    <!-- Top Summary Banner -->
    <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs flex flex-wrap items-center justify-between gap-4">
      <div>
        <h2 class="text-base font-bold text-slate-900">多维证据计量与循证统计分析</h2>
        <p class="text-xs text-slate-500 mt-0.5">
          基于当前会话的{{ topic.papers.length }}条证据聚合命题与{{ topic.graphLinks.length }}条实体关系，实时计算的定量图景。
        </p>
      </div>

      <div class="flex items-center gap-2">
        <el-button size="small" @click="renderAll">
          <el-icon class="mr-1"><Refresh /></el-icon>
          重新渲染图表
        </el-button>
      </div>
    </div>

    <el-empty
      v-if="topic.papers.length === 0"
      description="暂无数据：先在工作台/文献页运行一次挖掘管线，图表将基于真实聚合结果渲染。"
    />

    <!-- 2x2 Grid of ECharts Academic Visualizations -->
    <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <!-- Chart 1: Evidence Strength per Claim -->
      <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs">
        <div class="flex items-center justify-between mb-3 border-b border-slate-100 pb-2">
          <div>
            <h3 class="text-xs font-semibold text-slate-800 uppercase tracking-wide">命题证据强度对比 (Top 12)</h3>
            <span class="text-[11px] text-slate-400 font-mono">Evidence Strength per Claim (Support / Contradict)</span>
          </div>
          <el-tag size="small" type="info">堆叠柱状图</el-tag>
        </div>
        <div ref="strengthChartRef" class="w-full h-72"></div>
      </div>

      <!-- Chart 2: Entity Co-occurrence Matrix Heatmap -->
      <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs">
        <div class="flex items-center justify-between mb-3 border-b border-slate-100 pb-2">
          <div>
            <h3 class="text-xs font-semibold text-slate-800 uppercase tracking-wide">Subject-Object 实体关联热力图</h3>
            <span class="text-[11px] text-slate-400 font-mono">Entity Relation Co-occurrence Heatmap</span>
          </div>
          <el-tag size="small" type="success">关联强度矩阵</el-tag>
        </div>
        <div ref="heatmapChartRef" class="w-full h-72"></div>
      </div>

      <!-- Chart 3: Evidence Polarity Distribution -->
      <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs">
        <div class="flex items-center justify-between mb-3 border-b border-slate-100 pb-2">
          <div>
            <h3 class="text-xs font-semibold text-slate-800 uppercase tracking-wide">证据极性分布</h3>
            <span class="text-[11px] text-slate-400 font-mono">Evidence Polarity Distribution</span>
          </div>
          <el-tag size="small" type="warning">南丁格尔玫瑰图</el-tag>
        </div>
        <div ref="evidenceChartRef" class="w-full h-72"></div>
      </div>

      <!-- Chart 4: Biomarker Ranking -->
      <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs">
        <div class="flex items-center justify-between mb-3 border-b border-slate-100 pb-2">
          <div>
            <h3 class="text-xs font-semibold text-slate-800 uppercase tracking-wide">核心命题支持证据排行</h3>
            <span class="text-[11px] text-slate-400 font-mono">Claim Support Ranking</span>
          </div>
          <el-tag size="small" type="primary">排名指数</el-tag>
        </div>
        <div ref="biomarkerChartRef" class="w-full h-72"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue';
import * as echarts from 'echarts';
import { ResearchTopic } from '../types';

const props = defineProps<{
  topic: ResearchTopic;
}>();

const strengthChartRef = ref<HTMLDivElement | null>(null);
const heatmapChartRef = ref<HTMLDivElement | null>(null);
const evidenceChartRef = ref<HTMLDivElement | null>(null);
const biomarkerChartRef = ref<HTMLDivElement | null>(null);

let strengthChart: echarts.ECharts | null = null;
let heatmapChart: echarts.ECharts | null = null;
let evidenceChart: echarts.ECharts | null = null;
let biomarkerChart: echarts.ECharts | null = null;

/** 截断规范签名用于坐标轴显示 */
function shortName(name: string, max = 22): string {
  return name.length > max ? name.slice(0, max) + '…' : name;
}

function renderAll() {
  nextTick(() => {
    initStrengthChart();
    initHeatmapChart();
    initEvidenceChart();
    initBiomarkerChart();
  });
}

function handleResize() {
  strengthChart?.resize();
  heatmapChart?.resize();
  evidenceChart?.resize();
  biomarkerChart?.resize();
}

/** 图1：各命题 支持/反驳 证据堆叠对比（真实聚合数据） */
function initStrengthChart() {
  if (!strengthChartRef.value) return;
  strengthChart?.dispose();
  strengthChart = echarts.init(strengthChartRef.value);

  const top = [...props.topic.papers]
    .sort((a, b) => (b.evidenceCount ?? 0) - (a.evidenceCount ?? 0))
    .slice(0, 12);
  // 同名命题去重（聚合签名可能出现同 subject|predicate 不同 object 的组合）
  const names = top.map(p => shortName(p.signature ?? p.title));

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    legend: {
      data: ['支持证据', '反驳证据', '无效应/不确定'],
      bottom: 0,
      textStyle: { fontSize: 11 }
    },
    grid: {
      top: '8%',
      left: '3%',
      right: '4%',
      bottom: '14%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: names,
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      axisLabel: { color: '#64748b', fontSize: 10, interval: 0, rotate: 30 }
    },
    yAxis: {
      type: 'value',
      name: '证据条数',
      axisLine: { show: false },
      axisLabel: { color: '#64748b', fontSize: 11 },
      splitLine: { lineStyle: { color: '#f1f5f9' } }
    },
    series: [
      {
        name: '支持证据',
        type: 'bar',
        stack: 'total',
        data: top.map(p => p.supportCount ?? 0),
        itemStyle: { color: '#059669' },
        barWidth: '50%'
      },
      {
        name: '反驳证据',
        type: 'bar',
        stack: 'total',
        data: top.map(p => p.contradictCount ?? 0),
        itemStyle: { color: '#e11d48' }
      },
      {
        name: '无效应/不确定',
        type: 'bar',
        stack: 'total',
        data: top.map(p => (p.noEffectCount ?? 0) + (p.uncertainCount ?? 0)),
        itemStyle: { color: '#94a3b8', borderRadius: [4, 4, 0, 0] }
      }
    ]
  };

  strengthChart.setOption(option);
}

/** 图2：Subject × Object 关联强度热力图（从真实 graphLinks 计算） */
function initHeatmapChart() {
  if (!heatmapChartRef.value) return;
  heatmapChart?.dispose();
  heatmapChart = echarts.init(heatmapChartRef.value);

  // 取支持证据最多的前 6 个 subject / object 构建矩阵
  const weightOf = (l: { source: string; target: string; weight: number }) => l.weight;
  const sourceCount = new Map<string, number>();
  const targetCount = new Map<string, number>();
  for (const link of props.topic.graphLinks) {
    sourceCount.set(link.source, (sourceCount.get(link.source) ?? 0) + weightOf(link));
    targetCount.set(link.target, (targetCount.get(link.target) ?? 0) + weightOf(link));
  }
  const xLabels = [...sourceCount.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6).map(e => e[0]);
  const yLabels = [...targetCount.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6).map(e => e[0]);
  const xIdx = new Map(xLabels.map((n, i) => [n, i]));
  const yIdx = new Map(yLabels.map((n, i) => [n, i]));

  const data: [number, number, number][] = [];
  let maxVal = 0;
  for (const link of props.topic.graphLinks) {
    const xi = xIdx.get(link.source);
    const yi = yIdx.get(link.target);
    if (xi === undefined || yi === undefined) continue;
    data.push([xi, yi, weightOf(link)]);
    maxVal = Math.max(maxVal, weightOf(link));
  }

  const finalMax = Math.max(1, maxVal);

  const option: echarts.EChartsOption = {
    tooltip: {
      position: 'top',
      formatter: (params: any) => {
        const xName = xLabels[params.data[0]];
        const yName = yLabels[params.data[1]];
        return `<div class="text-xs font-sans">
          <div class="font-bold text-slate-800">${xName} × ${yName}</div>
          <div class="text-sky-600 font-mono mt-0.5">关联证据强度: ${params.data[2]}</div>
        </div>`;
      }
    },
    grid: {
      top: '8%',
      left: '3%',
      right: '6%',
      bottom: '14%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: xLabels.map(n => shortName(n, 14)),
      splitArea: { show: true },
      axisLabel: { interval: 0, rotate: 20, fontSize: 10, color: '#475569' }
    },
    yAxis: {
      type: 'category',
      data: yLabels.map(n => shortName(n, 14)),
      splitArea: { show: true },
      axisLabel: { fontSize: 10, color: '#475569' }
    },
    visualMap: {
      min: 0,
      max: finalMax,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: '0%',
      inRange: {
        color: ['#f0fdf4', '#86efac', '#22c55e', '#15803d', '#14532d']
      },
      textStyle: { fontSize: 10 }
    },
    series: [
      {
        name: '关联强度',
        type: 'heatmap',
        data: data,
        label: {
          show: true,
          fontSize: 10,
          color: '#1e293b',
          formatter: (p: any) => p.data[2]
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowColor: 'rgba(0, 0, 0, 0.4)'
          }
        }
      }
    ]
  };

  heatmapChart.setOption(option);
}

/** 图3：证据极性分布玫瑰图（真实数据，来自 App.vue 的 evidenceDistribution） */
function initEvidenceChart() {
  if (!evidenceChartRef.value) return;
  evidenceChart?.dispose();
  evidenceChart = echarts.init(evidenceChartRef.value);

  const palette = ['#0284c7', '#e11d48', '#64748b', '#f59e0b'];
  const filtered = props.topic.evidenceDistribution.filter(d => d.value > 0);

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'item',
      formatter: '{b}: <span class="font-mono font-bold">{c}</span> ({d}%)'
    },
    legend: {
      bottom: 0,
      textStyle: { fontSize: 10 }
    },
    series: [
      {
        name: '证据极性分布',
        type: 'pie',
        radius: ['25%', '65%'],
        center: ['50%', '42%'],
        roseType: 'radius',
        itemStyle: {
          borderRadius: 4
        },
        data: filtered.map((item, idx) => ({
          ...item,
          itemStyle: {
            color: palette[idx % palette.length]
          }
        })),
        label: {
          fontSize: 10,
          formatter: '{b}'
        }
      }
    ]
  };

  evidenceChart.setOption(option);
}

/** 图4：命题支持证据排行（真实数据） */
function initBiomarkerChart() {
  if (!biomarkerChartRef.value) return;
  biomarkerChart?.dispose();
  biomarkerChart = echarts.init(biomarkerChartRef.value);

  const rankings = [...props.topic.biomarkerRanking].reverse();

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: any) => {
        const p = params[0];
        const item = rankings[p.dataIndex];
        return `<div class="text-xs font-sans">
          <div class="font-bold text-slate-800">${shortName(item.name, 30)}</div>
          <div class="font-mono text-sky-600 mt-0.5">支持证据: ${item.score} · 独立文献: ${item.articles}</div>
        </div>`;
      }
    },
    grid: {
      top: '5%',
      left: '3%',
      right: '10%',
      bottom: '5%',
      containLabel: true
    },
    xAxis: {
      type: 'value',
      axisLabel: { fontSize: 10, color: '#64748b' },
      splitLine: { lineStyle: { color: '#f1f5f9' } }
    },
    yAxis: {
      type: 'category',
      data: rankings.map(r => shortName(r.name, 18)),
      axisLabel: { fontSize: 10, color: '#334155' }
    },
    series: [
      {
        name: '支持证据数',
        type: 'bar',
        data: rankings.map(r => r.score),
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: '#6366f1' },
            { offset: 1, color: '#0284c7' }
          ]),
          borderRadius: [0, 4, 4, 0]
        },
        label: {
          show: true,
          position: 'right',
          fontSize: 10,
          fontFamily: 'monospace',
          formatter: '{c}'
        },
        barWidth: '50%'
      }
    ]
  };

  biomarkerChart.setOption(option);
}

// 数据到达/变化时重渲染（App.vue 每次 refreshTopicFromResearch 会替换 topic 对象引用）
watch(() => props.topic, () => renderAll(), { deep: true });

onMounted(() => {
  renderAll();
  window.addEventListener('resize', handleResize);
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize);
  strengthChart?.dispose();
  heatmapChart?.dispose();
  evidenceChart?.dispose();
  biomarkerChart?.dispose();
});
</script>
