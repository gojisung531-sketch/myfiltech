<script setup>
// ③ 판정 및 자동 답변 (specs/05 §3 ③, specs/11 BidDetailView)
// 판정 값(verdict·위험도)은 서버가 준 그대로 표시한다. 이 화면은 값을 재계산하거나 바꾸지 않는다.
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import {
  evaluationHistory,
  listRequirementsWithEvaluation,
  revertEvaluation,
  updateEvaluation,
} from '@/api/bids'
import BaseModal from '@/components/BaseModal.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'
import DocumentOffcanvas from '@/components/DocumentOffcanvas.vue'
import LocationStatus from '@/components/LocationStatus.vue'
import EmptyState from '@/components/EmptyState.vue'
import ReadableText from '@/components/ReadableText.vue'
import RiskDot from '@/components/RiskDot.vue'
import VerdictBadge from '@/components/VerdictBadge.vue'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { statusInfo, viewerFromLocation } from '@/utils/evidenceLocation'
import { formatDateTime } from '@/utils/format'
import { RISK_LEVELS, VERDICTS } from '@/utils/options'

const props = defineProps({
  bid: { type: Object, required: true },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['evaluate', 'changed'])

const EVIDENCE_LABELS = {
  product: '제품 자료',
  test_report: '시험성적서',
  certificate: '인증서',
  delivery_record: '납품실적',
  bid_quote: '공고 원문',
  company: '회사 정보',
  document: '수동 입력',
}

const toast = useToastStore()
const auth = useAuthStore()
const rows = ref([])
const loading = ref(true)
const loadError = ref('')
const expanded = ref(new Set())
const filters = reactive({ verdict: '', highOnly: false, modifiedOnly: false })
const emptyViewer = {
  documentId: null,
  page: 0,
  quote: '',
  kind: 'attachment',
  title: '',
  text: '',
  note: '',
  location: null,
}
const viewer = ref({ ...emptyViewer })

// 수정 폼은 서버에서 받은 행과 분리된 사본이다. 저장 응답이 오기 전에는 원본 행을 바꾸지 않는다.
const editor = reactive({
  show: false,
  row: null,
  form: {},
  actionsText: '',
  saving: false,
  error: '',
  initial: '',
})
const confirmDiscard = ref(false)
const history = reactive({ show: false, row: null, items: [], loading: false, error: '' })
const confirmRevert = ref(null)
const confirmReeval = ref(null)
const acting = ref(null) // 되돌리기 요청이 진행 중인 요구사항 id
const rowError = reactive({}) // 행별 되돌리기 오류
let historySeq = 0

async function load() {
  loadError.value = ''
  try {
    rows.value = await listRequirementsWithEvaluation(props.bid.id)
  } catch (err) {
    loadError.value = errorMessage(err, '요구사항과 판정을 불러오지 못했습니다.')
  } finally {
    loading.value = false
  }
}
onMounted(load)

function reload() {
  loading.value = true
  load()
}

// 저장·되돌리기·수정 폼이 열려 있는 동안에는 다른 판정 변경을 시작하지 못하게 한다.
const locked = computed(() => editor.saving || !!acting.value || editor.show)

// 아래 집계는 필터와 무관하게 이 공고의 전체 요구사항 기준이다.
const evaluated = computed(() => rows.value.filter((r) => r.evaluation))
const summary = computed(() => {
  const counts = { MET: 0, NEEDS_SUPPLEMENT: 0, NEEDS_CONFIRMATION: 0, HIGH: 0, modified: 0 }
  for (const r of evaluated.value) {
    counts[r.evaluation.verdict] += 1
    if (r.evaluation.risk_level === 'HIGH') counts.HIGH += 1
    if (r.evaluation.is_modified) counts.modified += 1
  }
  return counts
})
const unevaluatedCount = computed(() => rows.value.length - evaluated.value.length)
const hasFilters = computed(() => !!filters.verdict || filters.highOnly || filters.modifiedOnly)
const visible = computed(() =>
  rows.value.filter((r) => {
    const e = r.evaluation
    if (filters.verdict === 'NONE') return !e
    if (filters.verdict && e?.verdict !== filters.verdict) return false
    if (filters.highOnly && e?.risk_level !== 'HIGH') return false
    if (filters.modifiedOnly && !e?.is_modified) return false
    return true
  }),
)

function resetFilters() {
  filters.verdict = ''
  filters.highOnly = false
  filters.modifiedOnly = false
}

function toggle(id) {
  const next = new Set(expanded.value)
  next.has(id) ? next.delete(id) : next.add(id)
  expanded.value = next
}

// ---- 근거 표시 ----
const isManual = (e) => !e.id && !e.document_id
function evidencePosition(e) {
  if (!e.page) return '위치 정보 없음'
  return e.type === 'bid_quote'
    ? `저장된 참조 위치 p.${e.page}`
    : `저장된 참조 위치 p.${e.page} (원문 대조 필요)`
}

function openEvidence(e, row) {
  const loc = e.source_location
  if (loc?.document_id) {
    // 저장 판정이 기록한 근거를 지금 원본과 대조한 위치(B6B). 판정은 바뀌지 않는다.
    viewer.value = {
      ...viewerFromLocation(loc, {
        title: row.title,
        text: e.type === 'bid_quote' ? row.requirement_text : e.label,
        note: '',
      }),
    }
    return
  }
  if (loc) {
    toast.show(
      `원문을 열 수 없습니다 — ${statusInfo(loc).label}. ${statusInfo(loc).reason || ''}`,
      'warning',
    )
    return
  }
  if (!e.document_id) {
    toast.show(
      isManual(e)
        ? '수동으로 입력한 근거라 연결된 원본 문서가 없습니다.'
        : '이 근거에는 연결된 원본 문서가 없습니다(문서 ID가 저장되지 않음). 근거 라벨과 인용문만 확인할 수 있습니다.',
      'warning',
    )
    return
  }
  const fromBid = e.type === 'bid_quote'
  viewer.value = {
    documentId: e.document_id,
    page: e.page || 0,
    quote: e.quote || '',
    kind: fromBid ? 'requirement_source' : 'reference',
    title: row.title,
    text: fromBid ? row.requirement_text : e.label,
    // 공고 원문 근거 외에는 서버가 위치를 고정값으로 기록하는 유형이 있어 위치를 검증된 값으로 보지 않는다.
    note: fromBid
      ? ''
      : '위치는 서버가 기록한 참조값이며 원문 대조가 필요합니다(고정값일 수 있음).',
  }
}

// ---- 수정 ----
const snapshot = () => JSON.stringify([editor.form, editor.actionsText])
const dirty = computed(() => editor.show && snapshot() !== editor.initial)

function openEditor(row) {
  if (locked.value) return
  const e = row.evaluation
  Object.assign(editor, {
    show: true,
    row,
    saving: false,
    error: '',
    form: {
      verdict: e.verdict,
      risk_level: e.risk_level,
      company_value: e.company_value,
      auto_answer: e.auto_answer,
      rationale: e.rationale,
      clarification_question: e.clarification_question,
      // document_id는 서버가 조회용으로 붙이는 값이라 편집 사본에서도 건드리지 않는다.
      evidences: e.evidences.map(({ type, id, label, page, quote }) => ({
        type,
        id: id || 0,
        label,
        page: page || 0,
        quote: quote || '',
      })),
    },
    actionsText: e.action_items.join('\n'),
  })
  editor.initial = snapshot()
}

function closeEditor() {
  confirmDiscard.value = false
  editor.show = false
  editor.error = ''
}

// 취소·X·배경 클릭 모두 이 경로를 지난다. 미저장 입력이 있으면 확인을 받는다.
function requestCloseEditor() {
  if (editor.saving) return
  if (dirty.value) confirmDiscard.value = true
  else closeEditor()
}

function validate() {
  for (const [i, ev] of editor.form.evidences.entries()) {
    if (!String(ev.label || '').trim()) return `근거 ${i + 1}의 이름을 입력하거나 삭제하세요.`
    const page = ev.page === '' || ev.page == null ? 0 : Number(ev.page)
    if (!Number.isInteger(page) || page < 0) {
      return `근거 ${i + 1}의 위치는 0 이상의 정수여야 합니다(없으면 0 또는 비움).`
    }
  }
  return ''
}

async function save() {
  if (editor.saving) return
  const problem = validate()
  if (problem) {
    editor.error = problem
    return
  }
  const payload = {
    verdict: editor.form.verdict,
    risk_level: editor.form.risk_level,
    company_value: editor.form.company_value,
    auto_answer: editor.form.auto_answer,
    rationale: editor.form.rationale,
    clarification_question: editor.form.clarification_question,
    action_items: editor.actionsText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean),
    // 기존 type/id 연결을 그대로 보낸다. 위치 미상(0)을 1페이지로 바꾸지 않는다.
    evidences: editor.form.evidences.map(({ type, id, label, page, quote }) => ({
      type,
      id: id || 0,
      label: label.trim(),
      page: page === '' || page == null ? 0 : Number(page),
      quote: quote || '',
    })),
  }
  editor.saving = true
  editor.error = ''
  try {
    const saved = await updateEvaluation(editor.row.evaluation.id, payload)
    editor.row.evaluation = saved // 서버 응답으로만 반영한다.
    closeEditor()
    toast.success('판정을 수정했습니다.')
    emit('changed')
  } catch (err) {
    editor.error = errorMessage(
      err,
      '저장하지 못했습니다. 입력은 그대로 남아 있으니 다시 저장하세요.',
    )
  } finally {
    editor.saving = false
  }
}

function onBeforeUnload(event) {
  if (dirty.value) {
    event.preventDefault()
    event.returnValue = ''
  }
}
window.addEventListener('beforeunload', onBeforeUnload)
onBeforeUnmount(() => window.removeEventListener('beforeunload', onBeforeUnload))

// ---- 자동 판정 기록으로 복원 (새 LLM 호출이 아님) ----
function askRevert(row) {
  if (locked.value || props.busy) return
  confirmRevert.value = row
}

async function doRevert() {
  const row = confirmRevert.value
  if (!row || acting.value) return
  acting.value = row.id
  rowError[row.id] = ''
  try {
    row.evaluation = await revertEvaluation(row.evaluation.id)
    confirmRevert.value = null
    toast.success('마지막 자동 판정 기록으로 복원했습니다.')
    emit('changed')
  } catch (err) {
    confirmRevert.value = null
    rowError[row.id] = errorMessage(err, '복원하지 못했습니다.')
  } finally {
    acting.value = null
  }
}

// ---- 이력 ----
async function openHistory(row) {
  const mine = ++historySeq
  Object.assign(history, { show: true, row, items: [], loading: true, error: '' })
  try {
    const items = await evaluationHistory(row.evaluation.id)
    if (mine === historySeq) history.items = items
  } catch (err) {
    if (mine === historySeq) history.error = errorMessage(err, '이력을 불러오지 못했습니다.')
  } finally {
    if (mine === historySeq) history.loading = false
  }
}

function closeHistory() {
  historySeq += 1
  history.show = false
}

// ---- 개별 재판정 ----
function askReevaluate(row) {
  if (locked.value || props.busy) return
  confirmReeval.value = row
}

function doReevaluate() {
  const row = confirmReeval.value
  confirmReeval.value = null
  if (!row || props.busy) return
  emit('evaluate', { keepModified: false, requirementIds: [row.id] })
}
</script>

<template>
  <div>
    <div v-if="loading" class="text-center py-5"><span class="spinner-border"></span></div>
    <div
      v-else-if="loadError"
      class="alert alert-danger d-flex align-items-center gap-2"
      role="alert"
    >
      <i class="bi bi-exclamation-octagon"></i>
      <span class="flex-grow-1">{{ loadError }}</span>
      <button class="btn btn-sm btn-outline-secondary" @click="reload">다시 시도</button>
    </div>
    <template v-else>
      <div v-if="!rows.length" class="alert alert-info small" role="status">
        <template v-if="bid.processing_status === 'EXTRACTING'">
          요구조건 추출이 진행 중입니다. 완료되면 이 화면에서 요구사항과 판정을 볼 수 있습니다.
        </template>
        <template v-else-if="bid.processing_status === 'FAILED'">
          처리에 실패해 저장된 요구사항이 없을 수 있습니다. 상세 오류를 확인하세요.
        </template>
        <template v-else-if="bid.processing_status === 'DRAFT'">
          아직 요구조건 추출을 실행하지 않아 판정할 요구사항이 없습니다.
          <template v-if="auth.isAdmin">
            관리자는
            <router-link :to="`/admin/bids/${bid.id}/edit`">공고 편집 화면</router-link>에서 추출을
            실행할 수 있습니다.
          </template>
          <template v-else>관리자가 추출을 실행하면 이 화면에 표시됩니다.</template>
        </template>
        <template v-else>
          저장된 요구사항이 없어 판정할 대상이 없습니다. 추출 누락 가능성이 있으니 첨부 원문을
          확인하세요.
        </template>
      </div>

      <div v-if="rows.length" class="card mb-3">
        <div class="card-body py-2">
          <div class="small text-muted mb-1">전체 {{ rows.length }}건 기준 (필터와 무관)</div>
          <div class="d-flex flex-wrap align-items-center gap-2">
            <span class="badge bg-success fs-6 fw-normal">충족 {{ summary.MET }}</span>
            <span class="badge bg-warning fs-6 fw-normal"
              >보완 필요 {{ summary.NEEDS_SUPPLEMENT }}</span
            >
            <span class="badge bg-info fs-6 fw-normal"
              >확인 필요 {{ summary.NEEDS_CONFIRMATION }}</span
            >
            <span class="badge bg-secondary fs-6 fw-normal">미판정 {{ unevaluatedCount }}</span>
            <span class="badge bg-danger fs-6 fw-normal">HIGH 위험 {{ summary.HIGH }}</span>
            <span class="small text-muted">담당자 수정 {{ summary.modified }}건</span>
          </div>
        </div>
        <div class="card-footer d-flex flex-wrap align-items-center gap-2">
          <select
            v-model="filters.verdict"
            class="form-select form-select-sm w-auto"
            aria-label="판정 필터"
          >
            <option value="">판정: 전체</option>
            <option v-for="v in VERDICTS" :key="v.value" :value="v.value">{{ v.label }}</option>
            <option value="NONE">미판정</option>
          </select>
          <div class="form-check">
            <input
              id="f-high"
              v-model="filters.highOnly"
              class="form-check-input"
              type="checkbox"
            />
            <label class="form-check-label small" for="f-high">HIGH만</label>
          </div>
          <div class="form-check">
            <input
              id="f-mod"
              v-model="filters.modifiedOnly"
              class="form-check-input"
              type="checkbox"
            />
            <label class="form-check-label small" for="f-mod">수정됨만</label>
          </div>
          <button v-if="hasFilters" class="btn btn-sm btn-outline-secondary" @click="resetFilters">
            <i class="bi bi-arrow-counterclockwise me-1"></i>필터 초기화
          </button>
          <span class="small text-muted ms-auto"
            >현재 목록 {{ visible.length }} / {{ rows.length }}건</span
          >
        </div>
      </div>

      <div v-if="rows.length && !evaluated.length" class="alert alert-info small" role="status">
        <template v-if="busy">요구사항은 저장되어 있고 판정이 진행 중입니다.</template>
        <template v-else>
          요구사항 {{ rows.length }}건이 저장되어 있지만 아직 판정하지 않았습니다. 상단의
          <strong>판정 실행</strong>으로 시작할 수 있습니다(LLM 설정이 필요할 수 있습니다).
        </template>
      </div>
      <EmptyState
        v-if="rows.length && !visible.length"
        message="선택한 필터에 맞는 요구사항이 없습니다. 필터를 바꿔 보세요."
      >
        <button class="btn btn-sm btn-outline-secondary" @click="resetFilters">필터 초기화</button>
      </EmptyState>

      <div class="list-group">
        <div v-for="row in visible" :key="row.id" class="list-group-item">
          <div
            class="d-flex align-items-start gap-2 row-head"
            role="button"
            tabindex="0"
            :aria-expanded="expanded.has(row.id)"
            @click="toggle(row.id)"
            @keydown.enter.prevent="toggle(row.id)"
            @keydown.space.prevent="toggle(row.id)"
          >
            <i
              class="bi mt-1"
              :class="expanded.has(row.id) ? 'bi-chevron-down' : 'bi-chevron-right'"
            ></i>
            <div class="verdict-col text-nowrap">
              <VerdictBadge :verdict="row.evaluation?.verdict" />
              <RiskDot :risk="row.evaluation?.risk_level" class="ms-1" />
            </div>
            <div class="flex-grow-1 small min-w-0">
              <span class="text-muted"
                >{{ row.category_label
                }}<span v-if="row.item_label"> · {{ row.item_label }}</span></span
              >
              <div class="text-break">
                <span class="fw-semibold">{{ row.title }}</span>
                <span v-if="row.is_mandatory" class="badge bg-danger ms-1">필수</span>
                <span v-if="row.evaluation?.is_modified" class="badge bg-secondary ms-1"
                  >담당자 수정</span
                >
                <span class="text-muted ms-1">{{ row.requirement_text }}</span>
              </div>
              <div v-if="row.evaluation?.auto_answer" class="text-body mt-1 text-break">
                {{ row.evaluation.auto_answer }}
              </div>
            </div>
          </div>

          <div v-if="expanded.has(row.id) && row.evaluation" class="detail mt-3 small">
            <div class="row g-3">
              <div class="col-lg-7">
                <section class="mb-3">
                  <div class="detail-label">공고 요구조건 (저장된 요구사항)</div>
                  <ReadableText :text="row.requirement_text || row.title" />
                </section>
                <section class="mb-3">
                  <div class="detail-label">회사 대응 값 (판정 시 서버 기록)</div>
                  <ReadableText
                    v-if="row.evaluation.company_value"
                    :text="row.evaluation.company_value"
                    mode="candidates"
                  />
                  <p v-else class="mb-0 text-muted">
                    미제공 (자료 미등록·연결 없음일 수 있음 — 미보유 아님)
                  </p>
                </section>
                <section class="mb-3">
                  <div class="detail-label">판정 사유</div>
                  <ReadableText v-if="row.evaluation.rationale" :text="row.evaluation.rationale" />
                  <p v-else class="mb-0 text-muted">미제공</p>
                  <div v-if="row.evaluation.rule_trace?.interpolation" class="text-muted mt-1">
                    계산: {{ row.evaluation.rule_trace.interpolation }}
                  </div>
                  <details
                    v-if="Object.keys(row.evaluation.rule_trace || {}).length"
                    class="ft-help mt-1"
                  >
                    <summary>서버 판정 계산 기록</summary>
                    <pre class="small mb-0 trace">{{
                      JSON.stringify(row.evaluation.rule_trace, null, 2)
                    }}</pre>
                  </details>
                </section>
                <section class="mb-3">
                  <div class="detail-label">
                    답변 초안 <span class="fw-normal text-muted">· 자동 제출 안 됨</span>
                  </div>
                  <ReadableText
                    v-if="row.evaluation.auto_answer"
                    :text="row.evaluation.auto_answer"
                  />
                  <p v-else class="mb-0 text-muted">미제공</p>
                </section>
                <section class="mb-3">
                  <div class="detail-label">후속 조치</div>
                  <ul v-if="row.evaluation.action_items.length" class="mb-0">
                    <li v-for="a in row.evaluation.action_items" :key="a" class="text-break">
                      {{ a }}
                    </li>
                  </ul>
                  <p v-else class="mb-0 text-muted">미제공</p>
                </section>
                <section>
                  <div class="detail-label">
                    발주처 질의 초안
                    <span class="fw-normal text-muted">· 자동 발송 안 됨</span>
                  </div>
                  <ReadableText
                    v-if="row.evaluation.clarification_question"
                    class="border-start border-3 ps-2"
                    :text="row.evaluation.clarification_question"
                  />
                  <p v-else class="mb-0 text-muted">미제공</p>
                </section>
              </div>

              <div class="col-lg-5">
                <section class="mb-3">
                  <div class="detail-label">연결 자료 · 근거</div>
                  <ul class="list-unstyled mb-0">
                    <li v-for="(e, i) in row.evaluation.evidences" :key="i" class="mb-2">
                      <span class="badge bg-secondary me-1">{{
                        EVIDENCE_LABELS[e.type] || e.type
                      }}</span>
                      <button
                        class="btn btn-link btn-sm p-0 text-start small text-break"
                        :class="{ 'text-body text-decoration-none': !e.document_id }"
                        @click="openEvidence(e, row)"
                      >
                        {{ e.label }}
                      </button>
                      <span v-if="!e.document_id" class="text-muted">
                        ({{ isManual(e) ? '수동 입력 · ' : '' }}원본 문서 미연결)</span
                      >
                      <div v-if="e.source_location" class="small">
                        <LocationStatus :location="e.source_location" />
                        <span class="text-muted ms-1">· 저장된 판정 근거</span>
                      </div>
                      <div v-else class="text-muted">{{ evidencePosition(e) }}</div>
                      <div v-if="e.quote" class="text-muted fst-italic text-break">
                        저장된 인용문: “{{ e.quote }}”
                      </div>
                    </li>
                    <li v-if="!row.evaluation.evidences.length" class="text-muted">
                      연결된 근거 없음 (자료 미등록·연결 없음일 수 있음 — 미보유 아님)
                    </li>
                  </ul>
                </section>
                <section class="text-muted">
                  <div class="detail-label">판정 정보</div>
                  <div>
                    {{ row.evaluation.decided_by_label }} 판정 ·
                    {{ formatDateTime(row.evaluation.updated_at) }}
                  </div>
                  <template v-if="row.evaluation.is_modified">
                    <div>
                      담당자 수정: {{ row.evaluation.modified_by_name || '-' }} ({{
                        formatDateTime(row.evaluation.modified_at)
                      }})
                    </div>
                    <div class="mt-1">
                      수정 전 자동 판정(서버 기록):
                      <VerdictBadge :verdict="row.evaluation.ai_verdict" small />
                      <div v-if="row.evaluation.ai_answer" class="text-break">
                        {{ row.evaluation.ai_answer }}
                      </div>
                    </div>
                  </template>
                </section>
              </div>
            </div>

            <div
              v-if="rowError[row.id]"
              class="alert alert-danger py-2 small mt-3 mb-0"
              role="alert"
            >
              {{ rowError[row.id] }}
            </div>
            <div class="d-flex flex-wrap gap-2 mt-3">
              <button
                class="btn btn-sm btn-outline-primary"
                :disabled="locked"
                @click="openEditor(row)"
              >
                <i class="bi bi-pencil me-1"></i>수정
              </button>
              <button
                v-if="row.evaluation.is_modified"
                class="btn btn-sm btn-outline-secondary"
                :disabled="locked || busy"
                @click="askRevert(row)"
              >
                <span v-if="acting === row.id" class="spinner-border spinner-border-sm me-1"></span
                >마지막 자동 판정 기록으로 복원
              </button>
              <button
                class="btn btn-sm btn-outline-secondary"
                :disabled="editor.saving"
                @click="openHistory(row)"
              >
                이력
              </button>
              <button
                class="btn btn-sm btn-outline-secondary"
                :disabled="locked || busy"
                @click="askReevaluate(row)"
              >
                이 항목만 재판정
              </button>
            </div>
          </div>
          <div v-else-if="expanded.has(row.id)" class="mt-2 small text-muted">
            이 요구사항은 아직 판정되지 않았습니다(‘확인 필요’와 다른 상태입니다).
            <button
              class="btn btn-sm btn-link"
              :disabled="locked || busy"
              @click="askReevaluate(row)"
            >
              이 항목 판정
            </button>
          </div>
        </div>
      </div>
    </template>

    <BaseModal :show="editor.show" title="판정 수정" size="lg" @close="requestCloseEditor">
      <form id="eval-form" @submit.prevent="save">
        <p class="small text-muted text-break">
          {{ editor.row?.title }} — {{ editor.row?.requirement_text }}
        </p>
        <div class="row g-3">
          <div class="col-md-6">
            <label class="form-label small mb-1" for="ev-verdict">판정</label>
            <select
              id="ev-verdict"
              v-model="editor.form.verdict"
              class="form-select form-select-sm"
              :disabled="editor.saving"
            >
              <option v-for="v in VERDICTS" :key="v.value" :value="v.value">{{ v.label }}</option>
            </select>
          </div>
          <div class="col-md-6">
            <label class="form-label small mb-1" for="ev-risk">위험도</label>
            <select
              id="ev-risk"
              v-model="editor.form.risk_level"
              class="form-select form-select-sm"
              :disabled="editor.saving"
            >
              <option v-for="v in RISK_LEVELS" :key="v.value" :value="v.value">
                {{ v.label }}
              </option>
            </select>
          </div>
          <div class="col-12">
            <label class="form-label small mb-1" for="ev-answer"
              >답변 초안 (Compliance Matrix 응답, 자동 제출되지 않음)</label
            >
            <textarea
              id="ev-answer"
              v-model="editor.form.auto_answer"
              class="form-control form-control-sm"
              rows="2"
              :disabled="editor.saving"
            ></textarea>
          </div>
          <div class="col-12">
            <label class="form-label small mb-1" for="ev-value">회사 대응 값</label>
            <input
              id="ev-value"
              v-model="editor.form.company_value"
              class="form-control form-control-sm"
              :disabled="editor.saving"
            />
          </div>
          <div class="col-12">
            <label class="form-label small mb-1" for="ev-rationale">판정 사유</label>
            <textarea
              id="ev-rationale"
              v-model="editor.form.rationale"
              class="form-control form-control-sm"
              rows="3"
              :disabled="editor.saving"
            ></textarea>
          </div>
          <div class="col-md-6">
            <label class="form-label small mb-1" for="ev-actions">후속 조치 (줄마다 1개)</label>
            <textarea
              id="ev-actions"
              v-model="editor.actionsText"
              class="form-control form-control-sm"
              rows="3"
              :disabled="editor.saving"
            ></textarea>
          </div>
          <div class="col-md-6">
            <label class="form-label small mb-1" for="ev-question"
              >발주처 질의 초안 (자동 발송되지 않음)</label
            >
            <textarea
              id="ev-question"
              v-model="editor.form.clarification_question"
              class="form-control form-control-sm"
              rows="3"
              :disabled="editor.saving"
            ></textarea>
          </div>
          <div class="col-12">
            <div class="small fw-semibold mb-1">근거 자료</div>
            <div class="small text-muted mb-2">
              기존 근거의 자료 연결(종류·ID)은 바뀌지 않으며 이름은 고칠 수 없습니다. 위치는 저장된
              참조값이고 0이면 위치 정보 없음입니다.
            </div>
            <div v-for="(ev, i) in editor.form.evidences" :key="i" class="row g-1 mb-2">
              <div class="col-12">
                <span class="badge bg-secondary me-1">{{
                  EVIDENCE_LABELS[ev.type] || ev.type
                }}</span>
                <span class="small text-muted">{{
                  ev.id ? '기존 자료 연결 유지' : '수동 입력 · 원본 문서 미연결'
                }}</span>
              </div>
              <div class="col-12 col-md-5">
                <input
                  v-model="ev.label"
                  class="form-control form-control-sm"
                  :readonly="!!ev.id"
                  :disabled="editor.saving"
                  :aria-label="`근거 ${i + 1} 이름`"
                />
              </div>
              <div class="col-4 col-md-2">
                <input
                  v-model.number="ev.page"
                  type="number"
                  min="0"
                  class="form-control form-control-sm"
                  placeholder="위치"
                  :disabled="editor.saving"
                  :aria-label="`근거 ${i + 1} 위치(페이지)`"
                />
              </div>
              <div class="col-8 col-md-4">
                <input
                  v-model="ev.quote"
                  class="form-control form-control-sm"
                  placeholder="인용문"
                  :disabled="editor.saving"
                  :aria-label="`근거 ${i + 1} 인용문`"
                />
              </div>
              <div class="col-12 col-md-1 text-end">
                <button
                  type="button"
                  class="btn btn-sm btn-link text-danger"
                  :disabled="editor.saving"
                  :aria-label="`근거 ${i + 1} 삭제`"
                  @click="editor.form.evidences.splice(i, 1)"
                >
                  <i class="bi bi-x-lg"></i>
                </button>
              </div>
            </div>
            <button
              type="button"
              class="btn btn-sm btn-outline-secondary"
              :disabled="editor.saving"
              @click="
                editor.form.evidences.push({
                  type: 'document',
                  id: 0,
                  label: '',
                  page: 0,
                  quote: '',
                })
              "
            >
              수동 근거 추가
            </button>
            <span class="small text-muted ms-2">원본 문서와 연결되지 않는 메모형 근거입니다.</span>
          </div>
        </div>
        <div v-if="editor.error" class="alert alert-danger py-2 small mt-3 mb-0" role="alert">
          {{ editor.error }}
        </div>
      </form>
      <template #footer>
        <span v-if="dirty" class="small text-muted me-auto">저장하지 않은 변경이 있습니다.</span>
        <button class="btn btn-secondary" :disabled="editor.saving" @click="requestCloseEditor">
          취소
        </button>
        <button class="btn btn-primary" form="eval-form" :disabled="editor.saving">
          <span v-if="editor.saving" class="spinner-border spinner-border-sm me-1"></span
          >{{ editor.error && !editor.saving ? '다시 저장' : '저장' }}
        </button>
      </template>
    </BaseModal>

    <BaseModal :show="history.show" title="판정 이력" size="lg" @close="closeHistory">
      <p class="small text-muted text-break">
        {{ history.row?.title }} — 서버에 저장된 변경 기록입니다(변경자·시각·저장된 스냅샷).
      </p>
      <div v-if="history.loading" class="text-center py-4">
        <span class="spinner-border spinner-border-sm"></span>
      </div>
      <div v-else-if="history.error" class="alert alert-danger small d-flex gap-2">
        <span class="flex-grow-1">{{ history.error }}</span>
        <button class="btn btn-sm btn-outline-secondary" @click="openHistory(history.row)">
          다시 시도
        </button>
      </div>
      <div v-else-if="!history.items.length" class="text-muted small">저장된 이력이 없습니다.</div>
      <div v-else class="table-responsive">
        <table class="table table-sm small history-table">
          <thead>
            <tr>
              <th>일시</th>
              <th>변경자</th>
              <th>판정</th>
              <th>답변 초안 · 사유</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="h in history.items" :key="h.id">
              <td class="text-nowrap">{{ formatDateTime(h.changed_at) }}</td>
              <td>{{ h.changed_by_name || '자동 판정 기록' }}</td>
              <td class="text-nowrap">
                <VerdictBadge :verdict="h.snapshot.verdict" small />
                <RiskDot :risk="h.snapshot.risk_level" class="ms-1" />
              </td>
              <td class="text-break">
                {{ h.snapshot.auto_answer || '미제공' }}
                <div v-if="h.snapshot.rationale" class="text-muted">{{ h.snapshot.rationale }}</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </BaseModal>

    <ConfirmModal
      :show="confirmDiscard"
      title="저장하지 않은 변경"
      message="수정한 내용이 저장되지 않았습니다. 닫으면 입력한 내용이 사라집니다. 닫을까요?"
      confirm-text="변경 버리고 닫기"
      @confirm="closeEditor"
      @cancel="confirmDiscard = false"
    />
    <ConfirmModal
      :show="!!confirmRevert"
      title="마지막 자동 판정 기록으로 복원"
      :message="`서버에 저장된 마지막 자동 판정 기록으로 이 항목을 복원합니다. 새 LLM 호출이 아닙니다.\n담당자가 수정한 판정·위험도·답변·사유·후속 조치·질의 문안·근거가 그 기록의 값으로 바뀝니다. 변경 이력은 남습니다.\n자동 판정 기록이 없으면 서버가 오류를 알려 줍니다.`"
      confirm-text="복원"
      variant="warning"
      :loading="!!acting"
      @confirm="doRevert"
      @cancel="confirmRevert = null"
    />
    <ConfirmModal
      :show="!!confirmReeval"
      title="이 항목만 재판정"
      :message="`‘${confirmReeval?.title || ''}’ 항목을 다시 판정합니다. 판정에는 LLM 호출이 포함될 수 있습니다.${confirmReeval?.evaluation?.is_modified ? '\n이 항목에는 담당자 수정이 있으며 재판정하면 수정한 내용이 덮어써질 수 있습니다.' : ''}`"
      confirm-text="재판정 실행"
      variant="warning"
      @confirm="doReevaluate"
      @cancel="confirmReeval = null"
    />

    <DocumentOffcanvas
      :document-id="viewer.documentId"
      :page="viewer.page"
      :quote="viewer.quote"
      :kind="viewer.kind"
      :context-title="viewer.title"
      :context-text="viewer.text"
      :position-note="viewer.note"
      :location="viewer.location"
      @close="viewer = { ...emptyViewer }"
    />
  </div>
</template>

<style scoped>
.verdict-col {
  width: 7.5rem;
  flex-shrink: 0;
}
.row-head {
  cursor: pointer;
}
.min-w-0 {
  min-width: 0;
}
.detail {
  margin-left: 1.5rem;
}
.detail-label {
  font-weight: 600;
  margin-bottom: 0.15rem;
}
.history-table {
  min-width: 36rem;
}
@media (max-width: 575.98px) {
  .verdict-col {
    width: 5.5rem;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.15rem;
    white-space: normal;
  }
  .detail {
    margin-left: 0;
  }
}
.trace {
  white-space: pre-wrap;
  max-height: 14rem;
  overflow: auto;
}
</style>
