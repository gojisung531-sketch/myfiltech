<script setup>
import { onMounted, ref } from 'vue'

import { listDrafts } from '@/api/drafts'
import { errorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/format'

const props = defineProps({
  bid: { type: Object, required: true },
  reviewing: { type: Boolean, default: false },
  downloading: { type: Boolean, default: false },
})
const emit = defineEmits(['toggle', 'download'])

const drafts = ref([])
const loading = ref(true)
const loadError = ref('')

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    drafts.value = await listDrafts(props.bid.id)
  } catch (err) {
    drafts.value = []
    loadError.value = errorMessage(err, '초안 목록을 불러오지 못했습니다.')
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<template>
  <div class="card">
    <div class="card-body">
      <h2 class="h6">검토 결과 확인</h2>
      <p class="small text-muted">
        초안을 열어 수정·저장할 수 있습니다. ‘검토 완료 표시’는 담당자가 검토했다는 내부
        표시이며(대시보드의 검토 건수에 반영), 원문 일치 검증·제출·법적 검토가 끝났다는 뜻이
        아닙니다. 이 화면에서 외부로 발송·제출되는 것은 없습니다.
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
        <dt class="col-sm-3">검토 상태</dt>
        <dd class="col-sm-9">
          <template v-if="bid.review_status === 'REVIEWED'">
            검토 완료 표시 — {{ bid.reviewed_by_name }} ({{ formatDateTime(bid.reviewed_at) }})
          </template>
          <template v-else>검토 전</template>
        </dd>
      </dl>

      <h3 class="h6 mt-3">저장된 초안</h3>
      <div v-if="loading" class="text-center py-3">
        <span class="spinner-border spinner-border-sm"></span>
      </div>
      <div v-else-if="loadError" class="alert alert-danger small d-flex gap-2 align-items-center">
        <span class="flex-grow-1">{{ loadError }}</span>
        <button class="btn btn-sm btn-outline-secondary" @click="load">다시 시도</button>
      </div>
      <ul v-else class="list-group mb-3">
        <li
          v-for="d in drafts"
          :key="d.doc_type"
          class="list-group-item d-flex flex-wrap align-items-center gap-2 small"
        >
          <span class="me-auto">
            {{ d.doc_type_label }}
            <template v-if="d.latest">
              — 최신 v{{ d.latest.version }} · {{ d.latest.status_label }}
              <span v-if="d.latest.is_modified" class="badge bg-info ms-1">담당자 수정본</span>
              <span class="badge bg-secondary ms-1">{{
                d.latest.used_llm ? 'LLM 보강' : '규칙 기반'
              }}</span>
            </template>
            <span v-else class="text-muted"> — 저장된 초안 없음</span>
          </span>
          <router-link
            v-if="d.latest"
            :to="`/bids/${bid.id}/drafts/${d.doc_type}`"
            class="btn btn-sm btn-outline-primary"
            >편집</router-link
          >
        </li>
      </ul>

      <div class="alert alert-secondary small">
        <strong>통합 보고서 PDF</strong>는 저장된 초안이 있는 문서는 그 최신 버전 내용을, 저장된
        초안이 없는 문서는 <em>저장하지 않은 규칙 기반 내용</em>을 즉석에서 만들어 함께 담습니다(LLM
        호출 없음). 따라서 ‘저장된 초안 원본’을 내려받는 것과 같지 않습니다. 각 초안의 PDF·XLSX는 ④
        초안 탭이나 편집 화면에서 받으세요.
      </div>
      <button
        class="btn btn-outline-secondary me-2"
        :disabled="downloading"
        @click="emit('download')"
      >
        <span v-if="downloading" class="spinner-border spinner-border-sm me-1"></span>
        <i v-else class="bi bi-file-earmark-pdf me-1"></i>통합 보고서 PDF
      </button>
      <button
        class="btn"
        :class="bid.review_status === 'REVIEWED' ? 'btn-outline-secondary' : 'btn-primary'"
        :disabled="reviewing"
        @click="emit('toggle')"
      >
        {{ bid.review_status === 'REVIEWED' ? '검토 표시 취소' : '검토 완료 표시' }}
      </button>
    </div>
  </div>
</template>
