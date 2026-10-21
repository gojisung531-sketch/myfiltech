<script setup>
// Tuning settings stored in AppSetting (specs/07 §6, specs/04 §5).
import { computed, onMounted, reactive, ref } from 'vue'

import { getAppSettings, resetAppSetting, saveAppSettings } from '@/api/settings'
import SettingsNav from '@/components/SettingsNav.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'

const GROUP_LABELS = {
  llm: 'LLM',
  extraction: '문서 추출',
  bid: '입찰 공고',
  evaluation: '판정',
  fit: '적합도',
  report: '보고서',
  jobs: '백그라운드 작업',
  upload: '업로드',
  auth: '로그인',
  company: '회사',
}

const toast = useToastStore()
const groups = ref([])
const edits = reactive({}) // key -> input text / value
const errors = ref({})
const saving = ref(false)

const changedKeys = computed(() =>
  Object.keys(edits).filter((key) => edits[key] !== toInput(findSetting(key))),
)

function findSetting(key) {
  for (const group of groups.value) {
    const setting = group.settings.find((s) => s.key === key)
    if (setting) return setting
  }
  return null
}

function toInput(setting) {
  const { value, value_type: type } = setting
  if (type === 'bool') return Boolean(value)
  if (type === 'json') return value === null ? '' : JSON.stringify(value, null, 2)
  return value === null ? '' : String(value)
}

function fromInput(setting, input) {
  const type = setting.value_type
  if (type === 'bool') return input
  if (input === '' || input === null) return null
  if (type === 'int') return Number.parseInt(input, 10)
  if (type === 'float') return Number.parseFloat(input)
  if (type === 'json') return JSON.parse(input)
  return input
}

function displayDefault(setting) {
  const value = setting.default
  if (value === null || value === undefined) return '(없음)'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

async function load() {
  try {
    groups.value = (await getAppSettings()).groups
    for (const key of Object.keys(edits)) delete edits[key]
    for (const group of groups.value) {
      for (const setting of group.settings) edits[setting.key] = toInput(setting)
    }
    errors.value = {}
  } catch (err) {
    toast.error(errorMessage(err))
  }
}
onMounted(load)

async function save() {
  const values = {}
  errors.value = {}
  for (const key of changedKeys.value) {
    try {
      values[key] = fromInput(findSetting(key), edits[key])
    } catch {
      errors.value[key] = ['올바른 JSON이 아닙니다.']
    }
  }
  if (Object.keys(errors.value).length) return
  saving.value = true
  try {
    await saveAppSettings(values)
    toast.success(`${Object.keys(values).length}개 설정을 저장했습니다.`)
    load()
  } catch (err) {
    errors.value = err.response?.data?.errors || {}
    toast.error(errorMessage(err))
  } finally {
    saving.value = false
  }
}

async function reset(setting) {
  try {
    await resetAppSetting(setting.key)
    toast.success(`${setting.key}을(를) 기본값으로 되돌렸습니다.`)
    load()
  } catch (err) {
    toast.error(errorMessage(err))
  }
}
</script>

<template>
  <div>
    <SettingsNav />
    <div class="d-flex align-items-center mb-3">
      <p class="small text-muted mb-0 me-auto">
        분석·추출·작업 동작을 조정하는 값입니다. 저장 즉시 적용됩니다.
      </p>
      <button
        class="btn btn-primary btn-sm"
        :disabled="!changedKeys.length || saving"
        @click="save"
      >
        <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>
        변경 사항 저장 <span v-if="changedKeys.length">({{ changedKeys.length }})</span>
      </button>
    </div>

    <div v-for="group in groups" :key="group.group" class="card mb-4">
      <div class="card-header fw-semibold">{{ GROUP_LABELS[group.group] || group.group }}</div>
      <ul class="list-group list-group-flush">
        <li v-for="setting in group.settings" :key="setting.key" class="list-group-item">
          <div class="row g-2 align-items-start">
            <div class="col-md-5">
              <label class="fw-semibold small d-block" :for="`s-${setting.key}`">{{
                setting.description || setting.key
              }}</label>
              <code class="small">{{ setting.key }}</code>
              <div v-if="setting.has_default" class="small text-muted">
                기본값: {{ displayDefault(setting) }}
              </div>
            </div>
            <div class="col-md-5">
              <div v-if="setting.value_type === 'bool'" class="form-check form-switch mt-1">
                <input
                  :id="`s-${setting.key}`"
                  v-model="edits[setting.key]"
                  class="form-check-input"
                  type="checkbox"
                />
              </div>
              <textarea
                v-else-if="setting.value_type === 'json'"
                :id="`s-${setting.key}`"
                v-model="edits[setting.key]"
                class="form-control form-control-sm font-monospace"
                rows="4"
                spellcheck="false"
              ></textarea>
              <textarea
                v-else-if="
                  setting.value_type === 'str' && String(setting.value ?? '').includes('\n')
                "
                :id="`s-${setting.key}`"
                v-model="edits[setting.key]"
                class="form-control form-control-sm"
                rows="6"
              ></textarea>
              <input
                v-else
                :id="`s-${setting.key}`"
                v-model="edits[setting.key]"
                class="form-control form-control-sm"
                :type="['int', 'float'].includes(setting.value_type) ? 'number' : 'text'"
                :step="setting.value_type === 'float' ? 'any' : undefined"
              />
              <div v-if="errors[setting.key]" class="text-danger small">
                {{ errors[setting.key].join(' ') }}
              </div>
            </div>
            <div class="col-md-2 text-end">
              <span v-if="changedKeys.includes(setting.key)" class="badge bg-warning text-dark me-1"
                >변경됨</span
              >
              <button
                v-if="setting.has_default && !setting.is_default"
                class="btn btn-sm btn-link p-0"
                @click="reset(setting)"
              >
                기본값으로
              </button>
            </div>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>
