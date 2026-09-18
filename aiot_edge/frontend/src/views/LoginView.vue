<template>
  <div class="login-page">
    <el-card class="login-card">
      <div class="login-header">
        <el-icon class="login-icon"><Connection /></el-icon>
        <h2>高校安防AIoT边缘协同预警系统</h2>
      </div>

      <el-tabs v-model="activeTab" class="login-tabs" stretch>
        <!-- 登录 -->
        <el-tab-pane label="登录" name="login">
          <!-- 登录方式切换 -->
          <div class="login-mode-switch">
            <el-radio-group v-model="loginMode" size="default">
              <el-radio-button value="password">密码登录</el-radio-button>
              <el-radio-button value="code">验证码登录</el-radio-button>
            </el-radio-group>
          </div>

          <el-form ref="loginFormRef" :model="loginForm" :rules="loginRules" label-position="top">
            <!-- 密码登录：用户名/邮箱 + 密码 -->
            <template v-if="loginMode === 'password'">
              <el-form-item label="用户名 / 邮箱" prop="username">
                <el-input v-model="loginForm.username" placeholder="请输入用户名或邮箱" prefix-icon="User" />
              </el-form-item>
              <el-form-item label="密码" prop="password">
                <el-input
                  v-model="loginForm.password"
                  type="password"
                  placeholder="请输入密码"
                  prefix-icon="Lock"
                  show-password
                  @keyup.enter="handleLogin"
                />
              </el-form-item>
            </template>

            <!-- 验证码登录：邮箱 + 验证码 -->
            <template v-else>
              <el-form-item label="邮箱" prop="username">
                <el-input v-model="loginForm.username" placeholder="请输入邮箱" prefix-icon="Message" />
              </el-form-item>
              <el-form-item label="邮箱验证码" prop="code">
                <div class="code-row">
                  <el-input
                    v-model="loginForm.code"
                    placeholder="6位验证码"
                    prefix-icon="Key"
                    maxlength="6"
                    @keyup.enter="handleLogin"
                  />
                  <el-button
                    class="code-btn"
                    :loading="loginSending"
                    :disabled="loginCountdown > 0"
                    @click="sendLoginCode"
                  >
                    {{ loginCountdown > 0 ? `${loginCountdown}s` : '获取验证码' }}
                  </el-button>
                </div>
              </el-form-item>
            </template>

            <el-button type="primary" :loading="loading" block size="large" @click="handleLogin">
              登 录
            </el-button>
          </el-form>
        </el-tab-pane>

        <!-- 注册 -->
        <el-tab-pane label="注册" name="register">
          <el-form ref="regFormRef" :model="regForm" :rules="regRules" label-position="top">
            <el-form-item label="用户名" prop="username">
              <el-input v-model="regForm.username" placeholder="3-20位字母数字下划线" prefix-icon="User" />
            </el-form-item>
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="regForm.email" placeholder="请输入邮箱地址" prefix-icon="Message" />
            </el-form-item>
            <el-form-item label="邮箱验证码" prop="code">
              <div class="code-row">
                <el-input
                  v-model="regForm.code"
                  placeholder="6位验证码"
                  prefix-icon="Key"
                  maxlength="6"
                />
                <el-button
                  class="code-btn"
                  :loading="regSending"
                  :disabled="regCountdown > 0"
                  @click="sendRegCode"
                >
                  {{ regCountdown > 0 ? `${regCountdown}s` : '获取验证码' }}
                </el-button>
              </div>
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="regForm.password"
                type="password"
                placeholder="6-30位，含字母和数字"
                prefix-icon="Lock"
                show-password
              />
            </el-form-item>
            <el-form-item label="确认密码" prop="confirm">
              <el-input
                v-model="regForm.confirm"
                type="password"
                placeholder="再次输入密码"
                prefix-icon="Lock"
                show-password
              />
            </el-form-item>
            <el-button type="success" :loading="loading" block size="large" @click="handleRegister">
              注 册
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../stores/user'

const router = useRouter()
const userStore = useUserStore()
const activeTab = ref('login')
const loading = ref(false)

// ━━━ 登录 ━━━
const loginMode = ref('password')   // password / code
const loginForm = reactive({ username: '', password: '', code: '' })
const loginRules = {
  username: [{ required: true, message: '请输入账号或邮箱', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  code: [{ required: true, message: '请输入邮箱验证码', trigger: 'blur' }],
}

const loginFormRef = ref(null)
const loginSending = ref(false)
const loginCountdown = ref(0)
let loginTimer = null

// 验证码登录时发送验证码到填写的邮箱
function sendLoginCode() {
  const account = loginForm.username.trim()
  if (!account) {
    ElMessage.warning('请先填写邮箱')
    return
  }
  if (!account.includes('@')) {
    ElMessage.warning('验证码登录请使用邮箱')
    return
  }
  doSendCode(account, 'login')
}

async function handleLogin() {
  // 按当前方式只校验对应字段
  const fields = loginMode.value === 'password' ? ['username', 'password'] : ['username', 'code']
  const valid = await loginFormRef.value?.validateField(fields).catch(() => false)
  if (valid === false || (Array.isArray(valid) && valid.length)) {
    // validateField 返回 true 表示通过
    return
  }
  loading.value = true
  try {
    if (loginMode.value === 'password') {
      await userStore.login(loginForm.username, loginForm.password, '', 'password')
    } else {
      await userStore.login(loginForm.username, '', loginForm.code, 'code')
    }
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}

// ━━━ 注册 ━━━
const regForm = reactive({ username: '', email: '', password: '', confirm: '', code: '' })
const validateConfirm = (rule, value, callback) => {
  if (value !== regForm.password) callback(new Error('两次密码不一致'))
  else callback()
}
const regRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]{3,20}$/, message: '3-20位字母、数字或下划线', trigger: 'blur' },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  code: [{ required: true, message: '请输入邮箱验证码', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 30, message: '6-30位', trigger: 'blur' },
    { pattern: /[a-zA-Z]/, message: '密码需包含字母', trigger: 'blur' },
    { pattern: /\d/, message: '密码需包含数字', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' },
  ],
}

const regFormRef = ref(null)
const regSending = ref(false)
const regCountdown = ref(0)
let regTimer = null

function sendRegCode() {
  const email = regForm.email.trim()
  if (!email) {
    ElMessage.warning('请先填写邮箱')
    return
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    ElMessage.warning('邮箱格式不正确')
    return
  }
  doSendCode(email, 'reg')
}

// 通用发送逻辑 + 60s 倒计时
async function doSendCode(email, kind) {
  const isLogin = kind === 'login'
  if (isLogin) loginSending.value = true
  else regSending.value = true
  try {
    await userStore.sendCode(email)
    ElMessage.success('验证码已发送，请查收邮箱')
    startCountdown(kind)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '发送失败')
  } finally {
    if (isLogin) loginSending.value = false
    else regSending.value = false
  }
}

function startCountdown(kind) {
  const isLogin = kind === 'login'
  const setter = isLogin ? (v) => (loginCountdown.value = v) : (v) => (regCountdown.value = v)
  const timerKey = isLogin ? 'loginTimer' : 'regTimer'
  clearInterval(isLogin ? loginTimer : regTimer)
  setter(60)
  const t = setInterval(() => {
    const cur = isLogin ? loginCountdown.value : regCountdown.value
    if (cur <= 1) {
      clearInterval(t)
      setter(0)
    } else {
      setter(cur - 1)
    }
  }, 1000)
  if (isLogin) loginTimer = t
  else regTimer = t
}

async function handleRegister() {
  const valid = await regFormRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await userStore.register(regForm.username, regForm.email, regForm.password, regForm.code)
    ElMessage.success('注册成功，请登录')
    activeTab.value = 'login'
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(ellipse at 30% 20%, rgba(56, 189, 248, 0.08), transparent 60%),
    var(--bg);
}

.login-card {
  width: 416px;
  border-radius: var(--radius-card);
}

.login-header {
  text-align: center;
  padding: var(--sp-24) 0 var(--sp-16);
}

.login-icon {
  width: 64px;
  height: 64px;
  border-radius: var(--radius-card);
  background: rgba(56, 189, 248, 0.12);
  color: var(--primary);
  font-size: 32px;
  margin: 0 auto;
}

.login-header h2 {
  margin: var(--sp-16) 0 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-1);
}

.login-tabs {
  margin-top: var(--sp-8);
}

.login-mode-switch {
  display: flex;
  justify-content: center;
  margin-bottom: var(--sp-16);
}

.code-row {
  display: flex;
  gap: 8px;
  width: 100%;
}

.code-btn {
  flex-shrink: 0;
  white-space: nowrap;
}
</style>
