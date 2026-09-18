<template>
  <div class="efficiency-page">
    <!-- 四类验收指标卡片 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :xs="12" :sm="12" :md="6" v-for="card in effCards" :key="card.label">
        <StatCard v-bind="card" :loading="loading" />
      </el-col>
    </el-row>

    <!-- 闭环状态分布 + 指标说明 -->
    <el-row :gutter="16">
      <el-col :xs="24" :md="14">
        <el-card class="chart-card">
          <template #header>
            <div class="card-header">
              <span class="card-title">
                <el-icon><PieChart /></el-icon>
                告警闭环状态分布
              </span>
            </div>
          </template>

          <div v-if="hasData" class="dist-wrap">
            <!-- 环形图（纯 CSS/SVG） -->
            <div class="ring-box">
              <svg viewBox="0 0 160 160" class="ring-svg">
                <circle cx="80" cy="80" r="62" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="18" />
                <circle
                  v-for="seg in ringSegments"
                  :key="seg.key"
                  cx="80" cy="80" r="62" fill="none"
                  :stroke="seg.color" stroke-width="18"
                  :stroke-dasharray="seg.dash"
                  :stroke-dashoffset="seg.offset"
                  :transform="'rotate(-90 80 80)'"
                  stroke-linecap="butt"
                />
              </svg>
              <div class="ring-center">
                <div class="ring-value">{{ fmtPct(closureRate) }}</div>
                <div class="ring-label">闭环率</div>
              </div>
            </div>

            <!-- 图例 + 数值 -->
            <div class="dist-legend">
              <div class="legend-item">
                <span class="legend-dot" style="background:#ef4444"></span>
                <span class="legend-name">未闭环</span>
                <span class="legend-val">{{ eff.open ?? 0 }} 条</span>
              </div>
              <div class="legend-item">
                <span class="legend-dot" style="background:#22c55e"></span>
                <span class="legend-name">已解决</span>
                <span class="legend-val">{{ eff.resolved ?? 0 }} 条</span>
              </div>
              <div class="legend-item">
                <span class="legend-dot" style="background:#7c8ca5"></span>
                <span class="legend-name">误报</span>
                <span class="legend-val">{{ eff.false_alarm ?? 0 }} 条</span>
              </div>
              <div class="legend-total">总告警 {{ eff.total ?? 0 }} 条</div>
            </div>
          </div>
          <el-empty v-else description="暂无数据" />
        </el-card>
      </el-col>

      <el-col :xs="24" :md="10">
        <el-card class="desc-card">
          <template #header>
            <div class="card-header">
              <span class="card-title">
                <el-icon><InfoFilled /></el-icon>
                验收指标说明
              </span>
            </div>
          </template>
          <div class="desc-list">
            <div class="desc-item">
              <div class="desc-name"><span class="desc-dot" style="background:var(--primary)"></span>事件发现率</div>
              <div class="desc-text">已确认有效事件 / 全部告警，反映边缘检测引擎对异常事件的捕获能力。</div>
            </div>
            <div class="desc-item">
              <div class="desc-name"><span class="desc-dot" style="background:var(--success)"></span>告警准确率</div>
              <div class="desc-text">真实告警 / 已闭环告警，剔除误报后的正确率，衡量检测精度。</div>
            </div>
            <div class="desc-item">
              <div class="desc-name"><span class="desc-dot" style="background:var(--orange)"></span>平均处置时长</div>
              <div class="desc-text">从告警触发到闭环的平均耗时，衡量处置响应效率。</div>
            </div>
            <div class="desc-item">
              <div class="desc-name"><span class="desc-dot" style="background:var(--warning)"></span>闭环率</div>
              <div class="desc-text">已闭环（解决+误报）/ 全部告警，衡量「发现→处置」闭环完整度。</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import request from '../api/request'
import StatCard from '../components/StatCard.vue'

const loading = ref(false)
const eff = ref({})

// 四类验收指标卡片（发现率/准确率/闭环率 ×100 转百分比显示）
const effCards = computed(() => [
  {
    label: '事件发现率',
    value: (eff.value.discovery_rate ?? 0) * 100,
    suffix: '%',
    decimals: 1,
    color: 'var(--primary)',
    icon: 'Search',
  },
  {
    label: '告警准确率',
    value: (eff.value.accuracy_rate ?? 0) * 100,
    suffix: '%',
    decimals: 1,
    color: 'var(--success)',
    icon: 'Aim',
  },
  {
    label: '平均处置时长',
    value: eff.value.avg_handle_duration ?? 0,
    suffix: 's',
    decimals: 1,
    color: 'var(--orange)',
    icon: 'Timer',
  },
  {
    label: '闭环率',
    value: (eff.value.closure_rate ?? 0) * 100,
    suffix: '%',
    decimals: 1,
    color: 'var(--warning)',
    icon: 'CircleCheck',
  },
])

const hasData = computed(() => (eff.value.total ?? 0) > 0)
const closureRate = computed(() => eff.value.closure_rate ?? 0)

// 环形图分段（按状态比例计算 dash）
const RING_LEN = 2 * Math.PI * 62 // 圆周长
const ringSegments = computed(() => {
  const d = eff.value
  if (!d || !d.total) return []
  const resolved = d.resolved ?? 0
  const falseAlarm = d.false_alarm ?? 0
  const open = d.open ?? 0
  const total = d.total
  const segs = []
  let acc = 0
  const parts = [
    { key: 'resolved', val: resolved, color: '#22c55e' },
    { key: 'false_alarm', val: falseAlarm, color: '#7c8ca5' },
    { key: 'open', val: open, color: '#ef4444' },
  ]
  for (const p of parts) {
    if (p.val <= 0) continue
    const frac = p.val / total
    const dash = frac * RING_LEN
    segs.push({ key: p.key, color: p.color, dash, offset: -acc })
    acc += dash
  }
  return segs
})

function fmtPct(v) {
  return (v * 100).toFixed(1) + '%'
}

async function loadEfficiency() {
  loading.value = true
  try {
    const res = await request.get('/alerts/efficiency')
    eff.value = res.data
  } catch (e) {
    /* pass */
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadEfficiency()
})
</script>

<style scoped>
.efficiency-page {
  display: flex;
  flex-direction: column;
  gap: var(--sp-24);
}

.stats-row {
  margin: 0;
}

.chart-card,
.desc-card {
  height: 100%;
}

/* ━━━ 闭环分布 ━━━ */
.dist-wrap {
  display: flex;
  align-items: center;
  gap: var(--sp-32);
  padding: var(--sp-16);
}

.ring-box {
  position: relative;
  width: 180px;
  height: 180px;
  flex-shrink: 0;
}

.ring-svg {
  width: 100%;
  height: 100%;
}

.ring-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.ring-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-1);
  font-variant-numeric: tabular-nums;
}

.ring-label {
  font-size: 12px;
  color: var(--text-3);
}

.dist-legend {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--sp-16);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: var(--sp-8);
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-name {
  font-size: 14px;
  color: var(--text-2);
}

.legend-val {
  margin-left: auto;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-1);
  font-variant-numeric: tabular-nums;
}

.legend-total {
  margin-top: var(--sp-8);
  padding-top: var(--sp-16);
  border-top: 1px solid var(--border);
  font-size: 13px;
  color: var(--text-3);
}

/* ━━━ 指标说明 ━━━ */
.desc-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-16);
}

.desc-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.desc-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-1);
  display: flex;
  align-items: center;
  gap: var(--sp-8);
}

.desc-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.desc-text {
  font-size: 12px;
  color: var(--text-3);
  line-height: 1.6;
  padding-left: 16px;
}
</style>
