import client from './client'

export const getStatus = () => client.get('/system/status').then((r) => r.data)
