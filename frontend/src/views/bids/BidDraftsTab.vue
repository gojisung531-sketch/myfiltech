<script setup>
// ④ 초안 생성 (specs/05 §3 ④)
// 표시하는 버전·수정 여부·규칙 기반 여부·상태는 모두 서버가 저장한 메타데이터다.
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
import { downloadFile, PDF_TYPES, XLSX_CONTENT_TYPES } from '@/utils/download'
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
const loading = ref(true)
const loadError = ref('')
const jobs = reactive({}) // doc_type → job id
const newVersion = reactive({})
const downloading = ref('')
const starting = ref('') // 생성 요청 전송 중인 문서 유형
const downloadError = reactive({}) // `${type}.${format}` → 메시지
let loadSeq = 0

async function load() {
  const mine = ++loadSeq
  loadError.value = ''
  try {
    const result = await listDrafts(props.bid.id)
    if (mine === loadSeq) drafts.value = result
  } catch (err) {
    if (mine === loadSeq) loadError.value = errorMessage(err, '초안 목록을 불러오지 못했습니다.')
  } finally {
    if (mine === loadSeq) loading.value = false
  }
}
onMounted(load)

async function generate(type) {
  if (starting.value || jobs[type]) return
  starting.value = type
  try {
    const res = await generateDraft(props.bid.id, type, !!newVersion[type])
    jobs[type] = res.job_id
  } catch (err) {
    toast.error(errorMessage(err, '초안 생성을 시작하지 못했습니다.'))
  } finally {
    starting.value = ''
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

// 이 목록의 버튼은 항상 서버의 '최신 버전'을 대상으로 한다(버전 지정 없음).
async function download(draft, format) {
  const key = `${draft.doc_type}.${format}`
  if (downloading.value) return
  downloading.value = key
  downloadError[key] = ''
  try {
    const xlsx = format === 'xlsx'
    await downloadFile(
      () => (xlsx ? downloadDraftXlsx : downloadDraftPdf)(props.bid.id, draft.doc_type),
      {
        types: xlsx ? XLSX_CONTENT_TYPES : PDF_TYPES,
        fallbackName: `${draft.doc_type}.${format}`,
        failMessage: `${format.toUpperCase()} 파일을 만들지 못했습니다.`,
      },
    )
    toast.success(
      `최신 v${draft.latest.version}의 ${format.toUpperCase()} 파일 저장을 요청했습니다.`,
    )
  } catch (err) {
    downloadError[key] = err.message
  } finally {
    downloading.value = ''
  }
}
</script>

<template>
  <div>
    <div v-if="!bid.requirement_count" class="alert alert-warning small">
      저장된 요구사항이 없어 판정할 수 없습니다.
      <template v-if="bid.processing_status === 'DRAFT'">
        요구조건 추출이 아직 실행되지 않은 상태입니다.
      </template>
      <template v-else-if="bid.processing_status === 'FAILED'">
        처리에 실패한 상태입니다. 상세 오류를 확인하세요.
      </template>
      이 상태에서 만든 초안은 판정 내용이 없을 수 있습니다.
    </div>
    <div v-else-if="!bid.verdict_counts?.total" class="alert alert-warning small">
      요구사항 {{ bid.requirement_count }}건은 있지만 아직 판정하지 않았습니다. ③ 판정 탭에서 판정을
      실행할 수 있습니다(LLM 설정이 필요할 수 있습니다). 판정 전에 만든 초안은 판정 내용이 비어 있을
      수 있습니다.
    </div>

    <div v-if="loading" class="text-center py-5"><span class="spinner-border"></span></div>
    <div
      v-else-if="loadError"
      class="alert alert-danger d-flex align-items-center gap-2"
      role="alert"
    >
      <i class="bi bi-exclamation-octagon"></i>
      <span class="flex-grow-1">{{ loadError }}</span>
      <button class="btn btn-sm btn-outline-secondary" @click="load">다시 시도</button>
    </div>
    <div v-else class="row g-3">
      <div v-for="d in drafts" :key="d.doc_type" class="col-md-6">
        <div class="card h-100">
          <div class="card-body">
            <div class="d-flex align-items-start">
              <i class="bi fs-3 me-3 draft-icon" :class="ICONS[d.doc_type]"></i>
              <div class="me-auto">
                <h2 class="h6 mb-1">{{ d.doc_type_label }}</h2>
                <div class="small text-muted">{{ DESCRIPTIONS[d.doc_type] }}</div>
              </div>
            </div>
            <div class="small mt-3">
              <template v-if="d.latest">
                <div>
                  최신 <strong>v{{ d.latest.version }}</strong> (저장된 버전
                  {{ d.version_count }}개)
                </div>
                <div class="d-flex flex-wrap gap-1 align-items-center mt-1">
                  <span
                    class="badge"
                    :class="d.latest.status === 'FINAL' ? 'bg-success' : 'bg-secondary'"
                    >{{ d.latest.status_label }}</span
                  >
                  <span v-if="d.latest.is_modified" class="badge bg-info">담당자 수정본</span>
                  <span v-else class="badge bg-secondary">수정 없음</span>
                  <span class="badge bg-secondary">{{
                    d.latest.used_llm ? 'LLM 보강' : '규칙 기반'
                  }}</span>
                  <span v-if="d.latest.created_at" class="text-muted"
                    >생성 {{ formatDateTime(d.latest.created_at) }} ·</span
                  >
                  <span class="text-muted">
                    수정 {{ formatDateTime(d.latest.updated_at) }}
                    <template v-if="d.latest.updated_by_name"
                      >· {{ d.latest.updated_by_name }}</template
                    >
                  </span>
                </div>
              </template>
              <span v-else class="text-muted"
                >저장된 초안이 없습니다. 생성하면 저장된 초안이 만들어집니다.</span
              >
            </div>
            <JobProgress
              v-if="jobs[d.doc_type]"
              :job-id="jobs[d.doc_type]"
              label="생성"
              class="mt-2"
              @done="(job) => onDone(d.doc_type, job)"
            />
            <div v-for="format in ['pdf', 'xlsx']" :key="format" class="mt-2">
              <div
                v-if="downloadError[`${d.doc_type}.${format}`]"
                class="alert alert-danger py-2 small mb-0"
                role="alert"
              >
                {{ downloadError[`${d.doc_type}.${format}`] }}
                <button
                  class="btn btn-sm btn-outline-secondary ms-2"
                  :disabled="!!downloading"
                  @click="download(d, format)"
                >
                  다시 시도
                </button>
              </div>
            </div>
          </div>
          <div class="card-footer d-flex flex-wrap align-items-center gap-2">
            <button
              class="btn btn-sm btn-primary"
              :disabled="!!jobs[d.doc_type] || !!starting"
              @click="generate(d.doc_type)"
            >
              <span
                v-if="starting === d.doc_type"
                class="spinner-border spinner-border-sm me-1"
              ></span
              >{{ d.latest ? '재생성' : '생성' }}
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
              :disabled="!!downloading"
              :title="`최신 v${d.latest.version}의 저장된 내용으로 PDF를 만듭니다`"
              @click="download(d, 'pdf')"
            >
              <span
                v-if="downloading === `${d.doc_type}.pdf`"
                class="spinner-border spinner-border-sm me-1"
              ></span>
              <i v-else class="bi bi-file-earmark-pdf me-1"></i>PDF
            </button>
            <button
              v-if="d.latest && XLSX_TYPES.includes(d.doc_type)"
              class="btn btn-sm btn-outline-secondary"
              :disabled="!!downloading"
              :title="`최신 v${d.latest.version}의 저장된 내용으로 XLSX를 만듭니다`"
              @click="download(d, 'xlsx')"
            >
              <span
                v-if="downloading === `${d.doc_type}.xlsx`"
                class="spinner-border spinner-border-sm me-1"
              ></span>
              <i v-else class="bi bi-file-earmark-excel me-1"></i>XLSX
            </button>
          </div>
        </div>
      </div>
    </div>

    <details class="ft-help mt-3">
      <summary>생성·재생성·다운로드 안내</summary>
      <p class="mb-1">
        <strong>생성 방식:</strong> 서버가 판정 결과로 내용을 규칙 기반으로 먼저 만들고, LLM이
        설정·사용 설정된 경우에만 문장을 보강합니다. 각 문서의 ‘규칙 기반/LLM 보강’은 서버에 저장된
        값입니다.
      </p>
      <p class="mb-1">
        <strong>재생성:</strong> 최신 버전이 <em>담당자 수정본</em>이면 덮어쓰지 않고 새 버전을
        만듭니다. 수정본이 아니면 최신 버전을 덮어쓰며(확정 상태는 초안으로 돌아감), ‘새 버전으로’를
        선택하면 항상 새 버전을 만듭니다.
      </p>
      <p class="mb-0">
        <strong>다운로드:</strong> 이 화면의 PDF·XLSX는 최신 버전의 저장된 내용 기준입니다. 이전
        버전은 편집 화면에서 버전을 선택해 받으세요. ‘확정’ 표시는 내부 검토 상태이며 제출·법적 검토
        완료를 뜻하지 않습니다. 모든 초안은 제출 전 담당자 검토가 필요합니다.
      </p>
    </details>
  </div>
</template>

<style scoped>
.draft-icon {
  color: var(--ft-primary);
}
</style>
