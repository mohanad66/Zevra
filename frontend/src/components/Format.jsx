export function fmt(n, digits = 2) {
  if (n === null || n === undefined || n === '') return '-'
  const num = typeof n === 'string' ? parseFloat(n) : n
  if (Number.isNaN(num)) return '-'
  return num.toLocaleString(undefined, { maximumFractionDigits: digits })
}

export function fmtCrypto(n, digits = 8) {
  return fmt(n, digits)
}

export function StatusBadge({ status }) {
  const cls = `pill pill-${status}`
  return <span className={cls}>{status}</span>
}

export function percentageClass(v) {
  const n = parseFloat(v)
  if (Number.isNaN(n)) return 'neg'
  return n >= 0 ? 'pos' : 'neg'
}

export function sign(v) {
  if (v === null || v === undefined) return ''
  return parseFloat(v) >= 0 ? '▲' : '▼'
}