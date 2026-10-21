import client from './client'

export const getLLMSettings = () => client.get('/settings/llm').then((r) => r.data)

export const updateLLMSettings = (data) => client.put('/settings/llm', data).then((r) => r.data)

export const updateProvider = (provider, data) =>
  client.put(`/settings/llm/providers/${provider}`, data, { timeout: 90000 }).then((r) => r.data)

export const verifyProvider = (provider, modelId) =>
  client
    .post(`/settings/llm/providers/${provider}/verify`, { model_id: modelId }, { timeout: 90000 })
    .then((r) => r.data)

export const createModelOption = (data) =>
  client.post('/settings/llm/models', data).then((r) => r.data)

export const updateModelOption = (id, data) =>
  client.patch(`/settings/llm/models/${id}`, data).then((r) => r.data)

export const deleteModelOption = (id) => client.delete(`/settings/llm/models/${id}`)

// Prompts (specs/10 LLM · 설정)
export const listPrompts = () => client.get('/settings/prompts').then((r) => r.data)
export const getPrompt = (key) => client.get(`/settings/prompts/${key}`).then((r) => r.data)
export const savePromptVersion = (key, payload) =>
  client.post(`/settings/prompts/${key}`, payload).then((r) => r.data)
export const activatePrompt = (key, version) =>
  client.post(`/settings/prompts/${key}/activate`, { version }).then((r) => r.data)
export const resetPrompt = (key) =>
  client.post(`/settings/prompts/${key}/reset`).then((r) => r.data)
export const testPrompt = (key, payload) =>
  client.post(`/settings/prompts/${key}/test`, payload, { timeout: 600000 }).then((r) => r.data)

// Tuning (AppSetting)
export const getAppSettings = () => client.get('/settings/app').then((r) => r.data)
export const saveAppSettings = (values) =>
  client.put('/settings/app', { values }).then((r) => r.data)
export const resetAppSetting = (key) =>
  client.post(`/settings/app/${key}/reset`).then((r) => r.data)
