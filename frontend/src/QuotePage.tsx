// 行情页（东财式三栏布局）：搜索栏 → 三栏主区 → 新闻
//   左栏 220px：自选股列表（常驻）
//   中栏 1fr ：标题+价格+操作 / 周期工具栏 / K线 / 对比表
//   右栏 300px：盘口数据表 / 资金流向卡 / K线形态卡
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, requireLogin } from './api'
import type { KlineBar, MinutePoint, NewsItem, QuoteResponse } from './types'
import KLineChart from './KLineChart'
import { StarButton } from './QuoteCard'
import { HOT_FALLBACK, inferMarket, stripMarket, mergeKlineMetadata, type SearchItem } from './quote/helpers'
import WatchlistPanel from './quote/WatchlistPanel'
import OrderBookPanel from './quote/OrderBookPanel'
import FundFlowCard from './quote/FundFlowCard'
import PatternCard from './quote/PatternCard'


export default function QuotePage() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchItem[]>([])
  const [selected, setSelected] = useState<SearchItem>({ market: 'sh', code: '', name: '', type: 'GP' })
  const [hotItems, setHotItems] = useState(HOT_FALLBACK)
  const [compareCode, setCompareCode] = useState('')
  const [compareData, setCompareData] = useState<QuoteResponse | null>(null)
  const [industry, setIndustry] = useState<{ peers: { code: string; name: string; pe: number; pb: number; change_pct: number; market_cap: number; is_target: boolean }[]; avg_pe: number | null; avg_pb: number | null } | null>(null)
  const [data, setData] = useState<QuoteResponse | null>(null)
  const [news, setNews] = useState<NewsItem[]>([])
  const [mode, setMode] = useState<'day' | 'minute'>('day')
  const [period, setPeriod] = useState<string>('day')
  const [multiDay, setMultiDay] = useState<number>(0)
  const [subIndicator, setSubIndicator] = useState<'macd' | 'kdj'>('macd')
  const [klineFullscreen, setKlineFullscreen] = useState(false)
  const [live, setLive] = useState(true)
  const [err, setErr] = useState('')
  const [searching, setSearching] = useState(false)
  const [chartLoading, setChartLoading] = useState(false)
  const [dayRange, setDayRange] = useState<30 | 60 | 120 | 250 | 'all'>(120)
  const [defaultRank, setDefaultRank] = useState<{ code: string; amount: number; scope: string } | null>(null)
  // watchlist 版本号：星标/删除/添加后自增以刷新左栏
  const [wlVersion, setWlVersion] = useState(0)
  const [showIndustry, setShowIndustry] = useState(false)
  const timerRef = useRef<number | null>(null)
  const searchTimer = useRef<number | null>(null)
  const chartRequestRef = useRef(0)

  // 默认展示 A 股全市场当日成交额第一；数据源失败时回退到稳定示例。
  useEffect(() => {
    api.getTopTurnoverStock().then((stock) => {
      const market = stock.code.startsWith('6') ? 'sh' : /^[48]/.test(stock.code) ? 'bj' : 'sz'
      setSelected({ market, code: stock.code, name: stock.name, type: 'GP' })
      setQuery(stock.name)
      setDefaultRank({ code: stock.code, amount: stock.amount, scope: stock.scope })
    }).catch(() => {
      const h = HOT_FALLBACK[0]
      setSelected({ market: 'sh', code: h.code, name: h.name, type: 'GP' })
      setQuery(h.name)
    })
  }, [])

  // 加载每日热门股票
  useEffect(() => {
    api.getHotStocks().then((items) => {
      if (items && items.length >= 3) {
        setHotItems(items.map((i) => ({ code: i.code, name: i.name })))
      }
    }).catch(() => {})
  }, [])

  const load = useCallback(async (code: string, m: 'day' | 'minute', fresh: number, range: 30 | 60 | 120 | 250 | 'all' = 120) => {
    const requestId = ++chartRequestRef.current
    if (!fresh) setChartLoading(true)
    try {
      let q: QuoteResponse
      if (m === 'day' && range === 'all') {
        const [recent, history] = await Promise.all([
          api.getQuote(code, 120, 'day', fresh),
          api.getQuote(code, 120, 'day', 0, 1),
        ])
        const merged = new Map((history.kline as KlineBar[]).map(bar => [bar.date, bar]))
        for (const bar of recent.kline as KlineBar[]) merged.set(bar.date, bar)
        q = {
          ...history,
          ...recent,
          kline: [...merged.values()].sort((a, b) => a.date.localeCompare(b.date)),
          metadata: {
            brief: recent.metadata?.brief,
            kline: mergeKlineMetadata(history.metadata?.kline, recent.metadata?.kline),
          },
        }
      } else {
        q = await api.getQuote(code, range === 'all' ? 120 : range, m, fresh)
      }
      if (requestId === chartRequestRef.current) {
        setData(q)
        setErr('')
      }
    } catch {
      if (requestId === chartRequestRef.current) setErr('行情加载失败')
    } finally {
      if (requestId === chartRequestRef.current) setChartLoading(false)
    }
  }, [])

  // 加载多日分时（2日/3日/4日/5日）：5分钟K线按交易日截取
  const loadMultiDay = useCallback(async (code: string, days: number) => {
    const requestId = ++chartRequestRef.current
    setChartLoading(true)
    try {
      // A股用腾讯5分钟，美股用yfinance 5分钟（后端自动选择）
      const count = 48 * (days + 3)
      const r = await fetch(`/api/kline/${code}?period=5min&count=${count}`, {
        credentials: 'same-origin',
      })
      const d = await r.json()
      if (d.bars && requestId === chartRequestRef.current) {
        // 按交易日分组，只保留最近N个交易日
        const dayMap = new Map<string, any[]>()
        for (const b of d.bars) {
          const day = b.date.split(' ')[0]
          if (!dayMap.has(day)) dayMap.set(day, [])
          dayMap.get(day)!.push(b)
        }
        const allDays = Array.from(dayMap.keys()).sort()
        const recentDays = allDays.slice(-days)
        const filtered = d.bars.filter((b: any) => recentDays.includes(b.date.split(' ')[0]))
        // 走日K模式展示5分钟K线蜡烛图
        setData(prev => ({
          brief: prev?.brief ?? {},
          kline: filtered.map((b: any) => ({ date: b.date, open: b.open, close: b.close, high: b.high, low: b.low, volume: b.volume })),
          tech: {},
          metadata: { brief: prev?.metadata?.brief, kline: d.metadata },
          last_close: filtered[filtered.length - 1]?.close ?? null,
        }))
      }
      if (requestId === chartRequestRef.current) setErr('')
    } catch {
      if (requestId === chartRequestRef.current) setErr('多日分时加载失败')
    } finally {
      if (requestId === chartRequestRef.current) setChartLoading(false)
    }
  }, [])

  // 加载多周期K线（周K/月K/分钟级）
  const loadPeriod = useCallback(async (code: string, p: string) => {
    const requestId = ++chartRequestRef.current
    setChartLoading(true)
    try {
      const count = p.endsWith('min') ? 100000 : 250
      const r = await fetch(`/api/kline/${code}?period=${p}&count=${count}`, {
        credentials: 'same-origin',
      })
      const d = await r.json()
      if (d.bars && requestId === chartRequestRef.current) {
        setData(prev => ({
          brief: prev?.brief ?? {},
          kline: d.bars.map((b: any) => ({ date: b.date, open: b.open, close: b.close, high: b.high, low: b.low, volume: b.volume })),
          tech: d.tech ?? {},
          metadata: { brief: prev?.metadata?.brief, kline: d.metadata },
          last_close: d.tech?.price ?? null,
        }))
        setErr('')
      } else if (d.detail && requestId === chartRequestRef.current) {
        setErr(d.detail)
      }
    } catch {
      if (requestId === chartRequestRef.current) setErr('周期数据加载失败')
    } finally {
      if (requestId === chartRequestRef.current) setChartLoading(false)
    }
  }, [])

  // 选中变化时加载最近 120 个交易日，避免把全部历史压进默认视图。
  useEffect(() => {
    if (!selected.code) return
    setMode('day')
    setPeriod('day')
    setMultiDay(0)
    setDayRange(120)
    setLive(false)
    load(selected.code, 'day', 0, 120)
    api.getNews(selected.code).then((n) => setNews(n.news)).catch(() => setNews([]))
    api.getIndustry(selected.code).then(setIndustry).catch(() => setIndustry(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected.code])

  // 实时轮询
  useEffect(() => {
    if (!live) return
    // 切到非日K周期时停掉轮询，避免覆盖数据
    const effectiveLive = live && period === 'day'
    if (!effectiveLive) { if (timerRef.current) window.clearInterval(timerRef.current); return }
    timerRef.current = window.setInterval(() => load(selected.code, mode, 1, dayRange), 15000)
    return () => { if (timerRef.current) window.clearInterval(timerRef.current) }
  }, [dayRange, live, mode, period, selected.code, load])

  // 搜索防抖
  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); return }
    setSearching(true)
    try {
      const r = await api.search(q.trim())
      setResults(r.results)
      // 如果只有一个结果，自动选中
      if (r.results.length === 1) {
        setSelected(r.results[0])
        setQuery(r.results[0].name)
        setResults([])
      }
    } catch { setResults([]) } finally { setSearching(false) }
  }, [])

  // 回车时：如果有搜索结果选第一个，否则搜完自动选
  const onSearchEnter = async () => {
    const q = query.trim()
    if (!q) return
    if (results.length > 0) {
      pick(results[0])
      return
    }
    setSearching(true)
    try {
      const r = await api.search(q)
      if (r.results.length > 0) {
        setSelected(r.results[0])
        setQuery(r.results[0].name)
      }
      setResults([])
    } catch { setResults([]) } finally { setSearching(false) }
  }

  const onQueryChange = (v: string) => {
    setQuery(v)
    if (searchTimer.current) window.clearTimeout(searchTimer.current)
    searchTimer.current = window.setTimeout(() => doSearch(v), 300)
  }

  const pick = (item: SearchItem) => {
    setSelected(item)
    setDefaultRank(null)
    setQuery(item.name)
    setResults([])
  }

  // 自选股点击切换：尝试用名称（拉取 brief 后再展示真实名称）
  const pickWatchlistCode = (code: string) => {
    setSelected({ market: inferMarket(code), code: stripMarket(code), name: code, type: 'GP' })
    setDefaultRank(null)
    setQuery('')
    setResults([])
  }

  const b = data?.brief as {
    name?: string; price?: number; change_pct?: number
    pe?: number; pb?: number; turnover?: number; market_cap?: number
    open?: number; pre_close?: number; high?: number; low?: number
    limit_up?: number; limit_down?: number; volume?: number; amount?: number
    volume_ratio?: number
  } | undefined
  const change = b?.change_pct ?? 0
  const bars = (data?.kline as KlineBar[])?.filter((k) => k.date && typeof k.close === 'number') ?? []
  const minute = (data?.kline as MinutePoint[])?.filter((k) => k.time && typeof k.price === 'number') ?? []
  const briefMeta = data?.metadata?.brief
  const klineMeta = data?.metadata?.kline
  const delayLabel = ({ near_realtime: '近实时', delayed: '延迟', end_of_day: '日终' } as Record<string, string>)[klineMeta?.delay ?? ''] ?? klineMeta?.delay
  const adjustmentLabel = ({ qfq: '前复权', hfq: '后复权', none: '不复权' } as Record<string, string>)[klineMeta?.adjustment ?? ''] ?? klineMeta?.adjustment

  return (
    <div className="quote-page">
      {/* 顶部：搜索栏 + 热门股（跨三栏全宽） */}
      <div className="qp-search">
        <input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && onSearchEnter()}
          placeholder="搜索股票代码 / 名称 / 拼音（如 600519 / 茅台 / maotai）"
        />
        {searching && <span className="qp-searching">搜索中...</span>}
        {results.length > 0 && (
          <div className="qp-results">
            {results.map((r) => (
              <button key={r.code} className="qp-result" onClick={() => pick(r)}>
                <span className={`qp-market m-${r.market}`}>{r.market.toUpperCase()}</span>
                <span className="qp-name">{r.name}</span>
                <span className="qp-code">{r.code}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="qp-hot">
        {hotItems.map((h) => (
          <button
            key={h.code}
            className={`qp-hot-item ${selected.code === h.code ? 'active' : ''}`}
            onClick={() => pick({ market: h.code.startsWith('hk') ? 'hk' : h.code.startsWith('us') ? 'us' : 'sh', code: h.code, name: h.name, type: 'GP' })}
          >
            {h.name}
          </button>
        ))}
      </div>

      {err && !data && <div className="error-box">{err}</div>}

      {/* 三栏主区 */}
      {data && (
        <div className="quote-grid">
          {/* ========== 左栏：自选股 ========== */}
          <aside className="qp-left">
            <WatchlistPanel
              currentCode={selected.code}
              wlVersion={wlVersion}
              onPick={pickWatchlistCode}
              onAdd={async (codeToAdd) => {
                if (!requireLogin()) return
                try {
                  const p = await api.getProfile()
                  const list = p.watchlist || []
                  const next = [...new Set([...list, codeToAdd])]
                  await api.saveProfile({ watchlist: next })
                  setWlVersion((v) => v + 1)
                } catch { /* ignore */ }
              }}
              onRemove={async (codeToRemove) => {
                if (!requireLogin()) return
                try {
                  const p = await api.getProfile()
                  const list = p.watchlist || []
                  const next = list.filter((c) => c !== codeToRemove)
                  await api.saveProfile({ watchlist: next })
                  setWlVersion((v) => v + 1)
                } catch { /* ignore */ }
              }}
            />

            {/* 行业对比：弹窗按钮 */}
            {industry && industry.peers.length > 0 && (
              <button className="qp-industry-btn" onClick={() => setShowIndustry(true)}>
                行业对比 ({industry.peers.length}只)
              </button>
            )}
          </aside>

          {/* 行业对比弹窗 */}
          {showIndustry && industry && (
            <div className="qp-modal-overlay" onClick={() => setShowIndustry(false)}>
              <div className="qp-modal" onClick={e => e.stopPropagation()}>
                <div className="qp-modal-head">
                  <span>行业对比</span>
                  <button className="qp-modal-close" onClick={() => setShowIndustry(false)}>×</button>
                </div>
                {industry.avg_pe != null && (
                  <div className="qp-modal-meta">行业均PE {industry.avg_pe} {industry.avg_pb != null && `| 均PB ${industry.avg_pb}`}</div>
                )}
                <table className="portfolio-table qp-industry-table">
                  <thead><tr><th>名称</th><th>代码</th><th>PE</th><th>PB</th><th>涨跌幅</th></tr></thead>
                  <tbody>
                    {industry.peers.map((p) => (
                      <tr key={p.code} className={p.is_target ? 'industry-target-row' : ''}>
                        <td>{p.name}</td>
                        <td className="pf-code">{p.code}</td>
                        <td>{p.pe?.toFixed(1) ?? '--'}</td>
                        <td>{p.pb?.toFixed(2) ?? '--'}</td>
                        <td className={(p.change_pct ?? 0) >= 0 ? 'up' : 'down'}>
                          {p.change_pct != null ? `${p.change_pct >= 0 ? '+' : ''}${p.change_pct.toFixed(2)}%` : '--'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ========== 中栏：标题+操作 / 周期 / K线 / 对比 ========== */}
          <main className="qp-center">
            <div className="qp-main">
              <div className="qp-head">
                <div className="qp-title">
                  <span className="qp-name">{b?.name ?? selected.name}</span>
                  <span className="qp-code">{selected.code}</span>
                  {defaultRank?.code === selected.code && <span className="qp-rank-badge" title={defaultRank.scope === 'a_share_full_market' ? 'A股全市场实时快照' : '全市场数据不可用，已降级到候选池'}>
                    {defaultRank.scope === 'a_share_full_market' ? '今日成交额第一' : '候选池成交额第一'} · {(defaultRank.amount / 1e8).toFixed(1)}亿
                  </span>}
                </div>
                <div className={`qp-price ${change >= 0 ? 'up' : 'down'}`}>
                  {b?.price ?? '--'} <small>{change >= 0 ? '+' : ''}{change}%</small>
                </div>
                <div className="qp-actions">
                  <StarButton code={selected.code} />
                  <input
                    className="compare-input"
                    placeholder="对比代码"
                    value={compareCode}
                    onChange={(e) => setCompareCode(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && compareCode.trim()) {
                        api.getQuote(compareCode.trim(), 1, 'day', 0)
                          .then((q) => setCompareData(q))
                          .catch(() => setCompareData(null))
                      }
                    }}
                  />
                  {compareData && <button className="mode-btn" onClick={() => { setCompareData(null); setCompareCode('') }}>清除对比</button>}
                  <button className={`live-btn ${live ? 'on' : ''}`} onClick={() => setLive((v) => !v)}>
                    {live ? '● 实时' : '○ 实时'}
                  </button>
                </div>
              </div>

              <div className={`data-status ${klineMeta?.fallback_used ? 'warning' : ''}`} role="status" aria-label="行情数据状态">
                <span>行情源 {briefMeta?.provider_name || '未知'}</span>
                <span>图表源 {klineMeta?.provider_name || '未知'}</span>
                {(klineMeta?.as_of || data.data_date) && <span>截至 {klineMeta?.as_of || data.data_date}</span>}
                {delayLabel && <span>时效 {delayLabel}</span>}
                {adjustmentLabel && <span>复权 {adjustmentLabel}</span>}
                {Boolean(klineMeta?.rows_dropped) && <span>清洗 {klineMeta?.rows_dropped} 行</span>}
                {klineMeta?.fallback_used && <strong>已启用备用数据源{klineMeta.fallback_reason ? `（${klineMeta.fallback_reason}）` : ''}</strong>}
              </div>

              {/* 周期切换工具栏 - 单独一行 */}
              <div className="qp-toolbar">
                <select className="period-select" value={multiDay ? `day${multiDay}` : (mode === 'minute' && !multiDay ? 'minute' : 'none')} onChange={(e) => {
                  const v = e.target.value
                  if (v === 'minute') { setMode('minute'); setPeriod(''); setMultiDay(0); load(selected.code, 'minute', 0) }
                  else if (v.startsWith('day')) { const n = parseInt(v.slice(3)); setMode('day'); setMultiDay(n); setPeriod(''); loadMultiDay(selected.code, n) }
                }}>
                  <option value="none" disabled>选择分时</option>
                  <option value="minute">分时</option>
                  <option value="day2">2日</option>
                  <option value="day3">3日</option>
                  <option value="day4">4日</option>
                  <option value="day5">5日</option>
                </select>
                <span className="toolbar-sep" />
                <button className={`mode-btn ${mode === 'day' && period === 'day' ? 'active' : ''}`} onClick={() => { setMode('day'); setPeriod('day'); setDayRange(120); load(selected.code, 'day', 0, 120) }}>日K</button>
                <button className={`mode-btn ${period === 'week' ? 'active' : ''}`} onClick={() => { setPeriod('week'); setMode('day'); loadPeriod(selected.code, 'week') }}>周K</button>
                <button className={`mode-btn ${period === 'month' ? 'active' : ''}`} onClick={() => { setPeriod('month'); setMode('day'); loadPeriod(selected.code, 'month') }}>月K</button>
                {mode === 'day' && period === 'day' && <>
                  <span className="toolbar-sep" />
                  {([
                    [30, '1月'], [60, '3月'], [120, '6月'], [250, '1年'], ['all', '全部'],
                  ] as const).map(([value, label]) => <button key={value} className={`mode-btn ${dayRange === value ? 'active' : ''}`} onClick={() => {
                    setDayRange(value); setLive(false); load(selected.code, 'day', 0, value)
                  }}>{label}</button>)}
                </>}
                <span className="toolbar-sep" />
                <button className={`mode-btn ${period === '5min' ? 'active' : ''}`} onClick={() => { setPeriod('5min'); setMode('day'); loadPeriod(selected.code, '5min') }}>5分</button>
                <button className={`mode-btn ${period === '15min' ? 'active' : ''}`} onClick={() => { setPeriod('15min'); setMode('day'); loadPeriod(selected.code, '15min') }}>15分</button>
                <button className={`mode-btn ${period === '30min' ? 'active' : ''}`} onClick={() => { setPeriod('30min'); setMode('day'); loadPeriod(selected.code, '30min') }}>30分</button>
                <button className={`mode-btn ${period === '60min' ? 'active' : ''}`} onClick={() => { setPeriod('60min'); setMode('day'); loadPeriod(selected.code, '60min') }}>60分</button>
                <span className="toolbar-sep" />
                <button className={`mode-btn ${subIndicator === 'macd' ? 'active' : ''}`} onClick={() => setSubIndicator('macd')}>MACD</button>
                <button className={`mode-btn ${subIndicator === 'kdj' ? 'active' : ''}`} onClick={() => setSubIndicator('kdj')}>KDJ</button>
                <span className="toolbar-sep" />
                <button className="mode-btn" onClick={() => setKlineFullscreen(true)}>全屏</button>
              </div>

              <div className="qp-chart">
                {chartLoading ? <div className="kline-loading">正在加载图表数据...</div> : <KLineChart
                  bars={bars}
                  minute={minute}
                  lastClose={b?.pre_close ?? data.last_close ?? null}
                  currentPrice={b?.price ?? null}
                  symbol={b?.name ?? selected.name}
                  mode={mode}
                  onMode={(m) => { setMode(m); load(selected.code, m, 0) }}
                  dataDate={data.data_date}
                  isToday={data.is_today}
                  subIndicator={subIndicator}
                  onSubIndicator={setSubIndicator}
                  fullscreen={klineFullscreen}
                  onFullscreen={setKlineFullscreen}
                />}
              </div>

              {/* 对比表格（K线下方） */}
              {compareData && compareData.brief && (() => {
                const cb = compareData.brief as any
                const rows: [string, any, any][] = [
                  ['名称', b?.name ?? selected.name, cb?.name ?? compareCode],
                  ['现价', b?.price ?? '--', cb?.price ?? '--'],
                  ['涨跌幅', `${(b?.change_pct ?? 0) >= 0 ? '+' : ''}${b?.change_pct ?? '--'}%`, `${(cb?.change_pct ?? 0) >= 0 ? '+' : ''}${cb?.change_pct ?? '--'}%`],
                  ['PE', b?.pe ?? '--', cb?.pe ?? '--'],
                  ['PB', b?.pb ?? '--', cb?.pb ?? '--'],
                  ['换手率', b?.turnover != null ? `${b.turnover}%` : '--', cb?.turnover != null ? `${cb.turnover}%` : '--'],
                  ['市值(亿)', b?.market_cap ?? '--', cb?.market_cap ?? '--'],
                ]
                return (
                  <table className="compare-table">
                    <thead><tr><th>指标</th><th>{b?.name ?? selected.name}</th><th>{cb?.name ?? compareCode}</th></tr></thead>
                    <tbody>
                      {rows.map(([label, v1, v2], i) => (
                        <tr key={i}>
                          <td className="compare-label">{label}</td>
                          <td>{v1}</td>
                          <td>{v2}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )
              })()}
            </div>
          </main>

          {/* ========== 右栏：盘口 + 资金流向 + K线形态 ========== */}
          <aside className="qp-right">
            <OrderBookPanel brief={data.brief as any} />
            <FundFlowCard code={selected.code} />
            <PatternCard code={selected.code} />
          </aside>
        </div>
      )}

      {/* 底部新闻（跨三栏全宽） */}
      {news.length > 0 && (
        <div className="qp-news">
          <div className="qp-news-head">最新新闻</div>
          {news.map((n, i) => (
            <div className="quote-news-item" key={i}>
              <span className="quote-news-time">{n.time.slice(5, 16)} · {n.source}</span>
              {n.url ? <a className="quote-news-title" href={n.url} target="_blank" rel="noreferrer">{n.title}</a> : <span className="quote-news-title">{n.title}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
