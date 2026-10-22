<script setup>
// Extracted text / tables / original file preview for one document (specs/11 §4).
// 추출 텍스트의 구획 번호는 원본 PDF/HWP/XLSX의 실제 페이지·시트·셀 위치와 같다고 보장되지 않는다.
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { downloadDocument, getDocumentText } from '@/api/documents'
import { errorMessage } from '@/utils/errors'

const props = defineProps({
  document: { type: Object, required: true },
  initialPage: { type: Number, default: 0 }, // 저장된 참조 위치. 1-based; 0 = 없음
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
const hasPosition = computed(() => props.initialPage > 0 && !!content.value)
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
    canUsePosition.value && props.initialPage > 0 && props.initialPage <= count
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

      <template v-if="tab === 'text'">
        <div v-if="loadingText" class="text-center py-5"><span class="spinner-border"></span></div>
        <div v-else-if="textError" class="alert alert-danger py-2 small d-flex gap-2">
          <span class="flex-grow-1">{{ textError }}</span>
          <button class="btn btn-sm btn-outline-secondary" @click="loadText">다시 시도</button>
        </div>
        <template v-else>
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
          <div v-if="pages.length > 1" class="d-flex align-items-center gap-2 mb-2 small">
            <button class="btn btn-sm btn-outline-secondary" :disabled="page === 0" @click="page--">
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
          <pre v-if="hasText && pages[page]" class="extracted mb-0">{{ pages[page] }}</pre>
          <div v-else class="text-muted small">
            추출된 텍스트가 없습니다.
            <template v-if="document.status === 'NEEDS_OCR'">
              스캔 문서로 분류되어 OCR이 필요합니다.
            </template>
            <template v-else-if="document.status === 'FAILED'">문서 읽기에 실패했습니다.</template>
          </div>
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
          :src="fileUrl"
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
</style>
