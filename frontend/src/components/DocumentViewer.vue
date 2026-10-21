<script setup>
// Extracted text / tables / original file preview for one document (specs/11 §4).
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { downloadDocument, getDocumentText } from '@/api/documents'
import { errorMessage } from '@/utils/errors'

const props = defineProps({
  document: { type: Object, required: true },
  initialPage: { type: Number, default: 0 }, // 1-based; 0 = first page
})

const tab = ref('text')
const content = ref(null)
const page = ref(0)
const error = ref('')
const fileUrl = ref('')
const loadingFile = ref(false)

const pages = computed(() => content.value?.pages || [])
const tables = computed(() => content.value?.tables || [])

async function load() {
  error.value = ''
  try {
    content.value = await getDocumentText(props.document.id)
    const count = content.value?.pages?.length || 0
    page.value = props.initialPage > 0 && props.initialPage <= count ? props.initialPage - 1 : 0
  } catch (err) {
    error.value = errorMessage(err)
  }
}

watch(
  () => [props.document.id, props.document.updated_at],
  () => load(),
  { immediate: true },
)

async function fetchFile() {
  if (fileUrl.value || !props.document.has_file) return
  loadingFile.value = true
  try {
    const blob = await downloadDocument(props.document.id)
    const type = props.document.file_format === 'PDF' ? 'application/pdf' : blob.type
    fileUrl.value = URL.createObjectURL(new Blob([blob], { type }))
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    loadingFile.value = false
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

onBeforeUnmount(() => fileUrl.value && URL.revokeObjectURL(fileUrl.value))
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
      <div v-if="error" class="alert alert-danger py-2 small">{{ error }}</div>

      <template v-if="tab === 'text'">
        <div v-if="pages.length > 1" class="d-flex align-items-center gap-2 mb-2 small">
          <button class="btn btn-sm btn-outline-secondary" :disabled="page === 0" @click="page--">
            이전
          </button>
          <span>{{ page + 1 }} / {{ pages.length }} 페이지</span>
          <button
            class="btn btn-sm btn-outline-secondary"
            :disabled="page >= pages.length - 1"
            @click="page++"
          >
            다음
          </button>
        </div>
        <pre v-if="pages[page]" class="extracted mb-0">{{ pages[page] }}</pre>
        <div v-else class="text-muted small">추출된 텍스트가 없습니다.</div>
      </template>

      <template v-else-if="tab === 'tables'">
        <div v-if="!tables.length" class="text-muted small">인식된 표가 없습니다.</div>
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
        <iframe
          v-else-if="fileUrl && document.file_format === 'PDF'"
          :src="fileUrl"
          class="w-100 h-100 border-0"
          title="원본 PDF"
        ></iframe>
        <div v-else-if="fileUrl" class="text-center py-5">
          <p class="text-muted small">
            {{ document.file_format }} 파일은 브라우저에서 미리 볼 수 없습니다.
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
.extracted {
  white-space: pre-wrap;
  font-size: 0.85rem;
  font-family: inherit;
}
.cell {
  white-space: pre-line;
}
</style>
