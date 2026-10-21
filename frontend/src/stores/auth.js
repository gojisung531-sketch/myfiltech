import { defineStore } from 'pinia'

import * as authApi from '@/api/auth'

const STORAGE_KEY = 'filtech.auth'

function loadStored() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}
  } catch {
    return {}
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => {
    const stored = loadStored()
    return {
      user: stored.user || null,
      access: stored.access || null,
      refresh: stored.refresh || null,
    }
  },
  getters: {
    isAuthenticated: (state) => Boolean(state.access && state.user),
    isAdmin: (state) => state.user?.role === 'ADMIN',
  },
  actions: {
    persist() {
      try {
        localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({ user: this.user, access: this.access, refresh: this.refresh }),
        )
      } catch {
        // Storage unavailable (private mode); session stays in memory only.
      }
    },
    async login(username, password) {
      const data = await authApi.login(username, password)
      this.user = data.user
      this.access = data.access
      this.refresh = data.refresh
      this.persist()
      return data.user
    },
    async refreshAccess() {
      if (!this.refresh) throw new Error('no refresh token')
      const data = await authApi.refresh(this.refresh)
      this.access = data.access
      this.persist()
    },
    async logout() {
      const token = this.refresh
      if (token) {
        try {
          await authApi.logout(token)
        } catch {
          // Token already invalid; clearing locally is enough.
        }
      }
      this.clear()
    },
    setUser(user) {
      this.user = { ...this.user, ...user }
      this.persist()
    },
    clear() {
      this.user = null
      this.access = null
      this.refresh = null
      try {
        localStorage.removeItem(STORAGE_KEY)
      } catch {
        // ignore
      }
    },
  },
})
