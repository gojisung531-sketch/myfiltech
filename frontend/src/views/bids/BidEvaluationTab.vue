<script setup>
// ③ 판정 및 자동 답변 (specs/05 §3 ③, specs/11 BidDetailView)
import { computed, onMounted, reactive, ref } from 'vue'

import {
  evaluationHistory,
  listRequirementsWithEvaluation,
  revertEvaluation,
  updateEvaluation,
} from '@/api/bids'
import BaseModal from '@/components/BaseModal.vue'
import DocumentOffcanvas from '@/components/DocumentOffcanvas.vue'
import EmptyState from '@/components/EmptyState.vue'
import RiskDot from '@/components/RiskDot.vue'
import VerdictBadge from '@/components/VerdictBadge.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/format'
import { RISK_LEVELS, VERDICTS } from '@/utils/options'

const props = defineProps({
  bid: { type: Object, required: true },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['evaluate', 'changed'])

const EVIDENCE_LABELS = {
  product: '사양서',
  test_report: '시험성적서',
  certificate: '인증서',
  delivery_record: '납품실적',
  bid_quote: '공고 원문',
  company: '회사 정보',
  document: '문서',
}

const toast = useToastStore()
const rows = ref([])
const loading = ref(true)
const expanded = ref(new Set())
const filters = reactive({ verdict: '', highOnly: false, modifiedOnly: false })
const viewer = ref({ documentId: null, page: 0, quote: '' })
const editor = reactive({
  show: false,
  row: null,
  form: {},
  actionsText: '',
  saving: false,
  error: '',
})
const history = reactive({ show: false, row: null, items: [] })

async function load() {
  try {
    rows.value = await listRequirementsWithEvaluation(props.bid.id)
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    loading.value = false
  }
}
onMounted(load)

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
const visible = computed(() =>
  rows.value.filter((r) => {
    const e = r.evaluation
    if (filters.verdict && e?.verdict !== filters.verdict) return false
    if (filters.highOnly && e?.risk_level !== 'HIGH') return false
    if (filters.modifiedOnly && !e?.is_modified) return false
    return true
  }),
)

function toggle(id) {
  const next = new Set(expanded.value)
  next.has(id) ? next.delete(id) : next.add(id)
  expanded.value = next
}

function openEvidence(e) {
  if (e.document_id) viewer.value = { documentId: e.document_id, page: e.page || 0, quote: e.quote }
  else toast.show('연결된 원본 문서가 없습니다.', 'warning')
}

function openEditor(row) {
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
      evidences: e.evidences.map((ev) => ({ ...ev })),
    },
    actionsText: e.action_items.join('\n'),
  })
}

async function save() {
  editor.saving = true
  editor.error = ''
  const payload = {
    ...editor.form,
    action_items: editor.actionsText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean),
    evidences: editor.form.evidences
      .filter((ev) => ev.label.trim())
      .map(({ type, id, label, page, quote }) => ({
        type,
        id: id || 0,
        label,
        page: page || 0,
        quote: quote || '',
      })),
  }
  try {
    editor.row.evaluation = await updateEvaluation(editor.row.evaluation.id, payload)
    editor.show = false
    toast.success('판정을 수정했습니다.')
    emit('changed')
  } catch (err) {
    editor.error = errorMessage(err)
  } finally {
    editor.saving = false
  }
}

async function revert(row) {
  try {
    row.evaluation = await revertEvaluation(row.evaluation.id)
    toast.success('AI 판정으로 되돌렸습니다.')
    emit('changed')
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

async function openHistory(row) {
  try {
    Object.assign(history, { show: true, row, items: await evaluationHistory(row.evaluation.id) })
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

function reevaluate(row) {
  emit('evaluate', { keepModified: false, requirementIds: [row.id] })
}
</script>

<template>
  <div>
    <div v-if="loading" class="text-center py-5"><span class="spinner-border"></span></div>
    <template v-else>
      <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
        <span class="badge bg-success fs-6 fw-normal">충족 {{ summary.MET }}</span>
        <span class="badge bg-warning text-dark fs-6 fw-normal"
          >보완 필요 {{ summary.NEEDS_SUPPLEMENT }}</span
        >
        <span class="badge bg-info text-dark fs-6 fw-normal"
          >확인 필요 {{ summary.NEEDS_CONFIRMATION }}</span
        >
        <span class="badge bg-danger fs-6 fw-normal">HIGH 위험 {{ summary.HIGH }}</span>
        <span class="small text-muted me-auto">수정됨 {{ summary.modified }}건</span>
        <select
          v-model="filters.verdict"
          class="form-select form-select-sm w-auto"
          aria-label="판정 필터"
        >
          <option value="">판정: 전체</option>
          <option v-for="v in VERDICTS" :key="v.value" :value="v.value">{{ v.label }}</option>
        </select>
        <div class="form-check">
          <input id="f-high" v-model="filters.highOnly" class="form-check-input" type="checkbox" />
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
      </div>

      <div v-if="!evaluated.length" class="alert alert-info small">
        아직 판정하지 않았습니다. 상단의 <strong>판정 실행</strong>을 누르세요.
      </div>
      <EmptyState v-if="!visible.length" message="조건에 맞는 요구사항이 없습니다." />

      <div class="list-group">
        <div v-for="row in visible" :key="row.id" class="list-group-item">
          <div
            class="d-flex align-items-start gap-2"
            role="button"
            :aria-expanded="expanded.has(row.id)"
            @click="toggle(row.id)"
          >
            <i
              class="bi mt-1"
              :class="expanded.has(row.id) ? 'bi-chevron-down' : 'bi-chevron-right'"
            ></i>
            <div class="text-nowrap" style="width: 7.5rem">
              <VerdictBadge :verdict="row.evaluation?.verdict" />
              <RiskDot :risk="row.evaluation?.risk_level" class="ms-1" />
            </div>
            <div class="flex-grow-1 small">
              <span class="text-muted"
                >{{ row.category_label
                }}<span v-if="row.item_label"> · {{ row.item_label }}</span></span
              >
              <div>
                <span class="fw-semibold">{{ row.title }}</span>
                <span v-if="row.is_mandatory" class="badge bg-danger ms-1">필수</span>
                <span v-if="row.evaluation?.is_modified" class="badge bg-secondary ms-1"
                  >수정됨</span
                >
                <span class="text-muted ms-1">{{ row.requirement_text }}</span>
              </div>
              <div v-if="row.evaluation" class="text-body mt-1">
                {{ row.evaluation.auto_answer }}
              </div>
            </div>
          </div>

          <div v-if="expanded.has(row.id) && row.evaluation" class="mt-3 ms-4 small">
            <div class="row g-3">
              <div class="col-lg-7">
                <div class="fw-semibold mb-1">판정 근거</div>
                <p style="white-space: pre-line">{{ row.evaluation.rationale }}</p>
                <template v-if="row.evaluation.company_value">
                  <div class="fw-semibold mb-1">회사 대응 값</div>
                  <p>{{ row.evaluation.company_value }}</p>
                </template>
                <template v-if="row.evaluation.action_items.length">
                  <div class="fw-semibold mb-1">보완 조치</div>
                  <ul>
                    <li v-for="a in row.evaluation.action_items" :key="a">{{ a }}</li>
                  </ul>
                </template>
                <template v-if="row.evaluation.clarification_question">
                  <div class="fw-semibold mb-1">발주처 질의 문안</div>
                  <p class="border-start border-3 ps-2">
                    {{ row.evaluation.clarification_question }}
                  </p>
                </template>
                <div v-if="row.evaluation.rule_trace?.interpolation" class="text-muted">
                  계산: {{ row.evaluation.rule_trace.interpolation }}
                </div>
              </div>
              <div class="col-lg-5">
                <div class="fw-semibold mb-1">근거 자료</div>
                <ul class="list-unstyled">
                  <li v-for="(e, i) in row.evaluation.evidences" :key="i" class="mb-1">
                    <span class="badge bg-light text-dark border me-1">{{
                      EVIDENCE_LABELS[e.type] || e.type
                    }}</span>
                    <button
                      class="btn btn-link btn-sm p-0 text-start small"
                      :class="{ 'text-body text-decoration-none': !e.document_id }"
                      @click="openEvidence(e)"
                    >
                      {{ e.label }}<span v-if="e.page"> p.{{ e.page }}</span>
                    </button>
                    <div v-if="e.quote" class="text-muted fst-italic">“{{ e.quote }}”</div>
                  </li>
                  <li v-if="!row.evaluation.evidences.length" class="text-muted">근거 자료 없음</li>
                </ul>
                <div class="text-muted">
                  {{ row.evaluation.decided_by_label }} 판정 ·
                  {{ formatDateTime(row.evaluation.updated_at) }}
                  <template v-if="row.evaluation.is_modified">
                    <br />수정: {{ row.evaluation.modified_by_name }} ({{
                      formatDateTime(row.evaluation.modified_at)
                    }}) <br />원본 AI 판정:
                    <VerdictBadge :verdict="row.evaluation.ai_verdict" small />
                    <div class="mt-1">{{ row.evaluation.ai_answer }}</div>
                  </template>
                </div>
              </div>
            </div>
            <div class="d-flex flex-wrap gap-2 mt-2">
              <button class="btn btn-sm btn-outline-primary" @click="openEditor(row)">
                <i class="bi bi-pencil me-1"></i>수정
              </button>
              <button
                v-if="row.evaluation.is_modified"
                class="btn btn-sm btn-outline-secondary"
                @click="revert(row)"
              >
                AI 판정으로 되돌리기
              </button>
              <button class="btn btn-sm btn-outline-secondary" @click="openHistory(row)">
                이력
              </button>
              <button
                class="btn btn-sm btn-outline-secondary"
                :disabled="busy"
                @click="reevaluate(row)"
              >
                이 항목만 재판정
              </button>
            </div>
          </div>
          <div v-else-if="expanded.has(row.id)" class="mt-2 ms-4 small text-muted">
            판정 전입니다.
            <button class="btn btn-sm btn-link" :disabled="busy" @click="reevaluate(row)">
              이 항목 판정
            </button>
          </div>
        </div>
      </div>
    </template>

    <BaseModal :show="editor.show" title="판정 수정" size="lg" @close="editor.show = false">
      <form id="eval-form" @submit.prevent="save">
        <p class="small text-muted">{{ editor.row?.title }} — {{ editor.row?.requirement_text }}</p>
        <div class="row g-3">
          <div class="col-md-6">
            <label class="form-label small mb-1" for="ev-verdict">판정</label>
            <select
              id="ev-verdict"
              v-model="editor.form.verdict"
              class="form-select form-select-sm"
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
            >
              <option v-for="v in RISK_LEVELS" :key="v.value" :value="v.value">
                {{ v.label }}
              </option>
            </select>
          </div>
          <div class="col-12">
            <label class="form-label small mb-1" for="ev-answer"
              >자동 답변 (Compliance Matrix 응답)</label
            >
            <textarea
              id="ev-answer"
              v-model="editor.form.auto_answer"
              class="form-control form-control-sm"
              rows="2"
            ></textarea>
          </div>
          <div class="col-12">
            <label class="form-label small mb-1" for="ev-value">회사 대응 값</label>
            <input
              id="ev-value"
              v-model="editor.form.company_value"
              class="form-control form-control-sm"
            />
          </div>
          <div class="col-12">
            <label class="form-label small mb-1" for="ev-rationale">판정 근거</label>
            <textarea
              id="ev-rationale"
              v-model="editor.form.rationale"
              class="form-control form-control-sm"
              rows="3"
            ></textarea>
          </div>
          <div class="col-md-6">
            <label class="form-label small mb-1" for="ev-actions">보완 조치 (줄마다 1개)</label>
            <textarea
              id="ev-actions"
              v-model="editor.actionsText"
              class="form-control form-control-sm"
              rows="3"
            ></textarea>
          </div>
          <div class="col-md-6">
            <label class="form-label small mb-1" for="ev-question">발주처 질의 문안</label>
            <textarea
              id="ev-question"
              v-model="editor.form.clarification_question"
              class="form-control form-control-sm"
              rows="3"
            ></textarea>
          </div>
          <div class="col-12">
            <div class="small fw-semibold mb-1">근거 자료</div>
            <div v-for="(ev, i) in editor.form.evidences" :key="i" class="row g-1 mb-1">
              <div class="col-md-5">
                <input
                  v-model="ev.label"
                  class="form-control form-control-sm"
                  :aria-label="`근거 ${i + 1} 이름`"
                />
              </div>
              <div class="col-md-1">
                <input
                  v-model.number="ev.page"
                  type="number"
                  min="0"
                  class="form-control form-control-sm"
                  :aria-label="`근거 ${i + 1} 페이지`"
                />
              </div>
              <div class="col-md-5">
                <input
                  v-model="ev.quote"
                  class="form-control form-control-sm"
                  placeholder="인용문"
                  :aria-label="`근거 ${i + 1} 인용문`"
                />
              </div>
              <div class="col-md-1">
                <button
                  type="button"
                  class="btn btn-sm btn-link text-danger"
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
              근거 추가
            </button>
          </div>
        </div>
        <div v-if="editor.error" class="alert alert-danger py-2 small mt-3 mb-0">
          {{ editor.error }}
        </div>
      </form>
      <template #footer>
        <button class="btn btn-secondary" @click="editor.show = false">취소</button>
        <button class="btn btn-primary" form="eval-form" :disabled="editor.saving">저장</button>
      </template>
    </BaseModal>

    <BaseModal :show="history.show" title="판정 이력" size="lg" @close="history.show = false">
      <table class="table table-sm small">
        <thead>
          <tr>
            <th>일시</th>
            <th>변경자</th>
            <th>판정</th>
            <th>답변</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="h in history.items" :key="h.id">
            <td class="text-nowrap">{{ formatDateTime(h.changed_at) }}</td>
            <td>{{ h.changed_by_name || '자동 판정' }}</td>
            <td class="text-nowrap">
              <VerdictBadge :verdict="h.snapshot.verdict" small />
              <RiskDot :risk="h.snapshot.risk_level" class="ms-1" />
            </td>
            <td>{{ h.snapshot.auto_answer }}</td>
          </tr>
        </tbody>
      </table>
    </BaseModal>

    <DocumentOffcanvas
      :document-id="viewer.documentId"
      :page="viewer.page"
      :quote="viewer.quote"
      @close="viewer = { documentId: null, page: 0, quote: '' }"
    />
  </div>
</template>
