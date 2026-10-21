<script setup>
import { onMounted, reactive, ref, watch } from 'vue'

import { bidItems } from '@/api/bids'
import { products } from '@/api/company'
import BaseModal from '@/components/BaseModal.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'
import EmptyState from '@/components/EmptyState.vue'
import EntityForm from '@/components/EntityForm.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { formatNumber, productDimension } from '@/utils/format'
import { FILTER_TYPES } from '@/utils/options'

const props = defineProps({ bid: { type: Object, required: true } })
const emit = defineEmits(['changed'])

const FIELDS = [
  { key: 'item_no', label: '품목 번호', col: 'col-md-3' },
  { key: 'name', label: '품명', required: true, col: 'col-md-9' },
  { key: 'spec_text', label: '규격(원문)', type: 'textarea', col: 'col-12', rows: 2 },
  {
    key: 'filter_type',
    label: '필터 형식',
    type: 'select',
    options: FILTER_TYPES,
    col: 'col-md-4',
  },
  { key: 'quantity', label: '수량', type: 'number', col: 'col-md-4' },
  { key: 'unit', label: '단위', col: 'col-md-4' },
  { key: 'width_mm', label: '폭', type: 'number', unit: 'mm', col: 'col-md-3' },
  { key: 'height_mm', label: '높이', type: 'number', unit: 'mm', col: 'col-md-3' },
  { key: 'depth_mm', label: '깊이', type: 'number', unit: 'mm', col: 'col-md-3' },
  { key: 'depth_mm_max', label: '깊이 상한(범위)', type: 'number', unit: 'mm', col: 'col-md-3' },
  { key: 'diameter_mm', label: '외경', type: 'number', unit: 'mm', col: 'col-md-4' },
  { key: 'diameter2_mm', label: '외경2(원추)', type: 'number', unit: 'mm', col: 'col-md-4' },
  { key: 'length_mm', label: '길이', type: 'number', unit: 'mm', col: 'col-md-4' },
  { key: 'material_no', label: '자재번호', col: 'col-md-4' },
  { key: 'notes', label: '비고', col: 'col-md-8' },
]

const toast = useToastStore()
const items = ref([])
const productOptions = ref([])
const loading = ref(false)
const editor = reactive({ show: false, item: null, model: {}, saving: false })
const formRef = ref(null)
const removing = ref(null)

async function load() {
  loading.value = true
  try {
    items.value = await bidItems.list(props.bid.id)
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  load()
  const data = await products.list({ page_size: 200 })
  productOptions.value = data.results || data
})
watch(() => props.bid.updated_at, load)

function open(item) {
  const model = Object.fromEntries(FIELDS.map((f) => [f.key, item ? item[f.key] : null]))
  if (!item) model.unit = 'EA'
  Object.assign(editor, { show: true, item, model, saving: false })
}

async function save() {
  let payload
  try {
    payload = formRef.value.collect()
  } catch (err) {
    toast.error(err.message)
    return
  }
  payload.filter_type = payload.filter_type || ''
  editor.saving = true
  try {
    if (editor.item) await bidItems.update(props.bid.id, editor.item.id, payload)
    else await bidItems.create(props.bid.id, payload)
    editor.show = false
    emit('changed')
    load()
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    editor.saving = false
  }
}

async function setMatch(item, productId) {
  try {
    await bidItems.update(props.bid.id, item.id, { matched_product: productId || null })
    toast.success('매칭 제품을 변경했습니다.')
    load()
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

async function doDelete() {
  try {
    await bidItems.remove(props.bid.id, removing.value.id)
    removing.value = null
    emit('changed')
    load()
  } catch (err) {
    toast.error(errorMessage(err))
  }
}
</script>

<template>
  <div>
    <div class="d-flex justify-content-end mb-2">
      <button class="btn btn-sm btn-outline-primary" @click="open(null)">
        <i class="bi bi-plus-lg me-1"></i>품목 추가
      </button>
    </div>
    <div v-if="loading" class="text-center py-4">
      <span class="spinner-border spinner-border-sm"></span>
    </div>
    <div v-else-if="!items.length" class="card">
      <EmptyState message="품목이 없습니다. 추출을 실행하거나 직접 추가하세요." />
    </div>
    <div v-for="item in items" v-else :key="item.id" class="card mb-3">
      <div class="card-header d-flex align-items-center gap-2">
        <span class="badge bg-secondary">{{ item.item_no || '-' }}</span>
        <span class="fw-semibold me-auto">{{ item.name }}</span>
        <button class="btn btn-sm btn-outline-secondary" @click="open(item)">수정</button>
        <button class="btn btn-sm btn-outline-danger" @click="removing = item">삭제</button>
      </div>
      <div class="card-body small">
        <div class="row g-3">
          <div class="col-lg-5">
            <dl class="row mb-0">
              <dt class="col-4">형식</dt>
              <dd class="col-8">{{ item.filter_type_label || '-' }}</dd>
              <dt class="col-4">치수</dt>
              <dd class="col-8">
                {{ productDimension(item) }}
                <span v-if="item.depth_mm_max">(깊이 ~{{ item.depth_mm_max }})</span>
              </dd>
              <dt class="col-4">수량</dt>
              <dd class="col-8">{{ formatNumber(item.quantity) }} {{ item.unit }}</dd>
              <dt class="col-4">자재번호</dt>
              <dd class="col-8">{{ item.material_no || '-' }}</dd>
              <dt class="col-4">규격</dt>
              <dd class="col-8" style="white-space: pre-line">{{ item.spec_text || '-' }}</dd>
            </dl>
          </div>
          <div class="col-lg-7">
            <label class="form-label small mb-1" :for="`match-${item.id}`">매칭 제품</label>
            <select
              :id="`match-${item.id}`"
              class="form-select form-select-sm mb-2"
              :value="item.matched_product || ''"
              @change="setMatch(item, Number($event.target.value) || null)"
            >
              <option value="">매칭 제품 없음</option>
              <option v-for="p in productOptions" :key="p.id" :value="p.id">
                {{ p.model_no }} — {{ p.name }}
              </option>
            </select>
            <table v-if="item.candidates.length" class="table table-sm mb-0">
              <thead>
                <tr>
                  <th>후보</th>
                  <th class="text-end">점수</th>
                  <th>근거</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="c in item.candidates" :key="c.product">
                  <td class="text-nowrap">{{ c.rank }}. {{ c.model_no }}</td>
                  <td class="text-end">{{ Math.round(c.score * 100) }}</td>
                  <td class="text-muted">{{ c.reason }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="text-muted mb-0">추출 후 후보 제품이 계산됩니다.</p>
          </div>
        </div>
      </div>
    </div>

    <BaseModal
      :show="editor.show"
      :title="editor.item ? '품목 수정' : '품목 추가'"
      size="lg"
      @close="editor.show = false"
    >
      <form id="item-form" @submit.prevent="save">
        <EntityForm ref="formRef" :fields="FIELDS" :model-value="editor.model" id-prefix="item" />
      </form>
      <template #footer>
        <button class="btn btn-secondary" @click="editor.show = false">취소</button>
        <button class="btn btn-primary" form="item-form" :disabled="editor.saving">저장</button>
      </template>
    </BaseModal>

    <ConfirmModal
      :show="!!removing"
      title="품목 삭제"
      :message="`'${removing?.name}' 품목을 삭제합니다. 이 품목에 연결된 요구사항은 공고 공통으로 바뀝니다.`"
      confirm-text="삭제"
      @confirm="doDelete"
      @cancel="removing = null"
    />
  </div>
</template>
