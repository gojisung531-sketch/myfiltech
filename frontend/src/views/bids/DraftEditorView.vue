<script setup>
// ⑤ 초안 편집 · 버전 · PDF (specs/05 §3 ⑤, specs/11 DraftEditorView)
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

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
import EditableTable from '@/components/EditableTable.vue'
import { useToastStore } from '@/stores/toast'
import { saveResponse } from '@/utils/download'
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
const dirty = ref(false)
const error = ref('')

const bidId = computed(() => Number(route.params.id))
const type = computed(() => route.params.type)
const version = computed(() => (route.query.version ? Number(route.query.version) : null))
const isLatest = computed(
  () => !versions.value.length || draft.value?.version === versions.value[0].version,
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

async function load() {
  error.value = ''
  try {
    const [b, d, v] = await Promise.all([
      bid.value?.id === bidId.value ? bid.value : getBid(bidId.value),
      getDraft(bidId.value, type.value, version.value),
      draftVersions(bidId.value, type.value),
    ])
    bid.value = b
    draft.value = d
    versions.value = v
    content.value = JSON.parse(JSON.stringify(d.content))
    if (type.value === 'REVIEW_REPORT') {
      content.value.key_risks_text = (content.value.key_risks || []).join('\n')
      content.value.next_actions = content.value.next_actions || []
    }
    dirty.value = false
  } catch (err) {
    error.value = errorMessage(err)
  }
}
onMounted(load)
watch([type, version], load)
// sync: load() resets `dirty` right after replacing `content`
watch(content, () => (dirty.value = true), { deep: true, flush: 'sync' })

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

async function save(status) {
  saving.value = true
  try {
    draft.value = await saveDraft(bidId.value, type.value, {
      version: draft.value.version,
      content: payloadContent(),
      ...(status ? { status } : {}),
    })
    toast.success(`v${draft.value.version}을(를) 저장했습니다.`)
    await load()
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    saving.value = false
  }
}

async function download(format) {
  if (dirty.value) await save()
  try {
    const request = format === 'xlsx' ? downloadDraftXlsx : downloadDraftPdf
    saveResponse(await request(bidId.value, type.value, draft.value.version), `draft.${format}`)
  } catch (err) {
    toast.error(errorMessage(err, `${format.toUpperCase()} 파일을 만들지 못했습니다.`))
  }
}

function selectVersion(value) {
  router.replace({ query: value ? { version: value } : {} })
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
      <router-link :to="`/bids/${bidId}?tab=drafts`" class="btn btn-sm btn-outline-secondary">
        <i class="bi bi-arrow-left"></i>
      </router-link>
      <div class="me-auto">
        <h1 class="h5 mb-0">{{ DRAFT_TYPES[type] }}</h1>
        <div v-if="bid" class="small text-muted">{{ bid.title }}</div>
      </div>
      <select
        v-if="versions.length"
        class="form-select form-select-sm w-auto"
        aria-label="버전"
        :value="draft?.version"
        @change="
          selectVersion(
            Number($event.target.value) === versions[0].version ? null : $event.target.value,
          )
        "
      >
        <option v-for="v in versions" :key="v.id" :value="v.version">
          v{{ v.version }} · {{ formatDateTime(v.updated_at)
          }}{{ v.is_modified ? ' · 수정됨' : '' }}
        </option>
      </select>
      <span
        v-if="draft"
        class="badge"
        :class="draft.status === 'FINAL' ? 'bg-success' : 'bg-secondary'"
        >{{ draft.status_label }}</span
      >
      <button class="btn btn-sm btn-primary" :disabled="saving || !content" @click="save()">
        저장
      </button>
      <button
        v-if="draft"
        class="btn btn-sm btn-outline-success"
        :disabled="saving"
        @click="save(draft.status === 'FINAL' ? 'DRAFT' : 'FINAL')"
      >
        {{ draft.status === 'FINAL' ? '초안으로 되돌리기' : '확정' }}
      </button>
      <button class="btn btn-sm btn-outline-secondary" :disabled="!draft" @click="download('pdf')">
        <i class="bi bi-file-earmark-pdf me-1"></i>PDF
      </button>
      <button
        v-if="XLSX_TYPES.includes(type)"
        class="btn btn-sm btn-outline-success"
        :disabled="!draft"
        @click="download('xlsx')"
      >
        <i class="bi bi-file-earmark-excel me-1"></i>XLSX
      </button>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-else-if="!content" class="text-center py-5"><span class="spinner-border"></span></div>
    <template v-else>
      <div class="alert alert-light border small py-2">
        <i class="bi bi-info-circle me-1"></i>자동 생성된 초안입니다. 제출 전 반드시
        검토·수정하세요.
        <span v-if="!isLatest" class="text-danger ms-1"
          >이전 버전을 보고 있습니다 — 저장하면 이 버전을 덮어씁니다.</span
        >
        <span v-if="dirty" class="text-warning ms-1">저장하지 않은 변경 사항이 있습니다.</span>
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
  </div>
</template>
