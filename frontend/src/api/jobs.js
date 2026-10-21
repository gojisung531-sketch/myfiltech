import client from './client'

export const getJob = (id) => client.get(`/jobs/${id}`).then((r) => r.data)

export const listJobs = (params) => client.get('/jobs', { params }).then((r) => r.data)
export const retryJob = (id) => client.post(`/jobs/${id}/retry`).then((r) => r.data)
export const cancelJob = (id) => client.post(`/jobs/${id}/cancel`).then((r) => r.data)
export const listLLMLogs = (params) => client.get('/llm-logs', { params }).then((r) => r.data)
export const getLLMLog = (id) => client.get(`/llm-logs/${id}`).then((r) => r.data)
