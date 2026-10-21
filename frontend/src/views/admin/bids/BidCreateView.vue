<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { createBid } from '@/api/bids'
import FileDropzone from '@/components/FileDropzone.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { formatBytes } from '@/utils/format'
import { BID_ATTACHMENT_FORMATS } from '@/utils/options'

const router = useRouter()
const toast = useToastStore()
const title = ref('')
const sourceText = ref('')
const files = ref([])
const saving = ref(false)
const error = ref('')

const canSubmit = computed(() => files.value.length > 0 || sourceText.value.trim().length > 0)

function addFiles(picked) {
  const names = new Set(files.value.map((f) => f.name))
  files.value.push(...picked.filter((f) => !names.has(f.name)))
}

async function submit() {
  error.value = ''
  saving.value = true
  try {
    const bid = await createBid({
      title: title.value,
      sourceText: sourceText.value,
      files: files.value,
    })
    for (const s of bid.skipped || []) toast.error(`${s.filename}: ${s.reason}`)
    toast.success('공고를 등록했습니다. 내용을 확인하고 “추출 실행”을 누르세요.')
    router.push(`/admin/bids/${bid.id}/edit`)
  } catch (err) {
    const skipped = err.response?.data?.skipped || []
    error.value = [errorMessage(err), ...skipped.map((s) => `${s.filename}: ${s.reason}`)].join(
      '\n',
    )
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="mx-auto" style="max-width: 900px">
    <div class="d-flex align-items-center gap-2 mb-3">
      <router-link to="/admin/bids" class="btn btn-sm btn-outline-secondary">
        <i class="bi bi-arrow-left"></i>
      </router-link>
      <h1 class="h4 mb-0">입찰 공고 등록</h1>
    </div>

    <form class="card" @submit.prevent="submit">
      <div class="card-body">
        <div class="mb-3">
          <label class="form-label small" for="bid-title"
            >공고명 (비워 두면 추출 결과로 채웁니다)</label
          >
          <input id="bid-title" v-model="title" class="form-control form-control-sm" />
        </div>

        <label class="form-label small">공고문·첨부 파일</label>
        <FileDropzone :accept="BID_ATTACHMENT_FORMATS" :disabled="saving" @files="addFiles" />
        <ul v-if="files.length" class="list-group list-group-flush small mt-2">
          <li
            v-for="(file, index) in files"
            :key="file.name"
            class="list-group-item d-flex align-items-center px-0"
          >
            <i class="bi bi-file-earmark me-2"></i>
            <span class="me-auto">{{ file.name }}</span>
            <span class="text-muted me-3">{{ formatBytes(file.size) }}</span>
            <button
              type="button"
              class="btn btn-sm btn-link text-danger p-0"
              :aria-label="`${file.name} 제외`"
              @click="files.splice(index, 1)"
            >
              <i class="bi bi-x-lg"></i>
            </button>
          </li>
        </ul>

        <div class="mt-3">
          <label class="form-label small" for="bid-text">공고 본문 직접 입력 (선택)</label>
          <textarea
            id="bid-text"
            v-model="sourceText"
            class="form-control form-control-sm"
            rows="8"
            placeholder="공고 본문을 붙여 넣으세요. 파일과 함께 입력할 수 있습니다."
          ></textarea>
        </div>

        <p class="small text-muted mt-3 mb-0">
          등록하면 파일별 텍스트 추출과 분류가 바로 진행되고, 공고문으로 분류된 파일이 대표 첨부가
          됩니다. 공고 메타데이터·품목·요구사항은 편집 화면의 <strong>추출 실행</strong>으로 LLM이
          추출합니다.
        </p>
        <div
          v-if="error"
          class="alert alert-danger py-2 small mt-3 mb-0"
          style="white-space: pre-line"
        >
          {{ error }}
        </div>
      </div>
      <div class="card-footer text-end">
        <span v-if="saving" class="small text-muted me-2">파일을 처리하는 중입니다…</span>
        <button class="btn btn-primary" :disabled="!canSubmit || saving">
          <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>등록
        </button>
      </div>
    </form>
  </div>
</template>
