<script setup>
const TABS = [
  { to: '/admin/settings/llm', label: 'LLM 연결 · 모델', icon: 'bi-plug' },
  { to: '/admin/settings/prompts', label: '프롬프트', icon: 'bi-chat-square-text' },
  { to: '/admin/settings/tuning', label: '튜닝', icon: 'bi-sliders' },
  { to: '/admin/jobs', label: '작업', icon: 'bi-list-task' },
  { to: '/admin/llm-logs', label: 'LLM 호출 로그', icon: 'bi-journal-text' },
]
</script>

<template>
  <div>
    <h1 class="h4 mb-3">설정 · 운영</h1>
    <ul class="nav nav-tabs mb-4">
      <li v-for="tab in TABS" :key="tab.to" class="nav-item">
        <router-link class="nav-link" :to="tab.to" active-class="active">
          <i :class="['bi', tab.icon, 'me-1']"></i>{{ tab.label }}
        </router-link>
      </li>
    </ul>
  </div>
</template>
