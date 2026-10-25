<script setup>
// Extracted text / tables / original file preview for one document (specs/11 §4).
// 추출 텍스트의 구획 번호는 원본 PDF/HWP/XLSX의 실제 페이지·시트·셀 위치와 같다고 보장되지 않는다.
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

import { downloadDocument, getDocumentText } from '@/api/documents'
import { errorMessage } from '@/utils/errors'
import { fieldsText, kindLabel, ROLE_NOTE, statusInfo } from '@/utils/evidenceLocation'

const props = defineProps({
  document: { type: Object, required: true },
  initialPage: { type: Number, default: 0 }, // 저장된 참조 위치. 1-based; 0 = 없음
  // B6B 근거 위치 객체(서버가 원본·인용을 대조한 결과). 있으면 initialPage 대신 이것만 쓴다.
  location: { type: Object, default: null },
})

const tab = ref('text')
const content = ref(null)
const page = ref(0)
const loadingText = ref(false)
const textError = ref('')
const fileUrl = ref('')
const loadingFile = ref(false)
const fileError = ref('')
// 문서마다 올라가는 요청 번호. 늦게 도착한 이전 문서의 응답과 URL은 버린다.
let textSeq = 0
let fileSeq = 0

const pages = computed(() => content.value?.pages || [])
const tables = computed(() => content.value?.tables || [])
const hasText = computed(() => pages.value.some((p) => p && p.trim()))
const isPdf = computed(() => props.document.file_format === 'PDF')
// 저장된 숫자 위치(p.N)를 추출 텍스트 구획으로 자동 이동하는 데 써도 되는 경우만 true.
// API가 위치 종류(page/sheet/segment)나 원본 페이지↔구획 매핑을 주지 않으므로 비PDF에서는 쓰지 않는다.
// PDF도 추출 구획 수가 원본 페이지 수와 일치하는 경우에만 쓴다(page_count 없음은 확인 불가로 본다).
const canUsePosition = computed(
  () =>
    isPdf.value &&
    props.document.page_count != null &&
    props.document.page_count === pages.value.length,
)
const hasPosition = computed(() => !props.location && props.initialPage > 0 && !!content.value)
const positionUnmapped = computed(
  () => hasPosition.value && (!canUsePosition.value || props.initialPage > pages.value.length),
)
const unitLabel = computed(() => (isPdf.value ? '페이지' : '텍스트 구획'))

function revokeFile() {
  if (fileUrl.value) URL.revokeObjectURL(fileUrl.value)
  fileUrl.value = ''
}

function applyInitialPage() {
  // 자동 이동은 위치 매핑이 확인되는 경우만. 아니면 첫 구획에서 시작하고 사용자가 직접 넘긴다.
  const count = pages.value.length
  page.value =
    !props.location && canUsePosition.value && props.initialPage > 0 && props.initialPage <= count
      ? props.initialPage - 1
      : 0
}

async function loadText() {
  const mine = ++textSeq
  const id = props.document.id
  content.value = null
  textError.value = ''
  loadingText.value = true
  try {
    const result = await getDocumentText(id)
    if (mine !== textSeq) return
    content.value = result
    applyInitialPage()
  } catch (err) {
    if (mine === textSeq) textError.value = errorMessage(err, '추출 텍스트를 불러오지 못했습니다.')
  } finally {
    if (mine === textSeq) loadingText.value = false
  }
}

// 문서가 바뀌면 상태를 모두 초기화하고, 진행 중이던 요청 결과는 무시한다.
watch(
  () => [props.document.id, props.document.updated_at],
  () => {
    fileSeq += 1
    revokeFile()
    fileError.value = ''
    loadingFile.value = false
    tab.value = 'text'
    loadText()
  },
  { immediate: true },
)

// 같은 문서에서 다른 인용·위치를 고르면 현재 문서 위치만 갱신한다.
watch(
  () => props.initialPage,
  () => {
    if (content.value) applyInitialPage()
    tab.value = 'text'
  },
)

async function fetchFile() {
  if (fileUrl.value || loadingFile.value || !props.document.has_file) return
  const mine = ++fileSeq
  loadingFile.value = true
  fileError.value = ''
  try {
    const blob = await downloadDocument(props.document.id)
    if (mine !== fileSeq) return
    const type = isPdf.value ? 'application/pdf' : blob.type
    fileUrl.value = URL.createObjectURL(new Blob([blob], { type }))
  } catch (err) {
    if (mine === fileSeq) fileError.value = errorMessage(err, '원본 파일을 불러오지 못했습니다.')
  } finally {
    if (mine === fileSeq) loadingFile.value = false
  }
}

// ---- B6B 근거 위치 ----
// 서버가 계산한 위치를 현재 추출 텍스트와 다시 맞춰 보고, 맞을 때만 이동·강조한다.
const markEl = ref(null)
const chosen = ref(null) // MULTIPLE_MATCHES에서 사용자가 고른 후보 번호(자동 선택 없음)
const fullText = ref(false)

const loc = computed(() => props.location)
const info = computed(() => (loc.value ? statusInfo(loc.value) : null))
const candidates = computed(() => loc.value?.candidates || [])
const multiple = computed(() => loc.value?.status === 'MULTIPLE_MATCHES')
const active = computed(() => {
  const l = loc.value
  if (!l) return null
  if (multiple.value) return chosen.value == null ? null : candidates.value[chosen.value] || null
  const status = l.status
  if (['EXACT_MATCH', 'WHITESPACE_MATCH', 'MANUAL_REVIEWED_PAGE', 'PAGE_ONLY'].includes(status)) {
    if (candidates.value[0]) return candidates.value[0]
    return l.location_kind && l.location_kind !== 'NONE'
      ? { kind: l.location_kind, value: l.location_value, matched_text: null }
      : null
  }
  // 인용은 불일치라도 명시된 PDF 물리 페이지가 확인되면 페이지만 연다(인용 강조 없음).
  if (l.physical_page_verified && l.declared_page_kind === 'PHYSICAL_PDF_PAGE' && l.declared_page) {
    return { kind: 'PDF_PAGE', value: { page: l.declared_page }, matched_text: null }
  }
  return null
})
const pdfTarget = computed(() => {
  const a = active.value
  if (!a || a.kind !== 'PDF_PAGE' || !isPdf.value || !loc.value?.physical_page_verified) return 0
  const n = Number(a.value?.page)
  return Number.isInteger(n) && n > 0 ? n : 0
})
const hasPageText = computed(() => active.value?.value?.page_text_start != null)
const cellInfo = computed(() => {
  const a = active.value
  if (!a || a.kind !== 'SPREADSHEET_CELL') return null
  const v = a.value || {}
  const text = v.cell_text ?? ''
  const ok =
    Number.isInteger(v.start) &&
    Number.isInteger(v.end) &&
    v.start >= 0 &&
    v.end <= text.length &&
    v.start < v.end &&
    (a.matched_text == null || text.slice(v.start, v.end) === a.matched_text)
  return {
    sheet: v.sheet,
    address: v.cell,
    before: ok ? text.slice(0, v.start) : text,
    mark: ok ? text.slice(v.start, v.end) : '',
    after: ok ? text.slice(v.end) : '',
  }
})

// 위치를 현재 텍스트에 적용할 수 있는지 검증한다. 맞지 않으면 강조하지 않는다.
function resolveRange(a) {
  if (!a || !content.value) return null
  const v = a.value || {}
  const l = loc.value
  if (a.kind === 'EXTRACTED_TEXT_RANGE') {
    const text = content.value.extracted_text
    if (typeof text !== 'string')
      return { ok: false, reason: '현재 추출 텍스트 전체를 받지 못해 위치를 맞춰 볼 수 없습니다.' }
    const hash = v.text_sha256 || l.text_sha256
    if (hash && content.value.text_sha256 !== hash)
      return {
        ok: false,
        reason: '현재 추출 텍스트가 위치를 계산한 텍스트와 달라(해시 불일치) 강조하지 않았습니다.',
      }
    const s = v.start_utf16
    const e = v.end_utf16
    if (!Number.isInteger(s) || !Number.isInteger(e) || s < 0 || e > text.length || s >= e)
      return {
        ok: false,
        reason: '기록된 위치가 현재 추출 텍스트 범위를 벗어나 강조하지 않았습니다.',
      }
    if (a.matched_text != null && text.slice(s, e) !== a.matched_text)
      return {
        ok: false,
        reason: '그 위치의 글자가 기록된 일치 텍스트와 달라 강조하지 않았습니다.',
      }
    return { ok: true, scope: 'full', text, s, e }
  }
  if (a.kind === 'PDF_PAGE' && v.page_text_start != null) {
    const idx = Number(v.page) - 1
    const text = pages.value[idx]
    if (
      text == null ||
      pages.value.length !== l.physical_page_count ||
      (l.text_sha256 && content.value.text_sha256 !== l.text_sha256)
    )
      return {
        ok: false,
        reason: '추출 텍스트 구획이 실제 PDF 페이지와 맞는지 확인되지 않아 강조하지 않았습니다.',
      }
    if (text.slice(v.page_text_start, v.page_text_end) !== a.matched_text)
      return {
        ok: false,
        reason: '그 위치의 글자가 기록된 일치 텍스트와 달라 강조하지 않았습니다.',
      }
    return { ok: true, scope: 'page', page: idx, text, s: v.page_text_start, e: v.page_text_end }
  }
  return null
}
const highlight = computed(() => resolveRange(active.value))
const parts = computed(() => {
  const h = highlight.value
  if (!h?.ok) return null
  return { before: h.text.slice(0, h.s), mark: h.text.slice(h.s, h.e), after: h.text.slice(h.e) }
})

// 후보 목록에 보여 줄 앞뒤 문맥(맞는 경우에만)
function candidateContext(c) {
  const r = content.value ? resolveRange(c) : null
  if (!r?.ok) return null
  const from = Math.max(0, r.s - 30)
  return {
    before: (from > 0 ? '…' : '') + r.text.slice(from, r.s),
    mark: r.text.slice(r.s, r.e),
    after: r.text.slice(r.e, r.e + 30) + (r.e + 30 < r.text.length ? '…' : ''),
  }
}
function candidateWhere(c) {
  const v = c.value || {}
  if (c.kind === 'PDF_PAGE') {
    const extra =
      v.page_text_start != null ? ` · 페이지 텍스트 ${v.page_text_start}–${v.page_text_end}` : ''
    return `PDF 물리 p.${v.page}${extra}`
  }
  if (c.kind === 'SPREADSHEET_CELL') return `시트 ${v.sheet} · 셀 ${v.cell}`
  if (c.kind === 'EXTRACTED_TEXT_RANGE') return `추출 텍스트 ${v.start_utf16}–${v.end_utf16}`
  return c.kind
}
const lineText = computed(() => {
  const v = active.value?.value
  if (!v || v.extracted_line_start == null) return ''
  return v.extracted_line_start === v.extracted_line_end
    ? `추출 텍스트 ${v.extracted_line_start}행`
    : `추출 텍스트 ${v.extracted_line_start}–${v.extracted_line_end}행`
})
const headingText = computed(() => active.value?.value?.section_heading?.text || '')
const kindText = computed(() =>
  loc.value ? kindLabel(active.value?.kind || loc.value.location_kind, loc.value.file_format) : '',
)
const roleNote = computed(() => ROLE_NOTE[loc.value?.role] || '')
const fieldList = computed(() => fieldsText(loc.value))
const frameSrc = computed(() =>
  fileUrl.value && pdfTarget.value ? `${fileUrl.value}#page=${pdfTarget.value}` : fileUrl.value,
)

function choose(i) {
  chosen.value = i
}
function showWholeDocument() {
  fullText.value = true
  tab.value = 'text'
}

watch(
  () => props.location,
  () => {
    chosen.value = null
    fullText.value = false
  },
)
// 위치가 정해지면 해당 보기로 이동한다: PDF 물리쪽은 원본, 그 외는 추출 텍스트.
watch(
  active,
  (a) => {
    if (!a) return
    if (pdfTarget.value && props.document.has_file && !hasPageText.value) {
      tab.value = 'file'
      fetchFile()
    } else {
      tab.value = 'text'
    }
  },
  { immediate: true },
)
watch(
  () => [highlight.value, tab.value],
  async ([h, current]) => {
    if (!h?.ok || current !== 'text') return
    if (h.scope === 'page') page.value = h.page
    await nextTick()
    scrollToMark()
    // 패널이 열리는 동안 폭이 바뀌어 줄바꿈 위치가 달라질 수 있어 한 번 더 맞춘다.
    setTimeout(scrollToMark, 400)
  },
  { flush: 'post' },
)

// 문서 보기 영역 안에서만 강조 위치를 가운데로 가져온다(페이지 전체는 움직이지 않는다).
function scrollToMark() {
  const el = markEl.value
  const box = el?.closest('.viewer-body')
  if (!el || !box) return
  const e = el.getBoundingClientRect()
  const b = box.getBoundingClientRect()
  box.scrollTop += e.top - b.top - box.clientHeight / 2 + e.height / 2
}

function showTab(name) {
  tab.value = name
  if (name === 'file') fetchFile()
}

function saveFile() {
  const link = window.document.createElement('a')
  link.href = fileUrl.value
  link.download = props.document.original_filename
  link.click()
}

onBeforeUnmount(() => {
  textSeq += 1
  fileSeq += 1
  revokeFile()
})
</script>

<template>
  <div class="card h-100">
    <div class="card-header">
      <ul class="nav nav-tabs card-header-tabs">
        <li class="nav-item">
          <button class="nav-link" :class="{ active: tab === 'text' }" @click="showTab('text')">
            추출 텍스트
          </button>
        </li>
        <li class="nav-item">
          <button class="nav-link" :class="{ active: tab === 'tables' }" @click="showTab('tables')">
            표 ({{ tables.length }})
          </button>
        </li>
        <li v-if="document.has_file" class="nav-item">
          <button class="nav-link" :class="{ active: tab === 'file' }" @click="showTab('file')">
            원본
          </button>
        </li>
      </ul>
    </div>
    <div class="card-body viewer-body">
      <div
        v-if="document.status === 'NEEDS_OCR' || document.status === 'FAILED'"
        class="alert alert-warning py-2 small"
      >
        <strong>{{ document.status_label }}</strong>
        <span v-if="document.error_message"> — {{ document.error_message }}</span>
        <span v-else-if="document.status === 'NEEDS_OCR'">
          — 스캔 문서라 추출 텍스트가 없을 수 있습니다.</span
        >
        <span v-if="document.has_file"> 원본 탭에서 파일을 직접 확인하세요.</span>
      </div>
      <div v-else-if="!document.has_file" class="alert alert-secondary py-2 small">
        연결된 원본 파일이 없습니다.
      </div>

      <div v-if="loc" class="loc-box small mb-2" :class="{ sticky: !multiple }" role="status">
        <div class="d-flex flex-wrap align-items-center gap-1">
          <span class="badge" :class="info.tone">{{ info.label }}</span>
          <span class="fw-semibold">{{ kindText }}</span>
          <span v-if="fieldList" class="text-muted">· {{ fieldList }}</span>
        </div>
        <div v-if="roleNote" class="text-muted">{{ roleNote }}</div>
        <div v-if="info.reason" class="mt-1">{{ info.reason }}</div>
        <div v-if="loc.source_verification && loc.source_verification !== 'VERIFIED'" class="mt-1">
          <span class="badge bg-warning">원본 동일성 확인 안 됨</span> ({{
            loc.source_verification
          }})
        </div>
        <div v-if="loc.document_binding === 'CURRENT_RECORD_LINK'" class="text-muted mt-1">
          당시 파일이 아니라 현재 연결된 문서 기준입니다(저장 당시 파일 동일성은 확인되지 않음).
        </div>
        <div v-if="loc.record_value_consistency === 'DIFFERS_FROM_REVIEW'" class="mt-1">
          <span class="badge bg-warning">현재 등록 값이 수동 확인 당시와 다름</span>
        </div>

        <div v-if="multiple" class="mt-2">
          <div class="fw-semibold">
            후보 {{ candidates.length }}곳 — 직접 선택하세요
            <span v-if="chosen == null" class="text-muted fw-normal">(아직 선택 안 함)</span>
          </div>
          <ul class="list-unstyled mb-0 cand-list">
            <li
              v-for="(c, i) in candidates"
              :key="i"
              class="cand-opt"
              :class="{ on: chosen === i }"
            >
              <div class="d-flex flex-wrap align-items-center gap-2">
                <button
                  type="button"
                  class="btn btn-sm"
                  :class="chosen === i ? 'btn-secondary' : 'btn-outline-secondary'"
                  :aria-pressed="chosen === i"
                  @click="choose(i)"
                >
                  후보 {{ i + 1 }} 선택
                </button>
                <span class="text-muted">{{ candidateWhere(c) }}</span>
              </div>
              <div v-if="candidateContext(c)" class="ctx text-break">
                <span>{{ candidateContext(c).before }}</span
                ><mark class="hit">{{ candidateContext(c).mark }}</mark
                ><span>{{ candidateContext(c).after }}</span>
              </div>
              <div v-else-if="c.matched_text" class="ctx text-break">{{ c.matched_text }}</div>
            </li>
          </ul>
        </div>

        <template v-else-if="active">
          <div v-if="lineText" class="mt-1">
            {{ lineText }}
            <span v-if="headingText" class="text-muted"
              >· 가까운 번호 행: “{{ headingText }}” (참고용, 해당 항목의 범위로 확인되지
              않음)</span
            >
          </div>
          <div v-if="active.kind === 'PDF_PAGE' && pdfTarget" class="mt-1">
            확인된 PDF 물리 {{ pdfTarget }}쪽입니다(인쇄된 쪽번호와 다를 수 있음).
            <span v-if="!hasPageText">
              {{
                loc.status === 'QUOTE_NOT_FOUND'
                  ? '인용문은 일치하지 않았으며 이 페이지에서 직접 확인해야 합니다.'
                  : '인용 문자 대조는 하지 않았고 이미지 위 강조도 없습니다.'
              }}
            </span>
          </div>
          <div v-if="highlight && !highlight.ok" class="alert alert-warning py-1 px-2 mt-2 mb-0">
            {{ highlight.reason }}
          </div>
        </template>

        <div v-if="!info.confirmed || (highlight && !highlight.ok)" class="mt-2">
          <button type="button" class="btn btn-sm btn-outline-secondary" @click="showWholeDocument">
            문서 전체 보기
          </button>
        </div>
        <div v-if="!info.confirmed && !loc.document_id" class="mt-1 text-muted">
          열 수 있는 문서가 없습니다.
        </div>
        <div
          v-if="active && active.kind === 'EXTRACTED_TEXT_RANGE' && highlight?.ok"
          class="text-muted mt-1"
        >
          강조는 현재 추출 텍스트(해시 일치) 기준이며 원본 페이지·문단 위치를 뜻하지 않습니다.
        </div>
        <div
          v-if="active && active.kind === 'PDF_PAGE' && hasPageText && highlight?.ok"
          class="mt-1"
        >
          <button type="button" class="btn btn-sm btn-outline-secondary" @click="showTab('file')">
            원본 PDF {{ pdfTarget }}쪽 열기
          </button>
          <span class="text-muted ms-1"
            >추출 텍스트에서만 강조합니다(PDF 이미지 위 강조 없음).</span
          >
        </div>
      </div>

      <template v-if="tab === 'text'">
        <div v-if="loadingText" class="text-center py-5"><span class="spinner-border"></span></div>
        <div v-else-if="textError" class="alert alert-danger py-2 small d-flex gap-2">
          <span class="flex-grow-1">{{ textError }}</span>
          <button class="btn btn-sm btn-outline-secondary" @click="loadText">다시 시도</button>
        </div>
        <template v-else>
          <div v-if="cellInfo" class="cell-card small mb-2">
            <div class="text-muted">원본 엑셀의 실제 위치</div>
            <div class="fw-semibold">시트 “{{ cellInfo.sheet }}” · 셀 {{ cellInfo.address }}</div>
            <div class="cell-text text-break">
              <span>{{ cellInfo.before }}</span
              ><mark ref="markEl" class="hit">{{ cellInfo.mark }}</mark
              ><span>{{ cellInfo.after }}</span>
            </div>
            <div class="text-muted mt-1">
              ‘표’ 탭의 번호는 빈 행·열을 제거한 추출 표의 순서이며 원본 셀 주소가 아닙니다.
            </div>
          </div>

          <div v-if="positionUnmapped" class="alert alert-warning py-2 small">
            저장된 참조 위치 p.{{ initialPage }} · 위치 확인 필요(이동하지 않음)
            <details class="ft-help">
              <summary>이유</summary>
              <p v-if="!isPdf">
                이 문서 형식은 위치 종류(페이지·시트·텍스트 구획)와 원문 대응 정보가 없어 숫자만으로
                추출 텍스트 구획을 정할 수 없습니다. 원문에서 직접 찾아 확인하세요.
              </p>
              <p v-else>
                추출 텍스트 구획이 원본 페이지와 일치하는지 확인되지 않거나 해당 구획이 없습니다.
                원문에서 직접 찾아 확인하세요.
              </p>
            </details>
          </div>
          <div v-if="parts && highlight.scope === 'full'" class="small text-muted mb-1">
            추출 텍스트 전체 · 강조 위치로 이동했습니다.
          </div>
          <pre
            v-if="parts && highlight.scope === 'full'"
            class="extracted mb-0"
          ><span>{{ parts.before }}</span><mark ref="markEl" class="hit">{{ parts.mark }}</mark><span>{{ parts.after }}</span></pre>
          <pre
            v-else-if="fullText && typeof content?.extracted_text === 'string'"
            class="extracted mb-0"
            >{{ content.extracted_text }}</pre>
          <template v-else>
            <div v-if="pages.length > 1" class="d-flex align-items-center gap-2 mb-2 small">
              <button
                class="btn btn-sm btn-outline-secondary"
                :disabled="page === 0"
                @click="page--"
              >
                이전
              </button>
              <span>{{ page + 1 }} / {{ pages.length }} {{ unitLabel }}</span>
              <button
                class="btn btn-sm btn-outline-secondary"
                :disabled="page >= pages.length - 1"
                @click="page++"
              >
                다음
              </button>
              <span
                v-if="canUsePosition && initialPage > 0 && page === initialPage - 1"
                class="badge bg-secondary"
                >저장된 참조 위치</span
              >
            </div>
            <div v-if="!isPdf && pages.length > 1" class="small text-muted mb-2">
              텍스트 구획 번호는 원본의 실제 페이지·시트와 다를 수 있습니다.
            </div>
            <pre
              v-if="parts && highlight.scope === 'page' && page === highlight.page"
              class="extracted mb-0"
            ><span>{{ parts.before }}</span><mark ref="markEl" class="hit">{{ parts.mark }}</mark><span>{{ parts.after }}</span></pre>
            <pre v-else-if="hasText && pages[page]" class="extracted mb-0">{{ pages[page] }}</pre>
            <div v-else class="text-muted small">
              추출된 텍스트가 없습니다.
              <template v-if="document.status === 'NEEDS_OCR'">
                스캔 문서로 분류되어 OCR이 필요합니다.
              </template>
              <template v-else-if="document.status === 'FAILED'"
                >문서 읽기에 실패했습니다.</template
              >
            </div>
          </template>
        </template>
      </template>

      <template v-else-if="tab === 'tables'">
        <div v-if="loadingText" class="text-center py-5"><span class="spinner-border"></span></div>
        <div v-else-if="textError" class="alert alert-danger py-2 small">{{ textError }}</div>
        <div v-else-if="!tables.length" class="text-muted small">인식된 표가 없습니다.</div>
        <div v-for="(table, i) in tables" :key="i" class="mb-3">
          <div class="small text-muted mb-1">
            표 {{ i + 1 }}<span v-if="table.page"> · {{ table.page }}페이지</span>
            <span v-if="table.sheet"> · 시트 {{ table.sheet }}</span>
          </div>
          <div class="table-responsive">
            <table class="table table-sm table-bordered small mb-0">
              <tbody>
                <tr v-for="(row, r) in table.rows" :key="r">
                  <td v-for="(cell, c) in row" :key="c" class="cell">{{ cell }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>

      <template v-else>
        <div v-if="loadingFile" class="text-center py-5"><span class="spinner-border"></span></div>
        <div v-else-if="fileError" class="alert alert-danger py-2 small d-flex gap-2">
          <span class="flex-grow-1">{{ fileError }}</span>
          <button class="btn btn-sm btn-outline-secondary" @click="fetchFile">다시 시도</button>
        </div>
        <iframe
          v-else-if="fileUrl && isPdf"
          :key="frameSrc"
          :src="frameSrc"
          class="pdf-frame"
          title="원본 PDF"
        ></iframe>
        <div v-else-if="fileUrl" class="text-center py-5">
          <p class="text-muted small">
            {{ document.file_format }} 파일은 브라우저에서 미리 볼 수 없습니다. 내려받아 원문을
            확인하세요.
          </p>
          <button class="btn btn-outline-primary btn-sm" @click="saveFile">
            <i class="bi bi-download me-1"></i>{{ document.original_filename }} 내려받기
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.viewer-body {
  min-height: 60vh;
  max-height: 75vh;
  overflow: auto;
}
.pdf-frame {
  width: 100%;
  height: 68vh;
  border: 0;
}
.extracted {
  white-space: pre-wrap;
  font-size: 0.85rem;
  font-family: inherit;
}
.cell {
  white-space: pre-line;
}
.loc-box,
.cell-card {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--ft-border);
  border-left: 3px solid var(--ft-primary);
  border-radius: 0.3rem;
  background: var(--ft-bg);
}
.loc-box.sticky {
  position: sticky;
  top: 0;
  z-index: 2;
  max-height: 14rem;
  overflow: auto;
}
@media (max-width: 575.98px) {
  .loc-box.sticky {
    max-height: 8rem;
  }
}
.hit {
  padding: 0 0.1rem;
  background: #ffe28a;
  color: inherit;
  outline: 1px solid #c9a227;
}
.cand-opt {
  margin-top: 0.4rem;
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--ft-border);
  border-radius: 0.3rem;
  background: var(--ft-surface);
}
.cand-opt.on {
  border-color: var(--ft-primary);
}
.ctx,
.cell-text {
  margin-top: 0.25rem;
  white-space: pre-wrap;
}
</style>
