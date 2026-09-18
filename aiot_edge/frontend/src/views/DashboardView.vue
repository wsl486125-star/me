<template>
  <div class="dashboard">
    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :xs="12" :sm="12" :md="6" v-for="card in statCards" :key="card.label">
        <StatCard v-bind="card" :loading="statsLoading" />
      </el-col>
    </el-row>

    <!-- 服务器健康分布：三个独立卡片，每个一个自绘 SVG 仪表盘 -->
    <el-row :gutter="16" class="gauge-row">
      <el-col :xs="24" :sm="8" v-for="g in gauges" :key="g.key">
        <el-card class="gauge-card">
          <GaugeDial
            :value="g.value"
            :title="g.label"
            :icon="g.icon"
            :color="g.color"
          />
        </el-card>
      </el-col>
    </el-row>

    <!-- 趋势图区域 -->
    <el-card class="chart-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">
            <el-icon><TrendCharts /></el-icon>
            设备运行趋势
          </span>
          <el-select v-model="selectedDeviceId" placeholder="选择设备" @change="loadTrend" style="width:200px">
            <el-option v-for="d in devices" :key="d.id" :label="`${d.device_code} ${d.name}`" :value="d.id" />
          </el-select>
        </div>
      </template>
      <v-chart v-if="trendData.xAxis.length" :option="chartOption" style="height:350px" autoresize />
      <el-empty v-else description="暂无趋势数据，请确认采集器正在运行" />
    </el-card>

    <!-- 设备状态表格 -->
    <el-card class="table-card">
      <template #header>
        <span class="card-title">
          <el-icon><Monitor /></el-icon>
          设备状态总览
        </span>
      </template>
      <el-skeleton v-if="tableLoading" :rows="6" animated style="padding: 8px 24px" />
      <el-table v-else :data="deviceTable" stripe size="default">
        <el-table-column prop="device_code" label="设备编号" width="100" />
        <el-table-column prop="name" label="设备名称" width="120" />
        <el-table-column prop="device_type" label="类型" width="80" />
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <span class="status-dot" :class="deviceStatus(row.status).cls"></span>
            <span :style="{ color: deviceStatus(row.status).color }">{{ deviceStatus(row.status).text }}</span>
          </template>
        </el-table-column>
        <el-table-column label="CPU" min-width="160">
          <template #default="{ row }">
            <el-progress :percentage="row.cpu_usage ?? 0" :color="cpuColor(row.cpu_usage)" :stroke-width="16">
              <span>{{ row.cpu_usage?.toFixed(1) ?? '-' }}%</span>
            </el-progress>
          </template>
        </el-table-column>
        <el-table-column label="内存" width="100">
          <template #default="{ row }">{{ row.memory_usage?.toFixed(1) ?? '-' }}%</template>
        </el-table-column>
        <el-table-column label="延迟" width="100">
          <template #default="{ row }">
            <span :style="{ color: (row.network_latency ?? 0) > 200 ? 'var(--danger)' : '' }">
              {{ row.network_latency?.toFixed(1) ?? '-' }}ms
            </span>
          </template>
        </el-table-column>
        <el-table-column label="最近上报" width="170">
          <template #default="{ row }">
            {{ row.last_seen_at ? formatTime(row.last_seen_at) : '从未上报' }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import request from '../api/request'
import { deviceStatus } from '../utils/status'
import StatCard from '../components/StatCard.vue'
import GaugeDial from '../components/GaugeDial.vue'

use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

// ━━━ 图表配色（CPU / 内存 / 磁盘） ━━━
const CHART_COLORS = ['#38bdf8', '#22c55e', '#f97316']

// ━━━ 统计数据 ━━━
const dashboard = ref({})
const statsLoading = ref(true)

const statCards = computed(() => [
  { label: '在线设备', value: dashboard.value.online_devices ?? 0, color: 'var(--success)', icon: 'Monitor' },
  { label: '离线设备', value: dashboard.value.offline_devices ?? 0, color: 'var(--danger)', icon: 'WarningFilled' },
  { label: '当前告警', value: dashboard.value.firing_alerts_count ?? 0, color: 'var(--warning)', icon: 'Bell' },
  { label: '平均CPU', value: dashboard.value.avg_cpu ?? 0, suffix: '%', decimals: 1, color: 'var(--primary)', icon: 'Odometer' },
])

// ━━━ 服务器健康分布：三个自绘 SVG 仪表盘（全设备平均值） ━━━
function healthColor(v) {
  if (v >= 85) return '#ef4444'   // 红 · 危险
  if (v >= 70) return '#eab308'   // 黄 · 预警
  return '#22c55e'                 // 绿 · 正常
}

const gauges = computed(() => {
  const defs = [
    { key: 'cpu', label: 'CPU 使用率', icon: 'Cpu', value: dashboard.value.avg_cpu ?? 0 },
    { key: 'memory', label: '内存使用率', icon: 'DataBoard', value: dashboard.value.avg_memory ?? 0 },
    { key: 'disk', label: '磁盘使用率', icon: 'Coin', value: dashboard.value.avg_disk ?? 0 },
  ]
  return defs.map((d) => {
    const color = healthColor(d.value)
    return {
      key: d.key,
      label: d.label,
      icon: d.icon,
      value: d.value,
      color,
    }
  })
})

// ━━━ 趋势图 ━━━
const devices = ref([])
const selectedDeviceId = ref(null)
const trendData = ref({ xAxis: [], series: [] })

const chartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: {
    data: trendData.value.series.map((s) => s.name),
    textStyle: { color: '#94a3b8' },
  },
  grid: { left: '3%', right: '4%', bottom: '3%', top: '14%', containLabel: true },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: trendData.value.xAxis,
    axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
    axisTick: { show: false },
    axisLabel: { color: '#64748b' },
  },
  yAxis: {
    type: 'value',
    name: '占用率(%)',
    max: 100,
    splitLine: { show: false },
    axisLabel: { color: '#64748b' },
  },
  animationDuration: 400,
  animationDurationUpdate: 300,
  animationEasingUpdate: 'cubicOut',
  series: trendData.value.series.map((s, i) => {
    const color = CHART_COLORS[i % CHART_COLORS.length]
    return {
      name: s.name,
      type: 'line',
      smooth: true,
      data: s.data,
      showSymbol: false,
      lineStyle: { color, width: 2 },
      itemStyle: { color },
    }
  }),
}))

async function loadTrend() {
  if (!selectedDeviceId.value) return
  try {
    const res = await request.get('/stats/trend', {
      params: { device_id: selectedDeviceId.value, hours: 6, metric: 'all' },
    })
    trendData.value = res.data
  } catch (e) {
    // 静默
  }
}

// ━━━ 设备表格 ━━━
const deviceTable = ref([])
const tableLoading = ref(false)

async function loadDeviceOverview() {
  tableLoading.value = true
  try {
    const res = await request.get('/stats/devices/overview')
    deviceTable.value = res.data
    if (!selectedDeviceId.value && res.data.length) {
      selectedDeviceId.value = res.data[0].id
    }
  } finally {
    tableLoading.value = false
  }
}

// ━━━ 工具 ━━━
function cpuColor(val) {
  if (val == null) return '#64748b'
  if (val > 85) return '#ef4444'
  if (val > 60) return '#eab308'
  return '#22c55e'
}

function formatTime(iso) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN')
}

// ━━━ 定时轮询 ━━━
let timer = null

onMounted(async () => {
  await refreshAll()
  timer = setInterval(refreshAll, 5000)
})

onUnmounted(() => {
  clearInterval(timer)
})

async function refreshAll() {
  try {
    const [dashRes] = await Promise.all([request.get('/stats/dashboard')])
    dashboard.value = dashRes.data
  } catch (e) { /* pass */ } finally {
    statsLoading.value = false
  }
  await loadDeviceOverview()
  loadTrend()
}
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: var(--sp-24);
}

.stats-row {
  margin: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-8);
  font-size: 16px;
  font-weight: 600;
  color: var(--text-1);
}

/* ━━━ 服务器健康分布 · 自绘 SVG 仪表盘 ━━━ */
.gauge-row {
  margin: 0;
}

.gauge-card {
  border-radius: var(--radius-card);
  height: 100%;
}

.gauge-card :deep(.el-card__body) {
  padding: var(--sp-24) var(--sp-16) var(--sp-16);
}
</style>
