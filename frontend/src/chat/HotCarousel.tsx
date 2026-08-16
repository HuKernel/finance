// 欢迎页热门行情轮播（单排，自动轮播 + 手动切换）
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { KlineBar, MinutePoint, NewsItem, QuoteResponse } from '../types'
import { StarButton } from '../QuoteCard'
import KLineChart from '../KLineChart'

// 欢迎页热门行情轮播（单排，自动轮播 + 手动切换）
const HOT_FALLBACK = ['600519', 'hk00700', 'usAAPL', '300750']

function useHotCodes() {
  const [codes, setCodes] = useState<string[]>(HOT_FALLBACK)
  useEffect(() => {
    api.getHotStocks().then((items) => {
      if (items && items.length >= 3) {
        setCodes(items.map((i) => i.code))
      }
    }).catch(() => {})
  }, [])
  return codes
}

// 轮播专用K线：切换股票时只重新加载这部分（行情简报/新闻由外层预加载）
function HotKLine({ code, name, lastClose }: { code: string; name: string; lastClose: number | null }) {
  const [data, setData] = useState<QuoteResponse | null>(null)
  const [mode, setMode] = useState<'day' | 'minute'>('day')

  useEffect(() => {
    let cancelled = false
    setData(null)
    api.getQuote(code, 60, 'day', 0).then((q) => { if (!cancelled) setData(q) }).catch(() => {})
    return () => { cancelled = true }
  }, [code])

  // 分时模式实时刷新（15秒）
  useEffect(() => {
    if (mode !== 'minute') return
    const t = window.setInterval(() => {
      api.getQuote(code, 60, 'minute', 1).then(setData).catch(() => {})
    }, 15000)
    return () => window.clearInterval(t)
  }, [mode, code])

  const switchMode = (m: 'day' | 'minute') => {
    setMode(m)
    api.getQuote(code, 60, m, 0).then(setData).catch(() => {})
  }

  if (!data) {
    return <div className="kline-loading">K线加载中...</div>
  }

  const bars = (data.kline as KlineBar[]).filter((k) => k.date && typeof k.close === 'number')
  const minute = (data.kline as MinutePoint[]).filter((k) => k.time && typeof k.price === 'number')

  return (
    <KLineChart
      bars={bars}
      minute={minute}
      lastClose={lastClose ?? null}
      symbol={name}
      mode={mode}
      onMode={switchMode}
    />
  )
}

// 轮播卡片：头部/新闻用预加载数据即时切换，K线独立加载
function HotQuoteCard({ code, brief, news, dir }: {
  code: string; brief: QuoteResponse | null; news: NewsItem[]; dir: 1 | -1
}) {
  const b = brief?.brief as {
    name?: string; price?: number; change_pct?: number
    pe?: number; pb?: number; turnover?: number; market_cap?: number
  } | undefined
  const name = String(b?.name ?? code)
  const price = b?.price
  const change = b?.change_pct
  const [showNews, setShowNews] = useState(false)

  return (
    <div className={`quote-card hot-slide ${dir === 1 ? 'in-right' : 'in-left'}`}>
      <div className="quote-head">
        <span className="quote-name">{name}</span>
        <span className="quote-code">{code}</span>
        <span className={`quote-change ${(change ?? 0) >= 0 ? 'up' : 'down'}`}>
          {price ?? '--'} {change != null ? `${change >= 0 ? '+' : ''}${change}%` : ''}
        </span>
        <StarButton code={code} />
      </div>
      <div className="quote-meta">
        {b?.pe != null && <span>PE {b.pe}</span>}
        {b?.pb != null && <span>PB {b.pb}</span>}
        {b?.turnover != null && <span>换手 {b.turnover}%</span>}
        {b?.market_cap != null && <span>市值 {b.market_cap}亿</span>}
      </div>
      <HotKLine code={code} name={name} lastClose={brief?.last_close ?? null} />
      {news.length > 0 && (
        <div className="quote-news">
          <div className="quote-news-head">最新新闻</div>
          {news.slice(0, 3).map((n, i) => (
            <div className="quote-news-item" key={i}>
              <span className="quote-news-time">{n.time.slice(5, 16)} · {n.source}</span>
              {n.url ? <a className="quote-news-title" href={n.url} target="_blank" rel="noreferrer">{n.title.length > 70 ? n.title.slice(0, 70) + '…' : n.title}</a> : <span className="quote-news-title">{n.title.length > 70 ? n.title.slice(0, 70) + '…' : n.title}</span>}
            </div>
          ))}
          {news.length > 3 && (
            <button className="quote-news-more" onClick={() => setShowNews(true)}>查看全部 {news.length} 条 ›</button>
          )}
        </div>
      )}
      {showNews && (
        <div className="news-overlay" onClick={() => setShowNews(false)}>
          <div className="news-modal" onClick={(e) => e.stopPropagation()}>
            <div className="news-modal-head">
              <span>{name} 相关新闻</span>
              <button onClick={() => setShowNews(false)}>✕</button>
            </div>
            <div className="news-modal-list">
              {news.map((n, i) => (
                <div className="news-modal-item" key={i}>
                  <span className="quote-news-time">{n.time} · {n.source}</span>
                  {n.url ? <a className="quote-news-title" href={n.url} target="_blank" rel="noreferrer">{n.title}</a> : <span className="quote-news-title">{n.title}</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// 热门行情轮播容器：预加载4只简报+新闻，切换只重载K线，左右滑动过渡
export function HotCarousel() {
  const HOT_CODES = useHotCodes()
  const [idx, setIdx] = useState(0)
  const [dir, setDir] = useState<1 | -1>(1)
  const [briefs, setBriefs] = useState<Record<string, QuoteResponse | null>>({})
  const [newsMap, setNewsMap] = useState<Record<string, NewsItem[]>>({})
  const code = HOT_CODES[idx]

  const [paused, setPaused] = useState(false)

  useEffect(() => {
    HOT_CODES.forEach((c) => {
      api.getQuote(c, 60, 'day', 0).then((q) => setBriefs((m) => ({ ...m, [c]: q }))).catch(() => {})
      api.getNews(c).then((n) => setNewsMap((m) => ({ ...m, [c]: n.news }))).catch(() => {})
    })
  }, [HOT_CODES])

  // 自动轮播：鼠标悬停时暂停，移开恢复
  useEffect(() => {
    if (paused) return
    const t = window.setInterval(() => { setDir(1); setIdx((i) => (i + 1) % HOT_CODES.length) }, 6000)
    return () => window.clearInterval(t)
  }, [paused, HOT_CODES.length])

  const go = (d: 1 | -1) => {
    setDir(d)
    setIdx((i) => (i + d + HOT_CODES.length) % HOT_CODES.length)
  }

  return (
    <div className="chat-hot" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <div className="chat-hot-head">
        <span>热门行情</span>
        <span className="chat-hot-nav">
          <button className="hot-arrow" title="上一个" onClick={() => go(-1)}>‹</button>
          <span className="hot-dots">
            {HOT_CODES.map((_, i) => (
              <i key={i} className={i === idx ? 'on' : ''} onClick={() => { setDir(i > idx ? 1 : -1); setIdx(i) }} />
            ))}
          </span>
          <button className="hot-arrow" title="下一个" onClick={() => go(1)}>›</button>
        </span>
      </div>
      <div className="chat-hot-carousel">
        <HotQuoteCard key={code} code={code} brief={briefs[code] ?? null} news={newsMap[code] ?? []} dir={dir} />
      </div>
    </div>
  )
}
