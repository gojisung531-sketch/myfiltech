<script setup>
// Inline-editable document metadata (specs/04 §2.3–2.4). Edited rows become locked.
import { reactive } from 'vue'

const props = defineProps({
  rows: { type: Array, required: true },
  threshold: { type: Number, default: 0.7 },
  editable: { type: Boolean, default: true },
})
const emit = defineEmits(['save', 'remove', 'add', 'toggle-lock'])

const SOURCE_LABELS = { RULE: '규칙', LLM: 'LLM', MANUAL: '수동' }

const editing = reactive({ id: null, text: '', error: '' })
const draft = reactive({ key: '', label: '', text: '', error: '' })

function asText(value) {
  if (value === null || value === undefined) return ''
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}

function parseValue(text, original) {
  const trimmed = text.trim()
  if (trimmed === '') return null
  if (typeof original === 'string') return text
  try {
    return JSON.parse(trimmed)
  } catch {
    return text
  }
}

function startEdit(row) {
  Object.assign(editing, { id: row.id, text: asText(row.value), error: '' })
}

function saveEdit(row) {
  emit('save', row, { value: parseValue(editing.text, row.value) })
  editing.id = null
}

function addRow() {
  draft.error = ''
  if (!/^[a-z][a-z0-9_]*$/.test(draft.key)) {
    draft.error = '키는 영문 소문자, 숫자, _ 만 사용할 수 있습니다.'
    return
  }
  emit('add', {
    key: draft.key,
    label: draft.label || draft.key,
    value: parseValue(draft.text, undefined),
  })
  Object.assign(draft, { key: '', label: '', text: '' })
}

const isLow = (row) => row.confidence !== null && row.confidence < props.threshold
const isMultiline = (value) => value !== null && typeof value === 'object'
</script>

<template>
  <div>
    <div class="table-responsive">
      <table class="table table-sm align-middle small">
        <thead class="table-light">
          <tr>
            <th>항목</th>
            <th>값</th>
            <th>출처</th>
            <th class="text-end"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id" :class="{ 'table-warning': isLow(row) }">
            <td class="text-nowrap">
              <div class="fw-semibold">{{ row.label || row.key }}</div>
              <div class="text-muted font-monospace">{{ row.key }}</div>
            </td>
            <td class="w-50">
              <template v-if="editing.id === row.id">
                <textarea
                  v-model="editing.text"
                  class="form-control form-control-sm font-monospace"
                  :rows="isMultiline(row.value) ? 6 : 2"
                  :aria-label="`${row.label} 값`"
                ></textarea>
                <div class="mt-1 d-flex gap-1">
                  <button class="btn btn-sm btn-primary" @click="saveEdit(row)">저장</button>
                  <button class="btn btn-sm btn-secondary" @click="editing.id = null">취소</button>
                </div>
              </template>
              <template v-else>
                <pre v-if="isMultiline(row.value)" class="value mb-0">{{ asText(row.value) }}</pre>
                <span v-else-if="row.value !== null && row.value !== ''">
                  {{ row.value }} <span class="text-muted">{{ row.unit }}</span>
                </span>
                <span v-else class="text-muted">-</span>
                <div
                  v-if="row.raw_value && row.raw_value !== String(row.value)"
                  class="text-muted"
                  :title="row.evidence_quote"
                >
                  원문: {{ row.raw_value }}
                </div>
              </template>
            </td>
            <td class="text-nowrap">
              <span class="badge bg-light text-dark border">{{ SOURCE_LABELS[row.source] }}</span>
              <span
                v-if="row.confidence !== null"
                class="ms-1"
                :class="{ 'text-danger': isLow(row) }"
              >
                {{ Math.round(row.confidence * 100) }}%
              </span>
              <div v-if="row.evidence_page" class="text-muted">{{ row.evidence_page }}p</div>
            </td>
            <td class="text-end text-nowrap">
              <template v-if="editable">
                <button
                  class="btn btn-sm btn-link p-0 me-2"
                  :title="row.is_locked ? '잠금 해제 (재추출 시 갱신됨)' : '잠금 (재추출 시 유지)'"
                  :aria-label="row.is_locked ? '잠금 해제' : '잠금'"
                  @click="emit('toggle-lock', row)"
                >
                  <i
                    :class="
                      row.is_locked ? 'bi bi-lock-fill text-warning' : 'bi bi-unlock text-muted'
                    "
                  ></i>
                </button>
                <button
                  class="btn btn-sm btn-link p-0 me-2"
                  aria-label="수정"
                  @click="startEdit(row)"
                >
                  <i class="bi bi-pencil"></i>
                </button>
                <button
                  class="btn btn-sm btn-link p-0 text-danger"
                  aria-label="삭제"
                  @click="emit('remove', row)"
                >
                  <i class="bi bi-trash"></i>
                </button>
              </template>
              <i v-else-if="row.is_locked" class="bi bi-lock-fill text-warning"></i>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td colspan="4" class="text-center text-muted py-3">추출된 메타데이터가 없습니다.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <form v-if="editable" class="row g-2 align-items-end" @submit.prevent="addRow">
      <div class="col-sm-3">
        <label class="form-label small mb-1" for="meta-key">키</label>
        <input id="meta-key" v-model="draft.key" class="form-control form-control-sm" required />
      </div>
      <div class="col-sm-3">
        <label class="form-label small mb-1" for="meta-label">이름</label>
        <input id="meta-label" v-model="draft.label" class="form-control form-control-sm" />
      </div>
      <div class="col-sm-4">
        <label class="form-label small mb-1" for="meta-value">값</label>
        <input id="meta-value" v-model="draft.text" class="form-control form-control-sm" />
      </div>
      <div class="col-sm-2">
        <button class="btn btn-sm btn-outline-primary w-100">항목 추가</button>
      </div>
      <div v-if="draft.error" class="col-12 text-danger small">{{ draft.error }}</div>
    </form>
  </div>
</template>

<style scoped>
.value {
  white-space: pre-wrap;
  font-size: 0.75rem;
  max-height: 12rem;
  overflow: auto;
}
</style>
