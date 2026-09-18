import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import request from '../api/request'

function readStoredUser() {
  try {
    return JSON.parse(localStorage.getItem('user') || 'null')
  } catch (error) {
    console.warn('已清理损坏的用户缓存', error)
    localStorage.removeItem('user')
    return null
  }
}

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref(readStoredUser())

  const isLoggedIn = computed(() => !!token.value)

  async function login(username, password, code, loginType = 'password') {
    const res = await request.post('/auth/login', { username, password, code, login_type: loginType })
    token.value = res.data.access_token
    user.value = res.data.user
    localStorage.setItem('token', res.data.access_token)
    localStorage.setItem('user', JSON.stringify(res.data.user))
    return res.data
  }

  async function register(username, email, password, code) {
    const res = await request.post('/auth/register', { username, email, password, code })
    return res.data
  }

  async function sendCode(email) {
    const res = await request.post('/auth/send-code', { email })
    return res.data
  }

  async function fetchMe() {
    try {
      const res = await request.get('/auth/me')
      user.value = res.data
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  return { token, user, isLoggedIn, login, register, sendCode, fetchMe, logout }
})
