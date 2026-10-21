<script setup>
// ④ 초안 생성 (specs/05 §3 ④)
import { onMounted, reactive, ref } from 'vue'

import {
  DRAFT_TYPES,
  downloadDraftPdf,
  downloadDraftXlsx,
  generateDraft,
  listDrafts,
  XLSX_TYPES,
} from '@/api/drafts'
import JobProgress from '@/components/JobProgress.vue'
import { useToastStore } from '@/stores/toast'
import { saveResponse } from '@/utils/download'
import { errorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/format'

const props = defineProps({ bid: { type: Object, required: true } })

const DESCRIPTIONS = {
  COMPLIANCE_MATRIX: '요구사항별 충족 여부·제안 사양·응답·근거 (A4 가로)',
  BID_CHECKLIST: '자격·제출서류·심사·시험·일정 체크리스트',
  TECHNICAL_QUERY: '확인 필요·대체안 항목의 발주처 질의 공문',
  REVIEW_REPORT: '총평·입찰 권고·주요 위험·후속 조치 (내부용)',
}
const ICONS = {
  COMPLIANCE_MATRIX: 'bi-table',
  BID_CHECKLIST: 'bi-check2-square',
  TECHNICAL_QUERY: 'bi-envelope-paper',
  REVIEW_REPORT: 'bi-clipboard-data',
}

const toast = useToastStore()
const drafts = ref([])
const jobs = reactive({}) // doc_type → job id
const newVersion = reactive({})
const downloading = ref('')

async function load() {
  try {
    drafts.value = await listDrafts(props.bid.id)
  } catch (err) {
    toast.error(errorMessage(err))
  }
}
onMounted(load)

async function generate(type) {
  try {
    const res = await generateDraft(props.bid.id, type, !!newVersion[type])
    jobs[type] = res.job_id
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

function onDone(type, job) {
  delete jobs[type]
  if (job.status === 'SUCCEEDED') {
    const r = job.result
    toast.success(
      `${DRAFT_TYPES[type]} v${r.version} 생성 완료${r.used_llm ? '' : ' (LLM 미사용 — 규칙 기반 초안)'}`,
    )
  } else if (job.status === 'FAILED') toast.error(job.error || '초안 생성에 실패했습니다.')
  load()
}

async function download(type, format) {
  downloading.value = `${type}.${format}`
  try {
    const request = format === 'xlsx' ? downloadDraftXlsx : downloadDraftPdf
    saveResponse(await request(props.bid.id, type), `${type}.${format}`)
  } catch (err) {
    toast.error(errorMessage(err, `${format.toUpperCase()} 파일을 만들지 못했습니다.`))
  } finally {
    downloading.value = ''
  }
}
</script>

<template>
  <div>
    <div v-if="!bid.verdict_counts?.total" class="alert alert-warning small">
      아직 판정하지 않았습니다. 초안은 판정 결과를 바탕으로 만들어지므로 먼저
      <strong>판정 실행</strong>을 권장합니다.
    </div>
    <div class="row g-3">
      <div v-for="d in drafts" :key="d.doc_type" class="col-md-6">
        <div class="card h-100">
          <div class="card-body">
            <div class="d-flex align-items-start">
              <i class="bi fs-3 me-3 text-primary" :class="ICONS[d.doc_type]"></i>
              <div class="me-auto">
                <h2 class="h6 mb-1">{{ d.doc_type_label }}</h2>
                <div class="small text-muted">{{ DESCRIPTIONS[d.doc_type] }}</div>
              </div>
            </div>
            <div class="small mt-3">
              <template v-if="d.latest">
                최신 v{{ d.latest.version }} ({{ d.version_count }}개 버전) ·
                {{ d.latest.status_label }} · {{ formatDateTime(d.latest.updated_at) }}
                <span v-if="d.latest.is_modified" class="badge bg-secondary ms-1">수정됨</span>
                <span v-if="!d.latest.used_llm" class="badge bg-light text-dark border ms-1"
                  >규칙 기반</span
                >
              </template>
              <span v-else class="text-muted">아직 생성하지 않았습니다.</span>
            </div>
            <JobProgress
              v-if="jobs[d.doc_type]"
              :job-id="jobs[d.doc_type]"
              label="생성"
              class="mt-2"
              @done="(job) => onDone(d.doc_type, job)"
            />
          </div>
          <div class="card-footer d-flex flex-wrap align-items-center gap-2">
            <button
              class="btn btn-sm btn-primary"
              :disabled="!!jobs[d.doc_type]"
              @click="generate(d.doc_type)"
            >
              {{ d.latest ? '재생성' : '생성' }}
            </button>
            <div v-if="d.latest" class="form-check mb-0">
              <input
                :id="`nv-${d.doc_type}`"
                v-model="newVersion[d.doc_type]"
                class="form-check-input"
                type="checkbox"
              />
              <label class="form-check-label small" :for="`nv-${d.doc_type}`">새 버전으로</label>
            </div>
            <span class="ms-auto"></span>
            <router-link
              v-if="d.latest"
              :to="`/bids/${bid.id}/drafts/${d.doc_type}`"
              class="btn btn-sm btn-outline-primary"
            >
              <i class="bi bi-pencil me-1"></i>편집
            </router-link>
            <button
              v-if="d.latest"
              class="btn btn-sm btn-outline-secondary"
              :disabled="downloading === `${d.doc_type}.pdf`"
              @click="download(d.doc_type, 'pdf')"
            >
              <i class="bi bi-file-earmark-pdf me-1"></i>PDF
            </button>
            <button
              v-if="d.latest && XLSX_TYPES.includes(d.doc_type)"
              class="btn btn-sm btn-outline-success"
              :disabled="downloading === `${d.doc_type}.xlsx`"
              @click="download(d.doc_type, 'xlsx')"
            >
              <i class="bi bi-file-earmark-excel me-1"></i>XLSX
            </button>
          </div>
        </div>
      </div>
    </div>
    <p class="small text-muted mt-3 mb-0">
      재생성하면 최신 버전을 덮어씁니다. 담당자가 수정한 버전이 있거나 ‘새 버전으로’를 선택하면 새
      버전을 만들고 이전 버전은 보존됩니다.
    </p>
  </div>
</template>
