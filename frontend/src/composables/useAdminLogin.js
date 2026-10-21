import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'
import { errorMessage } from '@/utils/errors'

// Shared by AdminLoginView and the header login box (specs/03 §1, §4).
export function useAdminLogin() {
  const auth = useAuthStore()
  const system = useSystemStore()
  const router = useRouter()
  const loading = ref(false)
  const error = ref('')

  async function submit(username, password, redirect) {
    error.value = ''
    loading.value = true
    try {
      const user = await auth.login(username, password)
      if (user.role !== 'ADMIN') {
        await auth.logout()
        error.value = '관리자 권한이 없습니다.'
        return false
      }
      await system.fetchStatus(true)
      if (!system.llmConfigured) {
        await router.push({
          name: 'admin-llm-settings',
          query: { reason: 'llm_not_configured' },
        })
      } else {
        await router.push(redirect || '/')
      }
      return true
    } catch (err) {
      error.value = errorMessage(err, '로그인하지 못했습니다.')
      return false
    } finally {
      loading.value = false
    }
  }

  return { submit, loading, error }
}
