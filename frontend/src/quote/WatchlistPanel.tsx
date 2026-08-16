import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { Skeleton } from '../States'
import { inferMarket, stripMarket, type SearchItem } from './helpers'

// ========== 左栏：自选股面板 ==========
export default function WatchlistPanel({
  currentCode, wlVersion, onPick, onAdd, onRemove,
}: {
  currentCode: string
  wlVersion: number
  onPick: (code: string) => void
  onAdd: (code: string) => void
  onRemove: (code: string) => void
}) {
  const [addInput, setAddInput] = useState('')
  const [searchHits, setSearchHits] = useState<SearchItem[]>([])

  // 1) 拉取自选股 code 列表（wlVersion 变化时强制刷新）
  const profileQuery = useQuery({
    queryKey: ['watchlist', wlVersion],
    queryFn: () => api.getProfile(),
  })
  const codes = profileQuery.data?.watchlist || []

  // 2) 根据 code 列表并发拉取行情（名称+价格+涨跌幅），react-query 自动缓存/去重
  const quotesQuery = useQuery({
    queryKey: ['watchlist-quotes', codes],
    enabled: codes.length > 0,
    queryFn: async () => {
      return Promise.all(codes.map(async (code) => {
        try {
          const q = await api.getQuote(code, 1, 'day', 0)
          const bf = q.brief as any
          return { code, name: bf?.name ?? code, price: bf?.price, change_pct: bf?.change_pct }
        } catch {
          return { code, name: code }
        }
      }))
    },
  })
  const items = quotesQuery.data ?? []

  const onSearchAdd = (v: string) => {
    setAddInput(v)
    if (!v.trim()) { setSearchHits([]); return }
    // 复用搜索防抖
    window.clearTimeout((onSearchAdd as any)._t)
    ;(onSearchAdd as any)._t = window.setTimeout(async () => {
      try {
        const r = await api.search(v.trim())
        setSearchHits(r.results.slice(0, 5))
      } catch { setSearchHits([]) }
    }, 300)
  }

  const commitAdd = (code: string) => {
    onAdd(code)
    setAddInput('')
    setSearchHits([])
  }

  return (
    <div className="qp-watchlist">
      <div className="qp-watchlist-head">自选股</div>

      <div className="qp-watchlist-add">
        <input
          value={addInput}
          onChange={(e) => onSearchAdd(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              if (searchHits.length > 0) {
                commitAdd(`${inferMarket(searchHits[0].code)}${searchHits[0].code}`)
              } else if (addInput.trim()) {
                // 纯代码兜底
                const c = addInput.trim()
                commitAdd(/^\d{6}$/.test(c) || /^(sh|sz|hk|us)/i.test(c) ? c : `sh${c}`)
              }
            }
          }}
          placeholder="添加代码/名称"
        />
        {searchHits.length > 0 && (
          <div className="qp-results qp-watchlist-results">
            {searchHits.map((r) => (
              <button key={r.code} className="qp-result" onClick={() => commitAdd(`${inferMarket(r.code)}${r.code}`)}>
                <span className={`qp-market m-${r.market}`}>{r.market.toUpperCase()}</span>
                <span className="qp-name">{r.name}</span>
                <span className="qp-code">{r.code}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {profileQuery.isLoading && <div className="qp-watchlist-empty"><Skeleton variant="text" lines={2} style={{ padding: 0 }} /></div>}
      {!profileQuery.isLoading && codes.length === 0 && (
        <div className="qp-watchlist-empty">暂无自选股，搜索添加</div>
      )}
      <div className="qp-watchlist-list">
        {items.map((it) => {
          const stripCode = stripMarket(it.code)
          const active = stripCode === currentCode || it.code === currentCode
          const chg = it.change_pct
          return (
            <div
              key={it.code}
              className={`qp-watchlist-item ${active ? 'active' : ''}`}
              onClick={() => onPick(it.code)}
            >
              <span className="qp-watchlist-name">{it.name}</span>
              <span className="qp-watchlist-code">{stripCode}</span>
              <span className={`qp-watchlist-chg ${chg == null ? '' : chg >= 0 ? 'up' : 'down'}`}>
                {it.price != null && <span style={{ color: 'var(--text)', marginRight: 6 }}>{it.price}</span>}
                {chg != null ? `${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%` : '--'}
              </span>
              <button
                className="qp-watchlist-del"
                title="移除"
                onClick={(e) => { e.stopPropagation(); onRemove(it.code) }}
              >×</button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
