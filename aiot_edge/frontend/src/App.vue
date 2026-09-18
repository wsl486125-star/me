<template>
  <div id="app-root">
    <!-- 未登录：只显示路由视图 -->
    <router-view v-if="!userStore.isLoggedIn" />

    <!-- 已登录：侧边导航 + 顶部栏 + 内容区 -->
    <el-container v-else class="app-container">
      <!-- 侧边导航 -->
      <el-aside width="224px" class="app-aside">
        <div class="logo">
          <el-icon class="logo-icon"><Connection /></el-icon>
          <span class="logo-text">AIoT Edge</span>
        </div>
        <el-menu :default-active="activeMenu" router class="app-menu">
          <el-menu-item index="/dashboard">
            <el-icon><DataBoard /></el-icon>
            <span>仪表盘</span>
          </el-menu-item>
          <el-menu-item index="/devices">
            <el-icon><Monitor /></el-icon>
            <span>设备管理</span>
          </el-menu-item>
          <el-menu-item index="/groups">
            <el-icon><Collection /></el-icon>
            <span>设备分组</span>
          </el-menu-item>
          <el-menu-item index="/topology">
            <el-icon><Share /></el-icon>
            <span>网络感知</span>
          </el-menu-item>
          <el-menu-item index="/edge">
            <el-icon><Cpu /></el-icon>
            <span>边缘计算</span>
          </el-menu-item>
          <el-menu-item index="/security">
            <el-icon><Aim /></el-icon>
            <span>校园安防</span>
          </el-menu-item>
          <el-menu-item index="/alerts">
            <el-icon><Bell /></el-icon>
            <span>告警中心</span>
          </el-menu-item>
          <el-menu-item index="/efficiency">
            <el-icon><TrendCharts /></el-icon>
            <span>系统效能</span>
          </el-menu-item>
          <el-menu-item index="/assistant">
            <el-icon><ChatDotRound /></el-icon>
            <span>AI助手</span>
          </el-menu-item>
        </el-menu>
      </el-aside>

      <!-- 主体区域 -->
      <el-container>
        <!-- 顶部栏 -->
        <el-header class="app-header">
          <span class="header-title">高校安防AIoT边缘协同预警系统</span>
          <div class="header-right">
            <div class="header-clock">
              <el-icon class="clock-icon"><Clock /></el-icon>
              <span class="clock-time">{{ timeText }}</span>
              <span class="clock-date">{{ dateText }}</span>
            </div>
            <span class="header-divider"></span>
            <el-icon class="user-icon"><User /></el-icon>
            <span class="user-name">{{ userStore.user?.username }}</span>
            <el-button type="danger" size="small" plain @click="handleLogout">退出</el-button>
          </div>
        </el-header>

        <!-- 内容区 -->
        <el-main class="app-main">
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from './stores/user'

const userStore = useUserStore()
const router = useRouter()
const route = useRoute()

const activeMenu = computed(() => {
  // 设备详情页高亮「设备管理」菜单
  if (route.path.startsWith('/devices/')) return '/devices'
  return route.path
})

// ━━━ 顶部实时时钟 ━━━
const now = ref(new Date())
let clockTimer = null

function pad(n) {
  return String(n).padStart(2, '0')
}

const dateText = computed(() => {
  const d = now.value
  const week = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()]
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} 周${week}`
})

const timeText = computed(() => {
  const d = now.value
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})

onMounted(() => {
  clockTimer = setInterval(() => {
    now.value = new Date()
  }, 1000)
})

onUnmounted(() => {
  clearInterval(clockTimer)
})

function handleLogout() {
  userStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.app-container {
  height: 100vh;
}

/* ━━━ 侧边栏 · 玻璃拟态 ━━━ */
.app-aside {
  background: var(--bg-card);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-right: 1px solid var(--border);
  overflow-y: auto;
}

.app-aside .logo {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-8);
  border-bottom: 1px solid var(--border);
}

.logo-icon {
  font-size: 22px;
  color: var(--primary);
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.2), rgba(56, 189, 248, 0.08));
  box-shadow: 0 0 14px rgba(56, 189, 248, 0.25);
}

.logo-text {
  color: var(--text-1);
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 1px;
}

.app-menu {
  border-right: none;
  --el-menu-bg-color: transparent;
  --el-menu-text-color: var(--text-2);
  --el-menu-active-color: var(--primary);
  --el-menu-hover-bg-color: rgba(56, 189, 248, 0.08);
}

.app-menu .el-menu-item {
  height: 48px;
  margin: var(--sp-8);
  border-radius: var(--radius-btn);
  position: relative;
}

.app-menu .el-menu-item.is-active {
  background: linear-gradient(90deg, rgba(56, 189, 248, 0.16), rgba(56, 189, 248, 0.04));
  color: var(--primary);
}

.app-menu .el-menu-item.is-active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  border-radius: 2px;
  background: var(--primary);
  box-shadow: 0 0 8px rgba(56, 189, 248, 0.6);
}

/* ━━━ 顶部栏 ━━━ */
.app-header {
  height: 64px;
  background: var(--bg-card);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--sp-24);
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-1);
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--sp-8);
}

/* ━━━ 实时时钟 ━━━ */
.header-clock {
  display: flex;
  align-items: center;
  gap: var(--sp-8);
  margin-right: var(--sp-8);
}

.clock-icon {
  color: var(--text-3);
  font-size: 16px;
}

.clock-time {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-1);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.5px;
}

.clock-date {
  font-size: 12px;
  color: var(--text-3);
}

.header-divider {
  width: 1px;
  height: 20px;
  background: var(--border);
  margin: 0 var(--sp-8);
}

.user-icon {
  color: var(--primary);
  font-size: 18px;
}

.user-name {
  font-size: 14px;
  color: var(--text-2);
}

/* ━━━ 内容区 ━━━ */
.app-main {
  background: var(--bg);
  padding: var(--sp-24);
  overflow-y: auto;
}
</style>
