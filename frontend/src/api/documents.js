import client from './client'

const data = (r) => r.data

export const listDocuments = (params) => client.get('/documents', { params }).then(data)
export const getDocument = (id) => client.get(`/documents/${id}`).then(data)
export const updateDocument = (id, payload) => client.patch(`/documents/${id}`, payload).then(data)
export const deleteDocument = (id) => client.delete(`/documents/${id}`)
export const getDocumentText = (id) => client.get(`/documents/${id}/text`).then(data)

export const uploadDocuments = (files, ownerType, category) => {
  const form = new FormData()
  form.append('owner_type', ownerType)
  if (category) form.append('category', category)
  files.forEach((file) => form.append('files', file))
  return client
    .post('/documents', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000,
    })
    .then(data)
}

export const createTextDocument = (payload) => client.post('/documents', payload).then(data)

export const downloadDocument = (id) =>
  client.get(`/documents/${id}/download`, { responseType: 'blob' }).then(data)

export const reprocessDocument = (id, fromStep) =>
  client.post(`/documents/${id}/reprocess`, { from_step: fromStep }).then(data)

export const mappingPreview = (id) => client.get(`/documents/${id}/mapping-preview`).then(data)
export const applyDocument = (id) => client.post(`/documents/${id}/apply`).then(data)

export const listMetadata = (id) => client.get(`/documents/${id}/metadata`).then(data)
export const createMetadata = (id, payload) =>
  client.post(`/documents/${id}/metadata`, payload).then(data)
export const updateMetadata = (id, metaId, payload) =>
  client.patch(`/documents/${id}/metadata/${metaId}`, payload).then(data)
export const deleteMetadata = (id, metaId) => client.delete(`/documents/${id}/metadata/${metaId}`)

export const listSchemas = (params) => client.get('/metadata-schemas', { params }).then(data)
export const createSchema = (payload) => client.post('/metadata-schemas', payload).then(data)
export const updateSchema = (id, payload) =>
  client.patch(`/metadata-schemas/${id}`, payload).then(data)
export const deleteSchema = (id) => client.delete(`/metadata-schemas/${id}`)
export const reextractSchema = (id) => client.post(`/metadata-schemas/${id}/reextract`).then(data)

export const loadInitialData = (mode = 'skip') =>
  client.post('/admin/load-initial-data', { mode }).then(data)
