<script setup>
import { products } from '@/api/company'
import CompanyNav from '@/components/CompanyNav.vue'
import CrudPage from '@/components/CrudPage.vue'
import { formatNumber, productDimension } from '@/utils/format'
import { FILTER_TYPES, YES_NO } from '@/utils/options'

import { PRODUCT_FIELDS } from './productFields'

const COLUMNS = [
  { key: 'model_no', label: '모델명' },
  { key: 'filter_type_label', label: '형식' },
  { key: 'dimension', label: '치수', format: productDimension },
  { key: 'grades', label: '등급' },
  {
    key: 'rated_airflow_m3h',
    label: '정격풍량(m³/h)',
    class: 'text-end',
    format: (r) => formatNumber(r.rated_airflow_m3h),
  },
  { key: 'initial_dp_pa', label: '초기차압(Pa)', class: 'text-end' },
  { key: 'test_report_count', label: '성적서', class: 'text-end' },
]

const FILTERS = [
  { key: 'filter_type', label: '형식', options: FILTER_TYPES },
  { key: 'is_active', label: '판매 중', options: YES_NO },
]

function grades(row) {
  return [
    row.iso16890_class,
    row.iso29461_class,
    row.en1822_class,
    row.en779_class && `EN779 ${row.en779_class}`,
  ].filter(Boolean)
}
</script>

<template>
  <div>
    <CompanyNav />
    <CrudPage
      title="제품"
      :api="products"
      :columns="COLUMNS"
      :fields="PRODUCT_FIELDS"
      :filters="FILTERS"
      :defaults="{
        filter_type: 'OTHER',
        is_active: true,
        airflow_dp_curve: [],
        frame_options: [],
        dimension_variants: [],
        extra: {},
      }"
      :item-label="(r) => r.model_no"
      search-placeholder="모델명, 제품명, 용도"
    >
      <template #cell-model_no="{ row }">
        <router-link :to="`/admin/products/${row.id}`" class="fw-semibold">{{
          row.model_no
        }}</router-link>
        <span v-if="!row.is_active" class="badge bg-secondary ms-1">단종</span>
        <div class="small text-muted">{{ row.name }}</div>
      </template>
      <template #cell-grades="{ row }">
        <span v-for="g in grades(row)" :key="g" class="badge bg-light text-dark border me-1">{{
          g
        }}</span>
      </template>
    </CrudPage>
  </div>
</template>
