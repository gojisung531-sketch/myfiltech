import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'
import { useToastStore } from '@/stores/toast'
import DashboardView from '@/views/DashboardView.vue'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue') },
  {
    path: '/admin/login',
    name: 'admin-login',
    component: () => import('@/views/AdminLoginView.vue'),
  },
  { path: '/', name: 'dashboard', component: DashboardView, meta: { requiresAuth: true } },
  {
    path: '/bids/:id',
    name: 'bid-detail',
    component: () => import('@/views/bids/BidDetailView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/bids/:id/drafts/:type',
    name: 'draft-editor',
    component: () => import('@/views/bids/DraftEditorView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/account/password',
    name: 'change-password',
    component: () => import('@/views/ChangePasswordView.vue'),
    meta: { requiresAuth: true },
  },
  { path: '/admin', redirect: '/admin/users' },
  {
    path: '/admin/users',
    name: 'admin-users',
    component: () => import('@/views/admin/UserAdminView.vue'),
    meta: { requiresAuth: true, admin: true },
  },
  ...[
    ['/admin/company', 'admin-company', () => import('@/views/admin/company/CompanyInfoView.vue')],
    [
      '/admin/products',
      'admin-products',
      () => import('@/views/admin/company/ProductListView.vue'),
    ],
    [
      '/admin/products/:id',
      'admin-product',
      () => import('@/views/admin/company/ProductDetailView.vue'),
    ],
    [
      '/admin/test-reports',
      'admin-test-reports',
      () => import('@/views/admin/company/TestReportListView.vue'),
    ],
    [
      '/admin/certificates',
      'admin-certificates',
      () => import('@/views/admin/company/CertificateListView.vue'),
    ],
    [
      '/admin/delivery-records',
      'admin-delivery-records',
      () => import('@/views/admin/company/DeliveryRecordListView.vue'),
    ],
    [
      '/admin/documents',
      'admin-documents',
      () => import('@/views/admin/documents/DocumentListView.vue'),
    ],
    [
      '/admin/documents/:id',
      'admin-document',
      () => import('@/views/admin/documents/DocumentReviewView.vue'),
    ],
    [
      '/admin/metadata-schemas',
      'admin-metadata-schemas',
      () => import('@/views/admin/documents/MetadataSchemaView.vue'),
    ],
    ['/admin/jobs', 'admin-jobs', () => import('@/views/admin/ops/JobsView.vue')],
    ['/admin/llm-logs', 'admin-llm-logs', () => import('@/views/admin/ops/LLMLogsView.vue')],
    ['/admin/bids', 'admin-bids', () => import('@/views/admin/bids/BidAdminListView.vue')],
    ['/admin/bids/new', 'admin-bid-new', () => import('@/views/admin/bids/BidCreateView.vue')],
    ['/admin/bids/:id/edit', 'admin-bid-edit', () => import('@/views/admin/bids/BidEditView.vue')],
  ].map(([path, name, component]) => ({
    path,
    name,
    component,
    meta: { requiresAuth: true, admin: true },
  })),
  {
    path: '/admin/settings/llm',
    name: 'admin-llm-settings',
    component: () => import('@/views/admin/LLMSettingsView.vue'),
    meta: { requiresAuth: true, admin: true },
  },
  {
    path: '/admin/settings/prompts',
    name: 'admin-prompt-settings',
    component: () => import('@/views/admin/PromptSettingsView.vue'),
    meta: { requiresAuth: true, admin: true },
  },
  {
    path: '/admin/settings/tuning',
    name: 'admin-tuning-settings',
    component: () => import('@/views/admin/TuningSettingsView.vue'),
    meta: { requiresAuth: true, admin: true },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Global guard — order follows specs/11 §3.1.
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  const system = useSystemStore()

  try {
    await system.fetchStatus()
  } catch {
    // Backend unreachable: let the page render; API calls will surface the error.
  }

  if (system.loaded && !system.llmConfigured && !auth.isAdmin && to.name !== 'admin-login') {
    return {
      name: 'admin-login',
      query: { redirect: '/admin/settings/llm', reason: 'llm_not_configured' },
    }
  }

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return {
      name: to.meta.admin ? 'admin-login' : 'login',
      query: { redirect: to.fullPath },
    }
  }

  if (to.meta.admin && !auth.isAdmin) {
    useToastStore().error('관리자 권한이 없습니다.')
    return { name: 'dashboard' }
  }

  if (to.name === 'login' && auth.isAuthenticated) {
    return { name: 'dashboard' }
  }
  return true
})

export default router
