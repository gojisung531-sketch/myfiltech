import client from './client'

const data = (r) => r.data

// 검토 대기 관리대장 조회 (읽기 전용, GET만). 계약: filtech-backend/backend/docs/report-register-api.md
export const listRegisterVersions = (params) =>
  client.get('/report-register-versions', { params }).then(data)
export const getRegisterVersion = (id) => client.get(`/report-register-versions/${id}`).then(data)
export const listRegisterRows = (params) =>
  client.get('/report-register-rows', { params }).then(data)
export const getRegisterRow = (id) => client.get(`/report-register-rows/${id}`).then(data)
