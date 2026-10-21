<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { createBid } from '@/api/bids'
import FileDropzone from '@/components/FileDropzone.vue'
import { errorMessage } from '@/utils/errors'
import { formatBytes } from '@/utils/format'
import { BID_ATTACHMENT_FORMATS } from '@/utils/options'

const router = useRouter()
const title = ref('')
const sourceText = ref('')
const files = ref([])
const duplicates = ref([])
const saving = ref(false)
const error = ref('')
const failedFiles = ref([]) // 서버가 거절한 파일 [{ filename, reason }]
const created = ref(null) // 등록은 됐지만 일부 파일이 제외된 경우의 결과

const canSubmit = computed(() => files.value.length > 0 || sourceText.value.trim().length > 0)
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
      title: title.value,
      sourceText: sourceText.value,
      files: files.value,
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
          <label class="form-label small" for="bid-title"
            >공고명 (비워 두면 첫 파일명 또는 본문 첫 줄을 사용합니다)</label
          >
          <input
            id="bid-title"
            v-model="title"
            class="form-control form-control-sm"
            :disabled="saving"
          />
        </div>

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

        <div class="mt-3">
          <label class="form-label small" for="bid-text">공고 본문 직접 입력 (선택)</label>
          <textarea
            id="bid-text"
            v-model="sourceText"
            class="form-control form-control-sm"
            rows="8"
            :disabled="saving"
            placeholder="공고 본문을 붙여 넣으세요. 파일과 함께 입력할 수 있습니다."
          ></textarea>
        </div>

        <p class="small text-muted mt-3 mb-0">
          파일 또는 본문 중 하나는 필요합니다. 공고번호·공고명은 필수가 아닙니다. 등록하면 파일이
          저장되고 문서 읽기가 시작되며, 읽기 결과는 첨부 목록의 상태로 확인합니다. 요구조건 추출과
          적합도 분석은 등록 후 편집 화면의 <strong>추출 실행</strong>에서 별도로 진행합니다.
        </p>
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
        <span v-else-if="!canSubmit" class="small text-muted"
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
