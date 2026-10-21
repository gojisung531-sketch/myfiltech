<script setup>
import { computed, onMounted, ref } from 'vue'

import { addAttachments, deleteAttachment, updateAttachment } from '@/api/bids'
import { listSchemas } from '@/api/documents'
import ConfirmModal from '@/components/ConfirmModal.vue'
import FileDropzone from '@/components/FileDropzone.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { DOCUMENT_STATUS_VARIANT, formatBytes } from '@/utils/format'
import { BID_ATTACHMENT_FORMATS } from '@/utils/options'

const props = defineProps({ bid: { type: Object, required: true } })
const emit = defineEmits(['changed'])

const toast = useToastStore()
const schemas = ref([])
const uploading = ref(false)
const removing = ref(null)
const busy = ref(false)

const attachments = computed(() =>
  [...props.bid.attachments].sort((a, b) => a.order - b.order || a.id - b.id),
)
const backLink = computed(() => `/admin/bids/${props.bid.id}/edit?tab=attachments`)

onMounted(async () => {
  schemas.value = await listSchemas({ owner_type: 'BID' })
})

const skipped = ref([]) // 서버가 거절한 파일 [{ filename, reason }]
const uploadError = ref('')
const lastFiles = ref([]) // 실패 후 다시 시도할 파일
const addedCount = ref(0)

async function upload(files) {
  if (uploading.value) return
  uploading.value = true
  skipped.value = []
  uploadError.value = ''
  addedCount.value = 0
  lastFiles.value = files
  try {
    const res = await addAttachments(props.bid.id, files)
    skipped.value = res.skipped || []
    addedCount.value = files.length - skipped.value.length
    lastFiles.value = []
    emit('changed')
  } catch (err) {
    skipped.value = err.response?.data?.skipped || []
    uploadError.value = errorMessage(err, '첨부를 추가하지 못했습니다.')
  } finally {
    uploading.value = false
  }
}

async function patch(attachment, payload, message) {
  try {
    await updateAttachment(props.bid.id, attachment.id, payload)
    if (message) toast.success(message)
    emit('changed')
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

function move(index, delta) {
  // Re-number every attachment so equal orders from older uploads become distinct.
  const list = [...attachments.value]
  ;[list[index], list[index + delta]] = [list[index + delta], list[index]]
  Promise.all(
    list.map((a, i) => (a.order !== i ? updateAttachment(props.bid.id, a.id, { order: i }) : null)),
  )
    .then(() => emit('changed'))
    .catch((err) => toast.error(errorMessage(err)))
}

async function doDelete() {
  busy.value = true
  try {
    await deleteAttachment(props.bid.id, removing.value.id)
    toast.success('첨부를 삭제했습니다.')
    removing.value = null
    emit('changed')
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div>
    <div class="card mb-3">
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead class="table-light">
            <tr>
              <th style="width: 4rem">순서</th>
              <th>파일</th>
              <th style="width: 14rem">분류</th>
              <th>상태</th>
              <th class="text-center">대표</th>
              <th class="text-end">작업</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(a, index) in attachments" :key="a.id">
              <td class="text-nowrap">
                <button
                  class="btn btn-sm btn-link p-0"
                  :disabled="index === 0"
                  aria-label="위로"
                  @click="move(index, -1)"
                >
                  <i class="bi bi-arrow-up"></i>
                </button>
                <button
                  class="btn btn-sm btn-link p-0"
                  :disabled="index === attachments.length - 1"
                  aria-label="아래로"
                  @click="move(index, 1)"
                >
                  <i class="bi bi-arrow-down"></i>
                </button>
              </td>
              <td>
                <span class="fw-semibold text-break">{{ a.display_name }}</span>
                <div class="small text-muted">
                  {{ a.file_format }} · {{ formatBytes(a.file_size) }} · 메타데이터
                  {{ a.metadata_count }}건
                </div>
              </td>
              <td>
                <select
                  class="form-select form-select-sm"
                  :value="a.role"
                  :aria-label="`${a.display_name} 분류`"
                  @change="patch(a, { category: $event.target.value }, '분류를 변경했습니다.')"
                >
                  <option v-if="!a.role" value="">미분류</option>
                  <option v-for="s in schemas" :key="s.id" :value="s.code">{{ s.name }}</option>
                </select>
              </td>
              <td>
                <span :class="['badge', `bg-${DOCUMENT_STATUS_VARIANT[a.status]}`]">{{
                  a.status_label
                }}</span>
                <div v-if="a.error_message" class="small text-danger text-break">
                  {{ a.error_message }}
                </div>
              </td>
              <td class="text-center">
                <input
                  class="form-check-input"
                  type="radio"
                  name="primary-attachment"
                  :checked="a.is_primary"
                  :aria-label="`${a.display_name} 대표 첨부`"
                  @change="patch(a, { is_primary: true }, '대표 첨부를 변경했습니다.')"
                />
              </td>
              <td class="text-end text-nowrap">
                <router-link
                  :to="{ path: `/admin/documents/${a.document_id}`, query: { back: backLink } }"
                  class="btn btn-sm btn-outline-primary me-1"
                  >메타데이터</router-link
                >
                <button class="btn btn-sm btn-outline-danger" @click="removing = a">삭제</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="card-header fw-semibold">첨부 추가</div>
      <div class="card-body">
        <FileDropzone :accept="BID_ATTACHMENT_FORMATS" :disabled="uploading" @files="upload" />
        <div v-if="uploading" class="small text-muted mt-2">
          <span class="spinner-border spinner-border-sm me-1"></span>파일을 저장하고 읽는 중입니다…
        </div>
        <div v-if="uploadError" class="alert alert-danger small mt-2 mb-0" role="alert">
          {{ uploadError }}
          <button
            v-if="lastFiles.length"
            type="button"
            class="btn btn-sm btn-outline-secondary ms-2"
            :disabled="uploading"
            @click="upload(lastFiles)"
          >
            다시 시도
          </button>
        </div>
        <div v-if="skipped.length" class="alert alert-warning small mt-2 mb-0" role="alert">
          <strong v-if="addedCount">{{ addedCount }}개만 추가되었습니다.</strong>
          <strong v-else>추가된 파일이 없습니다.</strong>
          서버가 거절한 파일:
          <ul class="mb-0">
            <li v-for="s in skipped" :key="s.filename" class="text-break">
              {{ s.filename }} — {{ s.reason }}
            </li>
          </ul>
        </div>
        <div
          v-else-if="addedCount && !uploadError"
          class="alert alert-success small mt-2 mb-0"
          role="status"
        >
          {{ addedCount }}개 파일을 저장했습니다. 문서 읽기 결과는 위 목록의 상태에서 확인하세요.
        </div>
        <p class="small text-muted mt-2 mb-0">
          추가한 파일은 저장 후 바로 텍스트 읽기·분류가 시도되며, 성공 여부는 목록의 상태로
          확인합니다. 분류를 바꾸면 다음 추출 때 해당 분류 기준으로 메타데이터를 다시 추출합니다.
        </p>
      </div>
    </div>

    <ConfirmModal
      :show="!!removing"
      title="첨부 삭제"
      :message="`'${removing?.display_name}' 첨부를 삭제합니다.`"
      confirm-text="삭제"
      :loading="busy"
      @confirm="doDelete"
      @cancel="removing = null"
    />
  </div>
</template>
