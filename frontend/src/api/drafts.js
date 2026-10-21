import client from './client'

const data = (r) => r.data
const base = (bidId) => `/bids/${bidId}/drafts`

export const DRAFT_TYPES = {
  COMPLIANCE_MATRIX: 'Compliance Matrix',
  BID_CHECKLIST: '입찰 체크리스트',
  TECHNICAL_QUERY: '발주처 기술질의서',
  REVIEW_REPORT: '검토 보고서',
}

export const listDrafts = (bidId) => client.get(base(bidId)).then(data)
export const getDraft = (bidId, type, version) =>
  client.get(`${base(bidId)}/${type}`, { params: version ? { version } : {} }).then(data)
export const saveDraft = (bidId, type, payload) =>
  client.put(`${base(bidId)}/${type}`, payload).then(data)
export const generateDraft = (bidId, type, newVersion = false) =>
  client.post(`${base(bidId)}/${type}/generate`, { new_version: newVersion }).then(data)
export const draftVersions = (bidId, type) =>
  client.get(`${base(bidId)}/${type}/versions`).then(data)

const pdfRequest = (url, params) =>
  client.get(url, { params, responseType: 'blob', timeout: 300000 })

export const downloadDraftPdf = (bidId, type, version) =>
  pdfRequest(`${base(bidId)}/${type}/pdf`, version ? { version } : {})
export const downloadReportPdf = (bidId) => pdfRequest(`/bids/${bidId}/report.pdf`)

export const XLSX_TYPES = ['COMPLIANCE_MATRIX', 'BID_CHECKLIST']
export const downloadDraftXlsx = (bidId, type, version) =>
  client.get(`${base(bidId)}/${type}/xlsx`, {
    params: version ? { version } : {},
    responseType: 'blob',
    timeout: 120000,
  })
