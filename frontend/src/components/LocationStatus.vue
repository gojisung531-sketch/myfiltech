<script setup>
// 근거 위치의 확인 상태를 한 줄로 보여 준다. 서버가 준 status·kind만 번역하며 새 판단을 하지 않는다.
import { computed } from 'vue'

import { kindLabel, statusInfo } from '@/utils/evidenceLocation'

const props = defineProps({ location: { type: Object, default: null } })

const info = computed(() => statusInfo(props.location))
const kind = computed(() => {
  const l = props.location
  if (!l) return ''
  if (l.location_kind && l.location_kind !== 'NONE')
    return kindLabel(l.location_kind, l.file_format)
  // 인용은 못 찾았어도 PDF 물리 페이지가 확인된 경우
  if (l.physical_page_verified && l.declared_page) return `PDF 물리 p.${l.declared_page} 확인`
  if (l.status === 'MULTIPLE_MATCHES') return `후보 ${l.candidates?.length || 0}곳`
  return ''
})
</script>

<template>
  <span class="loc-status">
    <span class="badge" :class="info.tone">{{ info.label }}</span>
    <span v-if="kind" class="text-muted ms-1">{{ kind }}</span>
  </span>
</template>
