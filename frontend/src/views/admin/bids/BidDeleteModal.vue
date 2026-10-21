<script setup>
// Bid deletion asks for the bid title (specs/04 §3.3).
import { ref, watch } from 'vue'

import BaseModal from '@/components/BaseModal.vue'

const props = defineProps({ bid: { type: Object, default: null } })
const emit = defineEmits(['confirm', 'cancel'])

const typed = ref('')
const busy = ref(false)
watch(
  () => props.bid,
  () => {
    typed.value = ''
    busy.value = false
  },
)

function confirm() {
  busy.value = true
  emit('confirm', props.bid)
}
</script>

<template>
  <BaseModal :show="!!bid" title="공고 삭제" @close="emit('cancel')">
    <p class="small">
      공고와 첨부·품목·요구사항·판정·초안이 모두 삭제되며 되돌릴 수 없습니다. 확인을 위해 공고명을
      입력하세요.
    </p>
    <p class="small fw-semibold user-select-all">{{ bid?.title }}</p>
    <input v-model="typed" class="form-control form-control-sm" aria-label="공고명 확인" />
    <template #footer>
      <button class="btn btn-secondary" @click="emit('cancel')">취소</button>
      <button class="btn btn-danger" :disabled="typed !== bid?.title || busy" @click="confirm">
        삭제
      </button>
    </template>
  </BaseModal>
</template>
