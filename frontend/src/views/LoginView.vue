<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { errorMessage } from '@/utils/errors'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    router.push(route.query.redirect || '/')
  } catch (err) {
    error.value = errorMessage(err, '로그인하지 못했습니다.')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="row justify-content-center pt-5">
    <div class="col-sm-8 col-md-5 col-lg-4">
      <div class="card shadow-sm">
        <div class="card-body p-4">
          <h1 class="h5 mb-1">로그인</h1>
          <p class="text-muted small mb-4">입찰담당자 계정으로 로그인하세요.</p>
          <form @submit.prevent="submit">
            <div class="mb-3">
              <label class="form-label" for="login-username">아이디</label>
              <input
                id="login-username"
                v-model="username"
                class="form-control"
                autocomplete="username"
                autofocus
                required
              />
            </div>
            <div class="mb-3">
              <label class="form-label" for="login-password">비밀번호</label>
              <input
                id="login-password"
                v-model="password"
                type="password"
                class="form-control"
                autocomplete="current-password"
                required
              />
            </div>
            <div v-if="error" class="alert alert-danger py-2 small">{{ error }}</div>
            <button class="btn btn-primary w-100" :disabled="loading">
              <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>로그인
            </button>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>
