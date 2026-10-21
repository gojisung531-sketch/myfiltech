<script setup>
// Config-driven list + create/edit/delete page for company resources (specs/04 §2.2).
import { onMounted, reactive, ref, watch } from 'vue'

import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { displayValue } from '@/utils/format'

import BaseModal from './BaseModal.vue'
import ConfirmModal from './ConfirmModal.vue'
import EmptyState from './EmptyState.vue'
import EntityForm from './EntityForm.vue'

const props = defineProps({
  title: { type: String, required: true },
  api: { type: Object, required: true },
  columns: { type: Array, required: true },
  fields: { type: Array, required: true },
  filters: { type: Array, default: () => [] },
  defaults: { type: Object, default: () => ({}) },
  itemLabel: { type: Function, default: (row) => `#${row.id}` },
  searchPlaceholder: { type: String, default: '검색' },
})

const toast = useToastStore()
const rows = ref([])
const count = ref(0)
const page = ref(1)
const loading = ref(false)
const query = reactive({ q: '', ...Object.fromEntries(props.filters.map((f) => [f.key, ''])) })

const editor = reactive({ show: false, id: null, model: {}, error: '', saving: false })
const confirm = reactive({ show: false, row: null, saving: false })
const form = ref(null)

async function load() {
  loading.value = true
  try {
    const params = { page: page.value }
    for (const [key, value] of Object.entries(query)) if (value !== '') params[key] = value
    const data = await props.api.list(params)
    rows.value = data.results
    count.value = data.count
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    loading.value = false
  }
}

let searchTimer = null
watch(query, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    load()
  }, 300)
})
onMounted(load)

function emptyModel() {
  const model = {}
  for (const field of props.fields) {
    model[field.key] = field.type === 'checkbox' ? false : field.type === 'multiselect' ? [] : null
  }
  return { ...model, ...props.defaults }
}

function openCreate() {
  Object.assign(editor, { show: true, id: null, model: emptyModel(), error: '' })
}

function openEdit(row) {
  Object.assign(editor, { show: true, id: row.id, model: { ...emptyModel(), ...row }, error: '' })
}

async function save() {
  editor.error = ''
  let payload
  try {
    payload = form.value.collect()
  } catch (err) {
    editor.error = err.message
    return
  }
  editor.saving = true
  try {
    if (editor.id) await props.api.update(editor.id, payload)
    else await props.api.create(payload)
    toast.success('저장했습니다.')
    editor.show = false
    load()
  } catch (err) {
    editor.error = errorMessage(err)
  } finally {
    editor.saving = false
  }
}

function openDelete(row) {
  Object.assign(confirm, { show: true, row })
}

async function remove() {
  confirm.saving = true
  try {
    await props.api.remove(confirm.row.id)
    toast.success('삭제했습니다.')
    confirm.show = false
    load()
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    confirm.saving = false
  }
}

function goPage(delta) {
  page.value += delta
  load()
}

defineExpose({ load, openEdit })
</script>

<template>
  <div>
    <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
      <h2 class="h5 mb-0 me-auto">
        {{ title }} <span class="text-muted small">({{ count }})</span>
      </h2>
      <slot name="actions" />
      <button class="btn btn-primary btn-sm" @click="openCreate">
        <i class="bi bi-plus-lg me-1"></i>추가
      </button>
    </div>

    <slot name="notice" :rows="rows" />

    <div class="row g-2 mb-3">
      <div class="col-sm-4 col-lg-3">
        <input
          v-model="query.q"
          class="form-control form-control-sm"
          :placeholder="searchPlaceholder"
          aria-label="검색"
        />
      </div>
      <div v-for="filter in filters" :key="filter.key" class="col-auto">
        <select
          v-model="query[filter.key]"
          class="form-select form-select-sm"
          :aria-label="filter.label"
        >
          <option value="">{{ filter.label }}: 전체</option>
          <option v-for="opt in filter.options" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
      </div>
    </div>

    <div class="card">
      <div class="table-responsive">
        <table class="table table-hover table-sm align-middle mb-0">
          <thead class="table-light">
            <tr>
              <th v-for="col in columns" :key="col.key" :class="col.class">{{ col.label }}</th>
              <th class="text-end">작업</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td :colspan="columns.length + 1" class="text-center py-4">
                <span class="spinner-border spinner-border-sm"></span>
              </td>
            </tr>
            <tr v-else-if="!rows.length">
              <td :colspan="columns.length + 1"><EmptyState /></td>
            </tr>
            <tr v-for="row in rows" v-else :key="row.id">
              <td v-for="col in columns" :key="col.key" :class="col.class">
                <slot :name="`cell-${col.key}`" :row="row">
                  {{ col.format ? col.format(row) : displayValue(row[col.key]) }}
                </slot>
              </td>
              <td class="text-end text-nowrap">
                <button class="btn btn-sm btn-outline-secondary me-1" @click="openEdit(row)">
                  수정
                </button>
                <button class="btn btn-sm btn-outline-danger" @click="openDelete(row)">삭제</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="count > 20" class="card-footer d-flex justify-content-end gap-2">
        <button class="btn btn-sm btn-outline-secondary" :disabled="page === 1" @click="goPage(-1)">
          이전
        </button>
        <span class="small align-self-center">{{ page }} / {{ Math.ceil(count / 20) }}</span>
        <button
          class="btn btn-sm btn-outline-secondary"
          :disabled="page * 20 >= count"
          @click="goPage(1)"
        >
          다음
        </button>
      </div>
    </div>

    <BaseModal
      :show="editor.show"
      :title="`${title} ${editor.id ? '수정' : '추가'}`"
      size="lg"
      @close="editor.show = false"
    >
      <form :id="`crud-form-${title}`" @submit.prevent="save">
        <EntityForm ref="form" :fields="fields" :model-value="editor.model" :id-prefix="title" />
        <div v-if="editor.error" class="alert alert-danger py-2 small mt-3 mb-0">
          {{ editor.error }}
        </div>
      </form>
      <template #footer>
        <button class="btn btn-secondary" @click="editor.show = false">취소</button>
        <button class="btn btn-primary" :form="`crud-form-${title}`" :disabled="editor.saving">
          <span v-if="editor.saving" class="spinner-border spinner-border-sm me-1"></span>저장
        </button>
      </template>
    </BaseModal>

    <ConfirmModal
      :show="confirm.show"
      :title="`${title} 삭제`"
      :message="`'${confirm.row ? itemLabel(confirm.row) : ''}'을(를) 삭제합니다.`"
      confirm-text="삭제"
      :loading="confirm.saving"
      @confirm="remove"
      @cancel="confirm.show = false"
    />
  </div>
</template>
