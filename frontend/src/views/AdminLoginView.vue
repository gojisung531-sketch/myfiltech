<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'

import { useAdminLogin } from '@/composables/useAdminLogin'

const route = useRoute()
const { submit, loading, error } = useAdminLogin()

const username = ref('')
const password = ref('')
const llmMissing = computed(() => route.query.reason === 'llm_not_configured')

function login() {
  submit(username.value, password.value, route.query.redirect)
}
</script>

<template>
  <div class="row justify-content-center pt-5">
    <div class="col-sm-8 col-md-5 col-lg-4">
      <div v-if="llmMissing" class="alert alert-warning">
        <i class="bi bi-exclamation-triangle me-1"></i>LLM API Key가 설정되지 않았습니다. 관리자로
        로그인하여 설정하세요.
      </div>
      <div class="card shadow-sm">
        <div class="card-body p-4">
          <h1 class="h5 mb-1"><i class="bi bi-shield-lock me-1"></i>관리자 로그인</h1>
          <p class="text-muted small mb-4">관리자 계정으로 로그인하세요.</p>
          <form @submit.prevent="login">
            <div class="mb-3">
              <label class="form-label" for="admin-username">아이디</label>
              <input
                id="admin-username"
                v-model="username"
                class="form-control"
                autocomplete="username"
                autofocus
                required
              />
            </div>
            <div class="mb-3">
              <label class="form-label" for="admin-password">비밀번호</label>
              <input
                id="admin-password"
                v-model="password"
                type="password"
                class="form-control"
                autocomplete="current-password"
                required
              />
            </div>
            <div v-if="error" class="alert alert-danger py-2 small">{{ error }}</div>
            <button class="btn btn-dark w-100" :disabled="loading">
              <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>로그인
            </button>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>
