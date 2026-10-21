<script setup>
// Evidence document opened from a verdict or comparison cell (specs/11 BidDetailView).
import { ref, watch } from 'vue'

import { getDocument } from '@/api/documents'
import { errorMessage } from '@/utils/errors'

import DocumentViewer from './DocumentViewer.vue'

const props = defineProps({
  documentId: { type: Number, default: null },
  page: { type: Number, default: 0 },
  quote: { type: String, default: '' },
})
const emit = defineEmits(['close'])

const doc = ref(null)
const error = ref('')

watch(
  () => props.documentId,
  async (id) => {
    doc.value = null
    error.value = ''
    if (!id) return
    try {
      doc.value = await getDocument(id)
    } catch (err) {
      error.value = errorMessage(err)
    }
  },
  { immediate: true },
)
</script>

<template>
  <div v-if="documentId">
    <div
      class="offcanvas offcanvas-end show"
      style="width: min(900px, 95vw); visibility: visible"
      tabindex="-1"
      role="dialog"
      aria-label="근거 문서"
    >
      <div class="offcanvas-header border-bottom">
        <h5 class="offcanvas-title text-truncate">{{ doc?.display_name || '문서' }}</h5>
        <button type="button" class="btn-close" aria-label="닫기" @click="emit('close')"></button>
      </div>
      <div class="offcanvas-body">
        <div v-if="quote" class="alert alert-light border small">
          <i class="bi bi-quote me-1"></i>{{ quote }}<span v-if="page"> (p.{{ page }})</span>
        </div>
        <div v-if="error" class="alert alert-danger small">{{ error }}</div>
        <DocumentViewer v-else-if="doc" :document="doc" :initial-page="page" />
        <div v-else class="text-center py-5"><span class="spinner-border"></span></div>
      </div>
    </div>
    <div class="offcanvas-backdrop fade show" @click="emit('close')"></div>
  </div>
</template>
