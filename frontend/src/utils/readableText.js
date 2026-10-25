// 긴 서술문을 문단·목록으로 나눠 읽기 쉽게 한다. 내용은 바꾸지 않고 줄바꿈 위치만 정한다.
// - 기존 줄바꿈은 그대로 문단 경계로 쓴다.
// - 문장 경계는 '다.' 뒤 공백뿐이다(소수점·규격 번호·금액은 건드리지 않는다).
// - '[제목]' 표지와 '(1) (2)' 번호가 원문에 있을 때만 제목·목록으로 나눈다.
const MARKER = /(?:^|\s)(\[[^\]\n]{1,24}\])(?=\s|$)/g
const NUMBERED = /\s*(?=\(\d{1,2}\)\s)/

function sentences(text) {
  return text
    .split(/(?<=다\.)\s+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function bodyBlocks(text) {
  const blocks = []
  for (const line of text.split(/\n+/)) {
    const trimmed = line.trim()
    if (!trimmed) continue
    const numbered = trimmed.split(NUMBERED).filter(Boolean)
    if (numbered.length >= 2 && /^\(\d{1,2}\)/.test(numbered[0]) === false) {
      // 번호 앞에 서두가 있으면 서두는 문단, 나머지는 목록
      const lead = numbered[0]
      blocks.push({ type: 'p', lines: sentences(lead) })
      blocks.push({ type: 'list', items: numbered.slice(1) })
    } else if (numbered.length >= 2) {
      blocks.push({ type: 'list', items: numbered })
    } else {
      blocks.push({ type: 'p', lines: sentences(trimmed) })
    }
  }
  return blocks
}

export function toBlocks(value) {
  const text = typeof value === 'string' ? value.trim() : ''
  if (!text) return []
  const marks = [...text.matchAll(MARKER)].map((m) => ({
    title: m[1],
    at: m.index + m[0].indexOf(m[1]),
  }))
  if (!marks.length) return bodyBlocks(text)
  const blocks = []
  const head = text.slice(0, marks[0].at).trim()
  if (head) blocks.push(...bodyBlocks(head))
  marks.forEach((mark, i) => {
    const end = i + 1 < marks.length ? marks[i + 1].at : text.length
    const content = text.slice(mark.at + mark.title.length, end).trim()
    blocks.push({ type: 'heading', text: mark.title })
    if (content) blocks.push(...bodyBlocks(content))
  })
  return blocks
}

// 비교 후보 값처럼 서버가 '; 비교 후보 …'로 이어 붙인 문자열만 항목으로 나눈다.
export function splitCandidateValues(value) {
  const text = typeof value === 'string' ? value.trim() : ''
  if (!text) return []
  return text.split(/;\s+(?=비교 후보 )/).filter(Boolean)
}
