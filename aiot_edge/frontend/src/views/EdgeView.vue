<template>
  <div class="edge-page">
    <!-- 汇总卡片 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :xs="12" :sm="12" :md="6" v-for="card in summaryCards" :key="card.label">
        <StatCard v-bind="card" />
      </el-col>
    </el-row>

    <!-- 三层检测体系 -->
    <el-card>
      <template #header>
        <span class="card-title"><el-icon><Cpu /></el-icon>边缘计算 · 三层检测体系</span>
      </template>
      <el-row :gutter="16">
        <el-col :xs="12" :md="6" v-for="layer in layers" :key="layer.key">
          <div class="layer-card" :style="{ borderColor: layerColor(layer.key) }">
            <div class="layer-count" :style="{ color: layerColor(layer.key) }">
              <span v-count-up="layer.count"></span>
            </div>
            <div class="layer-label">{{ layer.label }}</div>
            <div class="layer-desc">{{ layer.desc }}</div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 孤立森林模型状态 -->
    <el-card>
      <template #header>
        <span class="card-title"><el-icon><MagicStick /></el-icon>孤立森林模型状态</span>
      </template>
      <el-table :data="models" stripe>
        <el-table-column prop="device_code" label="设备编号" width="120" />
        <el-table-column prop="device_name" label="设备名称" width="140" />
        <el-table-column label="在线状态" width="100">
          <template #default="{ row }">
            <span class="status-dot" :class="deviceStatus(row.status).cls"></span>
            <span :style="{ color: deviceStatus(row.status).color }">{{ deviceStatus(row.status).text }}</span>
          </template>
        </el-table-column>
        <el-table-column label="模型状态" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.trained" type="success" size="small" effect="dark">已训练</el-tag>
            <el-tag v-else type="info" size="small" effect="dark">数据不足</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="训练样本数" width="110">
          <template #default="{ row }">{{ row.trained ? row.n_samples : '-' }}</template>
        </el-table-column>
        <el-table-column label="最近训练时间" width="180">
          <template #default="{ row }">{{ row.trained_at ? new Date(row.trained_at).toLocaleString('zh-CN') : '-' }}</template>
        </el-table-column>
        <el-table-column label="缓存年龄" width="110">
          <template #default="{ row }">{{ row.age_seconds != null ? formatAge(row.age_seconds) : '-' }}</template>
        </el-table-column>
        <el-table-column label="是否过期" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.trained && row.expired" type="warning" size="small" effect="dark">已过期</el-tag>
            <span v-else-if="row.trained" class="cell-sub">未过期</span>
            <span v-else class="cell-sub">-</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="hint">模型缓存 1 小时自动过期并随新数据重训，样本数不足 50 时由前两层规则兜底检测。</div>
    </el-card>

    <!-- 实时检测流水 -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="card-title"><el-icon><DataLine /></el-icon>实时检测流水</span>
          <el-button size="small" @click="loadAll">刷新</el-button>
        </div>
      </template>
      <el-table :data="recentAlerts" stripe>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ new Date(row.triggered_at).toLocaleString('zh-CN') }}</template>
        </el-table-column>
        <el-table-column label="设备" width="150">
          <template #default="{ row }">
            <div>{{ row.device_name }}</div>
            <div class="cell-sub">{{ row.device_code }}</div>
          </template>
        </el-table-column>
        <el-table-column label="检测层" width="160">
          <template #default="{ row }">
            <span class="layer-tag" :style="{ color: layerColor(layerOfType(row.alert_type)), borderColor: layerColor(layerOfType(row.alert_type)) }">
              {{ layerLabelOfType(row.alert_type) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="检测说明" min-width="260" show-overflow-tooltip />
        <el-table-column label="严重程度" width="100">
          <template #default="{ row }">
            <span :style="{ color: severityColor(row.severity) }">{{ severityLabel(row.severity) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import request from '../api/request'
import { deviceStatus } from '../utils/status'
import { severityLabel, severityColor } from '../utils/alerts'
import StatCard from '../components/StatCard.vue'

const status = ref({ summary: {}, layers: [], models: [] })
const recentAlerts = ref([])

const summaryCards = computed(() => [
  { label: '累计检测告警', value: status.value.summary?.total_alerts ?? 0, color: 'var(--primary)', icon: 'DataLine' },
  { label: '当前激活告警', value: status.value.summary?.firing_alerts ?? 0, color: 'var(--warning)', icon: 'Warning' },
  { label: '已训练模型', value: status.value.summary?.trained_models ?? 0, color: 'var(--success)', icon: 'MagicStick' },
  { label: '感知设备总数', value: status.value.summary?.total_devices ?? 0, color: 'var(--text-1)', icon: 'Monitor' },
])

const layers = computed(() => status.value.layers || [])
const models = computed(() => status.value.models || [])

const LAYER_COLORS = {
  threshold: 'var(--primary)',
  sliding_window: 'var(--warning)',
  isolation_forest: 'var(--orange)',
  offline: 'var(--danger)',
}

const LAYER_LABELS = {
  threshold: '第一层 · 阈值规则',
  sliding_window: '第二层 · 滑动窗口',
  isolation_forest: '第三层 · 孤立森林',
  offline: '离线检测',
}

const TYPE_TO_LAYER = {
  cpu_high: 'threshold',
  latency_high: 'threshold',
  memory_high: 'threshold',
  cpu_spike: 'sliding_window',
  ml_anomaly: 'isolation_forest',
  offline: 'offline',
}

function layerColor(key) {
  return LAYER_COLORS[key] || 'var(--primary)'
}

function layerOfType(type) {
  return TYPE_TO_LAYER[type] || 'threshold'
}

function layerLabelOfType(type) {
  return LAYER_LABELS[layerOfType(type)]
}

function formatAge(seconds) {
  if (seconds < 60) return `${Math.round(seconds)}秒`
  if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`
  return `${(seconds / 3600).toFixed(1)}小时`
}

async function loadStatus() {
  try {
    const res = await request.get('/edge/status')
    status.value = res.data
  } catch (e) { /* pass */ }
}

async function loadRecent() {
  try {
    const res = await request.get('/alerts', { params: { status: 'all', page: 1, per_page: 15 } })
    recentAlerts.value = res.data.items
  } catch (e) { /* pass */ }
}

function loadAll() {
  loadStatus()
  loadRecent()
}

let timer = null
onMounted(() => {
  loadAll()
  timer = setInterval(loadStatus, 10000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.edge-page {
  display: flex;
  flex-direction: column;
  gap: var(--sp-24);
}

.stats-row {
  margin: 0;
}

.layer-card {
  border: 1px solid;
  border-radius: var(--radius-card);
  padding: var(--sp-24);
  text-align: center;
  background: var(--bg-surface);
  height: 100%;
}

.layer-count {
  font-size: 34px;
  font-weight: 700;
}

.layer-label {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-1);
  margin-top: var(--sp-8);
}

.layer-desc {
  font-size: 12px;
  color: var(--text-3);
  line-height: 1.6;
  margin-top: var(--sp-16);
  text-align: left;
}

.layer-tag {
  padding: 2px 10px;
  border: 1px solid;
  border-radius: var(--radius-btn);
  font-size: 12px;
}

.hint {
  margin-top: var(--sp-16);
  font-size: 12px;
  color: var(--text-3);
}
</style>
