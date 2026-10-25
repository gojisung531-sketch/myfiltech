<script setup>
// ② 회사 자료 비교 (specs/05 §3 ②)
// 이 화면의 시험성적서·인증·납품실적은 서버가 연결했거나 후보로 돌려준 참고 자료다.
// 목록에 있다는 사실만으로 해당 요구조건의 충족 근거로 읽지 않는다. 판정은 서버 값만 표시한다.
import { computed, onMounted, ref } from 'vue'

import { bidItems, getComparison } from '@/api/bids'
import BaseModal from '@/components/BaseModal.vue'
import DocumentOffcanvas from '@/components/DocumentOffcanvas.vue'
import EmptyState from '@/components/EmptyState.vue'
import LocationStatus from '@/components/LocationStatus.vue'
import ReadableText from '@/components/ReadableText.vue'
import RiskDot from '@/components/RiskDot.vue'
import VerdictBadge from '@/components/VerdictBadge.vue'
import { useToastStore } from '@/stores/toast'
import { CANDIDATE_LABELS } from '@/utils/candidateLabels'
import { errorMessage } from '@/utils/errors'
import { statusInfo, viewerFromLocation } from '@/utils/evidenceLocation'

const props = defineProps({
  bid: { type: Object, required: true },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['evaluate', 'changed'])

const toast = useToastStore()
const data = ref(null)
const loadError = ref('')
const viewer = ref(null) // { documentId, title, text, page, quote, kind, note }
const suggest = ref(null) // item whose product changed → offer re-evaluation

async function load() {
  loadError.value = ''
  try {
    data.value = await getComparison(props.bid.id)
  } catch (err) {
    if (data.value) toast.error(errorMessage(err))
    else loadError.value = errorMessage(err, '비교 자료를 불러오지 못했습니다.')
  }
}
onMounted(load)

const sections = computed(() => {
  if (!data.value) return []
  const groups = data.value.items.map((item) => ({
    key: `i${item.id}`,
    label: `${item.item_no || '-'}. ${item.name}`,
    rows: data.value.rows.filter((r) => r.item_id === item.id),
  }))
  groups.push({
    key: 'common',
    label: '공통 요구사항 (자격·서류·납기 등)',
    rows: data.value.rows.filter((r) => !r.item_id),
  })
  return groups.filter((g) => g.rows.length)
})

// 비어 있는 이유를 서버 상태로만 구분한다.
const emptyMessage = computed(() => {
  const status = props.bid.processing_status
  if (status === 'DRAFT') return '아직 요구조건 추출을 실행하지 않아 비교할 요구사항이 없습니다.'
  if (status === 'EXTRACTING') return '요구조건 추출이 진행 중입니다.'
  if (status === 'FAILED')
    return '처리에 실패해 비교할 요구사항이 없을 수 있습니다. 상세 오류를 확인하세요.'
  return '저장된 요구사항이 없습니다. 추출 누락 가능성이 있으니 원문을 확인하세요.'
})

const hasEvaluation = computed(() => data.value?.rows.some((r) => r.verdict))

async function changeProduct(item, productId) {
  try {
    await bidItems.update(props.bid.id, item.id, { matched_product: productId || null })
    toast.success('매칭 제품을 변경했습니다.')
    await load()
    emit('changed')
    if (data.value.rows.some((r) => r.item_id === item.id)) suggest.value = item
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

function reevaluateItem() {
  const ids = data.value.rows
    .filter((r) => r.item_id === suggest.value.id)
    .map((r) => r.requirement_id)
  suggest.value = null
  emit('evaluate', { keepModified: true, requirementIds: ids })
}

const RELATION = {
  SAVED_ID_REFERENCE: '저장된 판정이 연결한 인증서',
  CURRENT_REFERENCE_ONLY: '현재 등록 자료 참고(저장된 판정에 미반영)',
}
const STORED_RELATION_NOTE =
  '저장된 판정을 기준으로 한 근거입니다. 위치는 지금 원본과 다시 대조한 결과이며 판정은 바뀌지 않습니다.'

// 서버가 계산한 근거 위치를 원문 패널로 넘긴다(저장 판정 근거와 현재 회사 참고자료는 역할이 다르다).
function openLocation(loc, row, title, siblings = []) {
  if (!loc?.document_id) {
    toast.show(
      `원문을 열 수 없습니다 — ${statusInfo(loc).label}. ${statusInfo(loc).reason || ''}`,
      'warning',
    )
    return
  }
  viewer.value = {
    ...viewerFromLocation(loc, { title: `${row.title} — ${title}`, text: loc.quote }),
    locations: siblings,
  }
}

function open(target, kind, row) {
  const locs = (target.evidence_locations || []).filter((l) => l.document_id)
  if (locs.length) {
    viewer.value = {
      ...viewerFromLocation(locs[0], {
        title: `${row.title} — ${kind}`,
        text: target.label,
        note: RELATION[target.relation_to_evaluation] || '',
      }),
      locations: locs.filter((l) => l.document_id === locs[0].document_id),
    }
    return
  }
  if (target.document_id) {
    viewer.value = {
      documentId: target.document_id,
      title: `${row.title} — ${kind}`,
      text: target.label,
      page: 0,
      quote: '',
      kind: 'reference',
      note: '이 화면은 자료의 위치(페이지)를 받지 않아 문서의 처음부터 표시합니다.',
    }
  } else {
    toast.show(
      `이 ${kind}에는 연결된 원본 문서가 없습니다(문서 ID가 저장되지 않음). 자료 목록에서 직접 확인하세요.`,
      'warning',
    )
  }
}

// ---- 후보별 카탈로그 비교 (서버 값만 표시, 프런트에서 계산하지 않음) ----
// 서버 verdict 문자열을 후보 비교용 업무 용어로만 바꿔 보여 준다.

// 제품 ID로만 후보와 비교 결과를 연결한다(배열 순서·모델명 유사성 사용 안 함).
function candidatePairs(row) {
  const results = row.comparison_trace?.candidate_comparisons || []
  return (row.comparison_candidates || []).map((candidate) => ({
    candidate,
    result: results.find((r) => r.product_id === candidate.product_id) || null,
  }))
}

// 이 요구사항 카테고리에 대해 제조사가 기재한 값(있을 때만)
function claimText(row, candidate) {
  const claim = candidate.published_claims?.[row.category]
  if (!claim?.display) return ''
  return claim.scope ? `${claim.display} (${claim.scope})` : claim.display
}

// 카탈로그 기재 사양 요약: 서버가 준 자유 문장 필드만 이어 붙인다(코드값은 쓰지 않음).
function specSummary(candidate) {
  const s = candidate.specification || {}
  return [s.dimension_text, s.media, s.frame_material, s.gasket].filter(Boolean).join(' · ')
}

function openCandidateSource(row, candidate) {
  const source = candidate.source || {}
  if (!candidate.source_document_id) {
    toast.show('이 후보에는 연결된 제조사 원문 문서가 없습니다.', 'warning')
    return
  }
  viewer.value = {
    documentId: candidate.source_document_id,
    title: `${row.title} — 후보 ${candidate.model_no}`,
    text: source.label || candidate.model_no,
    page: source.page || 0,
    quote: source.quote || '',
    kind: 'reference',
    note: source.page
      ? '카탈로그 기재 위치(서버 기록)입니다. 원문과 대조하세요.'
      : '위치 미확인 — 문서의 처음부터 표시합니다.',
  }
}

function openReviewSource(row) {
  const review = row.interpretation_review || {}
  if (!review.source_document_id) {
    toast.show('이 해석 주의사항에는 연결된 원문 문서가 없습니다.', 'warning')
    return
  }
  viewer.value = {
    documentId: review.source_document_id,
    title: row.title,
    text: review.location || '공고 원문',
    page: 0,
    quote: review.source_quote || '',
    kind: 'requirement_source',
    note: '서버가 기록한 해석 주의사항의 원문입니다. 위치 미확인 — 직접 대조하세요.',
  }
}

const hasRefs = (row) =>
  row.test_reports.length || row.certificates.length || row.delivery_records.length
</script>

<template>
  <div>
    <div v-if="loadError" class="alert alert-danger d-flex align-items-center gap-2" role="alert">
      <i class="bi bi-exclamation-octagon"></i>
      <span class="flex-grow-1">{{ loadError }}</span>
      <button class="btn btn-sm btn-outline-secondary" @click="load">다시 시도</button>
    </div>
    <div v-else-if="!data" class="text-center py-5"><span class="spinner-border"></span></div>
    <template v-else>
      <div class="small mb-3">
        <div class="text-muted">
          판정 기준일 {{ data.reference_date
          }}<template v-if="data.is_simulation"> · 과거 공고를 오늘 기준으로 판정</template> ·
          연결·참고 자료는 충족 근거가 아닙니다 · 후보별 카탈로그 비교는 참고이며 최종 판정에
          반영되지 않습니다 · 단위·시험표준·시험조건 미제공(원문 확인 필요)
        </div>
        <details class="ft-help mt-1">
          <summary>이 화면 읽는 법</summary>
          <p>
            회사 값·제품 사양·참고 자료는 서로 다른 출처입니다. 참고 자료는 서버가 연결했거나 후보로
            제시한 것이며, 목록에 있다고 해서 해당 요구조건의 충족 근거가 되는 것은 아닙니다. 판정은
            서버가 계산한 값 그대로 표시하고, 비어 있는 칸은 자료 미등록·연결 없음일 수 있으며 필텍
            미보유를 뜻하지 않습니다.
          </p>
        </details>
      </div>

      <div v-if="data.items.length" class="row g-3 mb-3">
        <div v-for="item in data.items" :key="item.id" class="col-lg-6">
          <div class="card h-100">
            <div class="card-body small">
              <div class="fw-semibold mb-1 text-break">
                {{ item.item_no || '-' }}. {{ item.name }}
              </div>
              <div class="text-muted mb-2 text-break">{{ item.spec_text }}</div>
              <label class="form-label mb-1" :for="`cmp-${item.id}`">연결 제품</label>
              <select
                :id="`cmp-${item.id}`"
                class="form-select form-select-sm"
                :value="item.matched_product || ''"
                :disabled="busy"
                @change="changeProduct(item, Number($event.target.value) || null)"
              >
                <option value="">연결 제품 없음</option>
                <option v-for="c in item.candidates" :key="c.product" :value="c.product">
                  {{ c.model_no }} — {{ c.name }} (매칭 점수 {{ Math.round(c.score * 100) }})
                </option>
              </select>
              <div v-if="item.candidates.length" class="text-muted mt-1">
                <template v-if="item.candidates.find((c) => c.product === item.matched_product)">
                  선택 사유:
                  {{ item.candidates.find((c) => c.product === item.matched_product).reason }}
                </template>
                <div title="매칭 점수는 품목과 제품의 유사도이며 기술 적합도·낙찰 확률이 아닙니다.">
                  매칭 점수 ≠ 기술 적합도
                </div>
              </div>
              <div v-else class="text-muted mt-1">
                매칭 후보가 없습니다. 등록된 제품 자료가 없거나 연결할 제품이 없는 상태입니다.
              </div>
            </div>
          </div>
        </div>
      </div>

      <EmptyState
        v-if="!data.rows.length"
        :icon="bid.processing_status === 'DRAFT' ? 'bi-hourglass' : 'bi-question-circle'"
        :message="emptyMessage"
      />
      <div v-else-if="!hasEvaluation" class="alert alert-info small py-2">
        아직 판정을 실행하지 않았습니다. 아래 판정 열은 '미판정'이며 '확인 필요'와 다릅니다.
      </div>

      <div v-for="section in sections" :key="section.key" class="card mb-3">
        <div class="card-header fw-semibold text-break">{{ section.label }}</div>
        <div class="table-responsive">
          <table class="table table-sm align-top mb-0 small compare-table">
            <thead class="table-light">
              <tr>
                <th>요구사항</th>
                <th>요구 내용 (공고 원문 기준)</th>
                <th title="제품 등록 정보(카탈로그) 기준 값이며 검증된 시험성적서 값이 아닙니다.">
                  연결 제품 · 후보별 카탈로그 비교
                </th>
                <th>회사 값 (판정 시 서버 기록)</th>
                <th>연결·참고 자료</th>
                <th>최종 판정</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in section.rows" :key="row.requirement_id">
                <td>
                  <span class="text-muted">{{ row.category_label }}</span>
                  <div class="fw-semibold text-break">{{ row.title }}</div>
                </td>
                <td class="text-break">
                  <ReadableText :text="row.requirement_value" />
                  <div v-if="row.source_location" class="mt-1">
                    <button
                      type="button"
                      class="btn btn-link btn-sm p-0 text-start small"
                      @click="openLocation(row.source_location, row, '공고 원문')"
                    >
                      <i class="bi bi-quote me-1"></i>공고 원문 보기
                    </button>
                    <div class="small"><LocationStatus :location="row.source_location" /></div>
                  </div>
                </td>
                <td class="text-break">
                  <template v-if="row.product">
                    <span class="fw-semibold">{{ row.product.model_no }}</span>
                    <div v-if="row.product_spec">{{ row.product_spec }}</div>
                    <div v-else class="text-muted">이 항목의 제품 사양 정보 미제공</div>
                  </template>
                  <template v-else-if="row.comparison_candidates?.length">
                    <div class="text-muted mb-1">
                      연결 제품 없음 · 제안 제품·옵션 미확정 — 아래는 카탈로그 후보 비교(참고)
                    </div>
                    <div
                      v-for="pair in candidatePairs(row)"
                      :key="pair.candidate.product_id"
                      class="cand mb-2"
                    >
                      <div class="d-flex flex-wrap align-items-center gap-1">
                        <span class="fw-semibold">{{ pair.candidate.model_no }}</span>
                        <span class="badge bg-secondary">카탈로그 기준</span>
                        <span
                          v-if="pair.result"
                          class="badge"
                          :class="
                            CANDIDATE_LABELS[pair.result.candidate_verdict]?.cls || 'bg-secondary'
                          "
                          :title="`서버 비교 값: ${pair.result.candidate_verdict}`"
                          >{{
                            CANDIDATE_LABELS[pair.result.candidate_verdict]?.text ||
                            pair.result.candidate_verdict
                          }}</span
                        >
                        <span v-else class="badge bg-secondary">비교 결과 없음</span>
                      </div>
                      <div v-if="claimText(row, pair.candidate)" class="mt-1">
                        <span class="text-muted">기재 사양</span>
                        {{ claimText(row, pair.candidate) }}
                      </div>
                      <div v-else-if="specSummary(pair.candidate)" class="mt-1">
                        <span class="text-muted">기재 사양</span>
                        {{ specSummary(pair.candidate) }}
                      </div>
                      <div v-else class="mt-1 text-muted">이 항목의 기재 사양 없음</div>
                      <div v-if="pair.result?.rationale" class="mt-1">
                        <div class="text-muted">비교 사유</div>
                        <ReadableText :text="pair.result.rationale" />
                      </div>
                      <button
                        class="btn btn-link btn-sm p-0 text-start small"
                        @click="openCandidateSource(row, pair.candidate)"
                      >
                        <i class="bi bi-file-earmark-text me-1"></i>출처 원문 보기
                      </button>
                      <span class="text-muted ms-1">{{
                        pair.candidate.source?.page
                          ? `저장된 참조 위치 p.${pair.candidate.source.page}`
                          : '위치 미확인'
                      }}</span>
                    </div>
                  </template>
                  <span v-else class="text-muted">연결된 제품 없음</span>
                </td>
                <td class="text-break">
                  <template v-if="row.comparison_candidates?.length && !row.product">
                    <span class="text-muted">미확정 (제안 제품·옵션 확인 필요)</span>
                    <details v-if="row.company_value" class="ft-help mt-1">
                      <summary>서버 기록 값</summary>
                      <ReadableText :text="row.company_value" mode="candidates" />
                    </details>
                  </template>
                  <ReadableText v-else-if="row.company_value" :text="row.company_value" />
                  <span v-else class="text-muted">
                    {{ row.verdict ? '기록된 회사 값 없음' : '판정 전' }}
                  </span>
                </td>
                <td>
                  <details v-if="row.stored_evidence_locations?.length" class="ft-help mb-2">
                    <summary>
                      저장 판정 근거 위치 ({{ row.stored_evidence_locations.length }})
                    </summary>
                    <p class="mb-1">{{ STORED_RELATION_NOTE }}</p>
                    <div
                      v-for="(l, i) in row.stored_evidence_locations"
                      :key="i"
                      class="mb-1 text-break"
                    >
                      <button
                        type="button"
                        class="btn btn-link btn-sm p-0 text-start small"
                        @click="openLocation(l, row, '저장된 판정 근거')"
                      >
                        {{ (l.quote || '').slice(0, 40) || '위치' }}
                      </button>
                      <div><LocationStatus :location="l" /></div>
                    </div>
                  </details>
                  <details v-if="row.current_company_locations?.length" class="ft-help mb-2">
                    <summary>
                      현재 회사 참고 위치 ({{ row.current_company_locations.length }})
                    </summary>
                    <p class="mb-1">
                      현재 등록된 회사 자료의 위치입니다.
                      <template v-if="row.current_references_revise_stored_evaluation === false"
                        >이미 저장된 판정에는 반영되지 않았습니다.</template
                      >
                    </p>
                    <div
                      v-for="(l, i) in row.current_company_locations"
                      :key="i"
                      class="mb-1 text-break"
                    >
                      <button
                        type="button"
                        class="btn btn-link btn-sm p-0 text-start small"
                        @click="
                          openLocation(
                            l,
                            row,
                            '현재 회사 참고',
                            row.current_company_locations.filter(
                              (x) => x.document_id === l.document_id,
                            ),
                          )
                        "
                      >
                        {{ (l.quote || '').slice(0, 40) || '위치' }}
                      </button>
                      <div><LocationStatus :location="l" /></div>
                    </div>
                  </details>
                  <div v-if="row.test_reports.length" class="mb-1">
                    <div class="text-muted">시험성적서</div>
                    <button
                      v-for="r in row.test_reports"
                      :key="r.id"
                      class="btn btn-link btn-sm p-0 d-block text-start small text-break"
                      @click="open(r, '시험성적서', row)"
                    >
                      {{ r.label }}
                    </button>
                  </div>
                  <div v-if="row.certificates.length" class="mb-1">
                    <div class="text-muted">인증</div>
                    <button
                      v-for="c in row.certificates"
                      :key="c.id"
                      class="btn btn-link btn-sm p-0 d-block text-start small text-break"
                      @click="open(c, '인증', row)"
                    >
                      {{ c.label }}
                      <span v-if="c.relation_to_evaluation" class="badge bg-secondary">{{
                        c.relation_to_evaluation === 'SAVED_ID_REFERENCE'
                          ? '저장 판정 연결'
                          : '현재 참고만'
                      }}</span>
                      <span v-if="c.status === 'EXPIRED'" class="badge bg-danger">만료</span>
                      <span v-else-if="c.status === 'EXPIRING'" class="badge bg-warning"
                        >만료 임박</span
                      >
                    </button>
                  </div>
                  <div v-if="row.delivery_records.length">
                    <div class="text-muted">납품실적</div>
                    <button
                      v-for="d in row.delivery_records"
                      :key="d.id"
                      class="btn btn-link btn-sm p-0 d-block text-start small text-break"
                      @click="open(d, '납품실적', row)"
                    >
                      {{ d.label }}
                    </button>
                  </div>
                  <span v-if="!hasRefs(row)" class="text-muted">자료 미등록 또는 연결 없음</span>
                </td>
                <td>
                  <div class="text-nowrap">
                    <VerdictBadge :verdict="row.verdict" />
                    <RiskDot :risk="row.risk_level" class="ms-1" />
                  </div>
                  <div v-if="row.interpretation_review" class="mt-1">
                    <span class="badge bg-warning">원문 해석 확인 필요</span>
                    <ReadableText
                      v-if="row.interpretation_review.reason"
                      class="mt-1"
                      :text="row.interpretation_review.reason"
                    />
                    <button
                      v-if="row.interpretation_review.source_document_id"
                      class="btn btn-link btn-sm p-0 text-start small"
                      @click="openReviewSource(row)"
                    >
                      해석 근거 원문 보기
                    </button>
                  </div>
                  <details v-if="row.rationale" class="ft-help mt-1">
                    <summary>최종 판정 사유</summary>
                    <ReadableText :text="row.rationale" />
                  </details>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <BaseModal :show="!!suggest" title="재판정 제안" @close="suggest = null">
      <p class="small mb-0">
        '{{ suggest?.name }}' 품목의 연결 제품이 바뀌었습니다. 이 품목의 요구사항을 다시 판정할까요?
        (담당자가 수정한 판정은 유지됩니다)
      </p>
      <template #footer>
        <button class="btn btn-secondary" @click="suggest = null">나중에</button>
        <button class="btn btn-primary" :disabled="busy" @click="reevaluateItem">재판정</button>
      </template>
    </BaseModal>

    <DocumentOffcanvas
      :document-id="viewer?.documentId ?? null"
      :page="viewer?.page || 0"
      :quote="viewer?.quote || ''"
      :kind="viewer?.kind || 'reference'"
      :context-title="viewer?.title || ''"
      :context-text="viewer?.text || ''"
      :position-note="viewer?.note || ''"
      :location="viewer?.location || null"
      :locations="viewer?.locations || []"
      @close="viewer = null"
    />
  </div>
</template>

<style scoped>
.compare-table {
  min-width: 78rem;
  table-layout: fixed;
}
.compare-table th,
.compare-table td {
  padding: 0.7rem 0.85rem;
  border-left: 1px solid var(--ft-border);
  vertical-align: top;
}
.compare-table th:first-child,
.compare-table td:first-child {
  border-left: 0;
}
.compare-table th:nth-child(1) {
  width: 10rem;
}
.compare-table th:nth-child(2) {
  width: 15rem;
}
.compare-table th:nth-child(3) {
  width: 22rem;
}
.compare-table th:nth-child(4) {
  width: 10rem;
}
.compare-table th:nth-child(5) {
  width: 9rem;
}
.compare-table th:nth-child(6) {
  width: 12rem;
}
.cand {
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--ft-border);
  border-left: 3px solid var(--ft-border-strong);
  border-radius: 0.3rem;
  background: var(--ft-surface);
}
.compare-table th {
  white-space: nowrap;
}
</style>
