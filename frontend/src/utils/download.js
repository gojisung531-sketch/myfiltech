import { downloadErrorMessage } from './errors'

// Save an axios blob response using the server's RFC 5987 filename (specs/09 §5).
export function filenameFrom(disposition, fallback) {
  const star = /filename\*=UTF-8''([^;]+)/i.exec(disposition || '')
  if (star) return decodeURIComponent(star[1])
  const plain = /filename="?([^";]+)"?/i.exec(disposition || '')
  return plain ? plain[1] : fallback
}

export function saveResponse(response, fallback = 'download.pdf') {
  const name = filenameFrom(response.headers['content-disposition'], fallback)
  const url = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  return name
}

export const PDF_TYPES = ['application/pdf']
export const XLSX_CONTENT_TYPES = [
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
]

// 파일 응답만 저장한다. 오류 JSON·HTML·빈 본문은 파일로 저장하지 않고 메시지를 담은 Error를 던진다.
// 저장을 시도했다는 사실이 파일 내용의 정확성을 뜻하지는 않는다.
export async function downloadFile(request, { types, fallbackName, failMessage }) {
  let response
  try {
    response = await request()
  } catch (err) {
    throw new Error(await downloadErrorMessage(err, failMessage), { cause: err })
  }
  const type = String(response.headers?.['content-type'] || '')
    .split(';')[0]
    .trim()
    .toLowerCase()
  if (!types.includes(type)) {
    throw new Error(`${failMessage} (서버가 파일이 아닌 응답을 반환해 저장하지 않았습니다.)`)
  }
  if (!response.data?.size) {
    throw new Error(`${failMessage} (빈 파일이 반환되어 저장하지 않았습니다.)`)
  }
  return saveResponse(response, fallbackName)
}
