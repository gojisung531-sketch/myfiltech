<script setup>
// Prompt templates: edit → new version, compare, roll back, reset, test (specs/04 §5).
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { listDocuments } from '@/api/documents'
import {
  activatePrompt,
  getPrompt,
  listPrompts,
  resetPrompt,
  savePromptVersion,
  testPrompt,
} from '@/api/settings'
import BaseModal from '@/components/BaseModal.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'
import SettingsNav from '@/components/SettingsNav.vue'
import { useSystemStore } from '@/stores/system'
import { useToastStore } from '@/stores/toast'
import { diffLines } from '@/utils/diff'
import { errorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/format'

const toast = useToastStore()
const system = useSystemStore()

const prompts = ref([])
const selectedKey = ref('')
const detail = ref(null)
const form = reactive({ system_prompt: '', user_prompt_template: '', schemaText: '', notes: '' })
const saving = ref(false)
const formError = ref('')
const confirmReset = ref(false)
const compare = reactive({ show: false, version: null })
const test = reactive({
  mode: 'variables',
  variablesText: '{}',
  documentId: '',
  running: false,
  result: null,
  error: '',
})
const documents = ref([])

const active = computed(() => detail.value?.active)
const isDocumentPrompt = computed(() => selectedKey.value.startsWith('document.'))
const dirty = computed(
  () =>
    active.value &&
    (form.system_prompt !== active.value.system_prompt ||
      form.user_prompt_template !== active.value.user_prompt_template ||
      (!detail.value.dynamic_schema &&
        form.schemaText !== schemaToText(active.value.output_schema))),
)

function schemaToText(schema) {
  return schema ? JSON.stringify(schema, null, 2) : ''
}

async function loadList() {
  try {
    prompts.value = await listPrompts()
    if (!selectedKey.value && prompts.value.length) selectedKey.value = prompts.value[0].key
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

async function loadDetail() {
  if (!selectedKey.value) return
  try {
    detail.value = await getPrompt(selectedKey.value)
    resetForm()
    test.result = null
    test.error = ''
    test.mode = isDocumentPrompt.value ? 'document' : 'variables'
    test.variablesText = JSON.stringify(
      Object.fromEntries(detail.value.variables.map((v) => [v, ''])),
      null,
      2,
    )
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

function resetForm() {
  Object.assign(form, {
    system_prompt: active.value.system_prompt,
    user_prompt_template: active.value.user_prompt_template,
    schemaText: schemaToText(active.value.output_schema),
    notes: '',
  })
  formError.value = ''
}

watch(selectedKey, loadDetail)
onMounted(async () => {
  await loadList()
  try {
    documents.value = (await listDocuments({ page_size: 100 })).results
  } catch {
    documents.value = []
  }
})

function parsedSchema() {
  if (detail.value.dynamic_schema) return null
  if (!form.schemaText.trim()) return null
  return JSON.parse(form.schemaText)
}

async function save() {
  formError.value = ''
  let schema
  try {
    schema = parsedSchema()
  } catch {
    formError.value = '출력 스키마가 올바른 JSON이 아닙니다.'
    return
  }
  saving.value = true
  try {
    const saved = await savePromptVersion(selectedKey.value, {
      system_prompt: form.system_prompt,
      user_prompt_template: form.user_prompt_template,
      output_schema: schema,
      notes: form.notes,
    })
    toast.success(`v${saved.version}으로 저장하고 활성화했습니다.`)
    await Promise.all([loadDetail(), loadList()])
  } catch (err) {
    formError.value = errorMessage(err)
  } finally {
    saving.value = false
  }
}

async function activate(version) {
  try {
    await activatePrompt(selectedKey.value, version)
    toast.success(`v${version}을 활성화했습니다.`)
    await Promise.all([loadDetail(), loadList()])
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

async function doReset() {
  confirmReset.value = false
  try {
    const saved = await resetPrompt(selectedKey.value)
    toast.success(`기본값으로 복원했습니다 (v${saved.version}).`)
    await Promise.all([loadDetail(), loadList()])
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

const compareVersion = computed(() =>
  detail.value?.versions.find((v) => v.version === compare.version),
)
const compareSections = computed(() => {
  const other = compareVersion.value
  if (!other) return []
  return [
    ['시스템 프롬프트', other.system_prompt, active.value.system_prompt],
    ['사용자 프롬프트', other.user_prompt_template, active.value.user_prompt_template],
    ['출력 스키마', schemaToText(other.output_schema), schemaToText(active.value.output_schema)],
  ].map(([label, before, after]) => ({ label, lines: diffLines(before, after) }))
})

function openCompare(version) {
  Object.assign(compare, { show: true, version })
}

async function runTest() {
  test.error = ''
  test.result = null
  const payload = {
    system_prompt: form.system_prompt,
    user_prompt_template: form.user_prompt_template,
  }
  try {
    const schema = parsedSchema()
    if (!detail.value.dynamic_schema) payload.output_schema = schema
  } catch {
    test.error = '출력 스키마가 올바른 JSON이 아닙니다.'
    return
  }
  if (test.mode === 'document') {
    if (!test.documentId) {
      test.error = '테스트할 문서를 선택하세요.'
      return
    }
    payload.document_id = Number(test.documentId)
  } else {
    try {
      payload.variables = JSON.parse(test.variablesText)
    } catch {
      test.error = '변수가 올바른 JSON이 아닙니다.'
      return
    }
  }
  test.running = true
  try {
    test.result = await testPrompt(selectedKey.value, payload)
  } catch (err) {
    test.error = errorMessage(err)
  } finally {
    test.running = false
  }
}
</script>

<template>
  <div>
    <SettingsNav />
    <div class="row g-4">
      <div class="col-lg-3">
        <div class="list-group">
          <button
            v-for="p in prompts"
            :key="p.key"
            class="list-group-item list-group-item-action"
            :class="{ active: p.key === selectedKey }"
            @click="selectedKey = p.key"
          >
            <div class="d-flex justify-content-between">
              <span class="fw-semibold">{{ p.name }}</span>
              <span class="badge bg-secondary">v{{ p.version }}</span>
            </div>
            <div class="small font-monospace opacity-75">{{ p.key }}</div>
          </button>
        </div>
      </div>

      <div v-if="detail" class="col-lg-9">
        <div class="card mb-4">
          <div class="card-header d-flex align-items-center gap-2">
            <div class="me-auto">
              <span class="fw-semibold">{{ active.name }}</span>
              <span class="badge bg-success ms-2">활성 v{{ active.version }}</span>
              <div class="small text-muted">{{ active.description }}</div>
            </div>
            <button
              v-if="detail.has_default"
              class="btn btn-sm btn-outline-secondary"
              @click="confirmReset = true"
            >
              기본값 복원
            </button>
          </div>
          <form class="card-body" @submit.prevent="save">
            <div class="small mb-3">
              사용 가능한 변수:
              <code v-for="v in detail.variables" :key="v" class="me-2">{{ v }}</code>
              <span class="text-muted"
                >— Jinja2 문법 (<code v-pre>{{ 변수 }}</code
                >, <code>{% for %}</code>)</span
              >
            </div>
            <div class="mb-3">
              <label class="form-label small" for="p-system">시스템 프롬프트</label>
              <textarea
                id="p-system"
                v-model="form.system_prompt"
                class="form-control font-monospace small"
                rows="9"
                spellcheck="false"
              ></textarea>
            </div>
            <div class="mb-3">
              <label class="form-label small" for="p-user">사용자 프롬프트 템플릿</label>
              <textarea
                id="p-user"
                v-model="form.user_prompt_template"
                class="form-control font-monospace small"
                rows="14"
                spellcheck="false"
              ></textarea>
            </div>
            <div class="mb-3">
              <label class="form-label small" for="p-schema">출력 JSON 스키마</label>
              <div v-if="detail.dynamic_schema" class="alert alert-info py-2 small mb-0">
                이 프롬프트의 출력 스키마는 문서 분류의 메타데이터 필드 정의로 자동 생성됩니다.
                <router-link to="/admin/metadata-schemas">문서 분류</router-link>에서 필드를
                편집하세요.
              </div>
              <textarea
                v-else
                id="p-schema"
                v-model="form.schemaText"
                class="form-control font-monospace small"
                rows="10"
                spellcheck="false"
              ></textarea>
            </div>
            <div class="row g-2 align-items-end">
              <div class="col-md-8">
                <label class="form-label small" for="p-notes">변경 메모</label>
                <input id="p-notes" v-model="form.notes" class="form-control form-control-sm" />
              </div>
              <div class="col-md-4 d-flex gap-2">
                <button
                  type="button"
                  class="btn btn-sm btn-outline-secondary"
                  :disabled="!dirty"
                  @click="resetForm"
                >
                  되돌리기
                </button>
                <button class="btn btn-sm btn-primary flex-fill" :disabled="!dirty || saving">
                  <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>새
                  버전으로 저장
                </button>
              </div>
            </div>
            <div v-if="formError" class="alert alert-danger py-2 small mt-3 mb-0">
              {{ formError }}
            </div>
          </form>
        </div>

        <div class="card mb-4">
          <div class="card-header fw-semibold">
            테스트 실행
            <span class="text-muted small">— 편집 중인 내용으로 실행하며 저장하지 않습니다</span>
          </div>
          <div class="card-body">
            <div v-if="!system.llmConfigured" class="alert alert-warning py-2 small">
              LLM이 설정되지 않아 테스트할 수 없습니다.
              <router-link to="/admin/settings/llm">LLM 연결 설정</router-link>
            </div>
            <div class="btn-group btn-group-sm mb-3" role="group">
              <input
                id="tm-vars"
                v-model="test.mode"
                class="btn-check"
                type="radio"
                value="variables"
              />
              <label class="btn btn-outline-secondary" for="tm-vars">변수 직접 입력</label>
              <input
                id="tm-doc"
                v-model="test.mode"
                class="btn-check"
                type="radio"
                value="document"
                :disabled="!isDocumentPrompt"
              />
              <label class="btn btn-outline-secondary" for="tm-doc">문서로 테스트</label>
            </div>
            <textarea
              v-if="test.mode === 'variables'"
              v-model="test.variablesText"
              class="form-control font-monospace small mb-3"
              rows="6"
              spellcheck="false"
              aria-label="변수 JSON"
            ></textarea>
            <select
              v-else
              v-model="test.documentId"
              class="form-select form-select-sm mb-3"
              aria-label="테스트 문서"
            >
              <option value="">문서 선택</option>
              <option v-for="d in documents" :key="d.id" :value="d.id">
                {{ d.display_name }} ({{ d.category_name || '미분류' }})
              </option>
            </select>
            <button
              class="btn btn-sm btn-outline-primary"
              :disabled="test.running || !system.llmConfigured"
              @click="runTest"
            >
              <span v-if="test.running" class="spinner-border spinner-border-sm me-1"></span>실행
            </button>
            <div v-if="test.error" class="alert alert-danger py-2 small mt-3 mb-0">
              {{ test.error }}
            </div>
            <template v-if="test.result">
              <div v-if="!test.result.ok" class="alert alert-danger py-2 small mt-3">
                {{ test.result.error }}
              </div>
              <div v-else class="small text-muted mt-3">
                입력 {{ test.result.input_tokens ?? '-' }} 토큰 · 출력
                {{ test.result.output_tokens ?? '-' }} 토큰 ·
                {{ (test.result.latency_ms / 1000).toFixed(1) }}초
              </div>
              <div class="row g-3 mt-1">
                <div v-if="test.result.user" class="col-md-6">
                  <div class="small fw-semibold mb-1">렌더된 사용자 프롬프트</div>
                  <pre class="test-box">{{ test.result.user }}</pre>
                </div>
                <div :class="test.result.user ? 'col-md-6' : 'col-12'">
                  <div class="small fw-semibold mb-1">
                    {{ test.result.ok ? '파싱 결과' : '원시 응답' }}
                  </div>
                  <pre class="test-box">{{
                    test.result.ok
                      ? JSON.stringify(test.result.parsed, null, 2)
                      : test.result.raw_text || '(없음)'
                  }}</pre>
                </div>
              </div>
            </template>
          </div>
        </div>

        <div class="card">
          <div class="card-header fw-semibold">버전 기록</div>
          <table class="table table-sm align-middle mb-0">
            <thead>
              <tr>
                <th>버전</th>
                <th>메모</th>
                <th>작성</th>
                <th>일시</th>
                <th class="text-end"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="v in detail.versions" :key="v.version">
                <td>
                  v{{ v.version }}
                  <span v-if="v.is_active" class="badge bg-success ms-1">활성</span>
                </td>
                <td class="small">{{ v.notes || '-' }}</td>
                <td class="small">{{ v.updated_by_name || '-' }}</td>
                <td class="small">{{ formatDateTime(v.created_at) }}</td>
                <td class="text-end text-nowrap">
                  <button
                    v-if="!v.is_active"
                    class="btn btn-sm btn-outline-secondary me-1"
                    @click="openCompare(v.version)"
                  >
                    활성 버전과 비교
                  </button>
                  <button
                    v-if="!v.is_active"
                    class="btn btn-sm btn-outline-primary"
                    @click="activate(v.version)"
                  >
                    활성화
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <BaseModal
      :show="compare.show"
      :title="`v${compare.version} → 활성 v${active?.version} 비교`"
      size="xl"
      @close="compare.show = false"
    >
      <div v-for="section in compareSections" :key="section.label" class="mb-3">
        <div class="small fw-semibold mb-1">{{ section.label }}</div>
        <pre class="diff mb-0"><span
          v-for="(line, i) in section.lines"
          :key="i"
          :class="`diff-${line.type}`"
        >{{ line.type === 'add' ? '+ ' : line.type === 'del' ? '- ' : '  ' }}{{ line.text }}
</span></pre>
      </div>
    </BaseModal>

    <ConfirmModal
      :show="confirmReset"
      title="기본값 복원"
      message="기본 프롬프트로 새 버전을 만들어 활성화합니다. 기존 버전은 기록에 남습니다."
      confirm-text="복원"
      variant="primary"
      @confirm="doReset"
      @cancel="confirmReset = false"
    />
  </div>
</template>

<style scoped>
.test-box,
.diff {
  max-height: 22rem;
  overflow: auto;
  font-size: 0.75rem;
  background: var(--bs-light);
  padding: 0.5rem;
  white-space: pre-wrap;
}
.diff-add {
  background: #d1e7dd;
  display: block;
}
.diff-del {
  background: #f8d7da;
  display: block;
}
.diff-same {
  display: block;
  color: #6c757d;
}
</style>
