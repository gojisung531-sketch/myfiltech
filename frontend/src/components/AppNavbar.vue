<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import HeaderLoginBox from './HeaderLoginBox.vue'

const auth = useAuthStore()
const route = useRoute()

const COMPANY_PATHS = [
  '/admin/company',
  '/admin/products',
  '/admin/test-reports',
  '/admin/certificates',
  '/admin/delivery-records',
  '/admin/documents',
  '/admin/metadata-schemas',
]
const inCompanySection = computed(() => COMPANY_PATHS.some((p) => route.path.startsWith(p)))
</script>

<template>
  <nav class="navbar navbar-expand navbar-dark bg-dark">
    <div class="container-fluid">
      <router-link class="navbar-brand" to="/">
        <i class="bi bi-funnel me-2"></i>FilTech Bid Assistant
      </router-link>
      <ul v-if="auth.isAuthenticated" class="navbar-nav me-auto">
        <li class="nav-item">
          <router-link class="nav-link" to="/" exact-active-class="active">대시보드</router-link>
        </li>
        <template v-if="auth.isAdmin">
          <li class="nav-item">
            <router-link class="nav-link" :class="{ active: inCompanySection }" to="/admin/company">
              회사 자료
            </router-link>
          </li>
          <li class="nav-item">
            <router-link class="nav-link" to="/admin/bids" active-class="active">
              입찰 공고
            </router-link>
          </li>
          <li class="nav-item">
            <router-link class="nav-link" to="/admin/users" active-class="active">
              사용자
            </router-link>
          </li>
          <li class="nav-item">
            <router-link
              class="nav-link"
              :class="{
                active: ['/admin/settings', '/admin/jobs', '/admin/llm-logs'].some((p) =>
                  route.path.startsWith(p),
                ),
              }"
              to="/admin/settings/llm"
            >
              설정
            </router-link>
          </li>
        </template>
      </ul>
      <div class="ms-auto">
        <HeaderLoginBox />
      </div>
    </div>
  </nav>
</template>
