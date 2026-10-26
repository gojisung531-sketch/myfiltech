import client from './client'

const data = (r) => r.data
const multipart = { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000 }

export const listBids = (params) => client.get('/bids', { params }).then(data)
export const getBid = (id) => client.get(`/bids/${id}`).then(data)
export const updateBid = (id, payload) => client.patch(`/bids/${id}`, payload).then(data)
export const deleteBid = (id) => client.delete(`/bids/${id}`)
export const extractBid = (id) => client.post(`/bids/${id}/extract`).then(data)

// multipart 전송은 문자열의 줄바꿈을 CRLF로 바꾼다. 서버는 받은 본문의 SHA-256으로 미리보기 결과를
// 대조하므로, 미리보기와 등록이 같은 바이트를 보내도록 두 요청 모두 CRLF로 통일한다.
export const wireText = (text) => String(text || '').replace(/\r?\n/g, '\r\n')

// noticeMetadata(선택): { source_sha256, values, edited_fields } — 기본 정보 미리보기 결과.
// 생략하면 기존 요청과 동일하다.
export const createBid = ({ title, sourceText, files, noticeMetadata }) => {
  const form = new FormData()
  form.append('title', title || '')
  form.append('source_text', wireText(sourceText))
  files.forEach((file) => form.append('files', file))
  if (noticeMetadata) form.append('notice_metadata', JSON.stringify(noticeMetadata))
  return client.post('/bids', form, multipart).then(data)
}

// 본문에서 기본 정보만 읽는다(저장·요구조건 분석 없음). signal로 이전 요청을 취소한다.
export const previewNoticeMetadata = (sourceText, { signal } = {}) =>
  client
    .post(
      '/bids/preview-metadata',
      { source_text: wireText(sourceText) },
      { signal, timeout: 30000 },
    )
    .then(data)

export const addAttachments = (id, files) => {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  return client.post(`/bids/${id}/attachments`, form, multipart).then(data)
}
export const updateAttachment = (id, attachmentId, payload) =>
  client.patch(`/bids/${id}/attachments/${attachmentId}`, payload).then(data)
export const deleteAttachment = (id, attachmentId) =>
  client.delete(`/bids/${id}/attachments/${attachmentId}`)

function child(name) {
  return {
    list: (id, params) => client.get(`/bids/${id}/${name}`, { params }).then(data),
    create: (id, payload) => client.post(`/bids/${id}/${name}`, payload).then(data),
    update: (id, childId, payload) =>
      client.patch(`/bids/${id}/${name}/${childId}`, payload).then(data),
    remove: (id, childId) => client.delete(`/bids/${id}/${name}/${childId}`),
  }
}

export const bidItems = child('items')
export const bidRequirements = child('requirements')

export const dashboardSummary = () => client.get('/dashboard/summary').then(data)
export const reviewBid = (id, reviewed) =>
  client.post(`/bids/${id}/review`, { reviewed }).then(data)
export const getComparison = (id) => client.get(`/bids/${id}/comparison`).then(data)
export const listRequirementsWithEvaluation = (id) =>
  client.get(`/bids/${id}/requirements`, { params: { include: 'evaluation' } }).then(data)

export const evaluateBid = (id, { keepModified = true, requirementIds } = {}) =>
  client
    .post(`/bids/${id}/evaluate`, {
      keep_modified: keepModified,
      ...(requirementIds ? { requirement_ids: requirementIds } : {}),
    })
    .then(data)
export const getEvaluations = (id) => client.get(`/bids/${id}/evaluations`).then(data)
export const updateEvaluation = (eid, payload) =>
  client.patch(`/evaluations/${eid}`, payload).then(data)
export const revertEvaluation = (eid) => client.post(`/evaluations/${eid}/revert`).then(data)
export const evaluationHistory = (eid) => client.get(`/evaluations/${eid}/history`).then(data)
