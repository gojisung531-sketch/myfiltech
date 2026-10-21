<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { bidItems, bidRequirements } from '@/api/bids'
import BaseModal from '@/components/BaseModal.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { REQUIREMENT_CATEGORIES } from '@/utils/options'

import { NORMALIZED_FIELDS } from './normalizedFields'

const props = defineProps({ bid: { type: Object, required: true } })
const emit = defineEmits(['changed'])

const SOURCE_LABELS = { LLM: 'LLM', RULE: '규칙', MANUAL: '수동' }

const toast = useToastStore()
const requirements = ref([])
const items = ref([])
const loading = ref(false)
const category = ref('')
const removing = ref(null)
const editor = reactive({
  show: false,
  req: null,
  model: {},
  normalized: {},
  json: '',
  saving: false,
  error: '',
})

const visible = computed(() =>
  category.value
    ? requirements.value.filter((r) => r.category === category.value)
    : requirements.value,
)
const counts = computed(() => {
  const map = {}
  for (const r of requirements.value) map[r.category] = (map[r.category] || 0) + 1
  return map
})
const quickFields = computed(() => NORMALIZED_FIELDS[editor.model.category] || [])

async function load() {
  loading.value = true
  try {
    ;[requirements.value, items.value] = await Promise.all([
      bidRequirements.list(props.bid.id),
      bidItems.list(props.bid.id),
    ])
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(() => props.bid.updated_at, load)

function open(req) {
  const model = req
    ? {
        category: req.category,
        title: req.title,
        requirement_text: req.requirement_text,
        item: req.item,
        is_mandatory: req.is_mandatory,
        source_attachment: req.source_attachment,
        source_page: req.source_page,
        source_quote: req.source_quote,
      }
    : {
        category: category.value || 'OTHER',
        title: '',
        requirement_text: '',
        item: null,
        is_mandatory: true,
        source_attachment: null,
        source_page: null,
        source_quote: '',
      }
  const normalized = { ...(req?.normalized || {}) }
  Object.assign(editor, { show: true, req, model, normalized, saving: false, error: '' })
  editor.json = JSON.stringify(normalized, null, 2)
}

// Quick form and JSON box edit the same object.
function setQuick(field, raw) {
  let value = raw
  if (field.type === 'number') value = raw === '' ? undefined : Number(raw)
  if (field.type === 'bool') value = raw
  if (value === '' || value === undefined) delete editor.normalized[field.key]
  else editor.normalized[field.key] = value
  editor.json = JSON.stringify(editor.normalized, null, 2)
}

function onJson(text) {
  editor.json = text
  try {
    const parsed = text.trim() ? JSON.parse(text) : {}
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      editor.normalized = parsed
      editor.error = ''
    } else editor.error = '정규화 값은 JSON 객체여야 합니다.'
  } catch {
    editor.error = '정규화 값이 올바른 JSON이 아닙니다.'
  }
}

async function save() {
  if (editor.error) return
  editor.saving = true
  const payload = {
    ...editor.model,
    source_page: editor.model.source_page || null,
    normalized: editor.normalized,
  }
  try {
    if (editor.req) await bidRequirements.update(props.bid.id, editor.req.id, payload)
    else await bidRequirements.create(props.bid.id, payload)
    editor.show = false
    emit('changed')
    load()
  } catch (err) {
    editor.error = errorMessage(err)
  } finally {
    editor.saving = false
  }
}

async function unlock(req) {
  try {
    await bidRequirements.update(props.bid.id, req.id, { is_locked: false })
    toast.success('잠금을 해제했습니다. 다시 추출하면 이 항목은 추출 결과로 바뀝니다.')
    load()
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

async function move(index, delta) {
  // Swap within the full list (the view may be filtered), then re-number everything.
  const list = [...requirements.value]
  const from = list.indexOf(visible.value[index])
  const to = list.indexOf(visible.value[index + delta])
  ;[list[from], list[to]] = [list[to], list[from]]
  try {
    await Promise.all(
      list.map((r, i) =>
        r.order !== i ? bidRequirements.update(props.bid.id, r.id, { order: i }) : null,
      ),
    )
    load()
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

async function doDelete() {
  try {
    await bidRequirements.remove(props.bid.id, removing.value.id)
    removing.value = null
    emit('changed')
    load()
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

const summary = (n) =>
  Object.entries(n || {})
    .filter(([k]) => !['raw', 'placeholder'].includes(k))
    .map(([k, v]) => [k, typeof v === 'object' ? JSON.stringify(v) : String(v)])
</script>

<template>
  <div>
    <div class="d-flex flex-wrap gap-2 mb-3">
      <select v-model="category" class="form-select form-select-sm w-auto" aria-label="카테고리">
        <option value="">카테고리: 전체 ({{ requirements.length }})</option>
        <option v-for="c in REQUIREMENT_CATEGORIES" :key="c.value" :value="c.value">
          {{ c.label }} ({{ counts[c.value] || 0 }})
        </option>
      </select>
      <span class="small text-muted align-self-center me-auto">
        <i class="bi bi-lock"></i> 표시 항목은 수정되어 다시 추출해도 유지됩니다.
      </span>
      <button class="btn btn-sm btn-outline-primary" @click="open(null)">
        <i class="bi bi-plus-lg me-1"></i>요구사항 추가
      </button>
    </div>

    <div class="card">
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead class="table-light">
            <tr>
              <th style="width: 4rem"></th>
              <th>카테고리</th>
              <th>요구사항</th>
              <th>정규화 값</th>
              <th>출처</th>
              <th class="text-end">작업</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="6" class="text-center py-4">
                <span class="spinner-border spinner-border-sm"></span>
              </td>
            </tr>
            <tr v-else-if="!visible.length">
              <td colspan="6">
                <EmptyState message="요구사항이 없습니다. 추출을 실행하거나 직접 추가하세요." />
              </td>
            </tr>
            <tr
              v-for="(r, index) in visible"
              v-else
              :key="r.id"
              :class="{ 'table-warning': r.normalized?.placeholder }"
            >
              <td class="text-nowrap">
                <button
                  class="btn btn-sm btn-link p-0"
                  :disabled="index === 0"
                  aria-label="위로"
                  @click="move(index, -1)"
                >
                  <i class="bi bi-arrow-up"></i>
                </button>
                <button
                  class="btn btn-sm btn-link p-0"
                  :disabled="index === visible.length - 1"
                  aria-label="아래로"
                  @click="move(index, 1)"
                >
                  <i class="bi bi-arrow-down"></i>
                </button>
              </td>
              <td class="small text-nowrap">
                {{ r.category_label }}
                <div v-if="r.item_label" class="text-muted">{{ r.item_label }}</div>
              </td>
              <td class="small">
                <span class="fw-semibold">{{ r.title }}</span>
                <span v-if="r.is_mandatory" class="badge bg-danger ms-1">필수</span>
                <i v-if="r.is_locked" class="bi bi-lock ms-1" title="수정됨(잠금)"></i>
                <div class="text-muted">{{ r.requirement_text }}</div>
              </td>
              <td class="small" style="min-width: 14rem; max-width: 22rem">
                <div v-for="[key, value] in summary(r.normalized)" :key="key" class="text-break">
                  <span class="text-muted">{{ key }}</span> {{ value }}
                </div>
                <span v-if="!summary(r.normalized).length" class="text-muted">-</span>
              </td>
              <td class="small">
                <span class="badge bg-light text-dark border">{{ SOURCE_LABELS[r.source] }}</span>
                <div v-if="r.source_attachment_name" class="text-muted">
                  {{ r.source_attachment_name
                  }}<span v-if="r.source_page"> p.{{ r.source_page }}</span>
                </div>
                <div v-if="r.source_quote" class="text-muted fst-italic">
                  “{{ r.source_quote }}”
                </div>
              </td>
              <td class="text-end text-nowrap">
                <button
                  v-if="r.is_locked"
                  class="btn btn-sm btn-outline-secondary me-1"
                  @click="unlock(r)"
                >
                  잠금 해제
                </button>
                <button class="btn btn-sm btn-outline-primary me-1" @click="open(r)">수정</button>
                <button class="btn btn-sm btn-outline-danger" @click="removing = r">삭제</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <BaseModal
      :show="editor.show"
      :title="editor.req ? '요구사항 수정' : '요구사항 추가'"
      size="lg"
      @close="editor.show = false"
    >
      <form id="req-form" @submit.prevent="save">
        <div class="row g-3">
          <div class="col-md-4">
            <label class="form-label small mb-1" for="req-category">카테고리</label>
            <select
              id="req-category"
              v-model="editor.model.category"
              class="form-select form-select-sm"
            >
              <option v-for="c in REQUIREMENT_CATEGORIES" :key="c.value" :value="c.value">
                {{ c.label }}
              </option>
            </select>
          </div>
          <div class="col-md-5">
            <label class="form-label small mb-1" for="req-item">품목</label>
            <select id="req-item" v-model="editor.model.item" class="form-select form-select-sm">
              <option :value="null">공고 공통</option>
              <option v-for="i in items" :key="i.id" :value="i.id">
                {{ i.item_no }} {{ i.name }}
              </option>
            </select>
          </div>
          <div class="col-md-3">
            <div class="form-check mt-md-4">
              <input
                id="req-mandatory"
                v-model="editor.model.is_mandatory"
                class="form-check-input"
                type="checkbox"
              />
              <label class="form-check-label small" for="req-mandatory">필수 요구</label>
            </div>
          </div>
          <div class="col-12">
            <label class="form-label small mb-1" for="req-title">제목</label>
            <input
              id="req-title"
              v-model="editor.model.title"
              class="form-control form-control-sm"
              required
            />
          </div>
          <div class="col-12">
            <label class="form-label small mb-1" for="req-text">요구 내용</label>
            <textarea
              id="req-text"
              v-model="editor.model.requirement_text"
              class="form-control form-control-sm"
              rows="2"
            ></textarea>
          </div>

          <div v-if="quickFields.length" class="col-12">
            <div class="small fw-semibold mb-1">정규화 값 (간이 입력)</div>
            <div class="row g-2">
              <div v-for="f in quickFields" :key="f.key" class="col-md-4">
                <label class="form-label small mb-0" :for="`nq-${f.key}`">
                  {{ f.label }}<span v-if="f.unit" class="text-muted"> ({{ f.unit }})</span>
                </label>
                <select
                  v-if="f.type === 'select'"
                  :id="`nq-${f.key}`"
                  class="form-select form-select-sm"
                  :value="editor.normalized[f.key] ?? ''"
                  @change="setQuick(f, $event.target.value)"
                >
                  <option value="">-</option>
                  <option v-for="o in f.options" :key="o.value" :value="o.value">
                    {{ o.label }}
                  </option>
                </select>
                <div v-else-if="f.type === 'bool'" class="form-check">
                  <input
                    :id="`nq-${f.key}`"
                    class="form-check-input"
                    type="checkbox"
                    :checked="!!editor.normalized[f.key]"
                    @change="setQuick(f, $event.target.checked)"
                  />
                </div>
                <input
                  v-else
                  :id="`nq-${f.key}`"
                  class="form-control form-control-sm"
                  :type="f.type === 'number' ? 'number' : 'text'"
                  step="any"
                  :value="editor.normalized[f.key] ?? ''"
                  @change="setQuick(f, $event.target.value)"
                />
              </div>
            </div>
          </div>
          <div class="col-12">
            <label class="form-label small mb-1" for="req-json">정규화 값 (JSON 고급 편집)</label>
            <textarea
              id="req-json"
              class="form-control form-control-sm font-monospace"
              rows="5"
              spellcheck="false"
              :value="editor.json"
              @input="onJson($event.target.value)"
            ></textarea>
          </div>

          <div class="col-md-6">
            <label class="form-label small mb-1" for="req-source">출처 첨부</label>
            <select
              id="req-source"
              v-model="editor.model.source_attachment"
              class="form-select form-select-sm"
            >
              <option :value="null">-</option>
              <option v-for="a in bid.attachments" :key="a.id" :value="a.id">
                {{ a.display_name }}
              </option>
            </select>
          </div>
          <div class="col-md-2">
            <label class="form-label small mb-1" for="req-page">페이지</label>
            <input
              id="req-page"
              v-model="editor.model.source_page"
              type="number"
              min="1"
              class="form-control form-control-sm"
            />
          </div>
          <div class="col-md-4">
            <label class="form-label small mb-1" for="req-quote">인용문</label>
            <input
              id="req-quote"
              v-model="editor.model.source_quote"
              class="form-control form-control-sm"
            />
          </div>
        </div>
        <div v-if="editor.error" class="alert alert-danger py-2 small mt-3 mb-0">
          {{ editor.error }}
        </div>
      </form>
      <template #footer>
        <button class="btn btn-secondary" @click="editor.show = false">취소</button>
        <button class="btn btn-primary" form="req-form" :disabled="editor.saving || !!editor.error">
          저장
        </button>
      </template>
    </BaseModal>

    <ConfirmModal
      :show="!!removing"
      title="요구사항 삭제"
      :message="`'${removing?.title}' 요구사항을 삭제합니다.`"
      confirm-text="삭제"
      @confirm="doDelete"
      @cancel="removing = null"
    />
  </div>
</template>
