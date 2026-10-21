<script setup>
// 등록 → 문서 읽기 → 요구조건 추출 → 분석 완료. 서버가 알려 준 실제 상태만 반영한다.
import { computed } from 'vue'

const props = defineProps({ bid: { type: Object, required: true } })

const READ_OK = ['PARSED', 'EXTRACTING', 'EXTRACTED', 'REVIEWED']
const READ_BAD = ['FAILED', 'NEEDS_OCR']

const steps = computed(() => {
  const atts = props.bid.attachments || []
  const status = props.bid.processing_status
  const bad = atts.filter((a) => READ_BAD.includes(a.status))
  const waiting = atts.filter((a) => !READ_OK.includes(a.status) && !READ_BAD.includes(a.status))

  let read
  if (!atts.length) read = { state: 'wait', note: '첨부 없음' }
  else if (bad.length) read = { state: 'warn', note: `읽기 실패·확인 필요 ${bad.length}건` }
  else if (waiting.length) read = { state: 'wait', note: `대기·처리 중 ${waiting.length}건` }
  else read = { state: 'done', note: `${atts.length}건 읽음` }

  const extractDone = ['EXTRACTED', 'EVALUATING', 'EVALUATED'].includes(status)
  const extract =
    status === 'FAILED'
      ? { state: 'warn', note: '추출 실패' }
      : status === 'EXTRACTING'
        ? { state: 'run', note: '진행 중' }
        : extractDone
          ? { state: 'done', note: '완료' }
          : { state: 'wait', note: '미실행' }

  const analysis =
    status === 'EVALUATING'
      ? { state: 'run', note: '진행 중' }
      : status === 'EVALUATED'
        ? { state: 'done', note: '완료' }
        : { state: 'wait', note: '미실행' }

  return [
    { label: '등록', state: 'done', note: '저장됨' },
    { label: '문서 읽기', ...read },
    { label: '요구조건 추출', ...extract },
    { label: '분석', ...analysis },
  ]
})
const ICONS = {
  done: 'bi-check-circle-fill',
  warn: 'bi-exclamation-triangle-fill',
  run: 'bi-arrow-repeat',
  wait: 'bi-circle',
}
</script>

<template>
  <ol class="steps list-unstyled mb-3" aria-label="처리 단계">
    <li v-for="s in steps" :key="s.label" :class="`step-${s.state}`">
      <i :class="['bi', ICONS[s.state]]"></i>
      <span class="fw-semibold">{{ s.label }}</span>
      <span class="small">{{ s.note }}</span>
    </li>
  </ol>
</template>

<style scoped>
.steps {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: 0.5rem;
}
.steps li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--ft-border);
  border-radius: 0.4rem;
  background: var(--ft-surface);
  color: var(--ft-muted);
}
.step-done {
  color: var(--ft-ok-fg) !important;
  background: var(--ft-ok-bg) !important;
  border-color: var(--ft-ok-fg) !important;
}
.step-warn {
  color: var(--ft-warn-fg) !important;
  background: var(--ft-warn-bg) !important;
  border-color: var(--ft-warn-fg) !important;
}
.step-run {
  color: var(--ft-check-fg) !important;
  background: var(--ft-check-bg) !important;
  border-color: var(--ft-check-fg) !important;
}
</style>
