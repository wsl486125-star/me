<template>
  <div class="gauge-dial" :title="`${title}：${display}%`">
    <svg viewBox="0 0 220 126" class="gauge-svg" role="img" :aria-label="`${title} ${display}%`">
      <!-- 180° 半圆粗弧：整段按健康状态着色，圆角端点 -->
      <path
        :d="arcPath"
        fill="none"
        :stroke="color"
        :stroke-width="STROKE"
        stroke-linecap="round"
        :style="{ transition: 'stroke 600ms ease' }"
      />

      <!-- 蓝色细长指针（以竖直向上为基准绘制，整体旋转） -->
      <g
        :style="{
          transform: `rotate(${needleR}deg)`,
          transformOrigin: `${CX}px ${CY}px`,
          transition: 'transform 900ms cubic-bezier(0.22, 1, 0.36, 1)',
        }"
      >
        <path :d="needlePath" fill="#7b9ce1" />
      </g>
    </svg>

    <!-- 大号百分比 + 标签 -->
    <div class="gauge-readout">
      <div class="gauge-num">
        <span class="gauge-num-val">{{ display }}</span>
        <span class="gauge-num-unit">%</span>
      </div>
      <div class="gauge-title">{{ title }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

/*
 * 半圆指针仪表盘（经典简洁风）：
 * 180° 粗圆弧整段按健康状态着色 + 蓝色菱形指针 + 大号百分比读数。
 * 扁平无装饰，数值与指针带平滑过渡动效。
 */
const props = defineProps({
  value: { type: Number, default: 0 },
  title: { type: String, default: '' },
  icon: { type: String, default: '' },
  color: { type: String, default: '#22c55e' },
  min: { type: Number, default: 0 },
  max: { type: Number, default: 100 },
})

// ━━━ 几何常量 ━━━
const CX = 110            // 弧心 x
const CY = 110            // 弧心 y（半圆平边）
const R = 80              // 弧线半径
const STROKE = 26         // 弧线粗细
const NEEDLE_LEN = 66     // 指针长度（针尖恰好触及弧内缘 R-STROKE/2=67）
const NEEDLE_TAIL = 10    // 指针尾部（弧心下方）
const NEEDLE_HALF_W = 3.5 // 指针最大半宽

// 半圆弧路径：左端 → 顶部 → 右端
const arcPath = `M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`

// 指针形状：竖直向上的细长菱形
const needlePath = [
  `M ${CX} ${CY - NEEDLE_LEN}`,
  `L ${CX + NEEDLE_HALF_W} ${CY}`,
  `L ${CX} ${CY + NEEDLE_TAIL}`,
  `L ${CX - NEEDLE_HALF_W} ${CY}`,
  'Z',
].join(' ')

// 数值显示（整数百分比）
const display = computed(() => String(Math.round(Number(props.value) || 0)))

const ratio = computed(() => {
  const span = props.max - props.min || 1
  return Math.min(1, Math.max(0, (props.value - props.min) / span))
})

// 指针角度：0% → -90°(指左)  50% → 0°(垂直向上)  100% → 90°(指右)
const needleR = computed(() => ratio.value * 180 - 90)
</script>

<style scoped>
.gauge-dial {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.gauge-svg {
  width: 100%;
  max-width: 232px;
  display: block;
  overflow: visible;
}

.gauge-readout {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-top: -2px;
}

.gauge-num {
  display: flex;
  align-items: baseline;
  line-height: 1;
}

.gauge-num-val {
  font-size: 42px;
  font-weight: 700;
  color: var(--text-1);
  font-variant-numeric: tabular-nums;
  letter-spacing: -1px;
}

.gauge-num-unit {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-1);
  margin-left: 2px;
}

.gauge-title {
  margin-top: 8px;
  font-size: 14px;
  color: var(--text-2);
}
</style>
