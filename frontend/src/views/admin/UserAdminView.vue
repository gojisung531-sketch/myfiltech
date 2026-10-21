<script setup>
import { onMounted, reactive, ref, watch } from 'vue'

import { createUser, deactivateUser, listUsers, resetPassword, updateUser } from '@/api/users'
import BaseModal from '@/components/BaseModal.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'

const ROLE_LABELS = { ADMIN: '관리자', BID_MANAGER: '입찰담당자' }

const auth = useAuthStore()
const toast = useToastStore()

const users = ref([])
const count = ref(0)
const page = ref(1)
const filters = reactive({ role: '', is_active: 'true' })
const loading = ref(false)

const emptyForm = () => ({
  username: '',
  password: '',
  display_name: '',
  department: '',
  email: '',
  phone: '',
  role: 'BID_MANAGER',
  is_active: true,
})

const editor = reactive({ show: false, mode: 'create', id: null, form: emptyForm(), error: '' })
const reset = reactive({ show: false, user: null, password: '', error: '' })
const confirm = reactive({ show: false, user: null })
const saving = ref(false)

async function load() {
  loading.value = true
  try {
    const params = { page: page.value }
    if (filters.role) params.role = filters.role
    if (filters.is_active) params.is_active = filters.is_active
    const data = await listUsers(params)
    users.value = data.results
    count.value = data.count
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    loading.value = false
  }
}

watch(filters, () => {
  page.value = 1
  load()
})
onMounted(load)

function openCreate() {
  Object.assign(editor, { show: true, mode: 'create', id: null, form: emptyForm(), error: '' })
}

function openEdit(user) {
  Object.assign(editor, {
    show: true,
    mode: 'edit',
    id: user.id,
    form: { ...emptyForm(), ...user, password: '' },
    error: '',
  })
}

async function saveUser() {
  saving.value = true
  editor.error = ''
  try {
    const { username, password, ...rest } = editor.form
    if (editor.mode === 'create') {
      await createUser({ username, password, ...rest })
      toast.success(`사용자 '${username}'를 추가했습니다.`)
    } else {
      const { display_name, department, email, phone, role, is_active } = rest
      await updateUser(editor.id, { display_name, department, email, phone, role, is_active })
      toast.success('사용자 정보를 저장했습니다.')
    }
    editor.show = false
    load()
  } catch (err) {
    editor.error = errorMessage(err)
  } finally {
    saving.value = false
  }
}

function openConfirm(user) {
  Object.assign(confirm, { show: true, user })
}

function goPage(delta) {
  page.value += delta
  load()
}

function openReset(user) {
  Object.assign(reset, { show: true, user, password: '', error: '' })
}

async function doReset() {
  saving.value = true
  reset.error = ''
  try {
    await resetPassword(reset.user.id, reset.password)
    toast.success(`'${reset.user.username}' 비밀번호를 초기화했습니다.`)
    reset.show = false
  } catch (err) {
    reset.error = errorMessage(err)
  } finally {
    saving.value = false
  }
}

async function doDeactivate() {
  saving.value = true
  try {
    await deactivateUser(confirm.user.id)
    toast.success(`'${confirm.user.username}'를 비활성화했습니다.`)
    confirm.show = false
    load()
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    saving.value = false
  }
}

async function activate(user) {
  try {
    await updateUser(user.id, { is_active: true })
    toast.success(`'${user.username}'를 활성화했습니다.`)
    load()
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString('ko-KR', { hour12: false }) : '-'
}
</script>

<template>
  <div>
    <div class="d-flex align-items-center mb-3">
      <h1 class="h4 mb-0 me-auto">사용자 관리</h1>
      <button class="btn btn-primary" @click="openCreate">
        <i class="bi bi-person-plus me-1"></i>사용자 추가
      </button>
    </div>

    <div class="row g-2 mb-3">
      <div class="col-auto">
        <select v-model="filters.role" class="form-select form-select-sm" aria-label="역할">
          <option value="">전체 역할</option>
          <option value="BID_MANAGER">입찰담당자</option>
          <option value="ADMIN">관리자</option>
        </select>
      </div>
      <div class="col-auto">
        <select v-model="filters.is_active" class="form-select form-select-sm" aria-label="상태">
          <option value="true">활성</option>
          <option value="false">비활성</option>
          <option value="">전체</option>
        </select>
      </div>
    </div>

    <div class="card">
      <div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
          <thead class="table-light">
            <tr>
              <th>아이디</th>
              <th>이름</th>
              <th>역할</th>
              <th>부서</th>
              <th>이메일</th>
              <th>연락처</th>
              <th>최근 로그인</th>
              <th class="text-end">작업</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="8" class="text-center py-4">
                <span class="spinner-border spinner-border-sm"></span>
              </td>
            </tr>
            <tr v-else-if="!users.length">
              <td colspan="8" class="text-center text-muted py-4">사용자가 없습니다.</td>
            </tr>
            <tr
              v-for="user in users"
              v-else
              :key="user.id"
              :class="{ 'text-muted': !user.is_active }"
            >
              <td>
                {{ user.username }}
                <span v-if="!user.is_active" class="badge bg-secondary ms-1">비활성</span>
                <span v-if="user.must_change_password" class="badge bg-warning text-dark ms-1">
                  초기 비밀번호
                </span>
              </td>
              <td>{{ user.display_name || '-' }}</td>
              <td>
                <span :class="['badge', user.role === 'ADMIN' ? 'bg-dark' : 'bg-primary']">
                  {{ ROLE_LABELS[user.role] }}
                </span>
              </td>
              <td>{{ user.department || '-' }}</td>
              <td>{{ user.email || '-' }}</td>
              <td>{{ user.phone || '-' }}</td>
              <td class="small">{{ formatDate(user.last_login) }}</td>
              <td class="text-end text-nowrap">
                <button class="btn btn-sm btn-outline-secondary me-1" @click="openEdit(user)">
                  수정
                </button>
                <button class="btn btn-sm btn-outline-secondary me-1" @click="openReset(user)">
                  비밀번호 초기화
                </button>
                <button
                  v-if="user.is_active"
                  class="btn btn-sm btn-outline-danger"
                  :disabled="user.id === auth.user?.id"
                  @click="openConfirm(user)"
                >
                  비활성화
                </button>
                <button v-else class="btn btn-sm btn-outline-success" @click="activate(user)">
                  활성화
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="count > 20" class="card-footer d-flex justify-content-end gap-2">
        <button class="btn btn-sm btn-outline-secondary" :disabled="page === 1" @click="goPage(-1)">
          이전
        </button>
        <span class="small align-self-center">{{ page }} / {{ Math.ceil(count / 20) }}</span>
        <button
          class="btn btn-sm btn-outline-secondary"
          :disabled="page * 20 >= count"
          @click="goPage(1)"
        >
          다음
        </button>
      </div>
    </div>

    <BaseModal
      :show="editor.show"
      :title="editor.mode === 'create' ? '사용자 추가' : '사용자 수정'"
      @close="editor.show = false"
    >
      <form id="user-form" @submit.prevent="saveUser">
        <div class="row g-3">
          <div class="col-6">
            <label class="form-label" for="u-username">아이디</label>
            <input
              id="u-username"
              v-model="editor.form.username"
              class="form-control"
              :disabled="editor.mode === 'edit'"
              required
            />
          </div>
          <div v-if="editor.mode === 'create'" class="col-6">
            <label class="form-label" for="u-password">초기 비밀번호</label>
            <input
              id="u-password"
              v-model="editor.form.password"
              type="password"
              class="form-control"
              autocomplete="new-password"
              required
            />
          </div>
          <div class="col-6">
            <label class="form-label" for="u-name">이름</label>
            <input id="u-name" v-model="editor.form.display_name" class="form-control" />
          </div>
          <div class="col-6">
            <label class="form-label" for="u-role">역할</label>
            <select id="u-role" v-model="editor.form.role" class="form-select">
              <option value="BID_MANAGER">입찰담당자</option>
              <option value="ADMIN">관리자</option>
            </select>
          </div>
          <div class="col-6">
            <label class="form-label" for="u-dept">부서</label>
            <input id="u-dept" v-model="editor.form.department" class="form-control" />
          </div>
          <div class="col-6">
            <label class="form-label" for="u-phone">연락처</label>
            <input id="u-phone" v-model="editor.form.phone" class="form-control" />
          </div>
          <div class="col-12">
            <label class="form-label" for="u-email">이메일</label>
            <input id="u-email" v-model="editor.form.email" type="email" class="form-control" />
          </div>
        </div>
        <div v-if="editor.error" class="alert alert-danger py-2 small mt-3 mb-0">
          {{ editor.error }}
        </div>
      </form>
      <template #footer>
        <button class="btn btn-secondary" @click="editor.show = false">취소</button>
        <button class="btn btn-primary" form="user-form" :disabled="saving">
          <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>저장
        </button>
      </template>
    </BaseModal>

    <BaseModal :show="reset.show" title="비밀번호 초기화" @close="reset.show = false">
      <form id="reset-form" @submit.prevent="doReset">
        <p class="small text-muted">
          '{{ reset.user?.username }}' 계정의 새 비밀번호를 입력하세요.
        </p>
        <input
          v-model="reset.password"
          type="password"
          class="form-control"
          autocomplete="new-password"
          aria-label="새 비밀번호"
          required
        />
        <div v-if="reset.error" class="alert alert-danger py-2 small mt-3 mb-0">
          {{ reset.error }}
        </div>
      </form>
      <template #footer>
        <button class="btn btn-secondary" @click="reset.show = false">취소</button>
        <button class="btn btn-primary" form="reset-form" :disabled="saving">초기화</button>
      </template>
    </BaseModal>

    <ConfirmModal
      :show="confirm.show"
      title="사용자 비활성화"
      :message="`'${confirm.user?.username}' 계정을 비활성화합니다.\n비활성 계정은 로그인할 수 없습니다.`"
      confirm-text="비활성화"
      :loading="saving"
      @confirm="doDeactivate"
      @cancel="confirm.show = false"
    />
  </div>
</template>
