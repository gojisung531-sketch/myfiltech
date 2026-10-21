<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { changePassword } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'

const auth = useAuthStore()
const system = useSystemStore()
const toast = useToastStore()
const router = useRouter()

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (newPassword.value !== confirmPassword.value) {
    error.value = '새 비밀번호가 서로 일치하지 않습니다.'
    return
  }
  loading.value = true
  try {
    const user = await changePassword(oldPassword.value, newPassword.value)
    auth.setUser(user)
    await system.fetchStatus(true)
    toast.success('비밀번호를 변경했습니다.')
    router.push('/')
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="row justify-content-center pt-4">
    <div class="col-sm-8 col-md-6 col-lg-4">
      <div class="card shadow-sm">
        <div class="card-body p-4">
          <h1 class="h5 mb-4">비밀번호 변경</h1>
          <form @submit.prevent="submit">
            <div class="mb-3">
              <label class="form-label" for="pw-old">현재 비밀번호</label>
              <input
                id="pw-old"
                v-model="oldPassword"
                type="password"
                class="form-control"
                autocomplete="current-password"
                required
              />
            </div>
            <div class="mb-3">
              <label class="form-label" for="pw-new">새 비밀번호</label>
              <input
                id="pw-new"
                v-model="newPassword"
                type="password"
                class="form-control"
                autocomplete="new-password"
                required
              />
              <div class="form-text">8자 이상, 숫자만으로 구성할 수 없습니다.</div>
            </div>
            <div class="mb-3">
              <label class="form-label" for="pw-confirm">새 비밀번호 확인</label>
              <input
                id="pw-confirm"
                v-model="confirmPassword"
                type="password"
                class="form-control"
                autocomplete="new-password"
                required
              />
            </div>
            <div v-if="error" class="alert alert-danger py-2 small">{{ error }}</div>
            <button class="btn btn-primary w-100" :disabled="loading">
              <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>변경
            </button>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>
