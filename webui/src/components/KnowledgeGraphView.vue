<template>
  <div class="space-y-4">
    <!-- Graph Control Header Bar -->
    <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <!-- Entity Category Filters -->
        <div class="flex items-center gap-3 flex-wrap">
          <span class="text-xs font-semibold text-slate-700">实体类型过滤:</span>
          <div class="flex items-center gap-2">
            <el-checkbox v-model="visibleCategories[0]" label="生物标志物 (Subject)" size="small" />
            <el-checkbox v-model="visibleCategories[1]" label="疾病/临床结局 (Object)" size="small" />
          </div>
        </div>

        <!-- Co-occurrence Strength & Actions -->
        <div class="flex items-center gap-3 flex-wrap">
          <div class="flex items-center gap-2 text-xs text-slate-500">
            <span>最小文献共现数:</span>
            <el-slider
              v-model="minWeight"
              :min="0"
              :max="10"
              :step="0.5"
              size="small"
              class="w-24 sm:w-32"
            />
            <span class="font-mono text-slate-800">{{ minWeight }}</span>
          </div>

          <!-- Entity Search in Graph -->
          <el-input
            v-model="searchKeyword"
            placeholder="定位实体 (如 EGFR, Osimertinib)..."
            prefix-icon="Search"
            size="small"
            clearable
            class="w-44 sm:w-52"
            @input="handleSearchEntity"
          />

          <el-button-group size="small">
            <el-button @click="resetGraphZoom" title="重置视角">
              <el-icon><Refresh /></el-icon>
            </el-button>
            <el-button type="primary" @click="exportGraphImage" title="导出高分辨率图像">
              <el-icon><Download /></el-icon>
              <span>导出 PNG</span>
            </el-button>
          </el-button-group>
        </div>
      </div>
    </div>

    <!-- Main Graph Canvas & Inspector Grid -->
    <el-empty
      v-if="props.nodes.length === 0"
      description="暂无图谱数据：先在文献页/工作台运行一次挖掘管线，聚合命题将构成实体关系图谱。"
    />
    <div v-else class="grid grid-cols-1 lg:grid-cols-4 gap-4">
      <!-- ECharts Graph Container -->
      <div class="lg:col-span-3 bg-white rounded-lg border border-slate-200 p-2 shadow-xs relative">
        <div ref="chartContainer" class="w-full h-[580px] rounded"></div>

        <!-- Legend Overlay (Zero-Pill Rule) -->
        <div class="absolute bottom-4 left-4 bg-white/90 backdrop-blur-xs border border-slate-200/80 rounded-md p-2 text-xs shadow-xs space-y-1">
          <div class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1">节点图例 (Node Types)</div>
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full bg-[#0284c7]"></span>
            <span class="text-slate-700">生物标志物 / Subject</span>
          </div>
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full bg-[#e11d48]"></span>
            <span class="text-slate-700">疾病 / 临床结局 (Object)</span>
          </div>
        </div>
      </div>

      <!-- Node / Sub-Network Inspector Side Panel -->
      <div class="bg-white rounded-lg border border-slate-200 p-4 shadow-xs flex flex-col justify-between">
        <div v-if="selectedNode" class="space-y-4">
          <div>
            <div class="flex items-center justify-between text-xs text-slate-400 mb-1">
              <span>实体详细探测</span>
              <span class="font-mono text-sky-700 font-semibold">{{ getCategoryName(selectedNode.category) }}</span>
            </div>
            <h3 class="text-lg font-bold text-slate-900 leading-tight">
              {{ selectedNode.name }}
            </h3>
            <p class="text-xs text-slate-600 mt-2 leading-relaxed">
              {{ selectedNode.details || '暂无详细生化机制描述，已在 PubMed 建立实体链接。' }}
            </p>
          </div>

          <!-- Centrality & Metric Badges -->
          <div class="bg-slate-50 rounded p-3 border border-slate-100 text-xs space-y-1.5">
            <div class="flex justify-between">
              <span class="text-slate-400">关联证据强度:</span>
              <span class="font-mono font-bold text-slate-800">{{ selectedNode.value }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-400">直接关联 (Degree):</span>
              <span class="font-mono font-bold text-sky-700">{{ connectedEdges.length }} 条关系边</span>
            </div>
          </div>

          <!-- Connected Triples -->
          <div>
            <h4 class="text-xs font-semibold text-slate-700 uppercase tracking-wide mb-2">直接关联三元组关系</h4>
            <div class="space-y-1.5 max-h-56 overflow-y-auto pr-1">
              <div
                v-for="(edge, idx) in connectedEdges"
                :key="idx"
                class="p-2 rounded bg-slate-50 border border-slate-100 text-xs flex flex-col gap-1"
              >
                <div class="flex items-center justify-between">
                  <span class="font-semibold text-slate-800 truncate">{{ edge.target === selectedNode.id ? edge.source : edge.target }}</span>
                  <span class="text-[10px] font-mono text-emerald-700 bg-emerald-50 px-1 rounded">{{ edge.relation }}</span>
                </div>
                <div class="flex justify-between text-[11px] text-slate-400 font-mono">
                  <span>证据条数:</span>
                  <span>{{ edge.evidenceCount }} 条</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="text-center py-16 text-slate-400 text-xs space-y-2">
          <el-icon :size="28" class="text-slate-300"><Share /></el-icon>
          <p>在左侧力导向图谱中点击任意节点，查看实体关联分析与医学证据链。</p>
        </div>

        <!-- Quick Tips -->
        <div class="pt-4 border-t border-slate-100 text-[11px] text-slate-400">
          <p>提示：支持滚轮缩放、拖拽节点物理重排，或在上方搜索框直接查找靶标。</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue';
import * as echarts from 'echarts';
import { GraphNode, GraphLink } from '../types';
import { ElMessage } from 'element-plus';

const props = defineProps<{
  nodes: GraphNode[];
  links: GraphLink[];
}>();

const chartContainer = ref<HTMLDivElement | null>(null);
let chartInstance: echarts.ECharts | null = null;

const visibleCategories = ref([true, true]);
const minWeight = ref(0);
const searchKeyword = ref('');
const selectedNode = ref<GraphNode | null>(null);

const categoryColors = ['#0284c7', '#e11d48'];

function getCategoryName(category: number) {
  switch (category) {
    case 0: return '生物标志物 (Subject)';
    case 1: return '疾病/临床结局 (Object)';
    default: return '生物实体';
  }
}

const connectedEdges = computed(() => {
  if (!selectedNode.value) return [];
  const nodeId = selectedNode.value.id;
  return props.links.filter(l => l.source === nodeId || l.target === nodeId);
});

function initChart() {
  if (!chartContainer.value) return;
  chartInstance = echarts.init(chartContainer.value);
  updateChart();

  chartInstance.on('click', (params: any) => {
    if (params.dataType === 'node') {
      const found = props.nodes.find(n => n.id === params.data.id || n.name === params.data.name);
      if (found) {
        selectedNode.value = found;
      }
    }
  });

  window.addEventListener('resize', handleResize);
}

function handleResize() {
  if (chartInstance) {
    chartInstance.resize();
  }
}

function updateChart() {
  if (!chartInstance) return;

  // Filter nodes according to category toggles
  const activeNodes = props.nodes.filter(n => visibleCategories.value[n.category]);
  const activeNodeIds = new Set(activeNodes.map(n => n.id));

  // Filter links
  const activeLinks = props.links.filter(l => {
    return activeNodeIds.has(l.source) &&
      activeNodeIds.has(l.target) &&
      l.weight >= minWeight.value;
  });

  const chartNodes = activeNodes.map(node => {
    const isMatched = searchKeyword.value
      ? node.name.toLowerCase().includes(searchKeyword.value.toLowerCase())
      : false;

    return {
      id: node.id,
      name: node.name,
      category: node.category,
      symbolSize: isMatched ? node.symbolSize * 1.3 : node.symbolSize,
      value: node.value,
      itemStyle: {
        color: categoryColors[node.category],
        borderColor: isMatched ? '#f59e0b' : '#ffffff',
        borderWidth: isMatched ? 3 : 1.5,
        shadowBlur: isMatched ? 12 : 3,
        shadowColor: isMatched ? 'rgba(245, 158, 11, 0.5)' : 'rgba(0,0,0,0.1)'
      },
      label: {
        show: true,
        fontSize: 11,
        color: '#1e293b',
        formatter: '{b}'
      }
    };
  });

  const chartLinks = activeLinks.map(link => {
    return {
      source: link.source,
      target: link.target,
      value: link.weight,
      lineStyle: {
        width: Math.max(1, link.weight / 2.5),
        curveness: 0.15,
        color: '#94a3b8',
        opacity: 0.65
      },
      label: {
        show: true,
        formatter: link.relation,
        fontSize: 9,
        color: '#64748b'
      }
    };
  });

  const option: echarts.EChartsOption = {
    animationDuration: 1000,
    animationEasingUpdate: 'quinticInOut',
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        if (params.dataType === 'node') {
          return `<div class="font-sans text-xs">
            <div class="font-bold text-slate-800">${params.data.name}</div>
            <div class="text-slate-500 mt-1">${getCategoryName(params.data.category)}</div>
            <div class="text-sky-600 font-mono mt-0.5">影响力指数: ${params.data.value}</div>
          </div>`;
        } else if (params.dataType === 'edge') {
          return `<div class="font-sans text-xs">
            <div class="font-bold text-slate-800">${params.data.source} ➔ ${params.data.target}</div>
            <div class="text-slate-600 mt-0.5">关联证据强度: <span class="font-mono text-sky-600">${params.data.value}</span></div>
          </div>`;
        }
        return '';
      }
    },
    series: [
      {
        type: 'graph',
        layout: 'force',
        data: chartNodes,
        links: chartLinks,
        categories: [
          { name: '生物标志物 (Subject)' },
          { name: '疾病/临床结局 (Object)' }
        ],
        roam: true,
        draggable: true,
        force: {
          repulsion: 380,
          gravity: 0.1,
          edgeLength: [90, 180],
          friction: 0.6
        },
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [4, 8],
        emphasis: {
          focus: 'adjacency',
          lineStyle: {
            width: 3.5,
            color: '#0284c7'
          }
        }
      }
    ]
  };

  chartInstance.setOption(option, true);
}

function handleSearchEntity() {
  updateChart();
}

function resetGraphZoom() {
  if (chartInstance) {
    chartInstance.dispatchAction({
      type: 'restore'
    });
  }
}

function exportGraphImage() {
  if (!chartInstance) return;
  const url = chartInstance.getDataURL({
    type: 'png',
    pixelRatio: 2,
    backgroundColor: '#ffffff'
  });
  const a = document.createElement('a');
  a.download = `pubminer-knowledge-graph-${Date.now()}.png`;
  a.href = url;
  a.click();
  ElMessage.success('知识图谱 PNG 高清图像导出成功');
}

watch([visibleCategories, minWeight], () => {
  updateChart();
}, { deep: true });

watch(() => props.nodes, () => {
  if (props.nodes.length) {
    selectedNode.value = props.nodes[0];
  }
  updateChart();
}, { deep: true });

onMounted(() => {
  if (props.nodes.length) {
    selectedNode.value = props.nodes[0];
  }
  initChart();
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize);
  if (chartInstance) {
    chartInstance.dispose();
  }
});
</script>
