<script setup>
// 회사 정보·인증서 화면용: 수동으로 확인해 기록된 근거 위치 목록과 원문 패널.
// 위치는 서버가 원본과 대조한 결과이며, 이 화면은 값을 고치거나 새로 만들지 않는다.
import { computed, ref } from 'vue'

import { fieldsText, statusInfo } from '@/utils/evidenceLocation'

import DocumentOffcanvas from './DocumentOffcanvas.vue'
import LocationStatus from './LocationStatus.vue'

const props = defineProps({
  locations: { type: Array, default: () => [] },
  // 'button': 한 개의 버튼(표 행용) | 'list': 항목별 목록(회사 정보용)
  mode: { type: String, default: 'list' },
  title: { type: String, default: '' },
})

const current = ref(null)
const withDocument = computed(() => props.locations.filter((l) => l.document_id))

function open(loc) {
  current.value = loc
}
const siblings = computed(() =>
  current.value ? props.locations.filter((l) => l.document_id === current.value.document_id) : [],
)
const label = (l) => {
  const page = l.location_value?.page ? ` · p.${l.location_value.page}` : ''
  return `${fieldsText(l) || '위치'}${page}`
}
</script>

<template>
  <div>
    <button
      v-if="mode === 'button'"
      type="button"
      class="btn btn-sm btn-outline-secondary me-1"
      :disabled="!withDocument.length"
      @click="open(withDocument[0])"
    >
      근거 위치 ({{ locations.length }})
    </button>
    <template v-else>
      <div v-if="title" class="fw-semibold mb-1">{{ title }}</div>
      <p v-if="!locations.length" class="small text-muted mb-0">기록된 근거 위치가 없습니다.</p>
      <ul v-else class="list-unstyled small mb-0">
        <li v-for="(l, i) in locations" :key="i" class="mb-1">
          <button
            type="button"
            class="btn btn-link btn-sm p-0 text-start"
            :disabled="!l.document_id"
            :title="statusInfo(l).reason"
            @click="open(l)"
          >
            {{ label(l) }}
          </button>
          <span class="ms-1"><LocationStatus :location="l" /></span>
        </li>
      </ul>
    </template>

    <Teleport to="body">
      <DocumentOffcanvas
        :document-id="current?.document_id ?? null"
        :kind="current?.role === 'CURRENT_COMPANY_REFERENCE' ? 'current_reference' : 'reference'"
        :context-title="title || '수동 확인한 근거 위치'"
        :context-text="current ? fieldsText(current) : ''"
        :location="current"
        :locations="siblings"
        @close="current = null"
      />
    </Teleport>
  </div>
</template>
