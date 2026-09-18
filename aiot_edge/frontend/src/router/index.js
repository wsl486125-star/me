import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/dashboard',
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('../views/DashboardView.vue'),
  },
  {
    path: '/devices',
    name: 'Devices',
    component: () => import('../views/DevicesView.vue'),
  },
  {
    path: '/devices/:id',
    name: 'DeviceDetail',
    component: () => import('../views/DeviceDetailView.vue'),
  },
  {
    path: '/groups',
    name: 'Groups',
    component: () => import('../views/GroupsView.vue'),
  },
  {
    path: '/topology',
    name: 'Topology',
    component: () => import('../views/TopologyView.vue'),
  },
  {
    path: '/edge',
    name: 'Edge',
    component: () => import('../views/EdgeView.vue'),
  },
  {
    path: '/security',
    name: 'Security',
    component: () => import('../views/SecurityView.vue'),
  },
  {
    path: '/alerts',
    name: 'Alerts',
    component: () => import('../views/AlertsView.vue'),
  },
  {
    path: '/efficiency',
    name: 'Efficiency',
    component: () => import('../views/EfficiencyView.vue'),
  },
  {
    path: '/assistant',
    name: 'Assistant',
    component: () => import('../views/AssistantView.vue'),
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/dashboard',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫：未登录跳转登录页
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (!token && !to.meta.public) {
    next('/login')
  } else if (token && to.path === '/login') {
    next('/dashboard')
  } else {
    next()
  }
})

export default router
