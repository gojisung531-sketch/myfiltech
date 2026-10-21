<script setup>
import { computed, onMounted, ref } from 'vue'

import { products, testReports } from '@/api/company'
import CompanyNav from '@/components/CompanyNav.vue'
import CrudPage from '@/components/CrudPage.vue'
import { formatDate } from '@/utils/format'
import { STANDARD_FAMILIES } from '@/utils/options'

const productOptions = ref([])

onMounted(async () => {
  const data = await products.list({ page_size: 200 })
  productOptions.value = data.results.map((p) => ({ value: p.id, label: p.model_no }))
})

const COLUMNS = [
  { key: 'report_no', label: '성적서 번호' },
  { key: 'product_model_no', label: '모델' },
  { key: 'standard', label: '시험 규격' },
  { key: 'result_class', label: '판정 결과' },
  { key: 'issue_date', label: '발행일', format: (r) => formatDate(r.issue_date) },
  { key: 'flags', label: '비고' },
]

const FILTERS = [{ key: 'standard_family', label: '규격', options: STANDARD_FAMILIES }]

const fields = computed(() => [
  { key: 'report_no', label: '성적서 번호', required: true, col: 'col-md-4' },
  { key: 'product', label: '제품', type: 'select', options: productOptions.value, col: 'col-md-4' },
  { key: 'model_no_text', label: '모델명(원문)', col: 'col-md-4' },
  { key: 'sample_name', label: '시료명', col: 'col-md-6' },
  { key: 'sample_dimension', label: '시료 치수', col: 'col-md-6' },
  { key: 'standard', label: '시험 규격', col: 'col-md-6' },
  {
    key: 'standard_family',
    label: '규격 계열',
    type: 'select',
    options: STANDARD_FAMILIES,
    required: true,
    col: 'col-md-3',
  },
  { key: 'result_class', label: '판정 결과', col: 'col-md-3' },
  { key: 'test_date', label: '시험 일자', type: 'date', col: 'col-md-3' },
  { key: 'issue_date', label: '발행 일자', type: 'date', col: 'col-md-3' },
  { key: 'lab_name', label: '시험 기관', col: 'col-md-6' },
  { key: 'lab_accreditation', label: '인정 현황', col: 'col-md-6' },
  { key: 'test_airflow_m3h', label: '시험 풍량', type: 'number', unit: 'm³/h', col: 'col-md-3' },
  { key: 'initial_dp_pa', label: '초기 차압', type: 'number', unit: 'Pa', col: 'col-md-3' },
  { key: 'is_obsolete_standard', label: '폐지 규격', type: 'checkbox', col: 'col-md-3' },
  { key: 'is_official_certification', label: '공식 인증 시험', type: 'checkbox', col: 'col-md-3' },
  { key: 'notes', label: '비고', type: 'textarea', col: 'col-12' },
  { key: 'results', label: '시험 결과', type: 'json', empty: {}, col: 'col-md-6', rows: 6 },
  { key: 'conditions', label: '시험 조건', type: 'json', empty: {}, col: 'col-md-6', rows: 6 },
])
</script>

<template>
  <div>
    <CompanyNav />
    <CrudPage
      title="시험성적서"
      :api="testReports"
      :columns="COLUMNS"
      :fields="fields"
      :filters="FILTERS"
      :defaults="{
        standard_family: 'OTHER',
        is_official_certification: true,
        results: {},
        conditions: {},
      }"
      :item-label="(r) => r.report_no"
      search-placeholder="번호, 모델, 규격, 결과"
    >
      <template #cell-flags="{ row }">
        <span v-if="row.is_obsolete_standard" class="badge bg-warning text-dark me-1"
          >폐지 규격</span
        >
        <span v-if="!row.is_official_certification" class="badge bg-secondary">공식 인증 아님</span>
      </template>
    </CrudPage>
  </div>
</template>
