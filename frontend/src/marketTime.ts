import type { Time, UTCTimestamp } from 'lightweight-charts'

// 把各市场接口返回的交易所本地时间原样映射到图表，避免浏览器时区二次换算。
export function chartTime(value: string): Time {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/)
  if (!match) return value.slice(0, 10) as Time
  return (Date.UTC(+match[1], +match[2] - 1, +match[3], +match[4], +match[5]) / 1000) as UTCTimestamp
}

export function formatChartTime(time: Time | undefined) {
  if (!time) return ''
  if (typeof time === 'string') return time
  if (typeof time === 'number') return new Date(time * 1000).toLocaleString('zh-CN', { hour12: false, timeZone: 'UTC' })
  return `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}`
}
