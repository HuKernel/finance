import type { DataMetadata } from '../types'

export interface SearchItem { market: string; code: string; name: string; type: string }

export const HOT_FALLBACK = [
  { code: '600519', name: '贵州茅台' },
  { code: 'hk00700', name: '腾讯控股' },
  { code: 'usAAPL', name: '苹果' },
  { code: '300750', name: '宁德时代' },
]

// 推断市场前缀（watchlist 里的 code 形如 sh600519 / hk00700 / usAAPL / 600519）
export function inferMarket(code: string): string {
  if (code.startsWith('hk')) return 'hk'
  if (code.startsWith('us')) return 'us'
  if (/^(sh|sz|bj)/i.test(code)) return code.slice(0, 2).toLowerCase()
  if (/^\d{6}$/.test(code)) {
    const c = code[0]
    if (c === '6') return 'sh'      // 沪市
    if (c === '0' || c === '3') return 'sz' // 深市/创业板
    if (c === '8' || c === '4') return 'bj' // 北交所
    return 'sh'
  }
  return 'sh'
}

// 把任意 code 归一化为 "纯代码"（去掉市场前缀），后端 quote 接口接受带前缀或不带前缀
export function stripMarket(code: string): string {
  return code.replace(/^(sh|sz|bj|hk|us)/i, '')
}

export function mergeKlineMetadata(history?: DataMetadata, recent?: DataMetadata): DataMetadata {
  const sources = [...new Set([history?.source, recent?.source].filter(Boolean))]
  const providerNames = [...new Set([history?.provider_name, recent?.provider_name].filter(Boolean))]
  return {
    ...history,
    ...recent,
    source: sources.join(' + ') || undefined,
    provider_name: providerNames.join(' + ') || undefined,
    fallback_used: Boolean(history?.fallback_used || recent?.fallback_used),
    fallback_reason: recent?.fallback_reason || history?.fallback_reason,
    rows_dropped: (history?.rows_dropped ?? 0) + (recent?.rows_dropped ?? 0),
  }
}
