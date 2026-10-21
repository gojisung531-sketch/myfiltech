<script setup>
// Fit score and its rule breakdown (specs/08 §6.2).
import { computed } from 'vue'

const props = defineProps({ bid: { type: Object, required: true } })

const COMPONENTS = {
  product_type: '취급 제품 형식',
  power_plant: '발전소 공고',
  qualification: '자격 요건',
  spec_coverage: '시험규격 대응',
}
const VERDICTS = { MET: '충족', NEEDS_SUPPLEMENT: '보완 필요', NEEDS_CONFIRMATION: '확인 필요' }

const rows = computed(() =>
  Object.entries(COMPONENTS)
    .filter(([key]) => props.bid.fit_breakdown?.[key])
    .map(([key, label]) => ({ key, label, ...props.bid.fit_breakdown[key] })),
)
const ruleScore = computed(() => Math.round(rows.value.reduce((sum, r) => sum + r.points, 0)))
</script>

<template>
  <div class="card">
    <div class="card-header fw-semibold">적합도</div>
    <div class="card-body small">
      <template v-if="bid.fit_score !== null">
        <div class="d-flex align-items-baseline gap-2 mb-2">
          <span class="display-6 fw-semibold">{{ bid.fit_score }}</span>
          <span class="text-muted">/ 100 (규칙 점수 {{ ruleScore }})</span>
        </div>
        <table class="table table-sm mb-2">
          <tbody>
            <tr v-for="row in rows" :key="row.key">
              <td>
                {{ row.label }}
                <div v-if="typeof row.detail === 'string'" class="text-muted">{{ row.detail }}</div>
                <ul v-else-if="row.detail?.length" class="list-unstyled text-muted mb-0">
                  <li v-for="d in row.detail" :key="d.title">
                    {{ d.title }}: {{ VERDICTS[d.verdict] || 'LLM 판정 대기' }}
                  </li>
                </ul>
              </td>
              <td class="text-end text-nowrap">{{ row.points }} / {{ row.weight }}</td>
            </tr>
          </tbody>
        </table>
        <p class="mb-0" style="white-space: pre-line">{{ bid.fit_reason }}</p>
      </template>
      <p v-else class="text-muted mb-0">추출을 실행하면 적합도가 계산됩니다.</p>
      <div v-if="bid.placeholders?.length" class="alert alert-warning py-2 mt-3 mb-0">
        공고에서 찾지 못한 요구사항 카테고리가 있어 ‘확인 필요’ 항목을 추가했습니다.
      </div>
    </div>
  </div>
</template>
