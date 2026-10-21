<script setup>
import { onMounted, ref } from 'vue'

import { getCompany, updateCompany } from '@/api/company'
import CompanyNav from '@/components/CompanyNav.vue'
import EntityForm from '@/components/EntityForm.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/format'

const FIELDS = [
  { key: 'name', label: '회사명', required: true },
  { key: 'ceo', label: '대표자' },
  { key: 'business_no', label: '사업자등록번호' },
  { key: 'phone', label: '연락처' },
  { key: 'email', label: '이메일' },
  { key: 'homepage', label: '홈페이지' },
  { key: 'address', label: '주소', col: 'col-12' },
  { key: 'established_date', label: '설립일', type: 'date' },
  { key: 'employees', label: '임직원 수', type: 'number' },
  {
    key: 'is_sme',
    label: '중소기업 여부',
    type: 'select',
    options: [
      { value: true, label: '예' },
      { value: false, label: '아니오' },
    ],
  },
  { key: 'sme_cert_valid_until', label: '중소기업확인서 유효기간', type: 'date' },
  {
    key: 'g2b_registered_items',
    label: '나라장터 등록 물품 (세부품명번호)',
    type: 'json',
    col: 'col-12',
    empty: [],
    help: '예: [{"code": "4016150501", "name": "공기여과기"}]',
  },
  { key: 'main_products', label: '주요 제품', type: 'textarea', col: 'col-12' },
  { key: 'description', label: '회사 소개', type: 'textarea', col: 'col-12', rows: 5 },
]

const toast = useToastStore()
const company = ref(null)
const form = ref(null)
const saving = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    company.value = await getCompany()
  } catch (err) {
    toast.error(errorMessage(err))
  }
})

async function save() {
  error.value = ''
  let payload
  try {
    payload = form.value.collect()
  } catch (err) {
    error.value = err.message
    return
  }
  saving.value = true
  try {
    company.value = await updateCompany(payload)
    toast.success('회사 정보를 저장했습니다.')
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div>
    <CompanyNav />
    <div v-if="!company" class="text-center py-5"><span class="spinner-border"></span></div>
    <form v-else class="card" @submit.prevent="save">
      <div class="card-body">
        <p class="small text-muted">
          회사 소개 문서(TXT·DOCX·HWP·PDF)를 <router-link to="/admin/documents">문서</router-link>
          탭에 올리면 추출된 값을 검토 후 반영할 수 있습니다.
        </p>
        <EntityForm ref="form" :fields="FIELDS" :model-value="company" id-prefix="company" />
        <div v-if="error" class="alert alert-danger py-2 small mt-3 mb-0">{{ error }}</div>
      </div>
      <div class="card-footer d-flex align-items-center">
        <span class="small text-muted me-auto">
          최종 수정: {{ formatDateTime(company.updated_at) }}
        </span>
        <button class="btn btn-primary" :disabled="saving">
          <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>저장
        </button>
      </div>
    </form>
  </div>
</template>
