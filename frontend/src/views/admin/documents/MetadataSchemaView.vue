<script setup>
// Document categories and their metadata field definitions (specs/04 §2.4).
import { computed, onMounted, reactive, ref } from 'vue'

import {
  createSchema,
  deleteSchema,
  listSchemas,
  reextractSchema,
  updateSchema,
} from '@/api/documents'
import BaseModal from '@/components/BaseModal.vue'
import CompanyNav from '@/components/CompanyNav.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { FIELD_TYPES, OWNER_TYPES } from '@/utils/options'

const toast = useToastStore()
const schemas = ref([])
const ownerType = ref('COMPANY')
const editor = reactive({
  show: false,
  id: null,
  model: {},
  patterns: '',
  error: '',
  saving: false,
})
const confirm = reactive({ show: false, schema: null, mode: 'delete' })

const visible = computed(() =>
  schemas.value.filter((s) => !ownerType.value || s.owner_type === ownerType.value),
)

async function load() {
  try {
    schemas.value = await listSchemas()
  } catch (err) {
    toast.error(errorMessage(err))
  }
}
onMounted(load)

function openEdit(schema) {
  const model = schema
    ? JSON.parse(JSON.stringify(schema))
    : {
        code: '',
        name: '',
        owner_type: ownerType.value || 'COMPANY',
        description: '',
        target_model: '',
        priority: 100,
        is_active: true,
        fields: [],
      }
  Object.assign(editor, {
    show: true,
    id: schema?.id || null,
    model,
    patterns: (model.filename_patterns || []).join('\n'),
    error: '',
  })
}

function addField() {
  editor.model.fields.push({
    key: '',
    label: '',
    type: 'str',
    unit: '',
    required: false,
    description: '',
  })
}

async function save() {
  editor.error = ''
  editor.saving = true
  const payload = {
    ...editor.model,
    filename_patterns: editor.patterns
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean),
  }
  delete payload.document_count
  try {
    if (editor.id) await updateSchema(editor.id, payload)
    else await createSchema(payload)
    toast.success('문서 분류를 저장했습니다.')
    editor.show = false
    load()
  } catch (err) {
    editor.error = errorMessage(err)
  } finally {
    editor.saving = false
  }
}

function ask(schema, mode) {
  Object.assign(confirm, { show: true, schema, mode })
}

async function confirmAction() {
  const { schema, mode } = confirm
  confirm.show = false
  try {
    if (mode === 'delete') {
      await deleteSchema(schema.id)
      toast.success('삭제했습니다.')
    } else {
      const res = await reextractSchema(schema.id)
      toast.success(`문서 ${res.count}건의 메타데이터 재추출을 시작했습니다.`)
    }
    load()
  } catch (err) {
    toast.error(errorMessage(err))
  }
}
</script>

<template>
  <div>
    <CompanyNav />
    <div class="d-flex align-items-center gap-2 mb-3">
      <h2 class="h5 mb-0 me-auto">문서 분류 · 메타데이터 정의</h2>
      <select v-model="ownerType" class="form-select form-select-sm w-auto" aria-label="문서 종류">
        <option value="">전체</option>
        <option v-for="o in OWNER_TYPES" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <button class="btn btn-primary btn-sm" @click="openEdit(null)">
        <i class="bi bi-plus-lg me-1"></i>분류 추가
      </button>
    </div>

    <div class="card">
      <table class="table table-sm align-middle mb-0">
        <thead class="table-light">
          <tr>
            <th>순서</th>
            <th>분류</th>
            <th>파일명 규칙</th>
            <th class="text-end">필드</th>
            <th class="text-end">문서</th>
            <th class="text-end">작업</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in visible" :key="s.id" :class="{ 'text-muted': !s.is_active }">
            <td>{{ s.priority }}</td>
            <td>
              <div class="fw-semibold">
                {{ s.name }} <span v-if="!s.is_active" class="badge bg-secondary">비활성</span>
              </div>
              <div class="small text-muted font-monospace">
                {{ s.code }} → {{ s.target_model || '-' }}
              </div>
            </td>
            <td class="small font-monospace">{{ s.filename_patterns.join('  ·  ') || '-' }}</td>
            <td class="text-end">{{ s.fields.length }}</td>
            <td class="text-end">{{ s.document_count }}</td>
            <td class="text-end text-nowrap">
              <button class="btn btn-sm btn-outline-secondary me-1" @click="openEdit(s)">
                수정
              </button>
              <button
                class="btn btn-sm btn-outline-secondary me-1"
                :disabled="!s.document_count"
                @click="ask(s, 'reextract')"
              >
                재추출
              </button>
              <button class="btn btn-sm btn-outline-danger" @click="ask(s, 'delete')">삭제</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <BaseModal
      :show="editor.show"
      :title="editor.id ? '문서 분류 수정' : '문서 분류 추가'"
      size="xl"
      @close="editor.show = false"
    >
      <form id="schema-form" @submit.prevent="save">
        <div class="row g-3">
          <div class="col-md-3">
            <label class="form-label small" for="sc-code">코드</label>
            <input
              id="sc-code"
              v-model="editor.model.code"
              class="form-control form-control-sm font-monospace"
              :readonly="!!editor.id"
              required
            />
          </div>
          <div class="col-md-3">
            <label class="form-label small" for="sc-name">이름</label>
            <input
              id="sc-name"
              v-model="editor.model.name"
              class="form-control form-control-sm"
              required
            />
          </div>
          <div class="col-md-2">
            <label class="form-label small" for="sc-owner">문서 종류</label>
            <select
              id="sc-owner"
              v-model="editor.model.owner_type"
              class="form-select form-select-sm"
            >
              <option v-for="o in OWNER_TYPES" :key="o.value" :value="o.value">
                {{ o.label }}
              </option>
            </select>
          </div>
          <div class="col-md-2">
            <label class="form-label small" for="sc-priority">순서</label>
            <input
              id="sc-priority"
              v-model.number="editor.model.priority"
              type="number"
              class="form-control form-control-sm"
            />
          </div>
          <div class="col-md-2">
            <div class="form-check mt-4">
              <input
                id="sc-active"
                v-model="editor.model.is_active"
                class="form-check-input"
                type="checkbox"
              />
              <label class="form-check-label small" for="sc-active">사용</label>
            </div>
          </div>
          <div class="col-md-6">
            <label class="form-label small" for="sc-desc">설명 (LLM 분류에 사용)</label>
            <textarea
              id="sc-desc"
              v-model="editor.model.description"
              class="form-control form-control-sm"
              rows="3"
            ></textarea>
          </div>
          <div class="col-md-6">
            <label class="form-label small" for="sc-patterns"
              >파일명 규칙 (정규식, 한 줄에 하나)</label
            >
            <textarea
              id="sc-patterns"
              v-model="editor.patterns"
              class="form-control form-control-sm font-monospace"
              rows="3"
            ></textarea>
          </div>
        </div>

        <h3 class="h6 mt-4">메타데이터 필드</h3>
        <table class="table table-sm align-middle small">
          <thead>
            <tr>
              <th>키</th>
              <th>이름</th>
              <th>타입</th>
              <th>단위</th>
              <th>필수</th>
              <th>설명</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(field, i) in editor.model.fields" :key="i">
              <td>
                <input
                  v-model="field.key"
                  class="form-control form-control-sm font-monospace"
                  aria-label="키"
                  required
                />
              </td>
              <td>
                <input
                  v-model="field.label"
                  class="form-control form-control-sm"
                  aria-label="이름"
                  required
                />
              </td>
              <td>
                <select v-model="field.type" class="form-select form-select-sm" aria-label="타입">
                  <option v-for="t in FIELD_TYPES" :key="t.value" :value="t.value">
                    {{ t.label }}
                  </option>
                </select>
              </td>
              <td>
                <input
                  v-model="field.unit"
                  class="form-control form-control-sm"
                  aria-label="단위"
                />
              </td>
              <td class="text-center">
                <input
                  v-model="field.required"
                  class="form-check-input"
                  type="checkbox"
                  aria-label="필수"
                />
              </td>
              <td>
                <input
                  v-model="field.description"
                  class="form-control form-control-sm"
                  aria-label="설명"
                />
              </td>
              <td>
                <button
                  type="button"
                  class="btn btn-sm btn-link text-danger p-0"
                  aria-label="필드 삭제"
                  @click="editor.model.fields.splice(i, 1)"
                >
                  <i class="bi bi-x-lg"></i>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <button type="button" class="btn btn-sm btn-outline-primary" @click="addField">
          필드 추가
        </button>
        <div v-if="editor.error" class="alert alert-danger py-2 small mt-3 mb-0">
          {{ editor.error }}
        </div>
      </form>
      <template #footer>
        <button class="btn btn-secondary" @click="editor.show = false">취소</button>
        <button class="btn btn-primary" form="schema-form" :disabled="editor.saving">저장</button>
      </template>
    </BaseModal>

    <ConfirmModal
      :show="confirm.show"
      :title="confirm.mode === 'delete' ? '문서 분류 삭제' : '메타데이터 재추출'"
      :message="
        confirm.mode === 'delete'
          ? `'${confirm.schema?.name}' 분류를 삭제합니다.`
          : `'${confirm.schema?.name}' 분류의 문서 ${confirm.schema?.document_count}건을 다시 추출합니다. 잠긴 값은 유지됩니다.`
      "
      :confirm-text="confirm.mode === 'delete' ? '삭제' : '재추출'"
      :variant="confirm.mode === 'delete' ? 'danger' : 'primary'"
      @confirm="confirmAction"
      @cancel="confirm.show = false"
    />
  </div>
</template>
