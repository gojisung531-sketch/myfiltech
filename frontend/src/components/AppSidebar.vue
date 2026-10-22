<script setup>
import { computed, reactive, watch } from 'vue'
import { useRoute } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

defineProps({ open: { type: Boolean, default: false } })
const emit = defineEmits(['navigate'])

const auth = useAuthStore()
const route = useRoute()

// 기존 메뉴·권한을 그대로 옮긴 구성. admin: true 는 관리자 전용(라우터 가드와 동일).
const MENU = [
  { key: 'dashboard', label: '대시보드', icon: 'bi-speedometer2', to: '/' },
  {
    key: 'bids',
    label: '입찰 관리',
    icon: 'bi-file-earmark-text',
    to: '/admin/bids', // 그룹 이름을 누르면 대표 페이지로 이동
    admin: true,
    match: ['/admin/bids', '/bids/'],
    children: [
      { to: '/admin/bids', label: '공고 관리', icon: 'bi-list-ul', exact: true },
      { to: '/admin/bids/new', label: '공고 등록', icon: 'bi-plus-circle', exact: true },
    ],
  },
  {
    key: 'company',
    label: '필텍 자료',
    icon: 'bi-building',
    to: '/admin/company',
    admin: true,
    children: [
      { to: '/admin/company', label: '회사 정보', icon: 'bi-building' },
      { to: '/admin/products', label: '제품', icon: 'bi-box' },
      { to: '/admin/test-reports', label: '시험성적서', icon: 'bi-clipboard-data' },
      { to: '/admin/certificates', label: '인증서', icon: 'bi-patch-check' },
      { to: '/admin/delivery-records', label: '납품실적', icon: 'bi-truck' },
      { to: '/admin/documents', label: '문서', icon: 'bi-files' },
      { to: '/admin/metadata-schemas', label: '문서 분류', icon: 'bi-tags' },
    ],
  },
  {
    key: 'settings',
    label: '설정',
    icon: 'bi-gear',
    admin: true,
    children: [
      { to: '/admin/users', label: '사용자', icon: 'bi-people' },
      { to: '/admin/settings/llm', label: 'LLM 연결 · 모델', icon: 'bi-plug' },
      { to: '/admin/settings/prompts', label: '프롬프트', icon: 'bi-chat-square-text' },
      { to: '/admin/settings/tuning', label: '튜닝', icon: 'bi-sliders' },
      { to: '/admin/jobs', label: '작업', icon: 'bi-list-task' },
      { to: '/admin/llm-logs', label: 'LLM 호출 로그', icon: 'bi-journal-text' },
    ],
  },
]

const items = computed(() => MENU.filter((m) => !m.admin || auth.isAdmin))

function isChildActive(child) {
  const path = route.path
  if (child.exact) return path === child.to
  return path === child.to || path.startsWith(child.to + '/')
}
function isGroupActive(item) {
  if (item.children?.some(isChildActive)) return true
  return Boolean(item.match?.some((p) => route.path.startsWith(p)))
}
function isLeafActive(item) {
  if (item.to === '/') {
    return route.path === '/' || (!auth.isAdmin && route.path.startsWith('/bids/'))
  }
  return route.path === item.to
}

// 사용자가 직접 펼친/접은 상태. 현재 경로가 속한 그룹은 이동 시 자동으로 펼친다.
const expanded = reactive({})
watch(
  () => route.path,
  () => {
    for (const item of items.value) {
      if (item.children && isGroupActive(item)) expanded[item.key] = true
    }
  },
  { immediate: true },
)
function toggle(key) {
  expanded[key] = !expanded[key]
}
function onGroupLink(key) {
  expanded[key] = true
  emit('navigate')
}
</script>

<template>
  <aside id="ft-sidebar" class="ft-sidebar" :class="{ open }" aria-label="주 메뉴">
    <router-link class="ft-brand" to="/" @click="$emit('navigate')">
      <i class="bi bi-funnel"></i><span>FilTech Bid Assistant</span>
    </router-link>
    <nav v-if="auth.isAuthenticated" class="ft-menu">
      <ul class="list-unstyled mb-0">
        <li v-for="item in items" :key="item.key">
          <router-link
            v-if="!item.children"
            class="ft-link"
            :class="{ active: isLeafActive(item) }"
            :to="item.to"
            @click="$emit('navigate')"
          >
            <i :class="['bi', item.icon]"></i><span>{{ item.label }}</span>
          </router-link>
          <template v-else>
            <!-- 대표 페이지가 있는 그룹: 이름은 링크, 화살표는 별도 버튼(링크와 버튼을 중첩하지 않는다) -->
            <div v-if="item.to" class="ft-grouprow">
              <router-link
                class="ft-link ft-grouplink"
                :class="{ active: isGroupActive(item) }"
                :to="item.to"
                @click="onGroupLink(item.key)"
              >
                <i :class="['bi', item.icon]"></i><span>{{ item.label }}</span>
              </router-link>
              <button
                type="button"
                class="ft-caretbtn"
                :aria-expanded="Boolean(expanded[item.key])"
                :aria-controls="`ft-sub-${item.key}`"
                :aria-label="`${item.label} 하위 메뉴 ${expanded[item.key] ? '접기' : '펼치기'}`"
                @click="toggle(item.key)"
              >
                <i class="bi bi-chevron-down ft-caret" :class="{ flipped: expanded[item.key] }"></i>
              </button>
            </div>
            <button
              v-else
              type="button"
              class="ft-link ft-group"
              :class="{ active: isGroupActive(item) }"
              :aria-expanded="Boolean(expanded[item.key])"
              :aria-controls="`ft-sub-${item.key}`"
              @click="toggle(item.key)"
            >
              <i :class="['bi', item.icon]"></i><span>{{ item.label }}</span>
              <i class="bi bi-chevron-down ft-caret" :class="{ flipped: expanded[item.key] }"></i>
            </button>
            <ul v-show="expanded[item.key]" :id="`ft-sub-${item.key}`" class="ft-sub list-unstyled">
              <li v-for="child in item.children" :key="child.to">
                <router-link
                  class="ft-link ft-child"
                  :class="{ active: isChildActive(child) }"
                  :to="child.to"
                  @click="$emit('navigate')"
                >
                  <i :class="['bi', child.icon]"></i><span>{{ child.label }}</span>
                </router-link>
              </li>
            </ul>
          </template>
        </li>
      </ul>
    </nav>
  </aside>
</template>

<style scoped>
.ft-sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  width: var(--ft-sidebar-width);
  background: var(--ft-sidebar);
  color: #fff;
  overflow-y: auto;
  z-index: 1040;
  transition: transform 0.25s ease-out;
  transform: translateX(-100%);
}
.ft-sidebar.open {
  transform: none;
}
@media (max-width: 991.98px) {
  .ft-sidebar.open {
    box-shadow: 0 0 2rem rgba(0, 0, 0, 0.35);
  }
}
.ft-brand {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  height: var(--ft-topbar-height);
  padding: 0 1.25rem;
  color: #fff;
  font-weight: 700;
  text-decoration: none;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}
.ft-brand:hover {
  color: #fff;
}
.ft-menu {
  padding: 0.75rem 0.75rem 2rem;
}
.ft-link {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  width: 100%;
  padding: 0.6rem 0.75rem;
  margin-bottom: 0.15rem;
  border: 0;
  border-radius: 0.4rem;
  background: transparent;
  color: rgba(255, 255, 255, 0.78);
  font-size: 0.95rem;
  text-align: left;
  text-decoration: none;
}
.ft-link:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.08);
}
.ft-link:focus-visible {
  outline: 2px solid #fff;
  outline-offset: -2px;
}
.ft-link.active {
  color: #fff;
  background: rgba(255, 255, 255, 0.14);
}
.ft-grouprow {
  display: flex;
  align-items: stretch;
  gap: 0.15rem;
  margin-bottom: 0.15rem;
}
.ft-grouplink {
  flex: 1;
  width: auto;
  min-width: 0;
  margin-bottom: 0;
}
.ft-caretbtn {
  flex: 0 0 2.4rem;
  border: 0;
  border-radius: 0.4rem;
  background: transparent;
  color: rgba(255, 255, 255, 0.78);
}
.ft-caretbtn:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.08);
}
.ft-caretbtn:focus-visible {
  outline: 2px solid #fff;
  outline-offset: -2px;
}
.ft-group.active:not(:hover) {
  background: rgba(255, 255, 255, 0.1);
}
.ft-caret {
  margin-left: auto;
  font-size: 0.75rem;
  transition: transform 0.2s;
}
.ft-caret.flipped {
  transform: rotate(180deg);
}
.ft-sub {
  margin: 0 0 0.35rem 1rem;
  padding-left: 0.5rem;
  border-left: 1px solid rgba(255, 255, 255, 0.15);
}
.ft-child {
  font-size: 0.9rem;
  padding: 0.45rem 0.75rem;
}
</style>
