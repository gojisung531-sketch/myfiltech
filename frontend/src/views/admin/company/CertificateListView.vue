<script setup>
import { certificates } from '@/api/company'
import CompanyNav from '@/components/CompanyNav.vue'
import CrudPage from '@/components/CrudPage.vue'
import { CERT_STATUS_VARIANT, formatDate } from '@/utils/format'
import { CERT_STATUSES, CERT_TYPES } from '@/utils/options'

const COLUMNS = [
  { key: 'cert_no', label: '인증 번호' },
  { key: 'name', label: '인증명' },
  { key: 'cert_type_label', label: '종류' },
  {
    key: 'validity',
    label: '유효기간',
    format: (r) => `${formatDate(r.valid_from)} ~ ${formatDate(r.valid_until)}`,
  },
  { key: 'status', label: '상태' },
]

const FILTERS = [{ key: 'status', label: '상태', options: CERT_STATUSES }]

const FIELDS = [
  { key: 'cert_no', label: '인증 번호', required: true, col: 'col-md-4' },
  { key: 'name', label: '인증명', col: 'col-md-5' },
  {
    key: 'cert_type',
    label: '종류',
    type: 'select',
    options: CERT_TYPES,
    required: true,
    col: 'col-md-3',
  },
  { key: 'standard', label: '규격', col: 'col-md-6' },
  { key: 'holder', label: '인증 대상', col: 'col-md-6' },
  { key: 'scope', label: '인증 범위', type: 'textarea', col: 'col-12' },
  { key: 'product_codes', label: '세부품명번호', type: 'tags', col: 'col-md-6' },
  { key: 'issuer', label: '발급 기관', col: 'col-md-6' },
  { key: 'issue_date', label: '최초/갱신 인증일', type: 'date', col: 'col-md-4' },
  { key: 'valid_from', label: '유효 시작일', type: 'date', col: 'col-md-4' },
  { key: 'valid_until', label: '유효 종료일', type: 'date', col: 'col-md-4' },
  { key: 'notes', label: '비고', type: 'textarea', col: 'col-12' },
]
</script>

<template>
  <div>
    <CompanyNav />
    <CrudPage
      title="인증서"
      :api="certificates"
      :columns="COLUMNS"
      :fields="FIELDS"
      :filters="FILTERS"
      :defaults="{ cert_type: 'OTHER', product_codes: [] }"
      :item-label="(r) => r.cert_no"
      search-placeholder="번호, 인증명, 규격, 범위"
    >
      <template #notice="{ rows }">
        <div v-if="rows.some((r) => r.status === 'EXPIRED')" class="alert alert-danger py-2">
          <i class="bi bi-exclamation-octagon me-1"></i>만료된 인증서가 있습니다:
          {{
            rows
              .filter((r) => r.status === 'EXPIRED')
              .map((r) => r.name || r.cert_no)
              .join(', ')
          }}
        </div>
        <div v-else-if="rows.some((r) => r.status === 'EXPIRING')" class="alert alert-warning py-2">
          만료가 임박한 인증서가 있습니다.
        </div>
      </template>
      <template #cell-status="{ row }">
        <span :class="['badge', `bg-${CERT_STATUS_VARIANT[row.status]}`]">{{
          row.status_label
        }}</span>
      </template>
    </CrudPage>
  </div>
</template>
