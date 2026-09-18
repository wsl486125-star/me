<template>
  <div class="security-page">
    <!-- ━━━ 汇总统计卡片 ━━━ -->
    <el-row :gutter="16" class="stats-row">
      <el-col :xs="12" :sm="12" :md="6" v-for="card in summaryCards" :key="card.label">
        <StatCard v-bind="card" />
      </el-col>
    </el-row>

    <!-- ━━━ 态势图表：24h 趋势 + 场景构成 ━━━ -->
    <el-row :gutter="16">
      <el-col :xs="24" :md="14">
        <el-card class="chart-card">
          <template #header>
            <div class="card-header">
              <span class="card-title">
                <el-icon><TrendCharts /></el-icon>
                24 小时告警趋势
              </span>
              <span class="card-sub">按级别堆叠 · 今日累计 {{ stats.today_total ?? 0 }} 起</span>
            </div>
          </template>
          <v-chart v-if="hasTrend" :option="trendOption" style="height:238px" autoresize />
          <el-empty v-else description="暂无告警数据" :image-size="70" />
        </el-card>
      </el-col>
      <el-col :xs="24" :md="10">
        <el-card class="chart-card">
          <template #header>
            <div class="card-header">
              <span class="card-title">
                <el-icon><PieChart /></el-icon>
                场景事件构成
              </span>
              <span class="card-sub">按安防场景</span>
            </div>
          </template>
          <v-chart v-if="hasScenes" :option="sceneOption" style="height:238px" autoresize />
          <el-empty v-else description="今日暂无事件" :image-size="70" />
        </el-card>
      </el-col>
    </el-row>

    <!-- ━━━ 校园平面图 ━━━ -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="card-title">
            <el-icon><LocationFilled /></el-icon>
            校园安防平面图 · 分区态势
          </span>
          <span class="topo-legend">
            <span class="legend-item" v-for="lv in [1, 2, 3, 4]" :key="lv">
              <span class="dot" :style="{ background: levelInfo(lv).color }"></span>{{ levelInfo(lv).short }} {{ levelInfo(lv).label }}
            </span>
            <span class="legend-item"><span class="dot" style="background:var(--success)"></span>正常</span>
            <span class="legend-item"><span class="dash-swatch"></span>边缘协同链路</span>
          </span>
        </div>
      </template>

      <div class="map-wrap">
        <!-- 左侧：SVG 校园平面图 -->
        <svg class="campus-map" viewBox="0 0 680 430" role="img" aria-label="校园安防分区平面图">
          <!-- 校园底色与道路 -->
          <rect x="0" y="0" width="680" height="430" rx="12" fill="var(--bg-surface)" />
          <line x1="30" y1="215" x2="650" y2="215" stroke="var(--border)" stroke-width="14" stroke-linecap="round" />
          <line x1="340" y1="30" x2="340" y2="400" stroke="var(--border)" stroke-width="14" stroke-linecap="round" />
          <text x="30" y="205" fill="var(--text-3)" font-size="11">主 干 道</text>

          <!-- 三个分区块：颜色由该区最高活动级别驱动 -->
          <g v-for="z in zoneShapes" :key="z.zone">
            <rect
              :x="z.x" :y="z.y" :width="z.w" :height="z.h" rx="14"
              :fill="zoneFill(z.zone)" :stroke="zoneStroke(z.zone)" stroke-width="1.5"
            />
            <!-- 活动告警脉冲环：有活动事件的分区闪烁提示 -->
            <rect
              v-if="zoneOf(z.zone).max_active_level" class="zone-ring"
              :x="z.x - 4" :y="z.y - 4" :width="z.w + 8" :height="z.h + 8" rx="16"
              fill="none" :stroke="levelInfo(zoneOf(z.zone).max_active_level).color" stroke-width="2"
            />
            <text :x="z.x + 16" :y="z.y + 28" fill="var(--text-1)" font-size="15" font-weight="600">
              {{ z.zone }}
            </text>
            <text :x="z.x + 16" :y="z.y + 50" fill="var(--text-2)" font-size="12">
              设备 {{ zoneOf(z.zone).online_devices ?? 0 }}/{{ zoneOf(z.zone).device_count ?? 0 }} 在线
            </text>
            <text :x="z.x + 16" :y="z.y + 68" fill="var(--text-2)" font-size="12">
              今日事件 {{ zoneOf(z.zone).today_events ?? 0 }} 起
            </text>
            <!-- 活动事件级别徽章 -->
            <g v-if="zoneOf(z.zone).max_active_level">
              <rect
                :x="z.x + z.w - 96" :y="z.y + 14" width="82" height="26" rx="13"
                :fill="levelInfo(zoneOf(z.zone).max_active_level).bg"
                :stroke="levelInfo(zoneOf(z.zone).max_active_level).color" stroke-width="1"
              />
              <text
                :x="z.x + z.w - 55" :y="z.y + 31" text-anchor="middle" font-size="12" font-weight="600"
                :fill="levelInfo(zoneOf(z.zone).max_active_level).color"
              >
                {{ zoneOf(z.zone).active_events }} 起活动
              </text>
            </g>
          </g>

          <!-- 边缘协同链路：端点由真实节点坐标计算，沿图幅边缘走线，不穿越分区 -->
          <polyline
            v-for="link in collabLinks" :key="link.key"
            :points="link.points" fill="none" :stroke="collabStroke"
            stroke-width="1.5" stroke-dasharray="5 4" opacity="0.55"
          />

          <!-- 节点标记：三块之间的边缘节点在线状态 -->
          <g v-for="node in nodeMarkers" :key="node.node_code">
            <circle :cx="node.x" :cy="node.y" r="6"
                    :fill="node.status === 'online' ? 'var(--success)' : 'var(--danger)'"
                    :stroke="'var(--bg)'" stroke-width="2" />
            <text :x="node.x + 11" :y="node.y + 4" fill="var(--text-2)" font-size="11">
              {{ node.node_code }}
            </text>
          </g>
        </svg>

        <!-- 右侧：分区事件明细 -->
        <div class="zone-panel">
          <div class="zone-panel-title">分区活动事件</div>
          <el-empty v-if="!activeByZone.length" description="当前无活动事件" :image-size="60" />
          <div v-else class="zone-event-list">
            <div v-for="ev in activeByZone" :key="ev.id" class="zone-event-item" @click="openDetail(ev)">
              <span class="level-badge" :style="badgeStyle(ev.level)">{{ levelInfo(ev.level).short }}</span>
              <div class="zone-event-body">
                <div class="zone-event-title">{{ ev.type_label || eventTypeLabel(ev.event_type) }}</div>
                <div class="zone-event-sub">{{ ev.zone }} · {{ ev.device_name || ev.device_code }}</div>
              </div>
              <span class="zone-event-time">{{ shortTime(ev.occurred_at) }}</span>
            </div>
          </div>

          <!-- 边缘侧关键指标：本地闭环耗时 -->
          <div class="zone-panel-foot">
            <div class="foot-row">
              <span class="foot-label">边缘本地平均闭环</span>
              <span class="foot-value">{{ avgEdgeLatency != null ? avgEdgeLatency + ' ms' : '-' }}</span>
            </div>
            <div class="foot-row">
              <span class="foot-label">云端汇聚（网络+落库）</span>
              <span class="foot-value dim">秒级</span>
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- ━━━ 事件中心 ━━━ -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="card-title">
            <el-icon><BellFilled /></el-icon>
            安防事件中心
          </span>
          <div class="filter-bar">
            <span class="filter-hint">点击行查看证据链</span>
            <el-select v-model="filters.level" placeholder="全部级别" clearable size="small" style="width:120px" @change="reload">
              <el-option v-for="lv in [1, 2, 3, 4]" :key="lv"
                         :label="levelLabel(lv)" :value="lv" />
            </el-select>
            <el-select v-model="filters.zone" placeholder="全部分区" clearable size="small" style="width:130px" @change="reload">
              <el-option v-for="z in zoneOptions" :key="z" :label="z" :value="z" />
            </el-select>
            <el-radio-group v-model="filters.status" size="small" @change="reload">
              <el-radio-button value="all">全部</el-radio-button>
              <el-radio-button value="active">活动</el-radio-button>
              <el-radio-button value="closed">已闭环</el-radio-button>
            </el-radio-group>
            <el-button size="small" :icon="'Refresh'" @click="reload">刷新</el-button>
          </div>
        </div>
      </template>

      <el-skeleton v-if="loading && !events.length" :rows="6" animated style="padding: 8px 24px" />
      <el-table v-else :data="events" stripe :row-class-name="rowClass" @row-click="openDetail">
        <el-table-column label="级别" width="90">
          <template #default="{ row }">
            <span class="level-badge" :style="badgeStyle(row.level)">{{ levelInfo(row.level).short }}</span>
          </template>
        </el-table-column>
        <el-table-column label="事件类型" width="140">
          <template #default="{ row }">
            <div>{{ row.type_label || eventTypeLabel(row.event_type) }}</div>
            <div class="cell-sub">{{ row.scene }}</div>
          </template>
        </el-table-column>
        <el-table-column label="分区 / 设备" width="175">
          <template #default="{ row }">
            <div>{{ row.zone }}</div>
            <div class="cell-sub">{{ row.device_name || row.device_code }}</div>
          </template>
        </el-table-column>
        <el-table-column label="证据源" width="150">
          <template #default="{ row }">
            <el-tag v-for="s in row.sources" :key="s" size="small" class="src-tag"
                    :type="row.sources.length >= 2 ? 'danger' : 'info'" effect="plain">
              {{ sourceLabel(s) }}
            </el-tag>
            <span v-if="!row.sources?.length" class="cell-sub">-</span>
          </template>
        </el-table-column>
        <el-table-column label="置信度" width="85">
          <template #default="{ row }">
            {{ row.confidence != null ? (row.confidence * 100).toFixed(0) + '%' : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="边缘耗时" width="95">
          <template #default="{ row }">
            <span class="edge-latency">{{ row.local_latency_ms != null ? row.local_latency_ms + ' ms' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="事件说明" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.message }}
            <el-tag v-if="row.merge_count > 1" size="small" type="warning" effect="plain" class="src-tag">
              合并×{{ row.merge_count }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="发生时间" width="150">
          <template #default="{ row }">{{ fmtTime(row.occurred_at) }}</template>
        </el-table-column>
        <el-table-column label="处置状态" width="95">
          <template #default="{ row }">
            <el-tag :type="eventStatusInfo(row.status).type" size="small" effect="plain">
              {{ eventStatusInfo(row.status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="185" fixed="right">
          <template #default="{ row }">
            <el-button
              v-for="t in allowedTransitions(row.status).slice(0, 2)"
              :key="t" size="small" plain class="op-btn"
              :type="t === 'false_alarm' ? 'info' : 'primary'"
              @click.stop="handleTransition(row, t)"
            >
              {{ transitionText(t) }}
            </el-button>
            <span v-if="!allowedTransitions(row.status).length" class="cell-sub">已终结</span>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page"
        :page-size="perPage"
        :total="total"
        layout="prev, pager, next, total"
        @current-change="loadEvents"
        class="pagination"
      />
    </el-card>

    <!-- ━━━ 事件详情抽屉：多源融合证据链可视化 ━━━ -->
    <el-drawer v-model="detailVisible" :with-header="false" size="470px" append-to-body>
      <div v-if="detailEvent" class="detail-wrap">
        <div class="detail-head">
          <div class="detail-head-main">
            <span class="level-badge" :style="badgeStyle(detailEvent.level)">{{ levelInfo(detailEvent.level).short }}</span>
            <span class="detail-title">{{ detailEvent.type_label || eventTypeLabel(detailEvent.event_type) }}</span>
          </div>
          <el-button text :icon="'Close'" @click="detailVisible = false" />
        </div>
        <div class="detail-sub">
          {{ detailEvent.scene }} · {{ detailEvent.zone }} · {{ detailEvent.device_name || detailEvent.device_code }}
        </div>

        <div class="detail-section">
          <div class="detail-section-title">多源证据链</div>
          <div class="detail-tags">
            <el-tag v-for="s in detailEvent.sources" :key="s" size="small" effect="plain"
                    :type="(detailEvent.sources?.length || 0) >= 2 ? 'danger' : 'info'">
              {{ sourceLabel(s) }}
            </el-tag>
            <span v-if="!detailEvent.sources?.length" class="cell-sub">无</span>
          </div>
          <div class="detail-note" :class="{ highlight: (detailEvent.sources?.length || 0) >= 2 }">
            {{ (detailEvent.sources?.length || 0) >= 2
              ? `${detailEvent.sources.length} 路独立证据互证 → 云端定级自动升级`
              : '单源证据，未触发融合升级' }}
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-section-title">边缘本地联动</div>
          <div class="detail-tags">
            <el-tag v-for="a in detailEvent.local_actions" :key="a" size="small" effect="plain" type="success">
              {{ actionLabel(a) }}
            </el-tag>
            <span v-if="!detailEvent.local_actions?.length" class="cell-sub">无</span>
          </div>
          <div class="detail-note">
            边缘本地闭环耗时 <b>{{ detailEvent.local_latency_ms != null ? detailEvent.local_latency_ms + ' ms' : '-' }}</b>，
            云端汇聚为秒级（网络传输 + 落库）
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-section-title">分级推送通道</div>
          <div class="detail-tags">
            <el-tag v-for="c in detailEvent.pushed_channels" :key="c" size="small" effect="plain">
              {{ channelLabel(c) }}
            </el-tag>
            <span v-if="!detailEvent.pushed_channels?.length" class="cell-sub">无</span>
          </div>
          <div class="detail-note">推送通道由告警级别决定，级别越高通道越多（避免告警风暴）</div>
        </div>

        <div class="detail-section">
          <div class="detail-section-title">处置进度</div>
          <div class="stepper">
            <template v-for="(s, i) in STATUS_STEPS" :key="s.key">
              <div class="step">
                <span class="step-dot" :class="{ done: i <= activeStep }"></span>
                <span class="step-label" :class="{ done: i <= activeStep }">{{ s.label }}</span>
              </div>
              <div v-if="i < STATUS_STEPS.length - 1" class="step-line" :class="{ done: i < activeStep }"></div>
            </template>
          </div>
          <div class="detail-note" v-if="detailEvent.status === 'false_alarm'">
            该事件已被标记为误报样本，可用于后续阈值优化
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-section-title">事件信息</div>
          <div class="kv"><span>事件 ID</span><b>{{ detailEvent.event_id }}</b></div>
          <div class="kv"><span>边缘节点</span><b>{{ detailEvent.node_name || detailEvent.node_code || '-' }}</b></div>
          <div class="kv"><span>合并次数</span><b>{{ detailEvent.merge_count ?? 1 }}</b></div>
          <div class="kv"><span>置信度</span><b>{{ detailEvent.confidence != null ? (detailEvent.confidence * 100).toFixed(0) + '%' : '-' }}</b></div>
          <div class="kv"><span>发生时间</span><b>{{ fmtTime(detailEvent.occurred_at) }}</b></div>
          <div class="kv"><span>入库时间</span><b>{{ fmtTime(detailEvent.created_at) }}</b></div>
        </div>

        <div class="detail-section">
          <div class="detail-section-title">事件说明</div>
          <div class="detail-msg">{{ detailEvent.message || '-' }}</div>
        </div>

        <div class="detail-actions">
          <el-button
            v-for="t in allowedTransitions(detailEvent.status)"
            :key="t" size="small" plain
            :type="t === 'false_alarm' ? 'info' : 'primary'"
            @click="handleTransition(detailEvent, t)"
          >
            {{ transitionText(t) }}
          </el-button>
          <span v-if="!allowedTransitions(detailEvent.status).length" class="cell-sub">该事件已终结</span>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
/*
 * 校园安防视图 —— 「端—边—云」协同的云侧可视化入口
 *
 * 数据来源：
 *   GET /api/security/stats  汇总统计（级别分布/场景分布/24h趋势/处置概况）
 *   GET /api/security/map    校园平面图（分区设备/事件/最高活动级别）
 *   GET /api/security/nodes  边缘节点在线状态
 *   GET /api/security/events 事件列表（分页 + 级别/分区/状态筛选）
 *   PUT /api/security/events/{id}/status  处置状态机流转
 *
 * 展示要点：
 *   1. 证据链抽屉 —— 把后端已上报的「证据源 / 边缘本地联动 / 推送通道 / 边缘耗时」
 *      完整呈现，直观支撑「多源融合降误报」与「分级推送」两项机制；
 *   2. 24h 趋势与场景构成 —— 直接消费 /stats 返回的 trend_24h 与 type_distribution；
 *   3. 平面图脉冲环 + 数据驱动的边缘协同链路；
 *   4. 轮询带防重入与页面隐藏暂停，避免请求堆积与数据跳变。
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
// 注意：echarts 的 `PieChart` 与 Element Plus 全局注册的图标 `PieChart` 同名。
// main.js 已把 @element-plus/icons-vue 的所有图标注册为全局组件，若此处直接
// `import { PieChart }`，会以局部绑定**遮蔽**全局图标组件，导致模板里的
// `<el-icon><PieChart /></el-icon>` 实际渲染的是 echarts 的图表定义对象
// （非 Vue 组件），createVNode 抛 "Invalid vnode type"，整个组件树渲染失败 →
// 白屏，并连带其它路由一起空白。故此处重命名为 PieChartSeries。
import { BarChart, PieChart as PieChartSeries } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import request from '../api/request'
import StatCard from '../components/StatCard.vue'
import {
  levelInfo, levelLabel, eventTypeLabel, eventStatusInfo,
  sourceLabel, actionLabel, channelLabel, allowedTransitions,
} from '../utils/security'

use([BarChart, PieChartSeries, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

// ━━━ 图表配色（与 theme.css 语义色保持一致）━━━
const LEVEL_COLORS = { 1: '#ef4444', 2: '#f97316', 3: '#eab308', 4: '#38bdf8' }
const DONUT_COLORS = ['#38bdf8', '#22c55e', '#eab308', '#f97316', '#ef4444', '#a78bfa']

// ━━━ 处置状态机（与后端 EVENT_STATUS_FLOW 一致）━━━
const STATUS_STEPS = [
  { key: 'pending', label: '待确认' },
  { key: 'confirmed', label: '已确认' },
  { key: 'processing', label: '处置中' },
  { key: 'closed', label: '已闭环' },
]

const TRANSITION_TEXT = {
  confirmed: '确认',
  processing: '开始处置',
  false_alarm: '标记误报',
  closed: '闭环',
}

// ━━━ 状态 ━━━
const stats = ref({})
const mapData = ref({ zones: [] })
const nodes = ref([])
const events = ref([])
const loading = ref(false)
const page = ref(1)
const perPage = 20
const total = ref(0)
const filters = ref({ level: null, zone: null, status: 'all' })

// 详情抽屉
const detailVisible = ref(false)
const detailId = ref(null)
const detailSnapshot = ref(null)

// 分区平面图布局（固定坐标，SVG viewBox 680×430）
const zoneShapes = [
  { zone: '校门区',     x: 30,  y: 40,  w: 290, h: 140 },
  { zone: '实验楼区',   x: 360, y: 40,  w: 290, h: 140 },
  { zone: '周界宿舍区', x: 30,  y: 265, w: 620, h: 130 },
]

// 边缘节点标记位置（各分区左上角）
const nodeMarkers = computed(() => {
  const pos = {
    'EDGE-GATE':  { x: 300, y: 62 },
    'EDGE-LAB':   { x: 630, y: 62 },
    'EDGE-FENCE': { x: 630, y: 287 },
  }
  return nodes.value
    .filter((n) => pos[n.node_code])
    .map((n) => ({ ...n, ...pos[n.node_code] }))
})

// 边缘协同链路：端点取自真实节点坐标，沿图幅边缘走线（不穿越分区）
function routePoints(a, b) {
  const W = 680, H = 430, PAD = 22
  if (Math.abs(a.x - b.x) < 30) {
    const x = W - PAD
    return `${a.x},${a.y} ${x},${a.y} ${x},${b.y} ${b.x},${b.y}`
  }
  const y = Math.min(a.y, b.y) < H / 2 ? PAD : H - PAD
  return `${a.x},${a.y} ${a.x},${y} ${b.x},${y} ${b.x},${b.y}`
}

const collabLinks = computed(() => {
  const byCode = Object.fromEntries(nodeMarkers.value.map((n) => [n.node_code, n]))
  const pairs = [['EDGE-GATE', 'EDGE-LAB'], ['EDGE-LAB', 'EDGE-FENCE']]
  return pairs
    .filter(([a, b]) => byCode[a] && byCode[b])
    .map(([a, b]) => ({ key: `${a}-${b}`, points: routePoints(byCode[a], byCode[b]) }))
})

const collabStroke = computed(() =>
  nodes.value.length && nodes.value.every((n) => n.status === 'online')
    ? 'var(--primary)'
    : 'var(--danger)')

const zoneOptions = computed(() => mapData.value.zones.map((z) => z.zone))

const summaryCards = computed(() => [
  { label: '今日事件', value: stats.value.today_total ?? 0, color: 'var(--primary)', icon: 'Bell' },
  // level_distribution 的键经 JSON 序列化为字符串（"1"/"2"...），故用 String(1) 访问
  { label: '紧急告警', value: stats.value.level_distribution?.['1'] ?? 0, color: 'var(--danger)', icon: 'WarningFilled' },
  { label: '待确认', value: stats.value.pending_count ?? 0, color: 'var(--warning)', icon: 'Clock' },
  { label: '边缘节点在线', value: nodes.value.filter((n) => n.status === 'online').length,
    color: 'var(--success)', icon: 'Cpu' },
])

const activeByZone = computed(() => events.value.filter(
  (e) => ['pending', 'confirmed', 'processing'].includes(e.status),
).slice(0, 8))

// 边缘本地平均闭环耗时（论文「边缘协同降低响应延迟」的实测指标）
const avgEdgeLatency = computed(() => {
  const arr = events.value.map((e) => e.local_latency_ms).filter((v) => typeof v === 'number')
  if (!arr.length) return null
  return Math.round(arr.reduce((a, b) => a + b, 0) / arr.length)
})

// ━━━ 图表 option ━━━
const hasTrend = computed(() => (stats.value.trend_24h || []).some((x) => (x.total || 0) > 0))
const hasScenes = computed(() => (stats.value.type_distribution || []).length > 0)

const trendOption = computed(() => {
  const rows = stats.value.trend_24h || []
  const bar = (name, key, level) => ({
    name,
    type: 'bar',
    stack: 'total',
    barMaxWidth: 14,
    itemStyle: { color: LEVEL_COLORS[level] },
    data: rows.map((r) => r[key] || 0),
  })
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: {
      data: ['紧急', '严重', '一般', '提示'],
      textStyle: { color: '#94a3b8' },
      itemWidth: 10, itemHeight: 10, top: 0,
    },
    grid: { left: '3%', right: '3%', bottom: '2%', top: 34, containLabel: true },
    xAxis: {
      type: 'category',
      data: rows.map((r) => r.hour),
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
      axisTick: { show: false },
      axisLabel: { color: '#64748b', interval: 3 },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisLabel: { color: '#64748b' },
    },
    series: [bar('紧急', 'level_1', 1), bar('严重', 'level_2', 2), bar('一般', 'level_3', 3), bar('提示', 'level_4', 4)],
  }
})

const sceneOption = computed(() => {
  const rows = stats.value.type_distribution || []
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} 起 ({d}%)' },
    legend: {
      bottom: 0,
      textStyle: { color: '#94a3b8' },
      itemWidth: 10, itemHeight: 10,
    },
    series: [{
      type: 'pie',
      radius: ['42%', '66%'],
      center: ['50%', '44%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: 'rgba(15,23,42,0.7)', borderWidth: 2 },
      label: { color: '#cbd5e1', fontSize: 11, formatter: '{b} {c}' },
      labelLine: { lineStyle: { color: 'rgba(255,255,255,0.2)' }, length: 6, length2: 6 },
      data: rows.map((r, i) => ({
        name: r.label,
        value: r.count,
        itemStyle: { color: DONUT_COLORS[i % DONUT_COLORS.length] },
      })),
    }],
  }
})

// ━━━ 详情抽屉 ━━━
const detailEvent = computed(() => {
  if (detailId.value == null) return null
  return events.value.find((e) => e.id === detailId.value) || detailSnapshot.value
})

const activeStep = computed(() => {
  const s = detailEvent.value?.status
  if (!s || s === 'false_alarm') return -1
  return STATUS_STEPS.findIndex((x) => x.key === s)
})

function openDetail(row) {
  detailId.value = row.id
  detailSnapshot.value = row
  detailVisible.value = true
}

// ━━━ 数据加载 ━━━
async function loadStats() {
  try {
    stats.value = (await request.get('/security/stats')).data
  } catch (e) { /* 静默失败，下次轮询重试 */ }
}

async function loadMap() {
  try {
    mapData.value = (await request.get('/security/map')).data
  } catch (e) { /* pass */ }
}

async function loadNodes() {
  try {
    nodes.value = (await request.get('/security/nodes')).data.items
  } catch (e) { /* pass */ }
}

async function loadEvents() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: perPage, status: filters.value.status }
    if (filters.value.level) params.level = filters.value.level
    if (filters.value.zone) params.zone = filters.value.zone
    const res = await request.get('/security/events', { params })
    events.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    ElMessage.error('加载安防事件失败')
  } finally {
    loading.value = false
  }
}

function reload() {
  page.value = 1
  loadEvents()
}

async function refreshAll() {
  await Promise.allSettled([loadStats(), loadMap(), loadNodes(), loadEvents()])
}

// ━━━ 处置状态机流转 ━━━
function transitionText(t) {
  return TRANSITION_TEXT[t] || t
}

async function handleTransition(row, target) {
  const isFalseAlarm = target === 'false_alarm'
  try {
    let note = ''
    if (isFalseAlarm) {
      const { value } = await ElMessageBox.prompt(
        '请填写误报原因（将作为误报样本留存，用于后续阈值优化）',
        '标记误报',
        { confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：树枝晃动引起的振动误触发' },
      )
      note = value || ''
    }
    await request.put(`/security/events/${row.id}/status`, { status: target, note })
    ElMessage.success(`事件已流转为「${eventStatusInfo(target).label}」`)
    refreshAll()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e?.response?.data?.detail || '状态流转失败')
    }
  }
}

// ━━━ 平面图着色 ━━━
function zoneOf(zone) {
  return mapData.value.zones.find((z) => z.zone === zone) || {}
}

function zoneFill(zone) {
  const lv = zoneOf(zone).max_active_level
  if (!lv) return 'var(--bg-card)'
  return levelInfo(lv).bg
}

function zoneStroke(zone) {
  const lv = zoneOf(zone).max_active_level
  if (!lv) return 'var(--border)'
  return levelInfo(lv).color
}

function badgeStyle(level) {
  const info = levelInfo(level)
  return { background: info.bg, color: info.color, borderColor: info.color }
}

// ━━━ 工具函数 ━━━
function fmtTime(t) {
  return t ? new Date(t).toLocaleString('zh-CN', { hour12: false }) : '-'
}

function shortTime(t) {
  return t ? new Date(t).toLocaleTimeString('zh-CN', { hour12: false }) : '-'
}

function rowClass({ row }) {
  return row.status === 'pending' ? 'event-pending-row' : ''
}

// ━━━ 自动刷新：防重入 + 页面隐藏暂停 ━━━
let timer = null
let inFlight = false

async function safeRefresh() {
  if (inFlight || document.hidden) return
  inFlight = true
  try {
    await refreshAll()
  } finally {
    inFlight = false
  }
}

function onVisibilityChange() {
  if (!document.hidden) safeRefresh()
}

onMounted(() => {
  safeRefresh()
  timer = setInterval(safeRefresh, 5000)
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<style scoped>
.security-page {
  display: flex;
  flex-direction: column;
  gap: var(--sp-24);
}

.stats-row {
  margin: 0;
}

/* ━━━ 图表卡片 ━━━ */
.chart-card {
  height: 100%;
}

.card-sub {
  font-size: 12px;
  color: var(--text-3);
}

/* ━━━ 平面图区域 ━━━ */
.map-wrap {
  display: flex;
  gap: var(--sp-16);
  align-items: stretch;
}

.campus-map {
  flex: 1;
  min-width: 0;
  height: 430px;
  border-radius: var(--radius-card);
}

/* 活动告警脉冲环 */
.zone-ring {
  animation: zonePulse 1.6s ease-in-out infinite;
}

@keyframes zonePulse {
  0%, 100% { opacity: 0.9; }
  50% { opacity: 0.15; }
}

.zone-panel {
  width: 300px;
  flex-shrink: 0;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: var(--sp-16);
  display: flex;
  flex-direction: column;
  max-height: 430px;
}

.zone-panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-1);
  margin-bottom: var(--sp-16);
}

.zone-event-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--sp-8);
}

.zone-event-item {
  display: flex;
  align-items: center;
  gap: var(--sp-8);
  padding: var(--sp-8);
  border-radius: var(--radius-btn);
  background: var(--bg-card);
  border: 1px solid var(--border);
  cursor: pointer;
  transition: var(--transition);
}

.zone-event-item:hover {
  border-color: var(--primary);
}

.zone-event-body {
  flex: 1;
  min-width: 0;
}

.zone-event-title {
  font-size: 13px;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.zone-event-sub {
  font-size: 11px;
  color: var(--text-3);
  margin-top: 2px;
}

.zone-event-time {
  font-size: 11px;
  color: var(--text-3);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

/* 面板底部：边缘 vs 云端耗时对比 */
.zone-panel-foot {
  margin-top: var(--sp-16);
  padding-top: var(--sp-16);
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.foot-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.foot-label {
  font-size: 12px;
  color: var(--text-3);
}

.foot-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--primary);
  font-variant-numeric: tabular-nums;
}

.foot-value.dim {
  color: var(--text-2);
}

/* ━━━ 级别徽章 ━━━ */
.level-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
  border: 1px solid transparent;
  white-space: nowrap;
}

.edge-latency {
  font-size: 12px;
  color: var(--primary);
  font-variant-numeric: tabular-nums;
}

/* ━━━ 顶栏图例 / 筛选 ━━━ */
.topo-legend {
  display: flex;
  gap: var(--sp-16);
  align-items: center;
  flex-wrap: wrap;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-2);
}

.dash-swatch {
  display: inline-block;
  width: 18px;
  height: 0;
  border-top: 1.5px dashed var(--primary);
}

.filter-bar {
  display: flex;
  gap: var(--sp-8);
  align-items: center;
  flex-wrap: wrap;
}

.filter-hint {
  font-size: 12px;
  color: var(--text-3);
}

.src-tag {
  margin-right: 4px;
}

.op-btn {
  margin-right: 6px;
}

.pagination {
  margin-top: var(--sp-16);
  justify-content: center;
}

.cell-sub {
  font-size: 12px;
  color: var(--text-3);
}

/* ━━━ 详情抽屉 ━━━ */
.detail-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--sp-24);
}

.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-8);
}

.detail-head-main {
  display: flex;
  align-items: center;
  gap: var(--sp-8);
  min-width: 0;
}

.detail-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-1);
}

.detail-sub {
  font-size: 12px;
  color: var(--text-3);
  margin-top: -12px;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: var(--sp-8);
}

.detail-section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-2);
  letter-spacing: 0.5px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}

.detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.detail-note {
  font-size: 12px;
  color: var(--text-3);
  line-height: 1.6;
}

.detail-note.highlight {
  color: var(--orange);
}

.detail-note b {
  color: var(--primary);
}

.detail-msg {
  font-size: 13px;
  color: var(--text-2);
  line-height: 1.7;
  word-break: break-all;
}

.kv {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-16);
  font-size: 12px;
}

.kv > span {
  color: var(--text-3);
  flex-shrink: 0;
}

.kv > b {
  color: var(--text-1);
  font-weight: 500;
  text-align: right;
  word-break: break-all;
}

/* ━━━ 状态步进器 ━━━ */
.stepper {
  display: flex;
  align-items: flex-start;
}

.step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.step-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border);
  transition: var(--transition);
}

.step-dot.done {
  background: var(--primary);
}

.step-label {
  font-size: 11px;
  color: var(--text-3);
  white-space: nowrap;
}

.step-label.done {
  color: var(--text-1);
}

.step-line {
  flex: 1;
  height: 2px;
  margin-top: 3px;
  background: var(--border);
}

.step-line.done {
  background: var(--primary);
}

.detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-8);
  padding-top: var(--sp-8);
  border-top: 1px solid var(--border);
}

/* ━━━ 待确认行高亮（scoped，避免全局样式污染）━━━ */
:deep(.event-pending-row) {
  background-color: rgba(234, 179, 8, 0.06) !important;
}

:deep(.el-table__row) {
  cursor: pointer;
}

/* ━━━ 减弱动效 ━━━ */
@media (prefers-reduced-motion: reduce) {
  .zone-ring {
    animation: none;
  }
}
</style>
