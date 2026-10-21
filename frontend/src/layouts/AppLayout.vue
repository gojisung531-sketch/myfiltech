<script setup>
import AppNavbar from '@/components/AppNavbar.vue'
import ToastHost from '@/components/ToastHost.vue'
import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'

const auth = useAuthStore()
const system = useSystemStore()
</script>

<template>
  <div class="min-vh-100 d-flex flex-column">
    <AppNavbar />
    <div
      v-if="auth.isAdmin && system.loaded && !system.llmConfigured"
      class="alert alert-danger rounded-0 mb-0 py-2 text-center"
    >
      <i class="bi bi-exclamation-octagon me-1"></i>LLM API Key 미설정 —
      <router-link to="/admin/settings/llm" class="alert-link">설정하기</router-link>
    </div>
    <div
      v-if="auth.user?.must_change_password"
      class="alert alert-warning rounded-0 mb-0 py-2 text-center"
    >
      <i class="bi bi-shield-exclamation me-1"></i>초기 비밀번호를 사용 중입니다.
      <router-link to="/account/password" class="alert-link">비밀번호 변경</router-link>을
      권장합니다.
    </div>
    <main class="container-fluid py-4 flex-grow-1">
      <slot />
    </main>
    <ToastHost />
  </div>
</template>
