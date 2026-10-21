<script setup>
import { onMounted, ref } from 'vue'

import { listDrafts } from '@/api/drafts'
import { formatDateTime } from '@/utils/format'

const props = defineProps({
  bid: { type: Object, required: true },
  reviewing: { type: Boolean, default: false },
  downloading: { type: Boolean, default: false },
})
const emit = defineEmits(['toggle', 'download'])

const drafts = ref([])
onMounted(async () => {
  drafts.value = await listDrafts(props.bid.id).catch(() => [])
})
</script>

<template>
  <div class="card">
    <div class="card-body">
      <h2 class="h6">검토 결과 확인</h2>
      <p class="small text-muted">
        초안을 열어 수정·저장하고 PDF로 내려받으세요. 검토를 마쳤으면 확인 완료로 표시합니다
        (대시보드의 확인/미확인 건수에 반영).
      </p>
      <dl class="row small">
        <dt class="col-sm-3">판정 요약</dt>
        <dd class="col-sm-9">
          <template v-if="bid.verdict_counts?.total">
            충족 {{ bid.verdict_counts.MET }} · 보완 필요
            {{ bid.verdict_counts.NEEDS_SUPPLEMENT }} · 확인 필요
            {{ bid.verdict_counts.NEEDS_CONFIRMATION }} · HIGH 위험 {{ bid.verdict_counts.HIGH }}
          </template>
          <span v-else class="text-muted">판정 전</span>
        </dd>
        <dt class="col-sm-3">담당자 수정</dt>
        <dd class="col-sm-9">{{ bid.modified_evaluation_count }}건</dd>
        <dt class="col-sm-3">확인 상태</dt>
        <dd class="col-sm-9">
          <template v-if="bid.review_status === 'REVIEWED'">
            확인 완료 — {{ bid.reviewed_by_name }} ({{ formatDateTime(bid.reviewed_at) }})
          </template>
          <template v-else>미확인</template>
        </dd>
      </dl>
      <h3 class="h6 mt-3">초안</h3>
      <ul class="list-group mb-3">
        <li
          v-for="d in drafts"
          :key="d.doc_type"
          class="list-group-item d-flex align-items-center small"
        >
          <span class="me-auto">
            {{ d.doc_type_label }}
            <template v-if="d.latest">
              — v{{ d.latest.version }} · {{ d.latest.status_label }}
              <span v-if="d.latest.is_modified" class="badge bg-secondary ms-1">수정됨</span>
            </template>
            <span v-else class="text-muted"> — 미생성 (통합 PDF에는 규칙 기반 내용으로 포함)</span>
          </span>
          <router-link
            v-if="d.latest"
            :to="`/bids/${bid.id}/drafts/${d.doc_type}`"
            class="btn btn-sm btn-outline-primary"
            >편집</router-link
          >
        </li>
      </ul>
      <button
        class="btn btn-outline-secondary me-2"
        :disabled="downloading"
        @click="emit('download')"
      >
        <i class="bi bi-file-earmark-pdf me-1"></i>통합 보고서 PDF
      </button>
      <button
        class="btn"
        :class="bid.review_status === 'REVIEWED' ? 'btn-outline-secondary' : 'btn-success'"
        :disabled="reviewing"
        @click="emit('toggle')"
      >
        {{ bid.review_status === 'REVIEWED' ? '확인 취소' : '확인 완료' }}
      </button>
    </div>
  </div>
</template>
