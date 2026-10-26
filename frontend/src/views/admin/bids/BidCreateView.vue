<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { createBid } from '@/api/bids'
import FileDropzone from '@/components/FileDropzone.vue'
import NoticeFieldInput from '@/components/NoticeFieldInput.vue'
import { errorMessage } from '@/utils/errors'
import { formatBytes } from '@/utils/format'
import { BID_ATTACHMENT_FORMATS } from '@/utils/options'
import { EXTRA_FIELDS, PRIMARY_FIELDS, useNoticePreview } from '@/utils/useNoticePreview'

const router = useRouter()
const sourceText = ref('')
const meta = useNoticePreview(sourceText)
const files = ref([])
const duplicates = ref([])
const saving = ref(false)
const error = ref('')
const failedFiles = ref([]) // 서버가 거절한 파일 [{ filename, reason }]
const created = ref(null) // 등록은 됐지만 일부 파일이 제외된 경우의 결과

const hasInput = computed(() => files.value.length > 0 || sourceText.value.trim().length > 0)
// 본문을 읽는 중에는 잠깐 기다린다(읽기 실패는 등록을 막지 않는다).
const reading = computed(() => ['waiting', 'loading'].includes(meta.status.value))
const canSubmit = computed(() => hasInput.value && !reading.value)

const warningsFor = (key) => (meta.shown.value?.warnings || []).filter((w) => w.field === key)
const generalWarnings = computed(() => (meta.shown.value?.warnings || []).filter((w) => !w.field))
const quoteFor = (key) => (meta.current.value ? meta.shown.value.evidence?.[key]?.quote || '' : '')
const autoFilled = (key) =>
  meta.current.value &&
  !meta.edited[key] &&
  Boolean(meta.vals[key]) &&
  key in meta.shown.value.values
const shownPrimary = computed(() =>
  PRIMARY_FIELDS.filter((f) => f.key === 'title' || meta.vals[f.key] || meta.edited[f.key]),
)
const otherFields = computed(() => {
  const rest = [...PRIMARY_FIELDS, ...EXTRA_FIELDS].filter((f) => !shownPrimary.value.includes(f))
  return [...rest.filter((f) => meta.vals[f.key]), ...rest.filter((f) => !meta.vals[f.key])]
})
const foundOther = computed(() => otherFields.value.filter((f) => meta.vals[f.key]).length)
const missingNames = computed(() =>
  otherFields.value
    .filter((f) => !meta.vals[f.key] && PRIMARY_FIELDS.includes(f))
    .map((f) => f.label),
)
const fileKey = (f) => `${f.name}|${f.size}|${f.lastModified}`

// 이름이 같아도 크기·수정시각이 다르면 다른 파일로 보고 모두 유지한다.
function addFiles(picked) {
  const known = new Set(files.value.map(fileKey))
  duplicates.value = []
  for (const file of picked) {
    if (known.has(fileKey(file))) duplicates.value.push(file.name)
    else {
      known.add(fileKey(file))
      files.value.push(file)
    }
  }
}

async function submit() {
  if (saving.value || !canSubmit.value) return
  error.value = ''
  failedFiles.value = []
  saving.value = true
  try {
    const bid = await createBid({
      title: meta.vals.title || '',
      sourceText: sourceText.value,
      files: files.value,
      // 지금 본문과 같은 본문으로 읽은 결과만 보낸다(없으면 기존 방식 그대로).
      noticeMetadata: meta.payload() || undefined,
    })
    if (bid.skipped?.length) {
      created.value = bid
      return
    }
    router.push({ path: `/admin/bids/${bid.id}/edit`, query: { tab: 'attachments' } })
  } catch (err) {
    // 입력과 선택한 파일은 그대로 둔다. 거절 사유를 파일별로 보여 준다.
    failedFiles.value = err.response?.data?.skipped || []
    error.value = errorMessage(err, '등록하지 못했습니다. 잠시 후 다시 시도하세요.')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="mx-auto" style="max-width: 900px">
    <div class="d-flex align-items-center gap-2 mb-3">
      <router-link to="/admin/bids" class="btn btn-sm btn-outline-secondary" aria-label="목록으로">
        <i class="bi bi-arrow-left"></i>
      </router-link>
      <h2 class="h4 mb-0">입찰 공고 등록</h2>
    </div>

    <div v-if="created" class="card">
      <div class="card-body">
        <div class="alert alert-warning mb-3" role="alert">
          <strong>일부 파일만 등록되었습니다.</strong> 공고는 저장되었지만 아래 파일은 서버가 거절해
          제외되었습니다.
          <ul class="mb-0 mt-2">
            <li v-for="s in created.skipped" :key="s.filename" class="text-break">
              {{ s.filename }} — {{ s.reason }}
            </li>
          </ul>
        </div>
        <p class="small text-muted mb-0">
          등록된 파일은 첨부 목록에서 문서 읽기 상태를 확인하세요. 제외된 파일은 수정한 뒤 첨부
          탭에서 다시 추가할 수 있습니다.
        </p>
      </div>
      <div class="card-footer text-end">
        <router-link
          :to="{ path: `/admin/bids/${created.id}/edit`, query: { tab: 'attachments' } }"
          class="btn btn-primary"
          >등록된 공고 열기</router-link
        >
      </div>
    </div>

    <form v-else class="card" @submit.prevent="submit">
      <div class="card-body">
        <div class="mb-3">
          <label class="form-label small" for="bid-text">공고 본문 붙여넣기</label>
          <textarea
            id="bid-text"
            v-model="sourceText"
            class="form-control form-control-sm"
            rows="8"
            :disabled="saving"
            placeholder="공고 본문을 붙여 넣으면 아래 기본 정보가 자동으로 채워집니다. 파일과 함께 입력할 수도 있습니다."
            @paste="meta.onPaste"
          ></textarea>
          <div class="form-text">
            본문의 첨부 링크는 자동 다운로드되지 않습니다. 파일은 아래에서 직접 첨부하세요.
          </div>
        </div>

        <section class="nf-section mb-3" aria-labelledby="nf-heading">
          <div class="d-flex flex-wrap align-items-center gap-2 mb-1">
            <h3 id="nf-heading" class="h6 mb-0">기본 정보</h3>
            <span v-if="meta.status.value === 'loading'" class="small text-muted" role="status">
              <span class="spinner-border spinner-border-sm me-1"></span>본문에서 읽는 중…
            </span>
            <span v-else-if="meta.status.value === 'waiting'" class="small text-muted" role="status"
              >입력이 멈추면 읽습니다…</span
            >
            <span v-else-if="meta.shown.value && !meta.current.value" class="small text-muted"
              >본문이 바뀌어 다시 읽어야 합니다.</span
            >
            <button
              v-if="meta.canRead() && !saving"
              type="button"
              class="btn btn-sm btn-outline-secondary ms-auto"
              :disabled="meta.status.value === 'loading'"
              @click="meta.retry()"
            >
              <i class="bi bi-arrow-repeat me-1"></i>다시 읽기
            </button>
          </div>
          <p class="small text-muted mb-2">
            본문에서 찾은 값만 채웁니다. 틀린 값은 고치고, 없는 값은 비워 두어도 됩니다. 요구조건
            분석은 별도 단계로, 등록해도 자동 실행되지 않습니다.
          </p>

          <div
            v-if="meta.status.value === 'error'"
            class="alert alert-warning small py-2"
            role="alert"
          >
            <div>{{ meta.error.value }}</div>
            <div class="mt-1">
              입력한 본문·파일·수정한 값은 그대로입니다. 다시 읽기를 누르거나, 읽지 않고 그대로
              등록할 수 있습니다(이 경우 자동 읽은 기본 정보는 저장되지 않습니다).
            </div>
          </div>
          <ul v-if="generalWarnings.length" class="small text-warning-emphasis ps-3 mb-2">
            <li v-for="(w, i) in generalWarnings" :key="i">{{ w.message }}</li>
          </ul>

          <div class="row g-2" :class="{ 'nf-stale': meta.shown.value && !meta.current.value }">
            <NoticeFieldInput
              v-for="f in shownPrimary"
              :key="f.key"
              v-model="meta.vals[f.key]"
              :field="f"
              :edited="Boolean(meta.edited[f.key])"
              :auto="autoFilled(f.key)"
              :quote="quoteFor(f.key)"
              :warnings="warningsFor(f.key)"
              :kept="meta.kept.value.includes(f.key)"
              :can-restore="meta.current.value"
              :disabled="saving"
              @edit="meta.touch(f.key)"
              @restore="meta.restore(f.key)"
            />
          </div>

          <details class="mt-2">
            <summary class="small">
              추가 항목 (찾음 {{ foundOther
              }}<template v-if="missingNames.length"> · 못 찾음 {{ missingNames.length }}</template
              >)
            </summary>
            <p v-if="missingNames.length" class="small text-muted mt-1 mb-2">
              본문에서 찾지 못함: {{ missingNames.join(', ') }}. 필요하면 직접 입력하세요.
            </p>
            <div class="row g-2 mt-0">
              <NoticeFieldInput
                v-for="f in otherFields"
                :key="f.key"
                v-model="meta.vals[f.key]"
                :field="f"
                :edited="Boolean(meta.edited[f.key])"
                :auto="autoFilled(f.key)"
                :quote="quoteFor(f.key)"
                :warnings="warningsFor(f.key)"
                :kept="meta.kept.value.includes(f.key)"
                :can-restore="meta.current.value"
                :disabled="saving"
                @edit="meta.touch(f.key)"
                @restore="meta.restore(f.key)"
              />
            </div>
          </details>
        </section>

        <label class="form-label small">공고문·규격서 등 첨부 파일</label>
        <FileDropzone :accept="BID_ATTACHMENT_FORMATS" :disabled="saving" @files="addFiles" />
        <div v-if="duplicates.length" class="alert alert-info py-2 small mt-2 mb-0" role="status">
          이미 선택된 같은 파일이라 추가하지 않음: {{ duplicates.join(', ') }}
        </div>
        <ul v-if="files.length" class="list-group list-group-flush small mt-2">
          <li
            v-for="(file, index) in files"
            :key="fileKey(file)"
            class="list-group-item d-flex align-items-center px-0"
          >
            <i class="bi bi-file-earmark me-2"></i>
            <span class="me-auto text-break">{{ file.name }}</span>
            <span class="text-muted mx-3 text-nowrap">{{ formatBytes(file.size) }}</span>
            <button
              type="button"
              class="btn btn-sm btn-link text-danger p-0"
              :disabled="saving"
              :aria-label="`${file.name} 제외`"
              @click="files.splice(index, 1)"
            >
              <i class="bi bi-x-lg"></i>
            </button>
          </li>
        </ul>

        <p class="small text-muted mt-3 mb-0">
          파일 또는 본문 중 하나가 필요합니다(공고명·번호는 선택).
        </p>
        <details class="ft-help mt-1">
          <summary>등록 후 처리</summary>
          <p>
            등록하면 파일이 저장되고 문서 읽기가 시작되며, 읽기 결과는 첨부 목록의 상태로
            확인합니다. 요구조건 추출과 적합도 분석은 등록 후 편집 화면의
            <strong>추출 실행</strong>에서 별도로 진행합니다.
          </p>
        </details>
        <div v-if="error" class="alert alert-danger small mt-3 mb-0" role="alert">
          <div>{{ error }}</div>
          <ul v-if="failedFiles.length" class="mb-0 mt-1">
            <li v-for="s in failedFiles" :key="s.filename" class="text-break">
              {{ s.filename }} — {{ s.reason }}
            </li>
          </ul>
          <div class="mt-1">
            입력한 내용과 선택한 파일은 그대로 남아 있습니다. 문제를 고친 뒤 다시 등록하세요.
          </div>
        </div>
      </div>
      <div class="card-footer d-flex flex-wrap align-items-center justify-content-end gap-2">
        <span v-if="saving" class="small text-muted">파일을 저장하고 읽는 중입니다…</span>
        <span v-else-if="reading" class="small text-muted"
          >본문에서 기본 정보를 읽는 중입니다…</span
        >
        <span v-else-if="!hasInput" class="small text-muted"
          >파일을 선택하거나 본문을 입력하세요.</span
        >
        <button class="btn btn-primary" :disabled="!canSubmit || saving">
          <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span
          >{{ error ? '다시 시도' : '등록' }}
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.nf-section {
  border: 1px solid var(--ft-border);
  border-radius: 0.375rem;
  padding: 0.75rem;
  background: var(--ft-bg);
}
.nf-stale {
  opacity: 0.6;
}
</style>
