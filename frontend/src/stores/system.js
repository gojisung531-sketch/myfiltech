import { defineStore } from 'pinia'

import { getStatus } from '@/api/system'

export const useSystemStore = defineStore('system', {
  state: () => ({
    loaded: false,
    llmConfigured: false,
    activeProvider: null,
    appVersion: '',
    adminMustChangePassword: false,
  }),
  actions: {
    async fetchStatus(force = false) {
      if (this.loaded && !force) return
      const data = await getStatus()
      this.llmConfigured = data.llm_configured
      this.activeProvider = data.active_provider
      this.appVersion = data.app_version
      this.adminMustChangePassword = data.admin_must_change_password
      this.loaded = true
    },
  },
})
