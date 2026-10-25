// 후보별 카탈로그 비교의 서버 값(candidate_verdict)을 업무 용어로만 바꿔 보여 준다(계산하지 않음).
export const CANDIDATE_LABELS = {
  MET: { text: '충족', cls: 'bg-success' },
  NEEDS_SUPPLEMENT: { text: '미달', cls: 'bg-warning' },
  NEEDS_CONFIRMATION: { text: '확인 필요', cls: 'bg-info' },
}
