<template>
  <div class="device-detail">
    <!-- 返回 + 标题 -->
    <div class="detail-header">
      <el-button text @click="router.push('/devices')">
        <el-icon><Back /></el-icon>
        返回设备列表
      </el-button>
      <template v-if="device.id">
        <h2 class="detail-title">{{ device.name }}</h2>
        <span class="detail-code">{{ device.device_code }}</span>
        <span class="status-dot" :class="deviceStatus(device.status).cls"></span>
        <span :style="{ color: deviceStatus(device.status).color }">{{ deviceStatus(device.status).text }}</span>
      </template>
    </div>

    <el-alert
      v-if="pageError"
      type="error"
      :title="pageError"
      show-icon
      :closable="false"
    />

    <!-- 基本信息 -->
    <el-card>
      <template #header>
        <span class="card-title"><el-icon><InfoFilled /></el-icon>基本信息</span>
      </template>
      <div class="info-grid">
        <div class="info-item"><span class="info-label">设备类型</span><span class="info-value">{{ device.device_type || '-' }}</span></div>
        <div class="info-item"><span class="info-label">部署位置</span><span class="info-value">{{ device.location || '-' }}</span></div>
        <div class="info-item"><span class="info-label">最近上报</span><span class="info-value">{{ device.last_seen_at ? new Date(device.last_seen_at).toLocaleString('zh-CN') : '从未上报' }}</span></div>
        <div class="info-item"><span class="info-label">所属分组</span><span class="info-value">{{ groupName || '未分组' }}</span></div>
        <div class="info-item"><span class="info-label">创建时间</span><span class="info-value">{{ device.created_at ? new Date(device.created_at).toLocaleString('zh-CN') : '-' }}</span></div>
      </div>
    </el-card>

    <!-- 实时指标 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :xs="12" :sm="12" :md="6" v-for="card in realtimeCards" :key="card.label">
        <StatCard v-bind="card" :loading="historyLoading" />
      </el-col>
    </el-row>

    <!-- 24h 统计 -->
    <el-card>
      <template #header>
        <span class="card-title"><el-icon><DataAnalysis /></el-icon>近24小时统计</span>
      </template>
      <el-row :gutter="16">
        <el-col :xs="12" :sm="8" :md="4.8" v-for="card in stats24hCards" :key="card.label">
          <div class="mini-stat">
            <div class="mini-value" :style="{ color: card.color }">{{ card.value }}</div>
            <div class="mini-label">{{ card.label }}</div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 历史曲线 -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="card-title"><el-icon><TrendCharts /></el-icon>历史运行曲线</span>
          <div class="chart-controls">
            <el-radio-group v-model="selectedMetric" size="small" @change="loadHistory">
              <el-radio-button value="cpu">CPU</el-radio-button>
              <el-radio-button value="memory">内存</el-radio-button>
              <el-radio-button value="latency">延迟</el-radio-button>
              <el-radio-button value="bandwidth">带宽</el-radio-button>
            </el-radio-group>
            <el-radio-group v-model="selectedHours" size="small" @change="loadHistory">
              <el-radio-button :value="1">1小时</el-radio-button>
              <el-radio-button :value="6">6小时</el-radio-button>
              <el-radio-button :value="24">24小时</el-radio-button>
              <el-radio-button :value="168">7天</el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </template>
      <v-chart v-if="history.length" :option="chartOption" style="height:320px" autoresize />
      <el-empty v-else description="暂无历史数据" />
    </el-card>

    <!-- 告警历史 -->
    <el-card>
      <template #header>
        <span class="card-title"><el-icon><Bell /></el-icon>该设备告警历史</span>
      </template>
      <el-table :data="deviceAlerts" stripe>
        <el-table-column label="类型" width="130">
          <template #default="{ row }">{{ alertTypeLabel(row.alert_type) }}</template>
        </el-table-column>
        <el-table-column label="严重程度" width="100">
          <template #default="{ row }">
            <span class="dot" :style="{ background: severityColor(row.severity) }"></span>
            <span :style="{ color: severityColor(row.severity) }">{{ severityLabel(row.severity) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="指标值" width="90">
          <template #default="{ row }">{{ row.metric_value ?? '-' }}</template>
        </el-table-column>
        <el-table-column prop="message" label="告警说明" min-width="200" show-overflow-tooltip />
        <el-table-column label="触发时间" width="170">
          <template #default="{ row }">{{ new Date(row.triggered_at).toLocaleString('zh-CN') }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <span :style="{ color: alertStatusColor(row.status) }">
              {{ alertStatusLabel(row.status) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!deviceAlerts.length && !alertLoading" description="暂无告警记录" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import request from '../api/request'
import { deviceStatus } from '../utils/status'
import { alertTypeLabel, severityLabel, severityColor, alertStatusLabel, alertStatusColor } from '../utils/alerts'
import StatCard from '../components/StatCard.vue'

use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])

const router = useRouter()
const route = useRoute()
const deviceId = route.params.id

const device = ref({})
const history = ref([])
const historyLoading = ref(false)
const pageError = ref('')
const selectedMetric = ref('cpu')
const selectedHours = ref(6)
const deviceAlerts = ref([])
const alertLoading = ref(false)
const groupName = ref('')

// 指标字段映射
const METRICS = {
  cpu: { field: 'cpu_usage', label: 'CPU使用率(%)', unit: '%', color: 'var(--primary)' },
  memory: { field: 'memory_usage', label: '内存使用率(%)', unit: '%', color: 'var(--success)' },
  latency: { field: 'network_latency', label: '网络延迟(ms)', unit: 'ms', color: 'var(--warning)' },
  bandwidth: { field: 'bandwidth_usage', label: '带宽使用(Mbps)', unit: 'Mbps', color: '#f97316' },
}

// 最新一条指标
const latest = computed(() => (history.value.length ? history.value[history.value.length - 1] : null))

const realtimeCards = computed(() => [
  { label: '最新CPU使用率', value: latest.value?.cpu_usage ?? 0, suffix: '%', decimals: 1, color: 'var(--primary)', icon: 'Cpu' },
  { label: '最新内存使用率', value: latest.value?.memory_usage ?? 0, suffix: '%', decimals: 1, color: 'var(--success)', icon: 'DataBoard' },
  { label: '最新网络延迟', value: latest.value?.network_latency ?? 0, suffix: 'ms', decimals: 1, color: 'var(--warning)', icon: 'Timer' },
  { label: '最新带宽使用', value: latest.value?.bandwidth_usage ?? 0, suffix: 'Mbps', decimals: 1, color: 'var(--orange)', icon: 'DataLine' },
])

const stats24hCards = computed(() => {
  const s = device.value.stats_24h || {}
  return [
    { label: '数据采集量', value: s.data_count ?? 0, color: 'var(--text-1)' },
    { label: '平均CPU(%)', value: s.avg_cpu ?? '-', color: 'var(--primary)' },
    { label: '峰值CPU(%)', value: s.max_cpu ?? '-', color: 'var(--danger)' },
    { label: '平均内存(%)', value: s.avg_memory ?? '-', color: 'var(--success)' },
    { label: '平均延迟(ms)', value: s.avg_latency ?? '-', color: 'var(--warning)' },
  ]
})

const chartOption = computed(() => {
  const metric = METRICS[selectedMetric.value]
  const data = history.value.map((h) => {
    const v = h[metric.field]
    const n = Number(v)
    return Number.isFinite(n) ? Number(n.toFixed(1)) : null
  })
  const xAxis = history.value.map((h) =>
    new Date(h.collected_at).toLocaleTimeString('zh-CN', { hour12: false })
  )

  return {
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '12%', containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: xAxis,
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
      axisTick: { show: false },
      axisLabel: { color: '#64748b' },
    },
    yAxis: {
      type: 'value',
      name: metric.unit,
      nameTextStyle: { color: '#64748b' },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
      axisLabel: { color: '#64748b' },
    },
    animationDurationUpdate: 300,
    series: [
      {
        name: metric.label,
        type: 'line',
        smooth: true,
        data,
        showSymbol: false,
        lineStyle: { color: '#38bdf8', width: 2 },
        itemStyle: { color: '#38bdf8' },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(56,189,248,0.25)' },
              { offset: 1, color: 'rgba(56,189,248,0)' },
            ],
          },
        },
      },
    ],
  }
})

async function loadDevice() {
  pageError.value = ''
  try {
    const res = await request.get(`/devices/${deviceId}`)
    device.value = res.data
  } catch (error) {
    console.error('加载设备详情失败', error)
    device.value = {}
    pageError.value = '设备不存在或网络异常，无法加载设备详情'
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const res = await request.get(`/devices/${deviceId}/history`, {
      params: { hours: selectedHours.value },
    })
    history.value = res.data
  } catch (e) {
    console.error('加载设备历史失败', e)
    history.value = []
  } finally {
    historyLoading.value = false
  }
}

async function loadAlerts() {
  alertLoading.value = true
  try {
    const res = await request.get('/alerts', {
      params: { device_id: deviceId, status: 'all', page: 1, per_page: 20 },
    })
    deviceAlerts.value = res.data.items
  } catch (e) {
    console.error('加载设备告警失败', e)
    deviceAlerts.value = []
  } finally {
    alertLoading.value = false
  }
}

async function loadGroupName() {
  const gid = device.value.group_id
  if (!gid) return
  try {
    const gres = await request.get(`/groups/${gid}`)
    groupName.value = gres.data.name
  } catch (e) {
    console.error('加载设备分组失败', e)
    groupName.value = ''
  }
}

onMounted(async () => {
  await loadDevice()
  await Promise.allSettled([loadHistory(), loadAlerts(), loadGroupName()])
})
</script>

<style scoped>
.device-detail {
  display: flex;
  flex-direction: column;
  gap: var(--sp-24);
}

.detail-header {
  display: flex;
  align-items: center;
  gap: var(--sp-16);
}

.detail-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-1);
}

.detail-code {
  font-size: 13px;
  color: var(--text-3);
  padding: 2px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-btn);
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--sp-16);
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: var(--sp-8);
}

.info-label {
  font-size: 12px;
  color: var(--text-3);
}

.info-value {
  font-size: 14px;
  color: var(--text-1);
}

.stats-row {
  margin: 0;
}

.mini-stat {
  text-align: center;
  padding: var(--sp-16) 0;
  border-radius: var(--radius-btn);
  background: var(--bg-surface);
}

.mini-value {
  font-size: 22px;
  font-weight: 700;
}

.mini-label {
  font-size: 12px;
  color: var(--text-3);
  margin-top: var(--sp-8);
}

.chart-controls {
  display: flex;
  gap: var(--sp-16);
  align-items: center;
}
</style>
