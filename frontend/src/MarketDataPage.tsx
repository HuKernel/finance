import { useEffect, useState, useCallback } from 'react'
import { api } from './api'

// ============== 类型定义 ==============
type PageTab = 'sector' | 'sentiment' | 'radar' | 'ranking' | 'screener' | 'margin' | 'north'
type SectorType = 'concept' | 'industry'

interface Sector {
  code: string
  name: string
  change_pct: number | null
  turnover: number | null
  main_net_inflow: number | null
  main_net_pct: number | null
  leading_stock: string
  leading_code: string
}

interface Stock {
  code: string
  name: string
  price: number | null
  change_pct: number | null
  pe: number | null
  pb: number | null
  turnover: number | null
  market_cap: number | null
  negotiable_cap: number | null
}

interface MarginRow {
  exchange: string
  code: string
  name: string
  margin_balance: number | null
  margin_buy: number | null
  margin_repay: number | null
  short_volume: number | null
  short_sell: number | null
  short_repay: number | null
}

// ============== 工具函数 ==============
const fmtNum = (v: number | null | undefined, digits = 2): string => {
  if (v === null || v === undefined || v !== v) return '—'
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}
const fmtPct = (v: number | null | undefined): string => {
  if (v === null || v === undefined || v !== v) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}
const pctClass = (v: number | null | undefined): string => {
  if (v === null || v === undefined || v !== v) return ''
  return v >= 0 ? 'up' : 'down'
}
// 金额（元）-> 亿
const fmtYi = (v: number | null | undefined): string => {
  if (v === null || v === undefined || v !== v) return '—'
  const yi = v / 1e8
  return fmtNum(yi, 2)
}
// 万元 -> 亿
// 股数 -> 万股
const fmtWanGu = (v: number | null | undefined): string => {
  if (v === null || v === undefined || v !== v) return '—'
  return fmtNum(v / 1e4, 2)
}
const fmtYiCap = (v: number | null | undefined): string => {
  if (v === null || v === undefined || v !== v) return '—'
  return fmtNum(v, 2)
}

// ============== 主组件 ==============
export default function MarketDataPage() {
  const [tab, setTab] = useState<PageTab>('sector')
  const [focus, setFocus] = useState<{
    turnover: any | null
    leader: any | null
    ladder: any | null
    flash: any | null
  }>({ turnover: null, leader: null, ladder: null, flash: null })

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [rankings, sentiment, flash] = await Promise.all([
          api.get<any>('/api/market/rankings'),
          api.get<any>('/api/market/sentiment'),
          api.get<any>('/api/news/flash?limit=5'),
        ])
        if (cancelled) return
        setFocus({
          turnover: rankings?.turnover?.[0] || null,
          leader: rankings?.gainers?.[0] || null,
          ladder: sentiment?.ladder?.[0] || null,
          flash: flash?.news?.[0] || null,
        })
      } catch {
        if (cancelled) return
      }
    })()
    return () => { cancelled = true }
  }, [])

  const openQuote = (code?: string) => {
    if (!code) return
    window.location.hash = `#/quote?symbol=${encodeURIComponent(code)}`
  }

  const focusCards = [
    {
      label: '成交额核心',
      title: focus.turnover?.name || '--',
      sub: focus.turnover?.code || '今日最受关注的成交额龙头',
      value: focus.turnover ? `${fmtPct(focus.turnover.change_pct)} · ${fmtYi(focus.turnover.amount)}亿` : '—',
      onClick: () => openQuote(focus.turnover?.code),
    },
    {
      label: '涨幅龙头',
      title: focus.leader?.name || '--',
      sub: focus.leader?.code || '强势方向温度计',
      value: focus.leader ? `${fmtPct(focus.leader.change_pct)} · ${fmtNum(focus.leader.price)}` : '—',
      onClick: () => openQuote(focus.leader?.code),
    },
    {
      label: '连板高度',
      title: focus.ladder?.name || '--',
      sub: focus.ladder?.code || '情绪高度代表',
      value: focus.ladder ? `${focus.ladder.boards || 0}板 · ${focus.ladder.reason || '题材跟踪'}` : '—',
      onClick: () => openQuote(focus.ladder?.code),
    },
    {
      label: '快讯焦点',
      title: focus.flash?.source || '快讯',
      sub: focus.flash?.published_at || focus.flash?.time || '最新消息',
      value: focus.flash?.title || '—',
      onClick: () => setTab('radar'),
    },
  ]

  const marketLine = focus.leader?.name && focus.ladder?.name
    ? `${focus.leader.name} 领涨、${focus.ladder.name} 维持情绪高度；先观察成交额核心是否同步，避免只追单一强势股。`
    : '等待板块、资金和情绪数据齐全后生成今日主线判断。'
  const marketLineTone = focus.leader?.change_pct >= 5 && focus.ladder?.boards >= 3 ? 'strong' : focus.leader?.change_pct < 0 ? 'weak' : 'neutral'

  return (
    <div className="pane">
      <div className="pane-head">
        <h2>市场数据</h2>
        <div className="tabs">
          <button className={tab === 'sector' ? 'active' : ''} onClick={() => setTab('sector')}>板块轮动</button>
          <button className={tab === 'sentiment' ? 'active' : ''} onClick={() => setTab('sentiment')}>市场情绪</button>
          <button className={tab === 'radar' ? 'active' : ''} onClick={() => setTab('radar')}>资讯雷达</button>
          <button className={tab === 'ranking' ? 'active' : ''} onClick={() => setTab('ranking')}>全市场榜单</button>
          <button className={tab === 'screener' ? 'active' : ''} onClick={() => setTab('screener')}>条件选股</button>
          <button className={tab === 'margin' ? 'active' : ''} onClick={() => setTab('margin')}>融资融券</button>
          <button className={tab === 'north' ? 'active' : ''} onClick={() => setTab('north')}>北向资金</button>
        </div>
      </div>

      <div className={`mkt-line-summary ${marketLineTone}`}>
        <div><span>今日主线研判</span><strong>{marketLine}</strong></div>
        <div className="mkt-line-tags"><span>成交额</span><span>涨幅</span><span>情绪高度</span></div>
      </div>

      <div className="mkt-focus-grid">
        {focusCards.map((card) => (
          <button key={card.label} className="mkt-focus-card" onClick={card.onClick}>
            <span>{card.label}</span>
            <strong>{card.title}</strong>
            <em>{card.sub}</em>
            <p>{card.value}</p>
          </button>
        ))}
      </div>

      {tab === 'sector' && <SectorTab />}
      {tab === 'sentiment' && <SentimentTab />}
      {tab === 'radar' && <RadarTab />}
      {tab === 'ranking' && <RankingTab />}
      {tab === 'screener' && <ScreenerTab />}
      {tab === 'margin' && <MarginTab />}
      {tab === 'north' && <NorthTab />}
    </div>
  )
}

function SentimentTab() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    setLoading(true); setError('')
    try { setData(await api.get('/api/market/sentiment')) }
    catch (e: any) { setError(e.message || '市场情绪加载失败') }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])
  return <>
    <div className="backtest-controls"><button className="btn-primary" onClick={load} disabled={loading}>{loading ? '刷新中...' : '刷新'}</button></div>
    <StatusBar loading={loading} error={error} />
    {!loading && !error && data && <>
      <div className="mkt-pools-grid">
        {(data.pools || []).map((pool: any) => <div key={pool.name} className="backtest-trades">
          <h4>{pool.name}{!pool.available ? '（暂不可用）' : !pool.items?.length ? '（今日暂无）' : ''}</h4>
          {(pool.items || []).slice(0, 10).map((item: any) => <div key={item.code} className="mkt-pool-item">
            <span className="pf-code">{item.code}</span><span>{item.name}</span><span className={`mkt-pct ${pctClass(item.change_pct)}`}>{fmtPct(item.change_pct)}</span>
          </div>)}
          {!pool.items?.length && <div className="empty">暂无数据</div>}
        </div>)}</div>
      <div className="backtest-trades mkt-stack"><h4>连板梯队</h4>
        {(data.ladder || []).map((item: any) => <span key={item.code} className="pf-code mkt-ladder-chip">{item.name} {item.boards}板</span>)}
        {!data.ladder?.length && <div className="empty">暂无连板数据</div>}
      </div>
      <div className="backtest-trades mkt-stack"><h4>近期龙虎榜</h4><table className="portfolio-table"><thead><tr><th>代码</th><th>名称</th><th>上榜日</th><th>原因</th><th>净买额</th></tr></thead><tbody>
        {(data.lhb || []).map((item: any) => <tr key={`${item.code}-${item.date}`}><td className="pf-code">{item.code}</td><td>{item.name}</td><td>{item.date}</td><td>{item.reason}</td><td>{item.net_buy?.toLocaleString?.() ?? '—'}</td></tr>)}
        {!data.lhb?.length && <tr><td className="empty-row" colSpan={5}>暂无数据</td></tr>}</tbody></table></div>
    </>}
  </>
}

function RadarTab() {
  const [news, setNews] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    setLoading(true); setError('')
    try { setNews((await api.get<any>('/api/news/flash?limit=30')).news || []) }
    catch (e: any) { setError(e.message || '资讯雷达加载失败') }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])
  const sources = [...new Set(news.map(item => item.source))]
  return <><div className="backtest-controls"><button className="btn-primary" onClick={load} disabled={loading}>{loading ? '刷新中...' : '刷新快讯'}</button>{sources.map(source => <span key={source} className="pf-code">{source}</span>)}</div><StatusBar loading={loading} error={error} />
    {!loading && !error && <div className="backtest-trades">{news.map((item, i) => <div key={item.url || i} className="mkt-news-item">
      <div className="mkt-news-meta">{item.published_at || item.time} · {item.source}</div>
      {item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a> : <span>{item.title}</span>}
    </div>)}{!news.length && <div className="empty">暂无快讯</div>}</div>}</>
}

function RankingTab() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    setLoading(true); setError('')
    try { setData(await api.get('/api/market/rankings')) }
    catch (e: any) { setError(e.message || '全市场榜单加载失败') }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])
  const table = (title: string, items: any[]) => <div className="backtest-trades"><h4>{title}</h4><table className="portfolio-table"><thead><tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>成交额(元)</th></tr></thead><tbody>
    {items?.map(item => <tr key={item.code}><td className="pf-code">{item.code}</td><td>{item.name}</td><td>{fmtNum(item.price)}</td><td className={pctClass(item.change_pct)}>{fmtPct(item.change_pct)}</td><td>{item.amount?.toLocaleString?.() ?? '—'}</td></tr>)}
    {!items?.length && <tr><td className="empty-row" colSpan={5}>暂无数据</td></tr>}</tbody></table></div>
  return <><div className="backtest-controls"><button className="btn-primary" onClick={load} disabled={loading}>{loading ? '刷新中...' : '刷新榜单'}</button></div><StatusBar loading={loading} error={error} />
    {!loading && !error && data && <div className="mkt-rank-grid">{table('涨幅榜', data.gainers)}{table('跌幅榜', data.losers)}{table('成交额榜', data.turnover)}</div>}</>
}

// ============== 通用状态条 ==============
function StatusBar({ loading, error }: { loading: boolean; error: string }) {
  if (loading) return <div className="loading loading-center">加载中...</div>
  if (error) return <div className="alert-error mkt-error">{error}</div>
  return null
}

// ============== Tab1: 板块轮动 ==============
function SectorTab() {
  const [type, setType] = useState<SectorType>('concept')
  const [sectors, setSectors] = useState<Sector[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const url = type === 'concept' ? '/api/sectors/concepts?limit=20' : '/api/sectors/industries?limit=20'
      const d = await api.get<any>(url)
      if (d.error) { setError(d.error); setSectors([]); return }
      setSectors(d.sectors || [])
    } catch (e: any) { setError(e.message || '加载失败'); setSectors([]) }
    finally { setLoading(false) }
  }, [type])

  useEffect(() => { load() }, [load])

  // 板块轮动30秒自动刷新
  const [autoRefresh, setAutoRefresh] = useState(true)
  useEffect(() => {
    if (!autoRefresh) return
    const t = window.setInterval(() => load(), 30000)
    return () => window.clearInterval(t)
  }, [autoRefresh, load])

  return (
    <>
      <div className="tabs">
        <button className={type === 'concept' ? 'active' : ''} onClick={() => setType('concept')}>概念板块</button>
        <button className={type === 'industry' ? 'active' : ''} onClick={() => setType('industry')}>行业板块</button>
        <button className={autoRefresh ? 'active tabs-right' : 'tabs-right'} onClick={() => setAutoRefresh(v => !v)}>
          {autoRefresh ? '● 自动刷新' : '○ 自动刷新'}
        </button>
      </div>

      <StatusBar loading={loading} error={error} />

      {!loading && !error && (
        <table className="portfolio-table">
          <thead>
            <tr>
              <th className="mkt-col-rank">排名</th>
              <th>板块名称</th>
              <th>涨跌幅</th>
              <th>换手率</th>
              <th>主力净流入(亿)</th>
              <th>领涨股</th>
            </tr>
          </thead>
          <tbody>
            {sectors.length === 0 && (
              <tr><td className="empty-row" colSpan={6}>暂无数据</td></tr>
            )}
            {sectors.map((s, i) => (
              <tr key={s.code || i}>
                <td className="cell-code">{i + 1}</td>
                <td className="pf-name">{s.name}<span className="pf-code">{s.code}</span></td>
                <td className={`cell-mono ${pctClass(s.change_pct)}`}>{fmtPct(s.change_pct)}</td>
                <td className="cell-mono">{fmtNum(s.turnover, 2)}%</td>
                <td className="cell-mono">{fmtNum(s.main_net_inflow, 2)}</td>
                <td>{s.leading_stock || '—'}{s.leading_code && <span className="pf-code">{s.leading_code}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

// ============== Tab2: 条件选股 ==============
function ScreenerTab() {
  const [peMin, setPeMin] = useState('')
  const [peMax, setPeMax] = useState('')
  const [pbMin, setPbMin] = useState('')
  const [pbMax, setPbMax] = useState('')
  const [chgMin, setChgMin] = useState('')
  const [chgMax, setChgMax] = useState('')
  const [sortBy, setSortBy] = useState('change_pct')
  const [sortDesc, setSortDesc] = useState(true)
  const [stocks, setStocks] = useState<Stock[]>([])
  const [totalMarket, setTotalMarket] = useState<number | null>(null)
  const [matched, setMatched] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [hasResult, setHasResult] = useState(false)
  const [limit, setLimit] = useState('50')

  const screen = async () => {
    setLoading(true); setError('')
    try {
      const p = new URLSearchParams()
      p.set('limit', limit || '50')
      if (peMin) p.set('pe_min', peMin)
      if (peMax) p.set('pe_max', peMax)
      if (pbMin) p.set('pb_min', pbMin)
      if (pbMax) p.set('pb_max', pbMax)
      if (chgMin) p.set('change_pct_min', chgMin)
      if (chgMax) p.set('change_pct_max', chgMax)
      p.set('sort_by', sortBy)
      p.set('sort_desc', sortDesc ? 'true' : 'false')
      const d = await api.get<any>(`/api/screener?${p.toString()}`)
      if (d.error) { setError(d.error); return }
      setStocks(d.stocks || [])
      setTotalMarket(d.total_market ?? null)
      setMatched(d.matched ?? null)
      setHasResult(true)
    } catch (e: any) { setError(e.message || '筛选失败') }
    finally { setLoading(false) }
  }

  return (
    <>
      <div className="backtest-controls">
        <label className="bt-param-item">
          <span>PE</span>
          <input className="bt-param-input bt-param-input-wide" type="number" placeholder="最小" value={peMin} onChange={e => setPeMin(e.target.value)} />
          <span>~</span>
          <input className="bt-param-input bt-param-input-wide" type="number" placeholder="最大" value={peMax} onChange={e => setPeMax(e.target.value)} />
        </label>
        <label className="bt-param-item">
          <span>PB</span>
          <input className="bt-param-input bt-param-input-wide" type="number" placeholder="最小" value={pbMin} onChange={e => setPbMin(e.target.value)} />
          <span>~</span>
          <input className="bt-param-input bt-param-input-wide" type="number" placeholder="最大" value={pbMax} onChange={e => setPbMax(e.target.value)} />
        </label>
        <label className="bt-param-item">
          <span>涨跌幅%</span>
          <input className="bt-param-input bt-param-input-wide" type="number" placeholder="最小" value={chgMin} onChange={e => setChgMin(e.target.value)} />
          <span>~</span>
          <input className="bt-param-input bt-param-input-wide" type="number" placeholder="最大" value={chgMax} onChange={e => setChgMax(e.target.value)} />
        </label>
        <select className="alert-select flex-fix select-sort" value={sortBy} onChange={e => setSortBy(e.target.value)}>
          <option value="change_pct">排序: 涨跌幅</option>
          <option value="turnover">排序: 换手率</option>
          <option value="pe">排序: PE</option>
          <option value="pb">排序: PB</option>
          <option value="market_cap">排序: 市值</option>
        </select>
        <select className="alert-select flex-fix select-order" value={sortDesc ? 'desc' : 'asc'} onChange={e => setSortDesc(e.target.value === 'desc')}>
          <option value="desc">降序</option>
          <option value="asc">升序</option>
        </select>
        <label className="bt-param-item">
          <span>显示</span>
          <input className="bt-param-input" type="number" value={limit} onChange={e => setLimit(e.target.value)} />
          <span>只</span>
        </label>
        <button className="btn-primary" onClick={screen} disabled={loading}>{loading ? '筛选中...' : '筛选'}</button>
      </div>

      {hasResult && (
        <div className="mkt-screen-summary">
          共 {totalMarket ?? '—'} 只 | 筛选出 {matched ?? '—'} 只 | 显示 {stocks.length} 只
        </div>
      )}

      <StatusBar loading={loading} error={error} />

      {!loading && !error && hasResult && (
        <table className="portfolio-table">
          <thead>
            <tr>
              <th>代码</th>
              <th>名称</th>
              <th>最新价</th>
              <th>涨跌幅</th>
              <th>PE</th>
              <th>PB</th>
              <th>换手率</th>
              <th>市值(亿)</th>
            </tr>
          </thead>
          <tbody>
            {stocks.length === 0 && (
              <tr><td className="empty-row" colSpan={8}>无符合条件的股票</td></tr>
            )}
            {stocks.map((s, i) => (
              <tr key={s.code || i}>
                <td className="cell-code">{s.code}</td>
                <td className="pf-name">{s.name}</td>
                <td className="cell-mono">{fmtNum(s.price, 2)}</td>
                <td className={`cell-mono ${pctClass(s.change_pct)}`}>{fmtPct(s.change_pct)}</td>
                <td className="cell-mono">{fmtNum(s.pe, 2)}</td>
                <td className="cell-mono">{fmtNum(s.pb, 2)}</td>
                <td className="cell-mono">{fmtNum(s.turnover, 2)}%</td>
                <td className="cell-mono">{fmtYiCap(s.market_cap)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

// ============== Tab3: 融资融券 ==============
function MarginTab() {
  const today = new Date()
  const yesterday = new Date(today.getTime() - 86400000)
  const defaultDate = yesterday.toISOString().slice(0, 10).replace(/-/g, '')
  const [dateInput, setDateInput] = useState(yesterday.toISOString().slice(0, 10))
  const [marginTop, setMarginTop] = useState<MarginRow[]>([])
  const [shortTop, setShortTop] = useState<MarginRow[]>([])
  const [actDate, setActDate] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [hasResult, setHasResult] = useState(false)

  const query = async () => {
    setLoading(true); setError('')
    try {
      const d8 = dateInput.replace(/-/g, '') || defaultDate
      const d = await api.get<any>(`/api/margin/top?date=${d8}&limit=20`)
      if (d.error) { setError(d.error); return }
      setMarginTop(d.margin_top || [])
      setShortTop(d.short_top || [])
      setActDate(d.date || d8)
      setHasResult(true)
    } catch (e: any) { setError(e.message || '查询失败') }
    finally { setLoading(false) }
  }

  return (
    <>
      <div className="backtest-controls">
        <label className="bt-param-item">
          <span>日期</span>
          <input className="alert-input flex-fix input-date-fix" type="date" value={dateInput} onChange={e => setDateInput(e.target.value)} />
        </label>
        <button className="btn-primary" onClick={query} disabled={loading}>{loading ? '查询中...' : '查询'}</button>
      </div>

      <StatusBar loading={loading} error={error} />

      {!loading && !error && hasResult && (
        <>
          {actDate && <div className="mkt-date-note">日期：{actDate}</div>}
          <div className="mkt-margin-grid">
            <div>
              <h4 className="mkt-block-title">融资余额 TOP20</h4>
              <table className="portfolio-table">
                <thead>
                  <tr>
                    <th>代码</th>
                    <th>名称</th>
                    <th>融资余额(亿)</th>
                    <th>融资买入额(亿)</th>
                    <th>融券余量(万股)</th>
                  </tr>
                </thead>
                <tbody>
                  {marginTop.length === 0 && <tr><td className="empty-row" colSpan={5}>暂无数据</td></tr>}
                  {marginTop.map((r, i) => (
                    <tr key={(r.exchange || '') + r.code + i}>
                      <td className="cell-code">{r.code}</td>
                      <td className="pf-name">{r.name}</td>
                      <td className="cell-mono">{fmtYi(r.margin_balance)}</td>
                      <td className="cell-mono">{fmtYi(r.margin_buy)}</td>
                      <td className="cell-mono">{fmtWanGu(r.short_volume)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div>
              <h4 className="mkt-block-title">融券余量 TOP20</h4>
              <table className="portfolio-table">
                <thead>
                  <tr>
                    <th>代码</th>
                    <th>名称</th>
                    <th>融券余量(万股)</th>
                    <th>融券卖出量(万股)</th>
                    <th>融资余额(亿)</th>
                  </tr>
                </thead>
                <tbody>
                  {shortTop.length === 0 && <tr><td className="empty-row" colSpan={5}>暂无数据</td></tr>}
                  {shortTop.map((r, i) => (
                    <tr key={(r.exchange || '') + r.code + i}>
                      <td className="cell-code">{r.code}</td>
                      <td className="pf-name">{r.name}</td>
                      <td className="cell-mono">{fmtWanGu(r.short_volume)}</td>
                      <td className="cell-mono">{fmtWanGu(r.short_sell)}</td>
                      <td className="cell-mono">{fmtYi(r.margin_balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </>
  )
}

// ============== Tab4: 北向资金 ==============
function NorthTab() {
  const [market, setMarket] = useState<'沪股通' | '深股通'>('沪股通')
  const [topStocks, setTopStocks] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const query = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const ts = await api.get<any>(`/api/north-flow/top-stocks?market=${market}&period=5日排行`)
      if (ts.error) { setError('数据源不可用'); return }
      setTopStocks(ts.top || [])
    } catch (e: any) { setError(e.message || '查询失败') }
    finally { setLoading(false) }
  }, [market])

  useEffect(() => { query() }, [query])

  // 北向排行30秒自动刷新
  const [autoRefresh, setAutoRefresh] = useState(true)
  useEffect(() => {
    if (!autoRefresh) return
    const t = window.setInterval(() => {
      // 只刷新排行数据，不刷新个股历史
      api.get<any>(`/api/north-flow/top-stocks?market=${market}&period=5日排行`).then(ts => {
        if (!ts.error) setTopStocks(ts.top || [])
      }).catch(() => {})
    }, 30000)
    return () => window.clearInterval(t)
  }, [autoRefresh, market])

  return (
    <>
      <div className="backtest-controls">
        <button className={`mode-btn flex-fix ${autoRefresh ? 'active' : ''}`} onClick={() => setAutoRefresh(v => !v)}>
          {autoRefresh ? '● 排行自动刷新' : '○ 排行自动刷新'}
        </button>
      </div>

      <StatusBar loading={loading} error={error} />

      {!loading && !error && (
        <>
          <div className="mkt-note">
            注：2024年8月起港交所停止实时披露北向资金明细，以下为沪深股通成份股实时资金排行数据
          </div>

          {/* 北向持股排行 */}
          <div className="backtest-trades">
            <h4 className="mkt-head-gap">
              {market} 北向持股排行（5日资金净流入TOP20）
              <button className="mode-btn mkt-switch-btn"
                onClick={() => { const m = market === '沪股通' ? '深股通' : '沪股通'; setMarket(m); setTimeout(() => query(), 0) }}>
                切换到{market === '沪股通' ? '深股通' : '沪股通'}
              </button>
            </h4>
            <table className="portfolio-table">
              <thead>
                <tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>主力净流入(亿)</th><th>持股比例</th></tr>
              </thead>
              <tbody>
                {topStocks.length === 0 && <tr><td className="empty-row" colSpan={6}>暂无数据</td></tr>}
                {topStocks.map((s: any, i: number) => (
                  <tr key={i}>
                    <td className="pf-code">{s.code}</td>
                    <td>{s.name}</td>
                    <td className="cell-mono">{s.price ?? '—'}</td>
                    <td className={`cell-mono ${pctClass(s.change_pct)}`}>
                      {s.change_pct != null ? fmtNum(s.change_pct, 2) + '%' : '—'}
                    </td>
                    <td className="cell-mono">{s.net_inflow != null ? fmtNum(s.net_inflow / 1e8, 2) : '—'}</td>
                    <td className="cell-mono">{s.hold_pct != null ? fmtNum(s.hold_pct, 2) + '%' : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  )
}
