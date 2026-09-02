import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { authApi, type LoginPayload, type RegisterPayload, type User } from '../api'
import { TOKEN_KEY } from '../api/http'

export const useAuthStore = defineStore('auth', () => {
  const DEMO_KEY = 'adaptive_learning_demo'
  const user = ref<User | null>(null)
  const loading = ref(false)
  const token = ref(localStorage.getItem(TOKEN_KEY))
  const isDemo = ref(localStorage.getItem(DEMO_KEY) === '1')
  const isAuthenticated = computed(() => Boolean(token.value) || isDemo.value)

  function setSession(accessToken: string, currentUser?: User) {
    localStorage.setItem(TOKEN_KEY, accessToken)
    token.value = accessToken
    if (currentUser) user.value = currentUser
  }

  async function login(payload: LoginPayload) {
    loading.value = true
    try {
      const response = await authApi.login(payload)
      setSession(response.access_token, response.user)
      if (!response.user) user.value = await authApi.me()
    } finally {
      loading.value = false
    }
  }

  async function register(payload: RegisterPayload) {
    loading.value = true
    try {
      await authApi.register(payload)
      const response = await authApi.login({ email: payload.email, password: payload.password })
      setSession(response.access_token, response.user)
      if (!response.user) user.value = await authApi.me()
    } finally {
      loading.value = false
    }
  }

  async function fetchMe() {
    if (isDemo.value) {
      user.value = { id: 'demo', name: '演示学习者', email: 'demo@local', role: 'student' }
      return user.value
    }
    if (!token.value) return null
    try {
      user.value = await authApi.me()
      return user.value
    } catch (error) {
      logout()
      throw error
    }
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(DEMO_KEY)
    token.value = null
    isDemo.value = false
    user.value = null
  }

  function enterDemo() {
    localStorage.setItem(DEMO_KEY, '1')
    isDemo.value = true
    user.value = { id: 'demo', name: '演示学习者', email: 'demo@local', role: 'student' }
  }

  return { user, token, loading, isDemo, isAuthenticated, login, register, fetchMe, logout, enterDemo }
})
