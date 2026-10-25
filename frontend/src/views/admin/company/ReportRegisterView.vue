<script setup>
// 검토 대기 관리대장 조회 (읽기 전용). 정식 시험성적서/제품 자료가 아니며 판정에 쓰이기 전 자료다.
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { getRegisterVersion, listRegisterRows, listRegisterVersions } from '@/api/reportRegister'
import BaseModal from '@/components/BaseModal.vue'
import CompanyNav from '@/components/CompanyNav.vue'
import EmptyState from '@/components/EmptyState.vue'
import { errorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/format'
import { listText, options, OWNERSHIP, REVIEW_STATUS, TEST_TARGET } from '@/utils/reportRegister'

import ReportRegisterRowDetail from './ReportRegisterRowDetail.vue'

const PAGE_SIZE = 20

const versions = ref([])
const versionsLoading = ref(true)
const versionsError = ref('')
const versionId = ref(null)
const version = ref(null) // 선택 버전 상세(시트/검토상태 집계)
const versionError = ref('')

const rows = ref([])
const count = ref(null) // 현재 검색/필터 결과 수 (null = 아직 모름/실패)
const page = ref(1)
const rowsLoading = ref(false)
const rowsError = ref('')
const filters = reactive({
  q: '',
  sheet_name: '',
  review_status: '',
  ownership: '',
  test_target: '',
})

// 발행일: 'YYYY-MM-DDT00:00:00' 형태만 날짜로 줄여 보여 주고, 다른 값은 서버 값 그대로 둔다.
function dateText(value) {
  const shown = listText(value)
  return shown.empty ? shown.text : shown.text.replace(/T00:00:00$/, '')
}

const detailId = ref(null)
let opener = null
let rowsSeq = 0
let versionSeq = 0
let timer = null

const hasFilters = computed(() => Object.values(filters).some((v) => v !== ''))
const sheetOptions = computed(() =>
  Object.entries(version.value?.sheet_counts || {}).map(([name, n]) => ({
    value: name,
    label: `${name} (${n})`,
  })),
)
const lastPage = computed(() => Math.max(1, Math.ceil((count.value || 0) / PAGE_SIZE)))

// 버전 목록도 페이지네이션된 응답이라 next가 없을 때까지 읽는다.
async function loadVersions() {
  versionsLoading.value = true
  versionsError.value = ''
  try {
    const all = []
    let pageNo = 1
    for (;;) {
      const res = await listRegisterVersions({ page: pageNo, page_size: 200 })
      all.push(...res.results)
      if (!res.next || pageNo >= 20) break
      pageNo += 1
    }
    versions.value = all
    versionId.value = all.length ? all[all.length - 1].id : null
    if (!all.length) {
      version.value = null
      rows.value = []
      count.value = null
    }
  } catch (err) {
    versionsError.value = errorMessage(err, '관리대장 버전을 불러오지 못했습니다.')
  } finally {
    versionsLoading.value = false
  }
}

async function loadVersion() {
  const mine = ++versionSeq
  version.value = null
  versionError.value = ''
  if (!versionId.value) return
  try {
    const result = await getRegisterVersion(versionId.value)
    if (mine === versionSeq) version.value = result
  } catch (err) {
    if (mine === versionSeq)
      versionError.value = errorMessage(err, '버전 요약을 불러오지 못했습니다.')
  }
}

async function loadRows() {
  const mine = ++rowsSeq
  if (!versionId.value) return
  rowsLoading.value = true
  rowsError.value = ''
  try {
    const params = { file_version: versionId.value, page: page.value }
    for (const [key, value] of Object.entries(filters)) if (value !== '') params[key] = value
    const res = await listRegisterRows(params)
    if (mine !== rowsSeq) return
    rows.value = res.results
    count.value = res.count
  } catch (err) {
    if (mine !== rowsSeq) return
    rows.value = []
    count.value = null // 실패를 0건으로 보이지 않게 한다.
    rowsError.value = errorMessage(err, '관리대장 행을 불러오지 못했습니다.')
  } finally {
    if (mine === rowsSeq) rowsLoading.value = false
  }
}

onMounted(loadVersions)

// 버전이 바뀌면 필터를 비우고 1쪽부터 다시 읽는다.
watch(versionId, () => {
  for (const key of Object.keys(filters)) filters[key] = ''
  page.value = 1
  detailId.value = null
  loadVersion()
  loadRows()
})

watch(filters, () => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    page.value = 1
    loadRows()
  }, 300)
})
onBeforeUnmount(() => {
  clearTimeout(timer)
  rowsSeq += 1
  versionSeq += 1
  document.removeEventListener('keydown', onKey)
})

function resetFilters() {
  for (const key of Object.keys(filters)) filters[key] = ''
}

function goPage(delta) {
  page.value += delta
  loadRows()
}

function openDetail(row, event) {
  opener = event?.currentTarget || null
  detailId.value = row.id
  document.addEventListener('keydown', onKey)
}
function closeDetail() {
  detailId.value = null
  document.removeEventListener('keydown', onKey)
  const target = opener
  opener = null
  if (target && typeof target.focus === 'function') setTimeout(() => target.focus(), 0)
}
function onKey(event) {
  if (event.key === 'Escape') closeDetail()
}
</script>

<template>
  <div>
    <CompanyNav />

    <div class="d-flex flex-wrap align-items-baseline gap-2 mb-3">
      <h2 class="h5 mb-0">관리대장 검토</h2>
      <span class="small text-muted">검토 대기 자료 · 판정 자료 반영 전 · 읽기 전용</span>
    </div>

    <div v-if="versionsLoading" class="text-center py-5"><span class="spinner-border"></span></div>
    <div
      v-else-if="versionsError"
      class="alert alert-danger d-flex align-items-center gap-2"
      role="alert"
    >
      <i class="bi bi-exclamation-octagon"></i>
      <span class="flex-grow-1">{{ versionsError }}</span>
      <button class="btn btn-sm btn-outline-secondary" @click="loadVersions">다시 시도</button>
    </div>
    <EmptyState
      v-else-if="!versions.length"
      icon="bi-journal"
      message="등록된 관리대장 버전이 없습니다."
    />

    <template v-else>
      <div class="card mb-3">
        <div class="card-body">
          <div class="row g-3 align-items-start">
            <div class="col-md-5">
              <label class="form-label small mb-1" for="rr-version">관리대장 파일 버전</label>
              <select id="rr-version" v-model="versionId" class="form-select form-select-sm">
                <option v-for="v in versions" :key="v.id" :value="v.id">
                  #{{ v.id }} · {{ v.display_name }} · {{ formatDateTime(v.created_at) }}
                </option>
              </select>
              <div class="small text-muted mt-1">버전 {{ versions.length }}개 중 선택</div>
            </div>
            <div class="col-md-7 small">
              <div v-if="versionError" class="alert alert-danger py-2 mb-0 d-flex gap-2">
                <span class="flex-grow-1">{{ versionError }}</span>
                <button class="btn btn-sm btn-outline-secondary" @click="loadVersion">
                  다시 시도
                </button>
              </div>
              <div v-else-if="!version" class="text-muted">
                <span class="spinner-border spinner-border-sm me-1"></span>요약을 불러오는 중
              </div>
              <dl v-else class="row mb-0">
                <dt class="col-sm-4 fw-normal text-muted">파일명</dt>
                <dd class="col-sm-8 text-break mb-1">{{ version.display_name }}</dd>
                <dt class="col-sm-4 fw-normal text-muted">저장된 행 수</dt>
                <dd class="col-sm-8 mb-1">{{ version.row_count }}행</dd>
                <dt class="col-sm-4 fw-normal text-muted">시트별</dt>
                <dd class="col-sm-8 mb-1">
                  <span v-for="(n, name) in version.sheet_counts" :key="name" class="me-3"
                    >{{ name }} {{ n }}</span
                  >
                  <span v-if="!Object.keys(version.sheet_counts).length" class="text-muted"
                    >없음</span
                  >
                </dd>
                <dt class="col-sm-4 fw-normal text-muted">검토 상태</dt>
                <dd class="col-sm-8 mb-0">
                  <span v-for="(n, st) in version.review_status_counts" :key="st" class="me-3"
                    >{{ REVIEW_STATUS[st] || st }} {{ n }}</span
                  >
                  <span v-if="!Object.keys(version.review_status_counts).length" class="text-muted"
                    >없음</span
                  >
                </dd>
              </dl>
            </div>
          </div>
        </div>
      </div>

      <div class="row g-2 mb-3">
        <div class="col-12 col-sm-6 col-lg-3">
          <input
            v-model="filters.q"
            class="form-control form-control-sm"
            placeholder="성적서번호·모델·시료명·시험규격·기관"
            aria-label="검색"
            maxlength="200"
          />
        </div>
        <div class="col-6 col-sm-auto">
          <select v-model="filters.sheet_name" class="form-select form-select-sm" aria-label="시트">
            <option value="">시트: 전체</option>
            <option v-for="o in sheetOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </div>
        <div class="col-6 col-sm-auto">
          <select
            v-model="filters.review_status"
            class="form-select form-select-sm"
            aria-label="검토 상태"
          >
            <option value="">검토: 전체</option>
            <option v-for="o in options(REVIEW_STATUS)" :key="o.value" :value="o.value">
              {{ o.label }}
            </option>
          </select>
        </div>
        <div class="col-6 col-sm-auto">
          <select
            v-model="filters.ownership"
            class="form-select form-select-sm"
            aria-label="소유 구분"
          >
            <option value="">소유: 전체</option>
            <option v-for="o in options(OWNERSHIP)" :key="o.value" :value="o.value">
              {{ o.label }}
            </option>
          </select>
        </div>
        <div class="col-6 col-sm-auto">
          <select
            v-model="filters.test_target"
            class="form-select form-select-sm"
            aria-label="시험 대상"
          >
            <option value="">시험 대상: 전체</option>
            <option v-for="o in options(TEST_TARGET)" :key="o.value" :value="o.value">
              {{ o.label }}
            </option>
          </select>
        </div>
        <div v-if="hasFilters" class="col-auto">
          <button class="btn btn-sm btn-outline-secondary" @click="resetFilters">
            <i class="bi bi-arrow-counterclockwise me-1"></i>초기화
          </button>
        </div>
      </div>

      <div v-if="rowsError" class="alert alert-danger d-flex align-items-center gap-2" role="alert">
        <i class="bi bi-exclamation-octagon"></i>
        <span class="flex-grow-1">{{ rowsError }}</span>
        <button class="btn btn-sm btn-outline-secondary" @click="loadRows">다시 시도</button>
      </div>

      <div class="card">
        <div class="card-header small text-muted">
          <template v-if="rowsError">목록을 불러오지 못했습니다.</template>
          <template v-else-if="count === null">불러오는 중</template>
          <template v-else>
            {{ hasFilters ? '검색·필터 결과' : '전체' }} {{ count }}행
            <template v-if="version"> · 이 버전 저장 {{ version.row_count }}행</template>
          </template>
        </div>
        <div class="table-responsive">
          <table class="table table-hover table-sm align-middle mb-0 register-table">
            <thead>
              <tr>
                <th>시트 · 원본 행</th>
                <th>성적서번호</th>
                <th>모델</th>
                <th>시료명</th>
                <th>시험규격</th>
                <th>발행일 · 기관</th>
                <th>검토</th>
                <th>경고</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="rowsLoading">
                <td colspan="9" class="text-center py-4">
                  <span class="spinner-border spinner-border-sm"></span>
                </td>
              </tr>
              <tr v-else-if="rowsError">
                <td colspan="9">
                  <EmptyState
                    icon="bi-exclamation-triangle"
                    message="서버에서 목록을 받지 못했습니다."
                  />
                </td>
              </tr>
              <tr v-else-if="!rows.length">
                <td colspan="9">
                  <EmptyState
                    :message="
                      hasFilters
                        ? '조건에 맞는 행이 없습니다. 검색어나 필터를 바꿔 보세요.'
                        : '이 버전에 저장된 행이 없습니다.'
                    "
                  >
                    <button
                      v-if="hasFilters"
                      class="btn btn-sm btn-outline-secondary"
                      @click="resetFilters"
                    >
                      필터 초기화
                    </button>
                  </EmptyState>
                </td>
              </tr>
              <tr v-for="r in rows" v-else :key="r.id">
                <td class="text-nowrap">{{ r.source.sheet }} · {{ r.source.row }}행</td>
                <td class="text-break">
                  <span
                    :class="{ 'text-muted text-nowrap': listText(r.summary.report_no).empty }"
                    >{{ listText(r.summary.report_no).text }}</span
                  >
                </td>
                <td class="text-break">
                  <span
                    :class="{ 'text-muted text-nowrap': listText(r.summary.model).empty }"
                    :title="
                      listText(r.summary.model).empty
                        ? '목록 응답으로는 원본 칸이 비어 있는지 열이 없는지 구분할 수 없습니다. 상세에서 확인하세요.'
                        : ''
                    "
                    >{{ listText(r.summary.model).text }}</span
                  >
                </td>
                <td class="text-break">
                  <span
                    :class="{ 'text-muted text-nowrap': listText(r.summary.sample_name).empty }"
                    >{{ listText(r.summary.sample_name).text }}</span
                  >
                </td>
                <td class="text-break">
                  <span
                    :class="{ 'text-muted text-nowrap': listText(r.summary.test_standard).empty }"
                    >{{ listText(r.summary.test_standard).text }}</span
                  >
                </td>
                <td class="text-break small">
                  <span
                    :class="{ 'text-muted text-nowrap': listText(r.summary.issue_date).empty }"
                    >{{ dateText(r.summary.issue_date) }}</span
                  >
                  <div :class="{ 'text-muted text-nowrap': listText(r.summary.lab_name).empty }">
                    {{ listText(r.summary.lab_name).text }}
                  </div>
                </td>
                <td class="text-nowrap small">
                  <span class="badge bg-secondary">{{
                    REVIEW_STATUS[r.review.review_status] || r.review.review_status
                  }}</span>
                  <div class="text-muted mt-1">
                    소유 {{ OWNERSHIP[r.review.ownership] || r.review.ownership }} · 시험 대상
                    {{ TEST_TARGET[r.review.test_target] || r.review.test_target }}
                  </div>
                </td>
                <td class="small">
                  <span
                    v-if="r.warning_count"
                    class="badge bg-warning"
                    :title="r.warning_codes.join(', ')"
                    >경고 {{ r.warning_count }}</span
                  >
                  <span v-else class="text-muted">없음</span>
                </td>
                <td class="text-end">
                  <button
                    class="btn btn-sm btn-outline-secondary text-nowrap"
                    :aria-label="`${r.source.sheet} ${r.source.row}행 상세`"
                    @click="openDetail(r, $event)"
                  >
                    상세
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="count && count > PAGE_SIZE" class="card-footer d-flex justify-content-end gap-2">
          <button
            class="btn btn-sm btn-outline-secondary"
            :disabled="page === 1 || rowsLoading"
            @click="goPage(-1)"
          >
            이전
          </button>
          <span class="small align-self-center">{{ page }} / {{ lastPage }}</span>
          <button
            class="btn btn-sm btn-outline-secondary"
            :disabled="page >= lastPage || rowsLoading"
            @click="goPage(1)"
          >
            다음
          </button>
        </div>
      </div>
    </template>

    <BaseModal :show="detailId !== null" title="관리대장 행 상세" size="xl" @close="closeDetail">
      <ReportRegisterRowDetail v-if="detailId !== null" :row-id="detailId" @close="closeDetail" />
      <template #footer>
        <button class="btn btn-secondary" @click="closeDetail">닫기</button>
      </template>
    </BaseModal>
  </div>
</template>

<style scoped>
.register-table {
  min-width: 62rem;
}
.register-table thead th {
  background: var(--ft-bg);
  white-space: nowrap;
  font-size: 0.85rem;
}
</style>
