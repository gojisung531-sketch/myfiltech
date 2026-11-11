<script setup>
// 긴 서술문을 문단·목록으로 표시한다(내용 불변). 줄바꿈이 없는 짧은 문장은 그대로 한 문단이다.
import { computed } from 'vue'

import { splitCandidateValues, toBlocks } from '@/utils/readableText'

const props = defineProps({
  text: { type: String, default: '' },
  // 'candidates': '; 비교 후보 …' 구분 문자열을 후보별 항목으로 나눈다.
  mode: { type: String, default: 'text' },
})

const blocks = computed(() => {
  if (props.mode === 'candidates') {
    const items = splitCandidateValues(props.text)
    if (items.length >= 2) return [{ type: 'list', items }]
  }
  return toBlocks(props.text)
})
</script>

<template>
  <div class="readable">
    <template v-for="(b, i) in blocks" :key="i">
      <div v-if="b.type === 'heading'" class="readable-heading">{{ b.text }}</div>
      <ul v-else-if="b.type === 'list'" class="readable-list">
        <li v-for="(item, j) in b.items" :key="j">{{ item }}</li>
      </ul>
      <p v-else class="readable-p">
        <template v-for="(line, j) in b.lines" :key="j"
          ><span class="readable-line">{{ line }}</span>
        </template>
      </p>
    </template>
  </div>
</template>

<style scoped>
.readable {
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.readable-p {
  margin: 0 0 0.45rem;
}
.readable-line {
  display: block;
}
.readable-line + .readable-line {
  margin-top: 0.2rem;
}
.readable-heading {
  margin: 0.6rem 0 0.25rem;
  font-weight: 600;
}
.readable-list {
  margin: 0 0 0.45rem;
  padding-left: 1.2rem;
}
.readable-list li {
  margin-bottom: 0.2rem;
}
.readable > :last-child {
  margin-bottom: 0;
}
</style>
