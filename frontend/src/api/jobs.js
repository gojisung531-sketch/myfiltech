import client from './client'

export const getJob = (id, { signal } = {}) =>
  client.get(`/jobs/${id}`, { signal }).then((r) => r.data)

export const listJobs = (params) => client.get('/jobs', { params }).then((r) => r.data)
export const retryJob = (id) => client.post(`/jobs/${id}/retry`).then((r) => r.data)
export const cancelJob = (id) => client.post(`/jobs/${id}/cancel`).then((r) => r.data)
export const listLLMLogs = (params) => client.get('/llm-logs', { params }).then((r) => r.data)
export const getLLMLog = (id) => client.get(`/llm-logs/${id}`).then((r) => r.data)

const BID_TARGET = 'bids.BidNotice'
const SCAN_PAGE_SIZE = 100
const SCAN_MAX_PAGES = 20

// 현재 공고의 대기·실행 중 작업을 찾는다. GET /jobs는 target_id 필터가 없으므로 상태별로
// 전체 페이지를 읽어 target_type/target_id를 직접 대조한다. 끝까지 읽지 못하면 오류로 처리한다
// ("작업 없음"으로 오인하지 않기 위해).
export async function findActiveBidJobs(bidId, { signal } = {}) {
  const found = new Map()
  for (const status of ['PENDING', 'RUNNING']) {
    let page = 1
    for (;;) {
      const data = await client
        .get('/jobs', { params: { status, page, page_size: SCAN_PAGE_SIZE }, signal })
        .then((r) => r.data)
      for (const job of data.results || []) {
        if (job.target_type === BID_TARGET && Number(job.target_id) === Number(bidId)) {
          found.set(job.id, job)
        }
      }
      if (!data.next) break
      if (page >= SCAN_MAX_PAGES) throw new Error('작업 목록을 끝까지 확인하지 못했습니다.')
      page += 1
    }
  }
  return [...found.values()].sort((a, b) => a.id - b.id)
}

// 특정 작업이 이 공고의 것인지 확인한 뒤 돌려준다(아니면 null).
export async function getBidJob(bidId, jobId, { signal } = {}) {
  const job = await getJob(jobId, { signal })
  return job.target_type === BID_TARGET && Number(job.target_id) === Number(bidId) ? job : null
}
