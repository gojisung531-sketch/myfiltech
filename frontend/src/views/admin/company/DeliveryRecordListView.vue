<script setup>
import { computed, onMounted, ref } from 'vue'

import { deliveryRecords, products } from '@/api/company'
import CompanyNav from '@/components/CompanyNav.vue'
import CrudPage from '@/components/CrudPage.vue'
import { formatNumber } from '@/utils/format'
import { PLANT_TYPES, YES_NO } from '@/utils/options'

const productOptions = ref([])

onMounted(async () => {
  const data = await products.list({ page_size: 200 })
  productOptions.value = data.results.map((p) => ({ value: p.id, label: p.model_no }))
})

const COLUMNS = [
  { key: 'delivered_ym', label: '납품 시기' },
  { key: 'client', label: '발주처' },
  { key: 'project_name', label: '사업명' },
  { key: 'item_desc', label: '품목' },
  { key: 'quantity', label: '모델 · 수량' },
  { key: 'plant_type_label', label: '구분' },
  { key: 'notes', label: '비고' },
]

const FILTERS = [{ key: 'is_power_plant', label: '발전소', options: YES_NO }]

const fields = computed(() => [
  { key: 'delivered_ym', label: '납품 시기 (YYYY-MM)', required: true, col: 'col-md-3' },
  { key: 'client', label: '발주처', required: true, col: 'col-md-4' },
  { key: 'project_name', label: '사업명', col: 'col-md-5' },
  { key: 'item_desc', label: '품목', col: 'col-md-4' },
  { key: 'model_nos', label: '모델명(원문)', type: 'tags', col: 'col-md-4' },
  {
    key: 'products',
    label: '제품 연결',
    type: 'multiselect',
    options: productOptions.value,
    col: 'col-md-4',
  },
  {
    key: 'quantity',
    label: '수량',
    type: 'json',
    empty: [],
    col: 'col-md-6',
    help: '[{"model": "FT-VB500", "qty": 560, "unit": "EA"}]',
  },
  { key: 'amount_krw', label: '금액 (원)', type: 'number', col: 'col-md-3' },
  {
    key: 'plant_type',
    label: '구분',
    type: 'select',
    options: PLANT_TYPES,
    required: true,
    col: 'col-md-3',
  },
  { key: 'is_power_plant', label: '발전소 실적', type: 'checkbox', col: 'col-md-3' },
  { key: 'notes', label: '비고', type: 'textarea', col: 'col-12' },
])
</script>

<template>
  <div>
    <CompanyNav />
    <CrudPage
      title="납품실적"
      :api="deliveryRecords"
      :columns="COLUMNS"
      :fields="fields"
      :filters="FILTERS"
      :defaults="{ plant_type: 'OTHER', model_nos: [], products: [], quantity: [] }"
      :item-label="(r) => `${r.delivered_ym} ${r.project_name}`"
      search-placeholder="발주처, 사업명, 품목, 비고"
    >
      <template #cell-quantity="{ row }">
        <div v-for="q in row.quantity" :key="q.model" class="text-nowrap small">
          {{ q.model }} · {{ formatNumber(q.qty) }} {{ q.unit }}
        </div>
      </template>
    </CrudPage>
  </div>
</template>
