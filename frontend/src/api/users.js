import client from './client'

export const listUsers = (params) => client.get('/users', { params }).then((r) => r.data)

export const createUser = (data) => client.post('/users', data).then((r) => r.data)

export const updateUser = (id, data) => client.patch(`/users/${id}`, data).then((r) => r.data)

export const deactivateUser = (id) => client.delete(`/users/${id}`)

export const resetPassword = (id, newPassword) =>
  client.post(`/users/${id}/reset-password`, { new_password: newPassword }).then((r) => r.data)
