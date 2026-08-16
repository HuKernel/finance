// 自选股面板：展示实时行情简要 + 添加/删除
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'

// 自选股面板：展示实时行情简要 + 添加/删除
export function WatchList() {
  const [watchlist, setWatchlist] = useState<string[]>([])
  const [quotes, setQuotes] = useState<Record<string, { name?: string; price?: number; change_pct?: number }>>({})
  const [input, setInput] = useState('')
  const [adding, setAdding] = useState(false)

  const loadProfile = useCallback(async () => {
    try {
      const p = await api.getProfile()
      setWatchlist(p.watchlist || [])
    } catch { /* skip */ }
  }, [])

  useEffect(() => { loadProfile() }, [loadProfile])

  // 轮询自选股行情
  useEffect(() => {
    if (watchlist.length === 0) { setQuotes({}); return }
    let cancelled = false
    const fetchAll = async () => {
      const next: Record<string, { name?: string; price?: number; change_pct?: number }> = {}
      await Promise.all(watchlist.map(async (code) => {
        try {
          const q = await api.getQuote(code, 1, 'day', 0)
          if (!cancelled) next[code] = q.brief as any
        } catch { /* skip */ }
      }))
      if (!cancelled) setQuotes(next)
    }
    fetchAll()
    const timer = window.setInterval(fetchAll, 30000) // 30秒刷新
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [watchlist])

  const add = async () => {
    const code = input.trim()
    if (!code) return
    setAdding(true)
    try {
      // 先获取行情验证代码是否有效
      await api.getQuote(code, 1, 'day', 0)
      const next = [...new Set([...watchlist, code])]
      setWatchlist(next)
      await api.saveProfile({ watchlist: next })
      setInput('')
    } catch {
      // 无效代码忽略
    } finally {
      setAdding(false)
    }
  }

  const remove = async (code: string) => {
    const next = watchlist.filter(c => c !== code)
    setWatchlist(next)
    setQuotes(prev => { const cp = { ...prev }; delete cp[code]; return cp })
    await api.saveProfile({ watchlist: next })
  }

  return (
    <div className="watchlist">
      <div className="watchlist-head">自选股</div>
      <div className="watchlist-items">
        {watchlist.map((code) => {
          const q = quotes[code]
          const up = (q?.change_pct ?? 0) >= 0
          return (
            <div key={code} className="watchlist-item">
              <div className="watchlist-info">
                <span className="watchlist-name">{q?.name || code}</span>
                <span className="watchlist-code">{code}</span>
              </div>
              <div className="watchlist-data">
                <span className={`watchlist-price ${up ? 'up' : 'down'}`}>
                  {q?.price?.toFixed(2) ?? '--'}
                </span>
                <span className={`watchlist-chg ${up ? 'up' : 'down'}`}>
                  {q?.change_pct != null ? `${up ? '+' : ''}${q.change_pct.toFixed(2)}%` : ''}
                </span>
              </div>
              <button className="watchlist-del" title="删除" onClick={() => remove(code)}>x</button>
            </div>
          )
        })}
        {watchlist.length === 0 && <div className="watchlist-empty">暂无自选股</div>}
      </div>
      <div className="watchlist-add">
        <input
          aria-label="添加自选股代码"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && add()}
          placeholder="添加代码（如 600519）"
          disabled={adding}
        />
        <button onClick={add} disabled={adding || !input.trim()}>+</button>
      </div>
    </div>
  )
}
