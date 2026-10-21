// Turn an API error ({detail, code, errors}, specs/01 §6) into one Korean message.
export function errorMessage(error, fallback = '요청을 처리하지 못했습니다.') {
  const data = error?.response?.data
  if (!data) return error?.code === 'ECONNABORTED' ? '서버 응답 시간이 초과되었습니다.' : fallback
  if (data.errors && typeof data.errors === 'object') {
    const messages = Object.values(data.errors).flat().filter(Boolean)
    if (messages.length) return messages.join(' ')
  }
  return data.detail || fallback
}
