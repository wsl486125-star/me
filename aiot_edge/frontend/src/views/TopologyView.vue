<template>
  <div class="topology-page">
    <!-- 汇总卡片 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :xs="12" :sm="12" :md="6" v-for="card in summaryCards" :key="card.label">
        <StatCard v-bind="card" />
      </el-col>
    </el-row>

    <!-- 网络拓扑 -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="card-title"><el-icon><Share /></el-icon>网络拓扑 · 设备感知关系</span>
          <span class="topo-legend">
            <span class="legend-item"><span class="dot" style="background:#22c55e"></span>在线</span>
            <span class="legend-item"><span class="dot" style="background:#ef4444"></span>离线</span>
          </span>
        </div>
      </template>
      <v-chart v-if="deviceList.length" :option="topologyOption" style="height:400px" autoresize />
      <el-empty v-else description="暂无设备，无法生成拓扑" />
    </el-card>

    <!-- 分布图表 -->
    <el-row :gutter="16">
      <el-col :xs="24" :md="12">
        <el-card>
          <template #header>
            <span class="card-title"><el-icon><PieChart /></el-icon>设备类型分布</span>
          </template>
          <v-chart v-if="deviceList.length" :option="typePieOption" style="height:280px" autoresize />
          <el-empty v-else description="暂无数据" />
        </el-card>
      </el-col>
      <el-col :xs="24" :md="12">
        <el-card>
          <template #header>
            <span class="card-title"><el-icon><Histogram /></el-icon>部署位置分布</span>
          </template>
          <v-chart v-if="deviceList.length" :option="locationBarOption" style="height:280px" autoresize />
          <el-empty v-else description="暂无数据" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 实时监控 -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="card-title"><el-icon><Monitor /></el-icon>实时运行监控</span>
          <span class="cell-sub">每 5 秒自动刷新</span>
        </div>
      </template>
      <el-table :data="realtimeDevices" stripe>
        <el-table-column prop="device_code" label="设备编号" width="110" />
        <el-table-column prop="name" label="设备名称" width="140" />
        <el-table-column prop="device_type" label="类型" width="90" />
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <span class="status-dot" :class="deviceStatus(row.status).cls"></span>
            <span :style="{ color: deviceStatus(row.status).color }">{{ deviceStatus(row.status).text }}</span>
          </template>
        </el-table-column>
        <el-table-column label="CPU" min-width="160">
          <template #default="{ row }">
            <el-progress :percentage="row.cpu_usage ?? 0" :color="cpuColor(row.cpu_usage)" :stroke-width="14">
              <span>{{ row.cpu_usage?.toFixed(1) ?? '-' }}%</span>
            </el-progress>
          </template>
        </el-table-column>
        <el-table-column label="内存" width="90">
          <template #default="{ row }">{{ row.memory_usage?.toFixed(1) ?? '-' }}%</template>
        </el-table-column>
        <el-table-column label="延迟" width="90">
          <template #default="{ row }">{{ row.network_latency?.toFixed(1) ?? '-' }}ms</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { GraphChart, PieChart as PieChartGraph, BarChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import request from '../api/request'
import { deviceStatus } from '../utils/status'
import StatCard from '../components/StatCard.vue'

use([GraphChart, PieChartGraph, BarChart, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])

const dashboard = ref({})
const deviceList = ref([])
const realtimeDevices = ref([])

const summaryCards = computed(() => [
  { label: '感知设备总数', value: dashboard.value.total_devices ?? 0, color: 'var(--primary)', icon: 'Monitor' },
  { label: '在线设备', value: dashboard.value.online_devices ?? 0, color: 'var(--success)', icon: 'CircleCheck' },
  { label: '离线设备', value: dashboard.value.offline_devices ?? 0, color: 'var(--danger)', icon: 'WarningFilled' },
  { label: '当前告警', value: dashboard.value.firing_alerts_count ?? 0, color: 'var(--warning)', icon: 'Bell' },
])

// 核心节点类型（拓扑中心），尺寸更大
const CORE_SIZE = { 网关: 60, 交换机: 55, 路由器: 50 }
const LEAF_SIZE = { 传感器: 40, 未知: 36 }

function sizeByType(type) {
  if (CORE_SIZE[type]) return CORE_SIZE[type]
  return LEAF_SIZE[type] || 38
}

function pickCore(devices) {
  return (
    devices.find((d) => d.device_type === '网关') ||
    devices.find((d) => d.device_type === '交换机') ||
    devices.find((d) => d.device_type === '路由器') ||
    devices[0]
  )
}

const topologyOption = computed(() => {
  const devices = deviceList.value
  if (!devices.length) return {}

  const core = pickCore(devices)

  const nodes = devices.map((d) => ({
    id: d.id,
    name: d.name,
    device_type: d.device_type,
    status: d.status,
    symbolSize: sizeByType(d.device_type),
    itemStyle: { color: d.status === 'online' ? '#22c55e' : '#ef4444' },
  }))

  const links = devices
    .filter((d) => d.id !== core.id)
    .map((d) => ({ source: core.id, target: d.id }))

  return {
    tooltip: {
      formatter: (p) => {
        if (p.dataType === 'edge') return '协同链路'
        const d = p.data
        return `${d.name}<br/>类型：${d.device_type || '未知'}<br/>状态：${d.status === 'online' ? '在线' : '离线'}`
      },
    },
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        data: nodes,
        links,
        force: { repulsion: 260, edgeLength: [80, 150] },
        label: { show: true, position: 'bottom', color: '#94a3b8', fontSize: 12 },
        lineStyle: { color: 'rgba(56,189,248,0.35)', width: 1.5, curveness: 0.08 },
        emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
      },
    ],
  }
})

const typePieOption = computed(() => {
  const counts = {}
  deviceList.value.forEach((d) => {
    const t = d.device_type || '未知'
    counts[t] = (counts[t] || 0) + 1
  })
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { color: '#94a3b8' } },
    series: [
      {
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['50%', '45%'],
        itemStyle: { borderColor: '#0f172a', borderWidth: 2 },
        label: { color: '#94a3b8' },
        data: Object.entries(counts).map(([name, value]) => ({ name, value })),
      },
    ],
  }
})

const locationBarOption = computed(() => {
  const counts = {}
  deviceList.value.forEach((d) => {
    const l = d.location || '未标注'
    counts[l] = (counts[l] || 0) + 1
  })
  const entries = Object.entries(counts)
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '8%', containLabel: true },
    xAxis: {
      type: 'category',
      data: entries.map((e) => e[0]),
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
      axisLabel: { color: '#64748b', interval: 0 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
      axisLabel: { color: '#64748b' },
    },
    series: [
      {
        type: 'bar',
        data: entries.map((e) => e[1]),
        barWidth: 26,
        itemStyle: { color: '#38bdf8', borderRadius: [4, 4, 0, 0] },
      },
    ],
  }
})

function cpuColor(val) {
  if (val == null) return '#64748b'
  if (val > 85) return '#ef4444'
  if (val > 60) return '#eab308'
  return '#22c55e'
}

async function loadSummary() {
  try {
    const res = await request.get('/stats/dashboard')
    dashboard.value = res.data
  } catch (e) { /* pass */ }
}

async function loadDevices() {
  try {
    const res = await request.get('/devices')
    deviceList.value = res.data
  } catch (e) { /* pass */ }
}

async function loadRealtime() {
  try {
    const res = await request.get('/stats/devices/overview')
    realtimeDevices.value = res.data
  } catch (e) { /* pass */ }
}

let timer = null
onMounted(() => {
  loadSummary()
  loadDevices()
  loadRealtime()
  timer = setInterval(() => {
    loadSummary()
    loadRealtime()
  }, 5000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.topology-page {
  display: flex;
  flex-direction: column;
  gap: var(--sp-24);
}

.stats-row {
  margin: 0;
}

.topo-legend {
  display: flex;
  gap: var(--sp-16);
  font-size: 12px;
  color: var(--text-2);
}

.legend-item {
  display: inline-flex;
  align-items: center;
}
</style>
