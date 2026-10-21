<script setup>
const TABS = [
  { to: '/admin/company', label: '회사 정보', icon: 'bi-building' },
  { to: '/admin/products', label: '제품', icon: 'bi-box' },
  { to: '/admin/test-reports', label: '시험성적서', icon: 'bi-clipboard-data' },
  { to: '/admin/certificates', label: '인증서', icon: 'bi-patch-check' },
  { to: '/admin/delivery-records', label: '납품실적', icon: 'bi-truck' },
  { to: '/admin/documents', label: '문서', icon: 'bi-files' },
  { to: '/admin/metadata-schemas', label: '문서 분류', icon: 'bi-tags' },
]
</script>

<template>
  <div>
    <h1 class="h4 mb-3">회사 자료</h1>
    <ul class="nav nav-tabs mb-4">
      <li v-for="tab in TABS" :key="tab.to" class="nav-item">
        <router-link class="nav-link" :to="tab.to" active-class="active">
          <i :class="['bi', tab.icon, 'me-1']"></i>{{ tab.label }}
        </router-link>
      </li>
    </ul>
  </div>
</template>
