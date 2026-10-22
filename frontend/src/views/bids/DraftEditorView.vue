<script setup>
// ⑤ 초안 편집 · 버전 · PDF (specs/05 §3 ⑤, specs/11 DraftEditorView)
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'

import { getBid } from '@/api/bids'
import {
  DRAFT_TYPES,
  downloadDraftPdf,
  downloadDraftXlsx,
  draftVersions,
  getDraft,
  saveDraft,
  XLSX_TYPES,
} from '@/api/drafts'
import ConfirmModal from '@/components/ConfirmModal.vue'
import EditableTable from '@/components/EditableTable.vue'
import { useToastStore } from '@/stores/toast'
import { downloadFile, PDF_TYPES, XLSX_CONTENT_TYPES } from '@/utils/download'
import { errorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const toast = useToastStore()

const bid = ref(null)
const draft = ref(null)
const content = ref(null)
const versions = ref([])
const saving = ref(false)
const downloading = ref('')
const dirty = ref(false)
const loadError = ref('')
const versionsError = ref('')
const saveError = ref('')
const downloadError = ref('')
const discard = reactive({ show: false })
// 화면(공고·문서·버전) 전환 순번. 늦게 도착한 이전 화면의 응답이 새 화면을 덮어쓰지 않게 한다.
let loadSeq = 0
// 입력 변경 순번. 저장 요청 중에 더 입력했는지 구분한다.
let edits = 0
let discardResolve = null

const bidId = computed(() => Number(route.params.id))
const type = computed(() => route.params.type)
const version = computed(() => (route.query.version ? Number(route.query.version) : null))
// 버전 목록을 못 불러왔으면 최신 여부를 알 수 없으므로, 버전을 지정해 연 경우는 이전 버전으로 본다.
const isLatest = computed(() =>
  versions.value.length ? draft.value?.version === versions.value[0].version : !version.value,
)

const VERDICT_OPTIONS = ['충족', '보완 필요', '확인 필요', '미판정'].map((v) => ({
  value: v,
  label: v,
}))
const STATUS_OPTIONS = [
  { value: 'TODO', label: '미완료' },
  { value: 'DONE', label: '완료' },
  { value: 'NA', label: '해당 없음' },
]
const CM_COLUMNS = [
  { key: 'no', label: 'No', width: '3.5rem' },
  { key: 'item', label: '품목', width: '9rem', type: 'textarea' },
  { key: 'category', label: '구분', width: '6rem' },
  { key: 'requirement', label: '요구사항', type: 'textarea' },
  { key: 'offered', label: '제안 사양', type: 'textarea' },
  {
    key: 'compliance',
    label: '충족 여부',
    width: '7.5rem',
    type: 'select',
    options: VERDICT_OPTIONS,
  },
  { key: 'response', label: '응답', type: 'textarea' },
  { key: 'evidence', label: '근거', type: 'textarea' },
  { key: 'remark', label: '비고', width: '8rem', type: 'textarea' },
]
const CL_COLUMNS = [
  { key: 'status', label: '상태', width: '7rem', type: 'select', options: STATUS_OPTIONS },
  { key: 'text', label: '항목', type: 'textarea' },
  { key: 'due', label: '기한', width: '9rem' },
  { key: 'owner', label: '담당', width: '7rem' },
  { key: 'verdict', label: '판정', width: '6rem' },
  { key: 'note', label: '비고', type: 'textarea' },
]
const ACTION_COLUMNS = [
  { key: 'action', label: '조치', type: 'textarea' },
  { key: 'owner', label: '담당', width: '8rem' },
  { key: 'due', label: '기한', width: '9rem' },
]
const RECOMMENDATIONS = [
  { value: 'BID', label: '입찰 권고' },
  { value: 'CONDITIONAL', label: '조건부 입찰' },
  { value: 'NO_BID', label: '입찰 불참 권고' },
]

function setContent(source) {
  const c = JSON.parse(JSON.stringify(source))
  if (type.value === 'REVIEW_REPORT') {
    c.key_risks_text = (c.key_risks || []).join('\n')
    c.next_actions = c.next_actions || []
  }
  content.value = c
  dirty.value = false // 아래 deep watch(sync)가 먼저 dirty를 켠 뒤에 끈다.
}

async function loadVersions(mine, bidKey, typeKey) {
  versionsError.value = ''
  try {
    const result = await draftVersions(bidKey, typeKey)
    if (mine === loadSeq) versions.value = result
  } catch (err) {
    if (mine === loadSeq) {
      versionsError.value = errorMessage(err, '버전 목록을 불러오지 못했습니다.')
    }
  }
}

async function load() {
  const mine = ++loadSeq
  const bidKey = bidId.value
  const typeKey = type.value
  const versionKey = version.value
  loadError.value = ''
  saveError.value = ''
  downloadError.value = ''
  draft.value = null
  content.value = null
  versions.value = []
  dirty.value = false
  if (bid.value && bid.value.id !== bidKey) bid.value = null
  try {
    const [b, d] = await Promise.all([
      bid.value?.id === bidKey ? bid.value : getBid(bidKey),
      getDraft(bidKey, typeKey, versionKey),
    ])
    if (mine !== loadSeq) return
    bid.value = b
    draft.value = d
    setContent(d.content)
  } catch (err) {
    if (mine === loadSeq) loadError.value = errorMessage(err, '초안을 불러오지 못했습니다.')
    return
  }
  await loadVersions(mine, bidKey, typeKey)
}
onMounted(load)
watch([bidId, type, version], load)
// sync: setContent() resets `dirty` right after replacing `content`
watch(
  content,
  () => {
    edits += 1
    dirty.value = true
  },
  { deep: true, flush: 'sync' },
)

// ---- 미저장 변경 보호 (버전·문서·공고 전환, 화면 이탈, 탭 닫기) ----
function askDiscard() {
  if (!dirty.value) return Promise.resolve(true)
  discard.show = true
  return new Promise((resolve) => {
    discardResolve = resolve
  })
}
function answerDiscard(ok) {
  discard.show = false
  const resolve = discardResolve
  discardResolve = null
  resolve?.(ok)
}
onBeforeRouteLeave(() => askDiscard())
onBeforeRouteUpdate((to, from) => {
  const same =
    to.params.id === from.params.id &&
    to.params.type === from.params.type &&
    (to.query.version || '') === (from.query.version || '')
  return same ? true : askDiscard()
})
function onBeforeUnload(event) {
  if (dirty.value) {
    event.preventDefault()
    event.returnValue = ''
  }
}
window.addEventListener('beforeunload', onBeforeUnload)
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
  loadSeq += 1 // 이후 도착하는 응답은 무시
})

function payloadContent() {
  const c = JSON.parse(JSON.stringify(content.value))
  if (type.value === 'REVIEW_REPORT') {
    c.key_risks = c.key_risks_text
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
    delete c.key_risks_text
  }
  if (type.value === 'COMPLIANCE_MATRIX') c.rows.forEach((r, i) => (r.no = i + 1))
  if (type.value === 'TECHNICAL_QUERY') c.questions.forEach((q, i) => (q.no = i + 1))
  return c
}

// 저장에 성공하면 저장된 초안(서버 응답)을, 실패하면 null을 돌려준다. 다운로드는 이 결과에 의존한다.
async function save(status) {
  if (saving.value || !draft.value || !content.value) return null
  const ctx = { bidId: bidId.value, type: type.value, version: draft.value.version, seq: loadSeq }
  const editsAtSend = edits
  const body = {
    version: ctx.version,
    content: payloadContent(),
    ...(status ? { status } : {}),
  }
  saving.value = true
  saveError.value = ''
  let saved
  try {
    saved = await saveDraft(ctx.bidId, ctx.type, body)
  } catch (err) {
    // 입력(content)과 dirty는 그대로 둔다.
    saveError.value = errorMessage(
      err,
      '저장하지 못했습니다. 입력은 그대로 남아 있으니 다시 저장하세요.',
    )
    return null
  } finally {
    saving.value = false
  }
  toast.success(`v${saved.version}을(를) 저장했습니다.`)
  if (ctx.seq !== loadSeq) return saved // 저장 중 다른 화면으로 이동함: 현재 화면 상태는 건드리지 않는다.
  draft.value = saved
  if (edits === editsAtSend) {
    setContent(saved.content)
  } else {
    // 저장 요청을 보낸 뒤에도 입력이 있었다. 그 입력은 저장되지 않았다.
    dirty.value = true
  }
  // 저장은 이미 성공했다. 버전 목록 재조회가 실패해도 저장을 되돌리지 않는다.
  await loadVersions(ctx.seq, ctx.bidId, ctx.type)
  return saved
}

async function download(format) {
  if (saving.value || downloading.value || !draft.value) return
  downloadError.value = ''
  let target = { bidId: bidId.value, type: type.value, version: draft.value.version }
  let savedFirst = false
  if (dirty.value) {
    const saved = await save()
    if (!saved) {
      downloadError.value =
        '저장하지 못해 다운로드를 중단했습니다. 저장 오류를 해결한 뒤 다시 시도하세요(저장되지 않은 수정은 파일에 포함되지 않습니다).'
      return
    }
    savedFirst = true
    target = { ...target, version: saved.version }
  }
  const stillDirty = dirty.value
  downloading.value = format
  try {
    const xlsx = format === 'xlsx'
    await downloadFile(
      () =>
        (xlsx ? downloadDraftXlsx : downloadDraftPdf)(target.bidId, target.type, target.version),
      {
        types: xlsx ? XLSX_CONTENT_TYPES : PDF_TYPES,
        fallbackName: `draft.${format}`,
        failMessage: `${format.toUpperCase()} 파일을 만들지 못했습니다.`,
      },
    )
    toast.success(
      `v${target.version}의 저장된 내용으로 ${format.toUpperCase()} 파일 저장을 요청했습니다.` +
        (savedFirst ? ' (변경 내용을 먼저 저장했습니다)' : '') +
        (stillDirty ? ' 저장 이후 입력한 변경은 포함되지 않았습니다.' : ''),
    )
  } catch (err) {
    downloadError.value = err.message
  } finally {
    downloading.value = ''
  }
}

// 버전 전환: 미저장 변경이 있으면 확인을 받고, 취소하면 선택 상자를 현재 버전으로 되돌린다.
async function selectVersion(value, element) {
  const next = value && Number(value) !== versions.value[0]?.version ? { version: value } : {}
  if (!(await askDiscard())) {
    if (element && draft.value) element.value = draft.value.version
    return
  }
  dirty.value = false
  router.replace({ query: next })
}

const newQuestion = () => ({
  no: 0,
  reference: '',
  question: '',
  background: '',
  proposed_alternative: '',
  requirement_id: 0,
})
</script>

<template>
  <div>
    <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
      <router-link
        :to="`/bids/${bidId}?tab=drafts`"
        class="btn btn-sm btn-outline-secondary"
        aria-label="초안 목록으로"
      >
        <i class="bi bi-arrow-left"></i>
      </router-link>
      <div class="me-auto min-w-0">
        <h2 class="h5 mb-0">{{ DRAFT_TYPES[type] }}</h2>
        <div v-if="bid" class="small text-muted text-break">{{ bid.title }}</div>
      </div>
      <select
        v-if="versions.length"
        class="form-select form-select-sm w-auto"
        aria-label="버전"
        :value="draft?.version"
        :disabled="saving"
        @change="selectVersion($event.target.value, $event.target)"
      >
        <option v-for="v in versions" :key="v.id" :value="v.version">
          v{{ v.version }} · {{ formatDateTime(v.updated_at)
          }}{{ v.is_modified ? ' · 담당자 수정본' : '' }}
        </option>
      </select>
      <span
        v-if="draft"
        class="badge"
        :class="draft.status === 'FINAL' ? 'bg-success' : 'bg-secondary'"
        >{{ draft.status_label }}</span
      >
      <button
        class="btn btn-sm btn-primary"
        :disabled="saving || !content || !!downloading"
        @click="save()"
      >
        <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span
        >{{ saveError && !saving ? '다시 저장' : '저장' }}
      </button>
      <button
        v-if="draft"
        class="btn btn-sm btn-outline-secondary"
        :disabled="saving || !!downloading"
        title="확정은 내부 검토 상태 표시이며 제출·법적 검토 완료를 뜻하지 않습니다."
        @click="save(draft.status === 'FINAL' ? 'DRAFT' : 'FINAL')"
      >
        {{ draft.status === 'FINAL' ? '초안으로 되돌리기' : '확정 표시' }}
      </button>
      <button
        class="btn btn-sm btn-outline-secondary"
        :disabled="!draft || saving || !!downloading"
        @click="download('pdf')"
      >
        <span v-if="downloading === 'pdf'" class="spinner-border spinner-border-sm me-1"></span>
        <i v-else class="bi bi-file-earmark-pdf me-1"></i>PDF
      </button>
      <button
        v-if="XLSX_TYPES.includes(type)"
        class="btn btn-sm btn-outline-secondary"
        :disabled="!draft || saving || !!downloading"
        @click="download('xlsx')"
      >
        <span v-if="downloading === 'xlsx'" class="spinner-border spinner-border-sm me-1"></span>
        <i v-else class="bi bi-file-earmark-excel me-1"></i>XLSX
      </button>
    </div>

    <div
      v-if="saveError"
      class="alert alert-danger small d-flex align-items-center gap-2"
      role="alert"
    >
      <span class="flex-grow-1">{{ saveError }}</span>
    </div>
    <div v-if="downloadError" class="alert alert-danger small" role="alert">
      {{ downloadError }}
    </div>
    <div v-if="versionsError" class="alert alert-warning small d-flex align-items-center gap-2">
      <span class="flex-grow-1"
        >{{ versionsError }} 저장·다운로드는 지금 보는 v{{ draft?.version }} 기준으로
        동작합니다.</span
      >
      <button class="btn btn-sm btn-outline-secondary" @click="loadVersions(loadSeq, bidId, type)">
        다시 시도
      </button>
    </div>

    <div v-if="loadError" class="alert alert-danger d-flex align-items-center gap-2" role="alert">
      <span class="flex-grow-1">{{ loadError }}</span>
      <button class="btn btn-sm btn-outline-secondary" @click="load">다시 시도</button>
      <router-link :to="`/bids/${bidId}?tab=drafts`" class="btn btn-sm btn-outline-secondary"
        >초안 목록</router-link
      >
    </div>
    <div v-else-if="!content" class="text-center py-5"><span class="spinner-border"></span></div>
    <template v-else>
      <div class="alert alert-secondary small py-2">
        <i class="bi bi-info-circle me-1"></i>자동 생성된 초안입니다. 제출 전 반드시
        검토·수정하세요.
        <span class="ms-1"
          >저장·PDF·XLSX는 모두 지금 보는 <strong>v{{ draft?.version }}</strong
          >의 저장된 내용에 적용됩니다.</span
        >
        <span v-if="!isLatest" class="text-danger ms-1"
          >이전 버전을 보고 있습니다 — 저장하면 이 버전을 덮어씁니다.</span
        >
        <span v-if="draft?.is_modified" class="ms-1">(담당자 수정본)</span>
        <span v-if="dirty" class="fw-semibold ms-1 dirty-note"
          >저장하지 않은 변경 사항이 있습니다.</span
        >
      </div>

      <!-- Compliance Matrix -->
      <div v-if="type === 'COMPLIANCE_MATRIX'" class="card">
        <div class="card-body">
          <div class="row g-2 mb-3 small">
            <div class="col-md-4">
              <label class="form-label mb-0" for="cm-by">작성자</label>
              <input
                id="cm-by"
                v-model="content.header.prepared_by"
                class="form-control form-control-sm"
              />
            </div>
            <div class="col-md-4">
              <label class="form-label mb-0" for="cm-at">작성일</label>
              <input
                id="cm-at"
                v-model="content.header.prepared_at"
                class="form-control form-control-sm"
              />
            </div>
          </div>
          <EditableTable
            :columns="CM_COLUMNS"
            v-model:rows="content.rows"
            label="Compliance Matrix"
            :new-row="
              () => ({
                no: 0,
                item: '',
                category: '',
                requirement: '',
                offered: '',
                compliance: '확인 필요',
                response: '',
                evidence: '',
                remark: '',
                risk: '',
              })
            "
          />
        </div>
      </div>

      <!-- Checklist -->
      <template v-else-if="type === 'BID_CHECKLIST'">
        <div v-for="(section, si) in content.sections" :key="si" class="card mb-3">
          <div class="card-header d-flex align-items-center gap-2">
            <input
              v-model="section.title"
              class="form-control form-control-sm fw-semibold"
              :aria-label="`섹션 ${si + 1} 제목`"
            />
            <span class="small text-nowrap text-muted">
              {{ section.items.filter((i) => i.status === 'DONE').length }}/{{
                section.items.length
              }}
              완료
            </span>
          </div>
          <div class="card-body">
            <EditableTable
              :columns="CL_COLUMNS"
              v-model:rows="section.items"
              :label="section.title"
              :new-row="
                () => ({ text: '', due: '', owner: '', status: 'TODO', verdict: '', note: '' })
              "
            />
          </div>
        </div>
      </template>

      <!-- Technical query -->
      <div v-else-if="type === 'TECHNICAL_QUERY'" class="card">
        <div class="card-body">
          <div class="row g-2 mb-3">
            <div
              v-for="[key, label] in [
                ['to', '수신'],
                ['from', '발신'],
                ['date', '일자'],
                ['subject', '제목'],
              ]"
              :key="key"
              class="col-md-6"
            >
              <label class="form-label small mb-0" :for="`tq-${key}`">{{ label }}</label>
              <input
                :id="`tq-${key}`"
                v-model="content.header[key]"
                class="form-control form-control-sm"
              />
            </div>
          </div>
          <label class="form-label small mb-0" for="tq-intro">머리말</label>
          <textarea
            id="tq-intro"
            v-model="content.intro"
            class="form-control form-control-sm mb-3"
            rows="2"
          ></textarea>
          <div v-for="(q, qi) in content.questions" :key="qi" class="border rounded p-2 mb-2">
            <div class="d-flex align-items-center mb-1">
              <span class="fw-semibold me-2">질의 {{ qi + 1 }}</span>
              <input
                v-model="q.reference"
                class="form-control form-control-sm me-2"
                placeholder="관련 조항"
                :aria-label="`질의 ${qi + 1} 관련 조항`"
              />
              <button
                type="button"
                class="btn btn-sm btn-link text-danger"
                :aria-label="`질의 ${qi + 1} 삭제`"
                @click="content.questions.splice(qi, 1)"
              >
                <i class="bi bi-trash"></i>
              </button>
            </div>
            <textarea
              v-model="q.question"
              class="form-control form-control-sm mb-1"
              rows="3"
              :aria-label="`질의 ${qi + 1} 내용`"
            ></textarea>
            <div class="row g-1">
              <div class="col-md-6">
                <textarea
                  v-model="q.background"
                  class="form-control form-control-sm"
                  rows="2"
                  placeholder="배경"
                  :aria-label="`질의 ${qi + 1} 배경`"
                ></textarea>
              </div>
              <div class="col-md-6">
                <textarea
                  v-model="q.proposed_alternative"
                  class="form-control form-control-sm"
                  rows="2"
                  placeholder="대체안"
                  :aria-label="`질의 ${qi + 1} 대체안`"
                ></textarea>
              </div>
            </div>
          </div>
          <button
            type="button"
            class="btn btn-sm btn-outline-secondary mb-3"
            @click="content.questions.push(newQuestion())"
          >
            <i class="bi bi-plus-lg me-1"></i>질의 추가
          </button>
          <label class="form-label small mb-0 d-block" for="tq-closing">맺음말</label>
          <textarea
            id="tq-closing"
            v-model="content.closing"
            class="form-control form-control-sm"
            rows="2"
          ></textarea>
        </div>
      </div>

      <!-- Review report -->
      <div v-else-if="type === 'REVIEW_REPORT'" class="card">
        <div class="card-body">
          <div class="row g-3">
            <div class="col-md-4">
              <label class="form-label small mb-0" for="rr-rec">입찰 권고</label>
              <select
                id="rr-rec"
                v-model="content.recommendation"
                class="form-select form-select-sm"
              >
                <option v-for="o in RECOMMENDATIONS" :key="o.value" :value="o.value">
                  {{ o.label }}
                </option>
              </select>
            </div>
            <div class="col-md-8">
              <label class="form-label small mb-0" for="rr-reason">권고 사유</label>
              <textarea
                id="rr-reason"
                v-model="content.recommendation_reason"
                class="form-control form-control-sm"
                rows="2"
              ></textarea>
            </div>
            <div class="col-12">
              <label class="form-label small mb-0" for="rr-summary">총평</label>
              <textarea
                id="rr-summary"
                v-model="content.executive_summary"
                class="form-control form-control-sm"
                rows="4"
              ></textarea>
            </div>
            <div class="col-12">
              <label class="form-label small mb-0" for="rr-risks">주요 위험 (줄마다 1개)</label>
              <textarea
                id="rr-risks"
                v-model="content.key_risks_text"
                class="form-control form-control-sm"
                rows="4"
              ></textarea>
            </div>
            <div class="col-12">
              <div class="small fw-semibold mb-1">후속 조치</div>
              <EditableTable
                :columns="ACTION_COLUMNS"
                v-model:rows="content.next_actions"
                label="후속 조치"
                :new-row="() => ({ action: '', owner: '', due: '' })"
              />
            </div>
            <div class="col-12 small text-muted">
              적합도 {{ content.fit?.score ?? '-' }} · 충족 {{ content.stats?.met }} · 보완 필요
              {{ content.stats?.needs_supplement }} · 확인 필요
              {{ content.stats?.needs_confirmation }} · HIGH {{ content.stats?.high_risk }} (생성
              시점 통계)
            </div>
          </div>
        </div>
      </div>
    </template>

    <ConfirmModal
      :show="discard.show"
      title="저장하지 않은 변경"
      message="저장하지 않은 수정이 있습니다. 이동하면 입력한 내용이 사라집니다. 이동할까요?"
      confirm-text="변경 버리고 이동"
      @confirm="answerDiscard(true)"
      @cancel="answerDiscard(false)"
    />
  </div>
</template>

<style scoped>
.min-w-0 {
  min-width: 0;
}
.dirty-note {
  color: var(--ft-warn-fg);
}
</style>
