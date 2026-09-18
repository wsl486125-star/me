import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'

// 设计令牌 + 全局样式
import './styles/theme.css'
import './styles/global.css'

import countUp from './directives/countUp'
import App from './App.vue'
import router from './router'

// 深色模式
document.documentElement.classList.add('dark')

const app = createApp(App)

// 注册所有 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

// 注册数字滚动指令
app.directive('count-up', countUp)

app.mount('#app')
