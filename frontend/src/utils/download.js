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
