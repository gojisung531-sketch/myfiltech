<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  createModelOption,
  deleteModelOption,
  getLLMSettings,
  updateLLMSettings,
  updateModelOption,
  updateProvider,
  verifyProvider,
} from '@/api/settings'
import BaseModal from '@/components/BaseModal.vue'
import SettingsNav from '@/components/SettingsNav.vue'
import { useSystemStore } from '@/stores/system'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'

const PROVIDER_INFO = {
  ANTHROPIC: { name: 'Claude', vendor: 'Anthropic', icon: 'bi-stars' },
  OPENAI: { name: 'ChatGPT', vendor: 'OpenAI', icon: 'bi-chat-dots' },
  GEMINI: { name: 'Gemini', vendor: 'Google', icon: 'bi-gem' },
}
const PROVIDER_ORDER = ['ANTHROPIC', 'OPENAI', 'GEMINI']

const route = useRoute()
const system = useSystemStore()
const toast = useToastStore()

const data = ref(null)
const loading = ref(true)
const keyInput = ref(null)

const keyForm = reactive({ api_key: '', base_url: '', is_enabled: true, showKey: false })
const keyState = reactive({ saving: false, verifying: false, result: null })
const params = reactive({
  active_model_id: null,
  temperature: 0.2,
  max_output_tokens: 8192,
  timeout_sec: 180,
  max_retries: 2,
  json_mode: true,
  overridesText: '{}',
  error: '',
  saving: false,
})
const modelModal = reactive({ show: false, confirmDeleteId: null, error: '' })
const newModel = reactive({
  model_id: '',
  display_name: '',
  supports_pdf_input: false,
  max_output_tokens: '',
})

const settings = computed(() => data.value?.settings)
const activeProvider = computed(() => settings.value?.active_provider)
const currentConfig = computed(() => providerConfig(activeProvider.value))
const providerModels = computed(() =>
  (data.value?.models || []).filter((m) => m.provider === activeProvider.value),
)
const selectableModels = computed(() => providerModels.value.filter((m) => m.is_active))
const showMissingNotice = computed(() => Boolean(data.value && !data.value.llm_configured))

function providerConfig(code) {
  return data.value?.providers.find((p) => p.provider === code)
}

function applyPayload(payload) {
  data.value = payload
  const s = payload.settings
  Object.assign(params, {
    active_model_id: s.active_model_id,
    temperature: s.temperature,
    max_output_tokens: s.max_output_tokens,
    timeout_sec: s.timeout_sec,
    max_retries: s.max_retries,
    json_mode: s.json_mode,
    overridesText: JSON.stringify(s.per_task_overrides, null, 2),
    error: '',
  })
  syncKeyForm()
}

function syncKeyForm() {
  const config = currentConfig.value
  Object.assign(keyForm, {
    api_key: '',
    base_url: config?.base_url || '',
    is_enabled: config ? config.is_enabled || !config.has_api_key : true,
    showKey: false,
  })
  keyState.result = null
}

async function load() {
  loading.value = true
  try {
    applyPayload(await getLLMSettings())
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    loading.value = false
  }
  if (showMissingNotice.value || route.query.reason === 'llm_not_configured') {
    await nextTick()
    keyInput.value?.focus()
  }
}

onMounted(load)

async function changeProvider(provider) {
  if (provider === activeProvider.value) return
  try {
    applyPayload(await updateLLMSettings({ active_provider: provider }))
    await system.fetchStatus(true)
    toast.success(`활성 제공자를 ${PROVIDER_INFO[provider].name}(으)로 변경했습니다.`)
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

function replaceProvider(provider) {
  data.value.providers = data.value.providers.map((p) =>
    p.provider === provider.provider ? provider : p,
  )
}

async function saveKey() {
  keyState.saving = true
  keyState.result = null
  try {
    const payload = { base_url: keyForm.base_url, is_enabled: keyForm.is_enabled }
    if (keyForm.api_key.trim()) payload.api_key = keyForm.api_key.trim()
    const res = await updateProvider(activeProvider.value, payload)
    replaceProvider(res.provider)
    data.value.llm_configured = res.llm_configured
    keyForm.api_key = ''
    keyState.result = res.verify
    if (!res.verify) toast.success('저장했습니다.')
    await system.fetchStatus(true)
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    keyState.saving = false
  }
}

async function testConnection() {
  keyState.verifying = true
  keyState.result = null
  try {
    const model = providerModels.value.find((m) => m.id === params.active_model_id)
    const res = await verifyProvider(activeProvider.value, model?.model_id)
    replaceProvider(res.provider)
    keyState.result = res
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    keyState.verifying = false
  }
}

async function saveParams() {
  params.error = ''
  let overrides
  try {
    overrides = JSON.parse(params.overridesText || '{}')
  } catch {
    params.error = '작업별 설정이 올바른 JSON이 아닙니다.'
    return
  }
  params.saving = true
  try {
    applyPayload(
      await updateLLMSettings({
        active_model_id: params.active_model_id,
        temperature: Number(params.temperature),
        max_output_tokens: Number(params.max_output_tokens),
        timeout_sec: Number(params.timeout_sec),
        max_retries: Number(params.max_retries),
        json_mode: params.json_mode,
        per_task_overrides: overrides,
      }),
    )
    toast.success('LLM 설정을 저장했습니다.')
  } catch (err) {
    params.error = errorMessage(err)
  } finally {
    params.saving = false
  }
}

async function runModelAction(action) {
  modelModal.error = ''
  try {
    await action()
    applyPayload(await getLLMSettings())
  } catch (err) {
    modelModal.error = errorMessage(err)
  }
}

function addModel() {
  return runModelAction(async () => {
    await createModelOption({
      provider: activeProvider.value,
      model_id: newModel.model_id.trim(),
      display_name: newModel.display_name.trim() || newModel.model_id.trim(),
      supports_pdf_input: newModel.supports_pdf_input,
      max_output_tokens: newModel.max_output_tokens ? Number(newModel.max_output_tokens) : null,
    })
    Object.assign(newModel, {
      model_id: '',
      display_name: '',
      supports_pdf_input: false,
      max_output_tokens: '',
    })
  })
}

function deleteModel(model) {
  if (modelModal.confirmDeleteId !== model.id) {
    modelModal.confirmDeleteId = model.id
    return
  }
  modelModal.confirmDeleteId = null
  return runModelAction(() => deleteModelOption(model.id))
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString('ko-KR', { hour12: false }) : ''
}
</script>

<template>
  <div>
    <SettingsNav />

    <div v-if="showMissingNotice" class="alert alert-warning">
      <i class="bi bi-exclamation-triangle me-1"></i>LLM API Key가 설정되지 않았습니다. 사용할
      제공자를 선택하고 API Key를 입력하세요.
    </div>

    <div v-if="loading" class="text-center py-5"><span class="spinner-border"></span></div>

    <template v-else-if="data">
      <!-- 1. Provider -->
      <section class="card mb-4">
        <div class="card-header fw-semibold">1. LLM 제공자</div>
        <div class="card-body">
          <div class="row g-3">
            <div v-for="code in PROVIDER_ORDER" :key="code" class="col-md-4">
              <label
                class="card h-100 provider-card"
                :class="{ 'border-primary shadow-sm': activeProvider === code }"
              >
                <div class="card-body d-flex align-items-start">
                  <input
                    class="form-check-input me-3 mt-1"
                    type="radio"
                    name="provider"
                    :checked="activeProvider === code"
                    @change="changeProvider(code)"
                  />
                  <div>
                    <div class="fw-semibold">
                      <i :class="['bi', PROVIDER_INFO[code].icon, 'me-1']"></i>
                      {{ PROVIDER_INFO[code].name }}
                      <span class="text-muted small">({{ PROVIDER_INFO[code].vendor }})</span>
                    </div>
                    <div class="small mt-1">
                      <template v-if="providerConfig(code)?.has_api_key">
                        <i class="bi bi-key text-success me-1"></i>
                        {{ providerConfig(code).api_key_masked }}
                      </template>
                      <span v-else class="text-muted">API Key 없음</span>
                    </div>
                  </div>
                </div>
              </label>
            </div>
          </div>

          <form class="mt-4" @submit.prevent="saveKey">
            <h2 class="h6">{{ PROVIDER_INFO[activeProvider].name }} 연결 정보</h2>
            <div class="row g-3 align-items-end">
              <div class="col-lg-5">
                <label class="form-label" for="api-key">
                  API Key
                  <span v-if="currentConfig?.has_api_key" class="text-muted small">
                    (저장됨 {{ currentConfig.api_key_masked }} — 변경할 때만 입력)
                  </span>
                </label>
                <div class="input-group">
                  <input
                    id="api-key"
                    ref="keyInput"
                    v-model="keyForm.api_key"
                    :type="keyForm.showKey ? 'text' : 'password'"
                    class="form-control"
                    autocomplete="off"
                    :placeholder="currentConfig?.has_api_key ? '••••••••' : 'API Key 입력'"
                  />
                  <button
                    type="button"
                    class="btn btn-outline-secondary"
                    :aria-label="keyForm.showKey ? 'API Key 숨기기' : 'API Key 보기'"
                    @click="keyForm.showKey = !keyForm.showKey"
                  >
                    <i :class="keyForm.showKey ? 'bi bi-eye-slash' : 'bi bi-eye'"></i>
                  </button>
                </div>
              </div>
              <div class="col-lg-4">
                <label class="form-label" for="base-url">Base URL (선택)</label>
                <input
                  id="base-url"
                  v-model="keyForm.base_url"
                  class="form-control"
                  placeholder="프록시 사용 시에만 입력"
                />
              </div>
              <div class="col-lg-3">
                <div class="form-check form-switch mb-2">
                  <input
                    id="provider-enabled"
                    v-model="keyForm.is_enabled"
                    class="form-check-input"
                    type="checkbox"
                  />
                  <label class="form-check-label" for="provider-enabled">사용</label>
                </div>
              </div>
            </div>
            <div class="mt-3 d-flex gap-2">
              <button class="btn btn-primary" :disabled="keyState.saving">
                <span v-if="keyState.saving" class="spinner-border spinner-border-sm me-1"></span>
                저장
              </button>
              <button
                type="button"
                class="btn btn-outline-secondary"
                :disabled="keyState.verifying || !currentConfig?.has_api_key"
                @click="testConnection"
              >
                <span v-if="keyState.verifying" class="spinner-border spinner-border-sm me-1">
                </span>
                연결 테스트
              </button>
            </div>
            <div
              v-if="keyState.result"
              class="alert mt-3 mb-0 py-2"
              :class="keyState.result.ok ? 'alert-success' : 'alert-danger'"
            >
              <i :class="keyState.result.ok ? 'bi bi-check-circle' : 'bi bi-x-circle'"></i>
              {{ keyState.result.message }}
              <span v-if="!keyState.result.ok" class="small d-block">
                API Key는 저장되었습니다. 내용을 확인한 뒤 다시 테스트하세요.
              </span>
            </div>
            <div v-else-if="currentConfig?.last_verified_at" class="small text-muted mt-2">
              마지막 테스트: {{ formatDate(currentConfig.last_verified_at) }} —
              <span :class="currentConfig.last_verify_ok ? 'text-success' : 'text-danger'">
                {{ currentConfig.last_verify_ok ? '성공' : currentConfig.last_verify_error }}
              </span>
            </div>
          </form>
        </div>
      </section>

      <!-- 2. Model & parameters -->
      <section class="card mb-4">
        <div class="card-header fw-semibold">2. 모델 및 파라미터</div>
        <div class="card-body">
          <form @submit.prevent="saveParams">
            <div class="row g-3">
              <div class="col-lg-6">
                <label class="form-label" for="active-model">사용 모델</label>
                <div class="input-group">
                  <select id="active-model" v-model="params.active_model_id" class="form-select">
                    <option v-for="m in selectableModels" :key="m.id" :value="m.id">
                      {{ m.display_name }} ({{ m.model_id }}){{ m.is_default ? ' · 기본' : '' }}
                    </option>
                  </select>
                  <button
                    type="button"
                    class="btn btn-outline-secondary"
                    @click="modelModal.show = true"
                  >
                    모델 관리
                  </button>
                </div>
              </div>
              <div class="col-6 col-lg-3">
                <label class="form-label" for="p-temp">Temperature</label>
                <input
                  id="p-temp"
                  v-model="params.temperature"
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  class="form-control"
                />
              </div>
              <div class="col-6 col-lg-3">
                <label class="form-label" for="p-max">최대 출력 토큰</label>
                <input
                  id="p-max"
                  v-model="params.max_output_tokens"
                  type="number"
                  min="1"
                  class="form-control"
                />
              </div>
              <div class="col-6 col-lg-3">
                <label class="form-label" for="p-timeout">타임아웃(초)</label>
                <input
                  id="p-timeout"
                  v-model="params.timeout_sec"
                  type="number"
                  min="5"
                  class="form-control"
                />
              </div>
              <div class="col-6 col-lg-3">
                <label class="form-label" for="p-retries">재시도 횟수</label>
                <input
                  id="p-retries"
                  v-model="params.max_retries"
                  type="number"
                  min="0"
                  max="10"
                  class="form-control"
                />
              </div>
              <div class="col-lg-6 d-flex align-items-end">
                <div class="form-check form-switch mb-2">
                  <input
                    id="p-json"
                    v-model="params.json_mode"
                    class="form-check-input"
                    type="checkbox"
                  />
                  <label class="form-check-label" for="p-json">JSON(구조화) 출력 사용</label>
                </div>
              </div>
              <div class="col-12">
                <label class="form-label" for="p-overrides">작업별 설정 (JSON)</label>
                <textarea
                  id="p-overrides"
                  v-model="params.overridesText"
                  rows="6"
                  class="form-control font-monospace small"
                  spellcheck="false"
                ></textarea>
                <div class="form-text">
                  예: {"evaluation.judge": {"temperature": 0.0}, "draft.*": {"temperature": 0.3}}
                </div>
              </div>
            </div>
            <div v-if="params.error" class="alert alert-danger py-2 small mt-3 mb-0">
              {{ params.error }}
            </div>
            <button class="btn btn-primary mt-3" :disabled="params.saving">
              <span v-if="params.saving" class="spinner-border spinner-border-sm me-1"></span>
              설정 저장
            </button>
          </form>
        </div>
      </section>
    </template>

    <BaseModal
      :show="modelModal.show"
      :title="`모델 관리 — ${PROVIDER_INFO[activeProvider]?.name || ''}`"
      size="lg"
      @close="modelModal.show = false"
    >
      <table class="table table-sm align-middle">
        <thead>
          <tr>
            <th>모델 ID</th>
            <th>표시명</th>
            <th class="text-center">PDF 입력</th>
            <th class="text-center">기본</th>
            <th class="text-center">사용</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in providerModels" :key="m.id">
            <td class="font-monospace small">{{ m.model_id }}</td>
            <td>{{ m.display_name }}</td>
            <td class="text-center">
              <input
                class="form-check-input"
                type="checkbox"
                :checked="m.supports_pdf_input"
                :aria-label="`${m.model_id} PDF 입력`"
                @change="
                  runModelAction(() =>
                    updateModelOption(m.id, { supports_pdf_input: $event.target.checked }),
                  )
                "
              />
            </td>
            <td class="text-center">
              <input
                class="form-check-input"
                type="radio"
                name="default-model"
                :checked="m.is_default"
                :aria-label="`${m.model_id} 기본 모델`"
                @change="runModelAction(() => updateModelOption(m.id, { is_default: true }))"
              />
            </td>
            <td class="text-center">
              <input
                class="form-check-input"
                type="checkbox"
                :checked="m.is_active"
                :aria-label="`${m.model_id} 사용`"
                @change="
                  runModelAction(() =>
                    updateModelOption(m.id, { is_active: $event.target.checked }),
                  )
                "
              />
            </td>
            <td class="text-end">
              <button
                class="btn btn-sm"
                :class="modelModal.confirmDeleteId === m.id ? 'btn-danger' : 'btn-outline-danger'"
                @click="deleteModel(m)"
              >
                {{ modelModal.confirmDeleteId === m.id ? '삭제 확인' : '삭제' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <form class="row g-2 align-items-end" @submit.prevent="addModel">
        <div class="col-md-4">
          <label class="form-label small" for="nm-id">모델 ID</label>
          <input
            id="nm-id"
            v-model="newModel.model_id"
            class="form-control form-control-sm"
            required
          />
        </div>
        <div class="col-md-3">
          <label class="form-label small" for="nm-name">표시명</label>
          <input
            id="nm-name"
            v-model="newModel.display_name"
            class="form-control form-control-sm"
          />
        </div>
        <div class="col-md-2">
          <label class="form-label small" for="nm-max">최대 출력</label>
          <input
            id="nm-max"
            v-model="newModel.max_output_tokens"
            type="number"
            min="1"
            class="form-control form-control-sm"
          />
        </div>
        <div class="col-md-2">
          <div class="form-check">
            <input
              id="nm-pdf"
              v-model="newModel.supports_pdf_input"
              class="form-check-input"
              type="checkbox"
            />
            <label class="form-check-label small" for="nm-pdf">PDF 입력</label>
          </div>
        </div>
        <div class="col-md-1">
          <button class="btn btn-sm btn-primary w-100">추가</button>
        </div>
      </form>
      <div v-if="modelModal.error" class="alert alert-danger py-2 small mt-3 mb-0">
        {{ modelModal.error }}
      </div>
    </BaseModal>
  </div>
</template>

<style scoped>
.provider-card {
  cursor: pointer;
}
</style>
