import client from './client'

const data = (r) => r.data

export const getCompany = () => client.get('/company').then(data)
export const updateCompany = (payload) => client.put('/company', payload).then(data)

// Generic CRUD helpers for company resources (specs/10 회사 자료).
function resource(path) {
  return {
    list: (params) => client.get(path, { params }).then(data),
    get: (id) => client.get(`${path}/${id}`).then(data),
    create: (payload) => client.post(path, payload).then(data),
    update: (id, payload) => client.patch(`${path}/${id}`, payload).then(data),
    remove: (id) => client.delete(`${path}/${id}`),
  }
}

export const products = resource('/products')
export const testReports = resource('/test-reports')
export const certificates = resource('/certificates')
export const deliveryRecords = resource('/delivery-records')
