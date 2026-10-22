<script setup>
// 원문 보기: 선택한 요구사항/참고 자료 정보(왼쪽·위)와 문서 뷰어(오른쪽·아래)를 함께 보여 준다.
// 호출부는 저장된 값(document_id·인용문·위치)만 넘긴다. 이 화면은 값을 만들거나 검증하지 않는다.
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

import { getDocument } from '@/api/documents'
import { errorMessage } from '@/utils/errors'

import DocumentViewer from './DocumentViewer.vue'

const props = defineProps({
  documentId: { type: Number, default: null },
  page: { type: Number, default: 0 },
  quote: { type: String, default: '' },
  // 'requirement_source'(공고 요구조건의 출처) | 'reference'(필텍 쪽 연결·참고 자료) | 'attachment'(직접 연 첨부)
  kind: { type: String, default: 'attachment' },
  contextTitle: { type: String, default: '' }, // 선택한 요구사항·자료 이름
  contextText: { type: String, default: '' }, // 요구사항 원문 등 보조 설명
  positionNote: { type: String, default: '' }, // 위치 값 해석 주의 문구
})
const emit = defineEmits(['close'])

const KINDS = {
  requirement_source: { label: '공고 요구조건의 출처', badge: 'bg-info' },
  reference: { label: '필텍 쪽 연결·참고 자료', badge: 'bg-secondary' },
  attachment: { label: '직접 연 첨부', badge: 'bg-secondary' },
}

const doc = ref(null)
const error = ref('')
const loading = ref(false)
const panel = ref(null)
const closeButton = ref(null)
let seq = 0 // 늦게 도착한 이전 문서 응답이 새 문서에 섞이지 않게 한다.
let opener = null // 닫을 때 포커스를 돌려줄 원래 항목

async function load(id) {
  const mine = ++seq
  doc.value = null
  error.value = ''
  if (!id) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const result = await getDocument(id)
    if (mine === seq) doc.value = result
  } catch (err) {
    if (mine === seq) error.value = errorMessage(err, '문서 정보를 불러오지 못했습니다.')
  } finally {
    if (mine === seq) loading.value = false
  }
}

watch(
  () => props.documentId,
  async (id, previous) => {
    if (id && !previous) {
      opener = window.document.activeElement
      window.document.addEventListener('keydown', onKey)
      await nextTick()
      closeButton.value?.focus()
    }
    if (!id && previous) release()
    load(id)
  },
  { immediate: true },
)

function onKey(event) {
  if (event.key === 'Escape') close()
  else if (event.key === 'Tab' && panel.value) trapFocus(event)
}

function trapFocus(event) {
  const nodes = panel.value.querySelectorAll(
    'a[href], button:not([disabled]), input, select, textarea, iframe, [tabindex]:not([tabindex="-1"])',
  )
  if (!nodes.length) return
  const first = nodes[0]
  const last = nodes[nodes.length - 1]
  if (event.shiftKey && window.document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && window.document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

function release() {
  window.document.removeEventListener('keydown', onKey)
  const target = opener
  opener = null
  if (target && typeof target.focus === 'function') nextTick(() => target.focus())
}

function close() {
  emit('close')
}

onBeforeUnmount(() => {
  seq += 1
  window.document.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div v-if="documentId">
    <div
      ref="panel"
      class="offcanvas offcanvas-end show doc-panel"
      tabindex="-1"
      role="dialog"
      aria-modal="true"
      aria-label="원문 보기"
    >
      <div class="offcanvas-header border-bottom">
        <div class="min-w-0">
          <div class="small text-muted">{{ KINDS[kind]?.label }}</div>
          <h5 class="offcanvas-title text-break">{{ doc?.display_name || '문서' }}</h5>
        </div>
        <button
          ref="closeButton"
          type="button"
          class="btn-close"
          aria-label="닫기 (Esc)"
          @click="close"
        ></button>
      </div>
      <div class="offcanvas-body doc-body">
        <aside class="doc-context">
          <span class="badge" :class="KINDS[kind]?.badge">{{ KINDS[kind]?.label }}</span>
          <div v-if="contextTitle" class="fw-semibold mt-2 text-break">{{ contextTitle }}</div>
          <div v-if="contextText" class="small text-muted mt-1 text-break">{{ contextText }}</div>
          <div v-if="doc" class="small mt-2 text-break">
            <span class="text-muted">열린 문서:</span> {{ doc.display_name }}
          </div>

          <div v-if="quote" class="doc-quote small mt-3">
            <div class="text-muted">저장된 인용문</div>
            <div class="text-break fst-italic">“{{ quote }}”</div>
          </div>
          <div v-if="page" class="small mt-2">
            <span class="text-muted">저장된 참조 위치:</span> p.{{ page }}
          </div>
          <div v-if="positionNote" class="small text-muted mt-1">{{ positionNote }}</div>
          <div class="small mt-3">
            <span class="badge bg-warning">원문 대조 필요</span>
          </div>
          <details class="ft-help mt-1">
            <summary>이 표시의 뜻</summary>
            <p>
              문서를 열었다는 것은 근거가 정확하다는 검증 결과가 아닙니다. 저장된 인용문과 위치는
              원문과 직접 대조하세요.
            </p>
          </details>
        </aside>

        <section class="doc-viewer">
          <div v-if="error" class="alert alert-danger small d-flex align-items-center gap-2">
            <span class="flex-grow-1">{{ error }}</span>
            <button class="btn btn-sm btn-outline-secondary" @click="load(documentId)">
              다시 시도
            </button>
          </div>
          <DocumentViewer v-else-if="doc" :key="doc.id" :document="doc" :initial-page="page" />
          <div v-else-if="loading" class="text-center py-5">
            <span class="spinner-border"></span>
          </div>
        </section>
      </div>
    </div>
    <div class="offcanvas-backdrop fade show" @click="close"></div>
  </div>
</template>

<style scoped>
.doc-panel {
  width: min(1200px, 98vw);
  visibility: visible;
}
.doc-body {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
  align-content: start;
}
.doc-context {
  padding: 0.75rem 1rem;
  border: 1px solid var(--ft-border);
  border-radius: 0.4rem;
  background: var(--ft-bg);
}
.doc-quote {
  padding-left: 0.6rem;
  border-left: 3px solid var(--ft-primary);
}
.doc-viewer {
  min-width: 0;
}
.min-w-0 {
  min-width: 0;
}
@media (min-width: 992px) {
  .doc-body {
    grid-template-columns: 22rem minmax(0, 1fr);
    align-items: start;
  }
  .doc-context {
    position: sticky;
    top: 0;
  }
}
</style>
