import client from './client'

export const login = (username, password) =>
  client.post('/auth/login', { username, password }).then((r) => r.data)

export const refresh = (refreshToken) =>
  client.post('/auth/refresh', { refresh: refreshToken }).then((r) => r.data)

export const logout = (refreshToken) => client.post('/auth/logout', { refresh: refreshToken })

export const me = () => client.get('/auth/me').then((r) => r.data)

export const changePassword = (oldPassword, newPassword) =>
  client
    .post('/auth/change-password', { old_password: oldPassword, new_password: newPassword })
    .then((r) => r.data)
