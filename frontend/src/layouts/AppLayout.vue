<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import AppSidebar from '@/components/AppSidebar.vue'
import HeaderLoginBox from '@/components/HeaderLoginBox.vue'
import ToastHost from '@/components/ToastHost.vue'
import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'

const auth = useAuthStore()
const system = useSystemStore()
const route = useRoute()

const TITLES = {
  dashboard: '대시보드',
  'bid-detail': '공고 상세',
  'draft-editor': '초안 편집',
  'change-password': '비밀번호 변경',
  'admin-users': '설정 · 사용자',
  'admin-company': '필텍 자료 · 회사 정보',
  'admin-products': '필텍 자료 · 제품',
  'admin-product': '필텍 자료 · 제품 상세',
  'admin-test-reports': '필텍 자료 · 시험성적서',
  'admin-certificates': '필텍 자료 · 인증서',
  'admin-delivery-records': '필텍 자료 · 납품실적',
  'admin-documents': '필텍 자료 · 문서',
  'admin-document': '필텍 자료 · 문서 검토',
  'admin-metadata-schemas': '필텍 자료 · 문서 분류',
  'admin-bids': '입찰 관리 · 공고 관리',
  'admin-bid-new': '입찰 관리 · 공고 등록',
  'admin-bid-edit': '입찰 관리 · 공고 수정',
  'admin-llm-settings': '설정 · LLM 연결',
  'admin-prompt-settings': '설정 · 프롬프트',
  'admin-tuning-settings': '설정 · 튜닝',
  'admin-jobs': '설정 · 작업',
  'admin-llm-logs': '설정 · LLM 호출 로그',
  login: '로그인',
  'admin-login': '관리자 로그인',
}
const title = computed(() => TITLES[route.name] || 'FilTech Bid Assistant')

const STORAGE_KEY = 'filtech.sidebarOpen'
const showSidebar = computed(() => auth.isAuthenticated)
// 넓은 화면: 기본 펼침(저장된 값 우선). 좁은 화면: 기본 닫힘, 메뉴 버튼으로 열기.
const wide = ref(true)
const sidebarOpen = ref(false)
let query = null

function readStored() {
  try {
    return localStorage.getItem(STORAGE_KEY) !== '0'
  } catch {
    return true
  }
}
function onViewport(event) {
  wide.value = event.matches
  sidebarOpen.value = event.matches ? readStored() : false
}
onMounted(() => {
  query = window.matchMedia('(min-width: 992px)')
  onViewport(query)
  query.addEventListener('change', onViewport)
})
onBeforeUnmount(() => query?.removeEventListener('change', onViewport))

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
  if (wide.value) {
    try {
      localStorage.setItem(STORAGE_KEY, sidebarOpen.value ? '1' : '0')
    } catch {
      // 저장 불가 환경에서는 현재 화면에서만 유지
    }
  }
}
function closeIfNarrow() {
  if (!wide.value) sidebarOpen.value = false
}
watch(() => route.fullPath, closeIfNarrow)
</script>

<template>
  <div class="ft-shell">
    <AppSidebar v-if="showSidebar" :open="sidebarOpen" @navigate="closeIfNarrow" />
    <div
      v-if="showSidebar && sidebarOpen && !wide"
      class="ft-backdrop"
      aria-hidden="true"
      @click="sidebarOpen = false"
    ></div>

    <div class="ft-page" :class="{ 'with-sidebar': showSidebar && sidebarOpen && wide }">
      <header class="ft-topbar">
        <button
          v-if="showSidebar"
          type="button"
          class="btn btn-outline-secondary btn-sm ft-toggle"
          :aria-expanded="sidebarOpen"
          aria-controls="ft-sidebar"
          aria-label="메뉴 열기/닫기"
          @click="toggleSidebar"
        >
          <i class="bi bi-list"></i>
        </button>
        <router-link v-else class="ft-top-brand" to="/">
          <i class="bi bi-funnel me-2"></i>FilTech Bid Assistant
        </router-link>
        <h1 class="ft-title">{{ title }}</h1>
        <div class="ms-auto">
          <HeaderLoginBox />
        </div>
      </header>

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
    </div>
    <ToastHost />
  </div>
</template>

<style scoped>
.ft-shell {
  min-height: 100vh;
}
.ft-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  min-width: 0;
  transition: margin 0.25s ease-out;
}
.ft-page.with-sidebar {
  margin-left: var(--ft-sidebar-width);
}
.ft-topbar {
  position: sticky;
  top: 0;
  z-index: 1020;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  height: var(--ft-topbar-height);
  padding: 0 1.25rem;
  background: var(--ft-surface);
  border-bottom: 1px solid var(--ft-border);
}
.ft-toggle {
  font-size: 1.1rem;
  line-height: 1;
}
.ft-top-brand {
  font-weight: 700;
  text-decoration: none;
  color: var(--ft-text);
}
.ft-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.ft-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1030;
  background: rgba(36, 55, 70, 0.5);
}
@media (max-width: 575.98px) {
  .ft-topbar {
    padding: 0 0.75rem;
  }
  .ft-top-brand {
    display: none;
  }
}
</style>
