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

// Blob 응답(responseType: 'blob') 요청이 실패하면 오류 본문도 Blob이다. JSON이면 읽어서 메시지로 쓴다.
export async function downloadErrorMessage(error, fallback) {
  const data = error?.response?.data
  if (typeof Blob !== 'undefined' && data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text())
      return errorMessage({ response: { data: parsed } }, fallback)
    } catch {
      return fallback
    }
  }
  return errorMessage(error, fallback)
}
