import axios from 'axios'

import { useAuthStore } from '@/stores/auth'

const client = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  timeout: 60000,
})

let router = null
let refreshing = null

const NO_REFRESH_URLS = ['/auth/login', '/auth/refresh', '/auth/logout']

client.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.access && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${auth.access}`
  }
  return config
})

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const { config, response } = error
    if (!response || !config) throw error
    const auth = useAuthStore()

    // 401: refresh the access token once, then retry (specs/03 §1).
    if (response.status === 401 && !config._retried && !NO_REFRESH_URLS.includes(config.url)) {
      config._retried = true
      try {
        refreshing = refreshing || auth.refreshAccess()
        await refreshing
      } catch {
        auth.clear()
        router?.push({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
        throw error
      } finally {
        refreshing = null
      }
      config.headers.Authorization = `Bearer ${auth.access}`
      return client(config)
    }

    // 409 llm_not_configured: admins go to the LLM settings, others to the admin login
    // (specs/03 §4).
    if (response.status === 409 && response.data?.code === 'llm_not_configured') {
      router?.push(
        auth.isAdmin
          ? { name: 'admin-llm-settings', query: { reason: 'llm_not_configured' } }
          : {
              name: 'admin-login',
              query: { redirect: '/admin/settings/llm', reason: 'llm_not_configured' },
            },
      )
    }
    throw error
  },
)

export function attachRouter(appRouter) {
  router = appRouter
}

export default client
