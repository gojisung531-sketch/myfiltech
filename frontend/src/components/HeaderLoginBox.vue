<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAdminLogin } from '@/composables/useAdminLogin'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const { submit, loading, error } = useAdminLogin()

const open = ref(false)
const root = ref(null)
const username = ref('')
const password = ref('')

const ROLE_LABELS = { ADMIN: '관리자', BID_MANAGER: '입찰담당자' }

function onDocumentClick(event) {
  if (root.value && !root.value.contains(event.target)) open.value = false
}
onMounted(() => document.addEventListener('click', onDocumentClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick))

async function login() {
  if (await submit(username.value, password.value)) {
    open.value = false
    username.value = ''
    password.value = ''
  }
}

async function logout() {
  open.value = false
  await auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div ref="root" class="dropdown">
    <template v-if="auth.isAuthenticated">
      <button class="btn btn-outline-light btn-sm dropdown-toggle" @click="open = !open">
        <i class="bi bi-person-circle me-1"></i>{{ auth.user.display_name || auth.user.username }}
        <span class="badge bg-secondary ms-1">{{ ROLE_LABELS[auth.user.role] }}</span>
      </button>
      <ul class="dropdown-menu dropdown-menu-end" :class="{ show: open }">
        <li>
          <router-link class="dropdown-item" to="/account/password" @click="open = false">
            <i class="bi bi-key me-2"></i>비밀번호 변경
          </router-link>
        </li>
        <li><hr class="dropdown-divider" /></li>
        <li>
          <button class="dropdown-item" @click="logout">
            <i class="bi bi-box-arrow-right me-2"></i>로그아웃
          </button>
        </li>
      </ul>
    </template>

    <template v-else>
      <button class="btn btn-outline-light btn-sm dropdown-toggle" @click="open = !open">
        <i class="bi bi-shield-lock me-1"></i>관리자 로그인
      </button>
      <div class="dropdown-menu dropdown-menu-end p-3 login-box" :class="{ show: open }">
        <form @submit.prevent="login">
          <div class="mb-2">
            <label class="form-label small mb-1" for="hdr-username">아이디</label>
            <input
              id="hdr-username"
              v-model="username"
              class="form-control form-control-sm"
              autocomplete="username"
              required
            />
          </div>
          <div class="mb-2">
            <label class="form-label small mb-1" for="hdr-password">비밀번호</label>
            <input
              id="hdr-password"
              v-model="password"
              type="password"
              class="form-control form-control-sm"
              autocomplete="current-password"
              required
            />
          </div>
          <div v-if="error" class="text-danger small mb-2">{{ error }}</div>
          <button class="btn btn-primary btn-sm w-100" :disabled="loading">
            <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>로그인
          </button>
        </form>
      </div>
    </template>
  </div>
</template>

<style scoped>
.login-box {
  width: 260px;
}
</style>
