<template>
  <div class="alerts-page">
    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :xs="12" :sm="12" :md="6" v-for="card in alertStatCards" :key="card.label">
        <StatCard v-bind="card" />
      </el-col>
    </el-row>

    <!-- 告警列表 -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="card-title">
            <el-icon><Bell /></el-icon>
            告警中心
          </span>
          <el-radio-group v-model="statusFilter" @change="handleStatusChange">
            <el-radio-button value="all">全部</el-radio-button>
            <el-radio-button value="open">未闭环</el-radio-button>
            <el-radio-button value="firing">待处理</el-radio-button>
            <el-radio-button value="processing">处理中</el-radio-button>
            <el-radio-button value="resolved">已解决</el-radio-button>
          </el-radio-group>
        </div>
      </template>

      <el-skeleton v-if="loading" :rows="6" animated style="padding: 8px 24px" />
      <el-table
        v-else
        :data="alerts"
        stripe
        :row-class-name="alertRowClass"
      >
        <el-table-column label="设备" width="150">
          <template #default="{ row }">
            <div>{{ row.device_name }}</div>
            <div class="cell-sub">{{ row.device_code }}</div>
          </template>
        </el-table-column>
        <el-table-column label="告警类型" width="130">
          <template #default="{ row }">{{ alertTypeLabel(row.alert_type) }}</template>
        </el-table-column>
        <el-table-column label="严重程度" width="90">
          <template #default="{ row }">
            <span class="dot" :style="{ background: severityColor(row.severity) }"></span>
            <span :style="{ color: severityColor(row.severity) }">{{ severityLabel(row.severity) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <span
              class="status-tag"
              :style="{ background: alertStatusColor(row.status) }"
            >
              {{ alertStatusLabel(row.status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="告警说明" min-width="180" show-overflow-tooltip />
        <el-table-column label="处置时长" width="110">
          <template #default="{ row }">
            <span v-if="row.handle_duration != null" class="duration">{{ formatDuration(row.handle_duration) }}</span>
            <span v-else class="cell-sub">—</span>
          </template>
        </el-table-column>
        <el-table-column label="处置人" width="90">
          <template #default="{ row }">{{ row.handler || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <!-- 闭环流转按钮，按当前状态展示下一步动作 -->
            <template v-if="row.status === 'firing'">
              <el-button size="small" type="primary" plain @click="openTransition(row, 'confirmed')">确认</el-button>
              <el-button size="small" type="info" plain @click="openTransition(row, 'false_alarm')">误报</el-button>
            </template>
            <template v-else-if="row.status === 'confirmed'">
              <el-button size="small" type="primary" plain @click="openTransition(row, 'processing')">开始处理</el-button>
              <el-button size="small" type="info" plain @click="openTransition(row, 'false_alarm')">误报</el-button>
            </template>
            <template v-else-if="row.status === 'processing'">
              <el-button size="small" type="success" plain @click="openTransition(row, 'resolved')">标记解决</el-button>
              <el-button size="small" type="info" plain @click="openTransition(row, 'false_alarm')">误报</el-button>
            </template>
            <template v-else>
              <span class="cell-sub">{{ alertStatusLabel(row.status) }}</span>
            </template>
            <el-button size="small" link type="primary" @click="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <el-pagination
        v-model:current-page="page"
        :page-size="perPage"
        :total="total"
        layout="prev, pager, next, total"
        @current-change="loadAlerts"
        class="pagination"
      />
    </el-card>

    <!-- 处置对话框 -->
    <el-dialog v-model="transitionDialog.visible" title="告警处置" width="420px">
      <el-form label-position="top">
        <el-form-item label="处置动作">
          <span
            class="status-tag"
            :style="{ background: alertStatusColor(transitionDialog.target) }"
          >
            {{ alertStatusLabel(transitionDialog.target) }}
          </span>
        </el-form-item>
        <el-form-item label="处置人">
          <el-input v-model="transitionDialog.handler" placeholder="请输入处置人姓名" />
        </el-form-item>
        <el-form-item label="处置备注">
          <el-input
            v-model="transitionDialog.note"
            type="textarea"
            :rows="3"
            placeholder="记录处置情况（可选）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="transitionDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="confirmTransition">确认</el-button>
      </template>
    </el-dialog>

    <!-- 告警详情抽屉（证据快照 + AI 复核 + 处置时间线） -->
    <el-drawer v-model="detailDrawer.visible" title="告警详情与处置闭环" size="480px">
      <div v-if="detailDrawer.alert" class="alert-detail">
        <!-- 基本信息 -->
        <div class="detail-section">
          <h4 class="section-title">基本信息</h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="设备">{{ detailDrawer.alert.device_name }}（{{ detailDrawer.alert.device_code }}）</el-descriptions-item>
            <el-descriptions-item label="告警类型">{{ alertTypeLabel(detailDrawer.alert.alert_type) }}</el-descriptions-item>
            <el-descriptions-item label="严重程度">
              <span :style="{ color: severityColor(detailDrawer.alert.severity) }">{{ severityLabel(detailDrawer.alert.severity) }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="告警说明">{{ detailDrawer.alert.message }}</el-descriptions-item>
            <el-descriptions-item label="触发时间">{{ new Date(detailDrawer.alert.triggered_at).toLocaleString('zh-CN') }}</el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 证据快照（软件模拟"现场取证"） -->
        <div class="detail-section">
          <h4 class="section-title">
            <el-icon><Document /></el-icon>
            现场证据快照
          </h4>
          <div v-if="detailDrawer.alert.evidence" class="evidence-box">
            <div class="evidence-grid">
              <div class="evidence-item">
                <span class="evidence-label">CPU</span>
                <span class="evidence-value" :class="evidenceClass('cpu_usage')">
                  {{ fmtVal(detailDrawer.alert.evidence.cpu_usage) }}%
                </span>
              </div>
              <div class="evidence-item">
                <span class="evidence-label">内存</span>
                <span class="evidence-value">{{ fmtVal(detailDrawer.alert.evidence.memory_usage) }}%</span>
              </div>
              <div class="evidence-item">
                <span class="evidence-label">延迟</span>
                <span class="evidence-value">{{ fmtVal(detailDrawer.alert.evidence.network_latency) }}ms</span>
              </div>
              <div class="evidence-item">
                <span class="evidence-label">带宽</span>
                <span class="evidence-value">{{ fmtVal(detailDrawer.alert.evidence.bandwidth_usage) }}Mbps</span>
              </div>
              <div class="evidence-item">
                <span class="evidence-label">磁盘</span>
                <span class="evidence-value">{{ fmtVal(detailDrawer.alert.evidence.disk_usage) }}%</span>
              </div>
            </div>
            <div class="evidence-meta">
              <div><span class="meta-label">检测依据：</span>{{ detailDrawer.alert.evidence.detected_by }}</div>
              <div v-if="detailDrawer.alert.evidence.threshold != null">
                <span class="meta-label">阈值：</span>{{ detailDrawer.alert.evidence.threshold }}
              </div>
              <div v-if="detailDrawer.alert.evidence.metric_value != null">
                <span class="meta-label">触发值：</span>{{ detailDrawer.alert.evidence.metric_value }}
              </div>
            </div>
          </div>
          <el-empty v-else description="暂无证据快照（历史告警未采集）" :image-size="60" />
        </div>

        <!-- AI 语义复核 -->
        <div class="detail-section">
          <h4 class="section-title">
            <el-icon><MagicStick /></el-icon>
            AI 语义复核
          </h4>
          <div v-if="detailDrawer.alert.ai_review" class="ai-review-box">
            <div class="ai-review-text">{{ detailDrawer.alert.ai_review }}</div>
          </div>
          <el-empty v-else description="AI 复核进行中或暂无解读" :image-size="60" />
        </div>

        <!-- 处置时间线 -->
        <div class="detail-section">
          <h4 class="section-title">
            <el-icon><Clock /></el-icon>
            处置时间线
          </h4>
          <el-timeline>
            <el-timeline-item :timestamp="new Date(detailDrawer.alert.triggered_at).toLocaleString('zh-CN')" type="danger">
              告警触发
            </el-timeline-item>
            <el-timeline-item v-if="detailDrawer.alert.confirmed_at" :timestamp="new Date(detailDrawer.alert.confirmed_at).toLocaleString('zh-CN')" type="warning">
              已确认
            </el-timeline-item>
            <el-timeline-item v-if="detailDrawer.alert.processing_at" :timestamp="new Date(detailDrawer.alert.processing_at).toLocaleString('zh-CN')" type="primary">
              开始处理
            </el-timeline-item>
            <el-timeline-item v-if="detailDrawer.alert.resolved_at" :timestamp="new Date(detailDrawer.alert.resolved_at).toLocaleString('zh-CN')" :type="detailDrawer.alert.status === 'false_alarm' ? 'info' : 'success'">
              {{ detailDrawer.alert.status === 'false_alarm' ? '判定为误报' : '已解决（闭环）' }}
            </el-timeline-item>
          </el-timeline>
          <div v-if="detailDrawer.alert.handle_duration != null" class="duration-summary">
            闭环总耗时：<b>{{ formatDuration(detailDrawer.alert.handle_duration) }}</b>
          </div>
          <div v-if="detailDrawer.alert.handler" class="handle-meta">
            <span>处置人：{{ detailDrawer.alert.handler }}</span>
            <span v-if="detailDrawer.alert.handle_note">备注：{{ detailDrawer.alert.handle_note }}</span>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import request from '../api/request'
import StatCard from '../components/StatCard.vue'
import {
  alertTypeLabel,
  severityLabel,
  severityColor,
  alertStatusLabel,
  alertStatusColor,
} from '../utils/alerts'

const statusFilter = ref('all')
const alerts = ref([])
const loading = ref(false)
const page = ref(1)
const perPage = 20
const total = ref(0)

const alertStats = ref({})

const alertStatCards = computed(() => [
  { label: '待处理', value: alertStats.value.firing ?? 0, color: 'var(--danger)', icon: 'WarningFilled' },
  { label: '处理中', value: (alertStats.value.confirmed ?? 0) + (alertStats.value.processing ?? 0), color: 'var(--primary)', icon: 'Warning' },
  { label: '已解决', value: alertStats.value.resolved ?? 0, color: 'var(--success)', icon: 'CircleCheck' },
  { label: '误报', value: alertStats.value.false_alarm ?? 0, color: 'var(--text-3)', icon: 'Bell' },
])

// ━━━ 处置对话框 ━━━
const transitionDialog = reactive({
  visible: false,
  alertId: null,
  target: '',
  handler: '',
  note: '',
})

function openTransition(row, target) {
  transitionDialog.alertId = row.id
  transitionDialog.target = target
  transitionDialog.handler = row.handler || ''
  transitionDialog.note = ''
  transitionDialog.visible = true
}

async function confirmTransition() {
  try {
    await request.put(`/alerts/${transitionDialog.alertId}/transition`, {
      status: transitionDialog.target,
      handler: transitionDialog.handler,
      note: transitionDialog.note,
    })
    ElMessage.success('处置成功')
    transitionDialog.visible = false
    loadAlerts()
    loadStats()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

// ━━━ 详情抽屉 ━━━
const detailDrawer = reactive({
  visible: false,
  alert: null,
})

function openDetail(row) {
  detailDrawer.alert = row
  detailDrawer.visible = true
}

function fmtVal(v) {
  if (v == null) return '—'
  const n = Number(v)
  return Number.isInteger(n) ? n : n.toFixed(1)
}

function evidenceClass(key) {
  // CPU 高亮异常色
  const a = detailDrawer.alert
  if (a && a.evidence && key === 'cpu_usage' && a.evidence.cpu_usage != null && a.evidence.cpu_usage > 85) {
    return 'evidence-danger'
  }
  return ''
}

function formatDuration(secs) {
  if (secs == null) return '—'
  if (secs < 60) return `${secs}秒`
  if (secs < 3600) return `${Math.floor(secs / 60)}分${secs % 60}秒`
  return `${Math.floor(secs / 3600)}时${Math.floor((secs % 3600) / 60)}分`
}

function handleStatusChange() {
  page.value = 1
  loadAlerts()
}

async function loadAlerts() {
  loading.value = true
  try {
    const res = await request.get('/alerts', {
      params: {
        status: statusFilter.value,
        page: page.value,
        per_page: perPage,
      },
    })
    alerts.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    ElMessage.error('加载告警列表失败')
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    const res = await request.get('/alerts/stats')
    alertStats.value = res.data
  } catch (e) { /* pass */ }
}

// ━━━ 工具函数 ━━━
function alertRowClass({ row }) {
  if (row.status === 'firing') return 'alert-firing-row'
  return ''
}

onMounted(() => {
  loadAlerts()
  loadStats()
})
</script>

<style scoped>
.alerts-page {
  display: flex;
  flex-direction: column;
  gap: var(--sp-24);
}

.stats-row {
  margin: 0;
}

.pagination {
  margin-top: var(--sp-16);
  justify-content: center;
}
.status-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 20px;
  color: #fff;
  white-space: nowrap;
}
.alerts-page :deep(.alert-firing-row) {
  background-color: rgba(239, 68, 68, 0.06) !important;
}

/* ━━━ 详情抽屉 ━━━ */
.alert-detail {
  display: flex;
  flex-direction: column;
  gap: var(--sp-24);
}
.detail-section {
  display: flex;
  flex-direction: column;
  gap: var(--sp-16);
}
.section-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-1);
  display: flex;
  align-items: center;
  gap: var(--sp-8);
}

/* 证据快照 */
.evidence-box {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-btn);
  padding: var(--sp-16);
  display: flex;
  flex-direction: column;
  gap: var(--sp-16);
}
.evidence-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--sp-8);
}
.evidence-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: var(--sp-8);
  background: rgba(255, 255, 255, 0.03);
  border-radius: 6px;
}
.evidence-label {
  font-size: 12px;
  color: var(--text-3);
}
.evidence-value {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-1);
  font-variant-numeric: tabular-nums;
}
.evidence-value.evidence-danger {
  color: var(--danger);
}
.evidence-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--text-2);
}
.meta-label {
  color: var(--text-3);
}

/* AI 复核 */
.ai-review-box {
  background: linear-gradient(135deg, rgba(56, 189, 248, 0.08), rgba(56, 189, 248, 0.02));
  border: 1px solid rgba(56, 189, 248, 0.2);
  border-radius: var(--radius-btn);
  padding: var(--sp-16);
}
.ai-review-text {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-1);
}

.duration-summary {
  margin-top: var(--sp-8);
  font-size: 13px;
  color: var(--text-2);
}
.duration-summary b {
  color: var(--primary);
  font-size: 15px;
}
.handle-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--text-3);
}
</style>
