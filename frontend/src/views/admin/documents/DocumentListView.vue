<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'

import {
  createTextDocument,
  deleteDocument,
  listDocuments,
  listSchemas,
  reprocessDocument,
  uploadDocuments,
} from '@/api/documents'
import BaseModal from '@/components/BaseModal.vue'
import CompanyNav from '@/components/CompanyNav.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'
import EmptyState from '@/components/EmptyState.vue'
import FileDropzone from '@/components/FileDropzone.vue'
import JobProgress from '@/components/JobProgress.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { DOCUMENT_STATUS_VARIANT, formatBytes, formatDateTime } from '@/utils/format'

const COMPANY_FORMATS = ['.txt', '.docx', '.doc', '.hwp', '.hwpx', '.pdf']
const STATUSES = {
  PARSED: '텍스트 추출됨',
  NEEDS_OCR: 'OCR 필요',
  EXTRACTED: '추출 완료',
  REVIEWED: '검토 완료',
  FAILED: '실패',
}

const toast = useToastStore()
const documents = ref([])
const count = ref(0)
const page = ref(1)
const loading = ref(false)
const schemas = ref([])
const filters = reactive({ q: '', category: '', status: '' })
const uploadCategory = ref('')
const uploading = ref(false)
const jobs = ref([]) // [{ id, label }]
const textModal = reactive({
  show: false,
  title: '',
  category: '',
  text: '',
  error: '',
  saving: false,
})
const confirm = reactive({ show: false, doc: null, saving: false })

const companySchemas = computed(() => schemas.value.filter((s) => s.owner_type === 'COMPANY'))

async function load() {
  loading.value = true
  try {
    const params = { owner_type: 'COMPANY', page: page.value }
    for (const [key, value] of Object.entries(filters)) if (value) params[key] = value
    const data = await listDocuments(params)
    documents.value = data.results
    count.value = data.count
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    loading.value = false
  }
}

let timer = null
watch(filters, () => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    page.value = 1
    load()
  }, 300)
})

onMounted(async () => {
  load()
  schemas.value = await listSchemas()
})

async function onFiles(files) {
  uploading.value = true
  try {
    const res = await uploadDocuments(files, 'COMPANY', uploadCategory.value || null)
    for (const doc of res.documents) {
      jobs.value.push({ id: doc.job_id, label: doc.display_name })
      if (doc.duplicate_of.length)
        toast.show(`'${doc.display_name}'은(는) 이미 올라온 파일과 같습니다.`, 'warning')
    }
    for (const skipped of res.skipped) toast.error(`${skipped.filename}: ${skipped.reason}`)
    load()
  } catch (err) {
    const skipped = err.response?.data?.skipped || []
    toast.error(skipped.map((s) => `${s.filename}: ${s.reason}`).join('\n') || errorMessage(err))
  } finally {
    uploading.value = false
  }
}

function onJobDone(job) {
  jobs.value = jobs.value.filter((j) => j.id !== job.id)
  load()
}

async function submitText() {
  textModal.error = ''
  textModal.saving = true
  try {
    const res = await createTextDocument({
      title: textModal.title,
      source_text: textModal.text,
      owner_type: 'COMPANY',
      category: textModal.category || null,
    })
    const doc = res.documents[0]
    jobs.value.push({ id: doc.job_id, label: doc.display_name })
    textModal.show = false
    load()
  } catch (err) {
    textModal.error = errorMessage(err)
  } finally {
    textModal.saving = false
  }
}

function openText() {
  Object.assign(textModal, { show: true, title: '', category: '', text: '', error: '' })
}

async function reprocess(doc) {
  try {
    const res = await reprocessDocument(doc.id, 'parse')
    jobs.value.push({ id: res.job_id, label: doc.display_name })
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

function askDelete(doc) {
  Object.assign(confirm, { show: true, doc })
}

async function doDelete() {
  confirm.saving = true
  try {
    await deleteDocument(confirm.doc.id)
    toast.success('문서를 삭제했습니다.')
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
</script>

<template>
  <div>
    <CompanyNav />

    <div class="row g-4 mb-4">
      <div class="col-lg-8">
        <div class="card h-100">
          <div class="card-header fw-semibold">회사 자료 업로드</div>
          <div class="card-body">
            <div class="row g-2 mb-2 align-items-center">
              <div class="col-auto small">분류</div>
              <div class="col-sm-5">
                <select
                  v-model="uploadCategory"
                  class="form-select form-select-sm"
                  aria-label="업로드 분류"
                >
                  <option value="">자동 분류</option>
                  <option v-for="s in companySchemas" :key="s.id" :value="s.code">
                    {{ s.name }}
                  </option>
                </select>
              </div>
              <div class="col text-end">
                <button class="btn btn-sm btn-outline-secondary" @click="openText">
                  <i class="bi bi-textarea-t me-1"></i>텍스트로 입력
                </button>
              </div>
            </div>
            <FileDropzone :accept="COMPANY_FORMATS" :disabled="uploading" @files="onFiles" />
            <p class="small text-muted mt-2 mb-0">
              업로드하면 텍스트 추출 → 문서 분류 → 메타데이터 추출이 자동으로 진행됩니다. 결과는
              <strong>검토</strong> 화면에서 확인·수정한 뒤 회사 자료에 반영하세요.
            </p>
          </div>
        </div>
      </div>
      <div class="col-lg-4">
        <div class="card h-100">
          <div class="card-header fw-semibold">초기 데이터</div>
          <div class="card-body small">
            <p class="text-muted mb-0">
              개인 버전에서는 기존 가상 회사자료 적재를 사용하지 않습니다. 위의 파일 업로드 또는
              텍스트 입력으로 실제 필텍 자료(인증서·기술사양서·시험성적서·납품실적)를 등록하세요.
            </p>
          </div>
        </div>
      </div>
    </div>

    <div v-if="jobs.length" class="card mb-4">
      <div class="card-body">
        <JobProgress
          v-for="job in jobs"
          :key="job.id"
          :job-id="job.id"
          :label="job.label"
          class="mb-2"
          @done="onJobDone"
        />
      </div>
    </div>

    <div class="row g-2 mb-3">
      <div class="col-sm-4 col-lg-3">
        <input
          v-model="filters.q"
          class="form-control form-control-sm"
          placeholder="파일명, 제목"
          aria-label="검색"
        />
      </div>
      <div class="col-auto">
        <select v-model="filters.category" class="form-select form-select-sm" aria-label="분류">
          <option value="">분류: 전체</option>
          <option v-for="s in companySchemas" :key="s.id" :value="s.code">{{ s.name }}</option>
        </select>
      </div>
      <div class="col-auto">
        <select v-model="filters.status" class="form-select form-select-sm" aria-label="상태">
          <option value="">상태: 전체</option>
          <option v-for="(label, value) in STATUSES" :key="value" :value="value">
            {{ label }}
          </option>
        </select>
      </div>
    </div>

    <div class="card">
      <div class="table-responsive">
        <table class="table table-hover table-sm align-middle mb-0">
          <thead class="table-light">
            <tr>
              <th>문서</th>
              <th>분류</th>
              <th>상태</th>
              <th class="text-end">메타데이터</th>
              <th>등록</th>
              <th class="text-end">작업</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="6" class="text-center py-4">
                <span class="spinner-border spinner-border-sm"></span>
              </td>
            </tr>
            <tr v-else-if="!documents.length">
              <td colspan="6"><EmptyState message="등록된 회사 자료 문서가 없습니다." /></td>
            </tr>
            <tr v-for="doc in documents" v-else :key="doc.id">
              <td>
                <router-link :to="`/admin/documents/${doc.id}`" class="fw-semibold">{{
                  doc.display_name
                }}</router-link>
                <div class="small text-muted">
                  {{ doc.file_format }} · {{ formatBytes(doc.file_size) }}
                </div>
              </td>
              <td>
                {{ doc.category_name || '미분류' }}
                <span
                  v-if="doc.category_source === 'MANUAL'"
                  class="badge bg-light text-dark border"
                  >수동</span
                >
              </td>
              <td>
                <span :class="['badge', `bg-${DOCUMENT_STATUS_VARIANT[doc.status]}`]">{{
                  doc.status_label
                }}</span>
                <div v-if="doc.error_message" class="small text-danger">
                  {{ doc.error_message }}
                </div>
              </td>
              <td class="text-end">{{ doc.metadata_count }}</td>
              <td class="small">{{ formatDateTime(doc.created_at) }}</td>
              <td class="text-end text-nowrap">
                <router-link
                  :to="`/admin/documents/${doc.id}`"
                  class="btn btn-sm btn-outline-primary me-1"
                  >검토</router-link
                >
                <button class="btn btn-sm btn-outline-secondary me-1" @click="reprocess(doc)">
                  다시 처리
                </button>
                <button class="btn btn-sm btn-outline-danger" @click="askDelete(doc)">삭제</button>
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
      :show="textModal.show"
      title="텍스트로 입력"
      size="lg"
      @close="textModal.show = false"
    >
      <form id="text-doc-form" @submit.prevent="submitText">
        <div class="row g-3">
          <div class="col-md-7">
            <label class="form-label small" for="td-title">제목</label>
            <input
              id="td-title"
              v-model="textModal.title"
              class="form-control form-control-sm"
              required
            />
          </div>
          <div class="col-md-5">
            <label class="form-label small" for="td-category">분류</label>
            <select
              id="td-category"
              v-model="textModal.category"
              class="form-select form-select-sm"
            >
              <option value="">자동 분류</option>
              <option v-for="s in companySchemas" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </div>
          <div class="col-12">
            <label class="form-label small" for="td-text">내용</label>
            <textarea
              id="td-text"
              v-model="textModal.text"
              class="form-control"
              rows="12"
              required
            ></textarea>
          </div>
        </div>
        <div v-if="textModal.error" class="alert alert-danger py-2 small mt-3 mb-0">
          {{ textModal.error }}
        </div>
      </form>
      <template #footer>
        <button class="btn btn-secondary" @click="textModal.show = false">취소</button>
        <button class="btn btn-primary" form="text-doc-form" :disabled="textModal.saving">
          등록
        </button>
      </template>
    </BaseModal>

    <ConfirmModal
      :show="confirm.show"
      title="문서 삭제"
      :message="`'${confirm.doc?.display_name}' 문서와 메타데이터를 삭제합니다.\n이미 반영된 회사 자료(제품·성적서 등)는 유지됩니다.`"
      confirm-text="삭제"
      :loading="confirm.saving"
      @confirm="doDelete"
      @cancel="confirm.show = false"
    />
  </div>
</template>
