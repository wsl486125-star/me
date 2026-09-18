<template>
  <el-card class="stat-card" :style="{ '--stat-color': color }">
    <el-skeleton :loading="loading" animated>
      <template #template>
        <div class="stat-content">
          <el-skeleton-item variant="circle" style="width:44px;height:44px" />
          <div class="stat-info" style="flex:1">
            <el-skeleton-item variant="text" style="width:60%;height:26px" />
            <el-skeleton-item variant="text" style="width:44%;height:14px;margin-top:8px" />
          </div>
        </div>
      </template>
      <template #default>
        <div class="stat-content">
          <div class="stat-icon">
            <el-icon :size="22"><component :is="icon" /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">
              <span v-count-up="{ value, decimals }"></span>
              <span v-if="suffix" class="stat-suffix">{{ suffix }}</span>
            </div>
            <div class="stat-label">{{ label }}</div>
          </div>
        </div>
      </template>
    </el-skeleton>
  </el-card>
</template>

<script setup>
/*
 * 通用统计卡片 —— 图标 + 数值 + 标签，全局唯一实现。
 * 语义色 color 通过 --stat-color 变量注入，同时驱动图标与数值颜色，
 * 保证「在线绿 / 离线红 / 告警黄 / 主色蓝」在所有页面一致。
 */
defineProps({
  label: { type: String, required: true },
  value: { type: Number, default: 0 },
  icon: { type: String, default: 'DataBoard' },
  color: { type: String, default: 'var(--primary)' },
  suffix: { type: String, default: '' },
  decimals: { type: Number, default: undefined },
  loading: { type: Boolean, default: false },
})
</script>

<style scoped>
.stat-card :deep(.el-card__body) {
  padding: var(--sp-16);
}

.stat-content {
  display: flex;
  align-items: center;
  gap: var(--sp-16);
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-btn);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--stat-color);
  background: rgba(255, 255, 255, 0.05);
  background: color-mix(in srgb, var(--stat-color) 14%, transparent);
}

.stat-info {
  min-width: 0;
  flex: 1;
}

.stat-value {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--stat-color);
  font-variant-numeric: tabular-nums;
}

.stat-suffix {
  font-size: 14px;
  font-weight: 600;
  margin-left: 2px;
}

.stat-label {
  font-size: 13px;
  color: var(--text-2);
  margin-top: var(--sp-8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
