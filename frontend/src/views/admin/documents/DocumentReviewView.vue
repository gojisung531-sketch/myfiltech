<script setup>
// Review extracted metadata, fix it, preview the mapping and apply (specs/04 §2.3, specs/11 §4).
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  applyDocument,
  createMetadata,
  deleteMetadata,
  getDocument,
  listMetadata,
  listSchemas,
  mappingPreview,
  reprocessDocument,
  updateDocument,
  updateMetadata,
} from '@/api/documents'
import CompanyNav from '@/components/CompanyNav.vue'
import DocumentViewer from '@/components/DocumentViewer.vue'
import JobProgress from '@/components/JobProgress.vue'
import MetadataTable from '@/components/MetadataTable.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { DOCUMENT_STATUS_VARIANT, displayValue } from '@/utils/format'

const ACTION_LABELS = {
  create: '신규 생성',
  update: '변경',
  unchanged: '변경 없음',
  replace: '전체 교체',
}

const route = useRoute()
const toast = useToastStore()
const doc = ref(null)
const metadata = ref([])
const schemas = ref([])
const categoryId = ref(null)
const jobId = ref(null)
const preview = reactive({ loading: false, changes: null, error: '' })
const applying = ref(false)

const documentId = computed(() => Number(route.params.id))
// Bid attachments open this view from the bid edit screen (?back=/admin/bids/1/edit?tab=attachments).
const backLink = computed(() =>
  String(route.query.back || '').startsWith('/admin/') ? route.query.back : '/admin/documents',
)
const schemaOptions = computed(() =>
  schemas.value.filter((s) => s.owner_type === doc.value?.owner_type),
)
const canApply = computed(
  () => doc.value?.owner_type === 'COMPANY' && ['EXTRACTED', 'REVIEWED'].includes(doc.value.status),
)

async function load() {
  try {
    doc.value = await getDocument(documentId.value)
    categoryId.value = doc.value.category
    metadata.value = await listMetadata(documentId.value)
    preview.changes = null
    preview.error = ''
    if (canApply.value) loadPreview()
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

async function loadPreview() {
  preview.loading = true
  preview.error = ''
  try {
    preview.changes = (await mappingPreview(documentId.value)).changes
  } catch (err) {
    preview.changes = null
    preview.error = errorMessage(err)
  } finally {
    preview.loading = false
  }
}

onMounted(async () => {
  schemas.value = await listSchemas()
  load()
})

async function saveCategory(reextract) {
  try {
    const res = await updateDocument(documentId.value, { category: categoryId.value, reextract })
    if (res.job_id) jobId.value = res.job_id
    else load()
    toast.success('분류를 변경했습니다.')
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

async function reprocess(step) {
  try {
    jobId.value = (await reprocessDocument(documentId.value, step)).job_id
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

function onJobDone(job) {
  jobId.value = null
  if (job.status === 'SUCCEEDED') toast.success('처리가 끝났습니다.')
  load()
}

async function withReload(action, message) {
  try {
    await action()
    if (message) toast.success(message)
    metadata.value = await listMetadata(documentId.value)
    if (canApply.value) loadPreview()
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

const onSave = (row, payload) =>
  withReload(() => updateMetadata(documentId.value, row.id, payload), '저장했습니다 (잠금 설정됨).')
const onRemove = (row) =>
  withReload(() => deleteMetadata(documentId.value, row.id), '삭제했습니다.')
const onAdd = (payload) =>
  withReload(() => createMetadata(documentId.value, payload), '항목을 추가했습니다.')
const onToggleLock = (row) =>
  withReload(() => updateMetadata(documentId.value, row.id, { is_locked: !row.is_locked }))

async function apply() {
  applying.value = true
  try {
    await applyDocument(documentId.value)
    toast.success('회사 자료에 반영했습니다.')
    load()
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    applying.value = false
  }
}
</script>

<template>
  <div>
    <CompanyNav v-if="doc?.owner_type !== 'BID'" />
    <div v-if="!doc" class="text-center py-5"><span class="spinner-border"></span></div>
    <template v-else>
      <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
        <router-link :to="backLink" class="btn btn-sm btn-outline-secondary">
          <i class="bi bi-arrow-left"></i>
        </router-link>
        <h2 class="h5 mb-0 me-auto">{{ doc.display_name }}</h2>
        <span :class="['badge', `bg-${DOCUMENT_STATUS_VARIANT[doc.status]}`]">{{
          doc.status_label
        }}</span>
        <button
          class="btn btn-sm btn-outline-secondary"
          :disabled="!!jobId"
          @click="reprocess('parse')"
        >
          처음부터 다시 처리
        </button>
        <button
          class="btn btn-sm btn-outline-secondary"
          :disabled="!!jobId"
          @click="reprocess('extract')"
        >
          메타데이터 다시 추출
        </button>
      </div>

      <div v-if="doc.error_message" class="alert alert-warning py-2 small">
        {{ doc.error_message }}
      </div>
      <JobProgress v-if="jobId" :job-id="jobId" label="처리 중:" class="mb-3" @done="onJobDone" />

      <div class="row g-4">
        <div class="col-xl-6">
          <DocumentViewer :document="doc" />
        </div>
        <div class="col-xl-6">
          <div class="card mb-4">
            <div class="card-body">
              <div class="row g-2 align-items-end">
                <div class="col-sm-7">
                  <label class="form-label small mb-1" for="doc-category">문서 분류</label>
                  <select id="doc-category" v-model="categoryId" class="form-select form-select-sm">
                    <option :value="null">미분류</option>
                    <option v-for="s in schemaOptions" :key="s.id" :value="s.id">
                      {{ s.name }}
                    </option>
                  </select>
                </div>
                <div class="col-sm-5 d-flex gap-1">
                  <button
                    class="btn btn-sm btn-primary flex-fill"
                    :disabled="categoryId === doc.category"
                    title="새 분류 기준으로 메타데이터를 다시 추출합니다"
                    @click="saveCategory(true)"
                  >
                    변경 후 재추출
                  </button>
                  <button
                    class="btn btn-sm btn-outline-secondary"
                    :disabled="categoryId === doc.category"
                    @click="saveCategory(false)"
                  >
                    분류만
                  </button>
                </div>
              </div>
              <div class="small text-muted mt-2">
                {{ doc.category_source === 'MANUAL' ? '수동 지정' : '자동 분류' }}
                <span v-if="doc.category_confidence !== null">
                  · 신뢰도 {{ Math.round(doc.category_confidence * 100) }}%
                </span>
              </div>
            </div>
          </div>

          <div class="card mb-4">
            <div class="card-header fw-semibold">
              메타데이터
              <span class="text-muted small">— 수정한 값은 잠기며 다시 추출해도 유지됩니다</span>
            </div>
            <div class="card-body">
              <MetadataTable
                :rows="metadata"
                :threshold="doc.low_confidence_threshold"
                @save="onSave"
                @remove="onRemove"
                @add="onAdd"
                @toggle-lock="onToggleLock"
              />
            </div>
          </div>

          <div v-if="doc.owner_type === 'COMPANY'" class="card">
            <div class="card-header fw-semibold">회사 자료 반영</div>
            <div class="card-body small">
              <div v-if="!canApply" class="text-muted">
                메타데이터 추출이 끝난 뒤 반영할 수 있습니다.
              </div>
              <div v-else-if="preview.loading">
                <span class="spinner-border spinner-border-sm"></span>
              </div>
              <div v-else-if="preview.error" class="text-danger">{{ preview.error }}</div>
              <template v-else-if="preview.changes">
                <div v-for="change in preview.changes" :key="change.lookup" class="mb-2">
                  <div>
                    <strong>{{ change.model }}</strong> · {{ change.lookup }} —
                    <span class="badge bg-light text-dark border">{{
                      ACTION_LABELS[change.action]
                    }}</span>
                  </div>
                  <table v-if="Object.keys(change.changes).length" class="table table-sm mt-2 mb-0">
                    <thead>
                      <tr class="text-nowrap">
                        <th>필드</th>
                        <th>현재</th>
                        <th>반영 후</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(pair, field) in change.changes" :key="field">
                        <td class="font-monospace">{{ field }}</td>
                        <td class="text-muted">{{ displayValue(pair[0]) }}</td>
                        <td>{{ displayValue(pair[1]) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <button class="btn btn-primary btn-sm mt-2" :disabled="applying" @click="apply">
                  <span v-if="applying" class="spinner-border spinner-border-sm me-1"></span>
                  회사 자료에 반영
                </button>
              </template>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
