<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import { products } from '@/api/company'
import BaseModal from '@/components/BaseModal.vue'
import CompanyNav from '@/components/CompanyNav.vue'
import EntityForm from '@/components/EntityForm.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { displayValue, formatDate, formatNumber, productDimension } from '@/utils/format'

import { PRODUCT_FIELDS } from './productFields'

const route = useRoute()
const toast = useToastStore()
const product = ref(null)
const form = ref(null)
const editor = reactive({ show: false, model: {}, error: '', saving: false })

const SPEC_ROWS = [
  ['형식', (p) => p.filter_type_label],
  ['용도', (p) => p.application],
  ['치수', productDimension],
  ['여재', (p) => p.media],
  ['프레임', (p) => p.frame_material],
  ['개스킷', (p) => p.gasket],
  ['정격 풍량', (p) => p.rated_airflow_m3h && `${formatNumber(p.rated_airflow_m3h)} m³/h`],
  ['초기 차압', (p) => p.initial_dp_pa && `${p.initial_dp_pa} Pa`],
  ['권장 최종 차압', (p) => p.final_dp_pa && `${p.final_dp_pa} Pa`],
  ['ISO 16890', (p) => p.iso16890_class],
  ['ISO 29461-1', (p) => p.iso29461_class],
  ['EN 1822', (p) => p.en1822_class],
  ['EN 779', (p) => p.en779_class],
  ['MERV', (p) => p.ashrae_merv],
  ['사용 온도', (p) => p.max_temp_c != null && `최고 ${p.max_temp_c} °C`],
  ['사용 습도', (p) => p.max_rh != null && `최대 ${p.max_rh} %RH`],
  ['난연', (p) => p.fire_rating],
  ['개정', (p) => p.revision],
]

const specs = computed(() =>
  product.value
    ? SPEC_ROWS.map(([label, fn]) => [label, displayValue(fn(product.value) || null)])
    : [],
)

async function load() {
  try {
    product.value = await products.get(route.params.id)
  } catch (err) {
    toast.error(errorMessage(err))
  }
}
onMounted(load)

function openEdit() {
  Object.assign(editor, { show: true, model: { ...product.value }, error: '' })
}

async function save() {
  let payload
  try {
    payload = form.value.collect()
  } catch (err) {
    editor.error = err.message
    return
  }
  editor.saving = true
  try {
    await products.update(product.value.id, payload)
    editor.show = false
    toast.success('제품 정보를 저장했습니다.')
    load()
  } catch (err) {
    editor.error = errorMessage(err)
  } finally {
    editor.saving = false
  }
}
</script>

<template>
  <div>
    <CompanyNav />
    <div v-if="!product" class="text-center py-5"><span class="spinner-border"></span></div>
    <template v-else>
      <div class="d-flex align-items-center mb-3">
        <router-link to="/admin/products" class="btn btn-sm btn-outline-secondary me-2">
          <i class="bi bi-arrow-left"></i>
        </router-link>
        <h2 class="h5 mb-0 me-auto">
          {{ product.model_no }} <span class="text-muted">{{ product.name }}</span>
        </h2>
        <button class="btn btn-sm btn-primary" @click="openEdit">수정</button>
      </div>

      <div class="row g-4">
        <div class="col-lg-6">
          <div class="card h-100">
            <div class="card-header fw-semibold">주요 사양</div>
            <table class="table table-sm mb-0">
              <tbody>
                <tr v-for="[label, value] in specs" :key="label">
                  <th class="text-muted fw-normal w-25">{{ label }}</th>
                  <td>{{ value }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="col-lg-6">
          <div class="card mb-4">
            <div class="card-header fw-semibold">풍량–초기차압 특성</div>
            <table v-if="product.airflow_dp_curve.length" class="table table-sm mb-0 text-end">
              <tbody>
                <tr>
                  <th class="text-start text-muted fw-normal">풍량 (m³/h)</th>
                  <td v-for="pt in product.airflow_dp_curve" :key="pt.airflow_m3h">
                    {{ formatNumber(pt.airflow_m3h) }}
                  </td>
                </tr>
                <tr>
                  <th class="text-start text-muted fw-normal">초기 차압 (Pa)</th>
                  <td v-for="pt in product.airflow_dp_curve" :key="pt.airflow_m3h">
                    {{ pt.dp_pa }}
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="card-body text-muted small">데이터 없음</div>
          </div>
          <div v-if="product.frame_options.length" class="card mb-4">
            <div class="card-header fw-semibold">프레임 옵션</div>
            <ul class="list-group list-group-flush">
              <li
                v-for="opt in product.frame_options"
                :key="opt.model"
                class="list-group-item small"
              >
                {{ opt.material }} — {{ opt.model }}
                <span class="text-muted">({{ opt.note }})</span>
              </li>
            </ul>
          </div>
        </div>

        <div class="col-lg-6">
          <div class="card">
            <div class="card-header fw-semibold">
              시험성적서 ({{ product.test_reports.length }})
            </div>
            <table class="table table-sm mb-0">
              <thead>
                <tr>
                  <th>번호</th>
                  <th>규격</th>
                  <th>결과</th>
                  <th>발행일</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in product.test_reports" :key="r.id">
                  <td>{{ r.report_no }}</td>
                  <td>
                    {{ r.standard }}
                    <span v-if="r.is_obsolete_standard" class="badge bg-warning text-dark"
                      >폐지 규격</span
                    >
                  </td>
                  <td>{{ r.result_class }}</td>
                  <td>{{ formatDate(r.issue_date) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="col-lg-6">
          <div class="card">
            <div class="card-header fw-semibold">
              납품실적 ({{ product.delivery_records.length }})
            </div>
            <table class="table table-sm mb-0">
              <thead>
                <tr>
                  <th>시기</th>
                  <th>발주처</th>
                  <th>사업명</th>
                  <th>수량</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in product.delivery_records" :key="r.id">
                  <td>{{ r.delivered_ym }}</td>
                  <td>{{ r.client }}</td>
                  <td>
                    {{ r.project_name }}
                    <div v-if="r.notes" class="small text-muted">{{ r.notes }}</div>
                  </td>
                  <td class="text-nowrap">
                    <div
                      v-for="q in r.quantity.filter((q) => q.model === product.model_no)"
                      :key="q.model"
                    >
                      {{ formatNumber(q.qty) }} {{ q.unit }}
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>

    <BaseModal :show="editor.show" title="제품 수정" size="lg" @close="editor.show = false">
      <form id="product-form" @submit.prevent="save">
        <EntityForm
          ref="form"
          :fields="PRODUCT_FIELDS"
          :model-value="editor.model"
          id-prefix="product"
        />
        <div v-if="editor.error" class="alert alert-danger py-2 small mt-3 mb-0">
          {{ editor.error }}
        </div>
      </form>
      <template #footer>
        <button class="btn btn-secondary" @click="editor.show = false">취소</button>
        <button class="btn btn-primary" form="product-form" :disabled="editor.saving">저장</button>
      </template>
    </BaseModal>
  </div>
</template>
