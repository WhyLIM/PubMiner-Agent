<template>
  <div class="space-y-4">
    <!-- Top Summary Banner -->
    <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs flex flex-wrap items-center justify-between gap-4">
      <div>
        <h2 class="text-base font-bold text-slate-900">多维学术计量与循证统计分析</h2>
        <p class="text-xs text-slate-500 mt-0.5">
          基于 PubMed/PMC 全文元数据、MeSH 标注与实体共现频率的多维定量学术图景。
        </p>
      </div>

      <div class="flex items-center gap-2">
        <el-button size="small" @click="refreshAllCharts">
          <el-icon class="mr-1"><Refresh /></el-icon>
          重新渲染图表
        </el-button>
      </div>
    </div>

    <!-- 2x2 Grid of ECharts Academic Visualizations -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <!-- Chart 1: Publication Velocity & Citation Impact -->
      <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs">
        <div class="flex items-center justify-between mb-3 border-b border-slate-100 pb-2">
          <div>
            <h3 class="text-xs font-semibold text-slate-800 uppercase tracking-wide">历年文献发表量与引用增长趋势</h3>
            <span class="text-[11px] text-slate-400 font-mono">Publication Volume & Citation Velocity (2019-2026)</span>
          </div>
          <el-tag size="small" type="info">双轴趋势图</el-tag>
        </div>
        <div ref="trendChartRef" class="w-full h-72"></div>
      </div>

      <!-- Chart 2: Biomedical Entity Co-occurrence Matrix Heatmap -->
      <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs">
        <div class="flex items-center justify-between mb-3 border-b border-slate-100 pb-2">
          <div>
            <h3 class="text-xs font-semibold text-slate-800 uppercase tracking-wide">药物-靶点/突变实体共现关联热力图</h3>
            <span class="text-[11px] text-slate-400 font-mono">Drug-Target Co-occurrence Heatmap Matrix</span>
          </div>
          <el-tag size="small" type="success">关联强度矩阵</el-tag>
        </div>
        <div ref="heatmapChartRef" class="w-full h-72"></div>
      </div>

      <!-- Chart 3: Evidence Hierarchy & Study Design Distribution -->
      <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs">
        <div class="flex items-center justify-between mb-3 border-b border-slate-100 pb-2">
          <div>
            <h3 class="text-xs font-semibold text-slate-800 uppercase tracking-wide">循证医学证据金字塔与研究设计类型</h3>
            <span class="text-[11px] text-slate-400 font-mono">Evidence Hierarchy & Study Design Breakdown</span>
          </div>
          <el-tag size="small" type="warning">南丁格尔玫瑰图</el-tag>
        </div>
        <div ref="evidenceChartRef" class="w-full h-72"></div>
      </div>

      <!-- Chart 4: Biomarker Ranking & Translation Index -->
      <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs">
        <div class="flex items-center justify-between mb-3 border-b border-slate-100 pb-2">
          <div>
            <h3 class="text-xs font-semibold text-slate-800 uppercase tracking-wide">核心生物标志物研究活跃度与转化指数</h3>
            <span class="text-[11px] text-slate-400 font-mono">Biomarker Translational Relevance Index</span>
          </div>
          <el-tag size="small" type="primary">排名指数</el-tag>
        </div>
        <div ref="biomarkerChartRef" class="w-full h-72"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue';
import * as echarts from 'echarts';
import { ResearchTopic } from '../types';

const props = defineProps<{
  topic: ResearchTopic;
}>();

const trendChartRef = ref<HTMLDivElement | null>(null);
const heatmapChartRef = ref<HTMLDivElement | null>(null);
const evidenceChartRef = ref<HTMLDivElement | null>(null);
const biomarkerChartRef = ref<HTMLDivElement | null>(null);

let trendChart: echarts.ECharts | null = null;
let heatmapChart: echarts.ECharts | null = null;
let evidenceChart: echarts.ECharts | null = null;
let biomarkerChart: echarts.ECharts | null = null;

function initCharts() {
  initTrendChart();
  initHeatmapChart();
  initEvidenceChart();
  initBiomarkerChart();
  window.addEventListener('resize', handleResize);
}

function handleResize() {
  trendChart?.resize();
  heatmapChart?.resize();
  evidenceChart?.resize();
  biomarkerChart?.resize();
}

function refreshAllCharts() {
  handleResize();
}

function initTrendChart() {
  if (!trendChartRef.value) return;
  trendChart = echarts.init(trendChartRef.value);

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' }
    },
    legend: {
      data: ['年度文献篇数', '均篇被引频次'],
      bottom: 0,
      textStyle: { fontSize: 11 }
    },
    grid: {
      top: '12%',
      left: '3%',
      right: '4%',
      bottom: '12%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: props.topic.trendYears,
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      axisLabel: { color: '#64748b', fontSize: 11 }
    },
    yAxis: [
      {
        type: 'value',
        name: '发文量 (篇)',
        position: 'left',
        axisLine: { show: false },
        axisLabel: { color: '#64748b', fontSize: 11 },
        splitLine: { lineStyle: { color: '#f1f5f9' } }
      },
      {
        type: 'value',
        name: '均篇引用',
        position: 'right',
        axisLine: { show: false },
        axisLabel: { color: '#64748b', fontSize: 11 },
        splitLine: { show: false }
      }
    ],
    series: [
      {
        name: '年度文献篇数',
        type: 'bar',
        data: props.topic.pubCounts,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#38bdf8' },
            { offset: 1, color: '#0284c7' }
          ]),
          borderRadius: [4, 4, 0, 0]
        },
        barWidth: '40%'
      },
      {
        name: '均篇被引频次',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        data: props.topic.citationAverages,
        itemStyle: { color: '#f59e0b' },
        lineStyle: { width: 3 }
      }
    ]
  };

  trendChart.setOption(option);
}

function initHeatmapChart() {
  if (!heatmapChartRef.value) return;
  heatmapChart = echarts.init(heatmapChartRef.value);

  const matrix = props.topic.cooccurrenceMatrix;
  const option: echarts.EChartsOption = {
    tooltip: {
      position: 'top',
      formatter: (params: any) => {
        const xName = matrix.xLabels[params.data[0]];
        const yName = matrix.yLabels[params.data[1]];
        return `<div class="text-xs font-sans">
          <div class="font-bold text-slate-800">${xName} × ${yName}</div>
          <div class="text-sky-600 font-mono mt-0.5">文献共现强度: ${params.data[2]}</div>
        </div>`;
      }
    },
    grid: {
      top: '8%',
      left: '3%',
      right: '6%',
      bottom: '12%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: matrix.xLabels,
      splitArea: { show: true },
      axisLabel: { interval: 0, rotate: 20, fontSize: 10, color: '#475569' }
    },
    yAxis: {
      type: 'category',
      data: matrix.yLabels,
      splitArea: { show: true },
      axisLabel: { fontSize: 10, color: '#475569' }
    },
    visualMap: {
      min: 0,
      max: 100,
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
        name: '共现关联度',
        type: 'heatmap',
        data: matrix.data,
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

function initEvidenceChart() {
  if (!evidenceChartRef.value) return;
  evidenceChart = echarts.init(evidenceChartRef.value);

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
        name: '研究设计与证据金字塔',
        type: 'pie',
        radius: ['25%', '65%'],
        center: ['50%', '42%'],
        roseType: 'radius',
        itemStyle: {
          borderRadius: 4
        },
        data: props.topic.evidenceDistribution.map((item, idx) => ({
          ...item,
          itemStyle: {
            color: ['#0284c7', '#0d9488', '#f59e0b', '#8b5cf6', '#e11d48'][idx % 5]
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

function initBiomarkerChart() {
  if (!biomarkerChartRef.value) return;
  biomarkerChart = echarts.init(biomarkerChartRef.value);

  const rankings = [...props.topic.biomarkerRanking].reverse();

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    grid: {
      top: '5%',
      left: '3%',
      right: '6%',
      bottom: '5%',
      containLabel: true
    },
    xAxis: {
      type: 'value',
      max: 100,
      axisLabel: { fontSize: 10, color: '#64748b' },
      splitLine: { lineStyle: { color: '#f1f5f9' } }
    },
    yAxis: {
      type: 'category',
      data: rankings.map(r => r.name),
      axisLabel: { fontSize: 11, color: '#334155' }
    },
    series: [
      {
        name: '综合转化评分',
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

watch(() => props.topic, () => {
  initTrendChart();
  initHeatmapChart();
  initEvidenceChart();
  initBiomarkerChart();
}, { deep: true });

onMounted(() => {
  initCharts();
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize);
  trendChart?.dispose();
  heatmapChart?.dispose();
  evidenceChart?.dispose();
  biomarkerChart?.dispose();
});
</script>
