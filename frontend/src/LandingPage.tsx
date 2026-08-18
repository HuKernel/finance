import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import type { QuoteResponse } from './types'

type LandingPreview = {
  code: string
  marketLabel: string
  scopeLabel: string
  quote: QuoteResponse | null
}

type LandingBrief = {
  name?: string
  price?: number
  change_pct?: number
  pe?: number
  pb?: number
  turnover?: number
  open?: number
  high?: number
  low?: number
}

type RankingItem = {
  code: string
  name: string
  price?: number | null
  change_pct?: number | null
  amount?: number | null
}

type FlashItem = {
  title: string
  time?: string
  published_at?: string
  source?: string
  url?: string
}

type HotItem = {
  code: string
  name: string
  change_pct?: number | null
}

type SentimentItem = {
  code: string
  name: string
  change_pct?: number | null
  boards?: number | null
  reason?: string
}

type TodayDeskState = {
  flashNews: FlashItem[]
  gainers: RankingItem[]
  losers: RankingItem[]
  turnover: RankingItem[]
  hotStocks: HotItem[]
  ladder: SentimentItem[]
}

const FALLBACK_POINTS = '0,118 35,110 68,122 104,94 138,101 174,74 210,87 245,62 280,70 316,46 350,58 386,38 420,47 456,22 520,30'

function inferMarketLabel(code: string): string {
  if (code.startsWith('hk')) return '港股'
  if (code.startsWith('us')) return '美股'
  return 'A股'
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '--'
}

function formatPercent(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '--'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function formatAmountYi(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '--'
  return `${(value / 1e8).toFixed(1)}亿`
}

function shortTime(value: string | null | undefined): string {
  if (!value) return '--'
  if (/^\d{2}:\d{2}:\d{2}$/.test(value)) return value.slice(0, 5)
  if (value.length >= 16) return value.slice(5, 16)
  return value
}

function buildChartPoints(kline: QuoteResponse['kline'] | undefined): { points: string; marker: { x: number; y: number } } {
  const closes = Array.isArray(kline)
    ? kline
        .map((item) => ('close' in item && typeof item.close === 'number' ? item.close : null))
        .filter((value): value is number => value != null)
        .slice(-24)
    : []

  if (closes.length < 2) {
    return { points: FALLBACK_POINTS, marker: { x: 456, y: 22 } }
  }

  const min = Math.min(...closes)
  const max = Math.max(...closes)
  const range = Math.max(max - min, 1)
  const width = 520
  const height = 150
  const padY = 16
  const stepX = width / Math.max(closes.length - 1, 1)

  const coords = closes.map((close, index) => {
    const x = index * stepX
    const y = height - padY - ((close - min) / range) * (height - padY * 2)
    return { x, y }
  })

  const last = coords[coords.length - 1]
  return {
    points: coords.map(({ x, y }) => `${x.toFixed(0)},${y.toFixed(0)}`).join(' '),
    marker: { x: Number(last.x.toFixed(0)), y: Number(last.y.toFixed(0)) },
  }
}

function jumpToQuote(code?: string) {
  if (!code) {
    window.location.hash = '/quote'
    return
  }
  window.location.hash = `/quote?symbol=${encodeURIComponent(code)}`
}

export default function LandingPage({
  onAnalyze,
  onQuote,
}: {
  onAnalyze: () => void
  onQuote: () => void
}) {
  const [preview, setPreview] = useState<LandingPreview>({
    code: '600519',
    marketLabel: 'A股',
    scopeLabel: '首页示例',
    quote: null,
  })
  const [desk, setDesk] = useState<TodayDeskState>({
    flashNews: [],
    gainers: [],
    losers: [],
    turnover: [],
    hotStocks: [],
    ladder: [],
  })

  useEffect(() => {
    let cancelled = false

    const applyQuote = (code: string, scopeLabel: string, quote: QuoteResponse | null) => {
      if (cancelled) return
      setPreview({
        code,
        marketLabel: inferMarketLabel(code),
        scopeLabel,
        quote,
      })
    }

    const loadPreview = async () => {
      let code = '600519'
      let scopeLabel = '首页示例'

      try {
        const top = await api.getTopTurnoverStock()
        code = top.code
        scopeLabel = top.scope === 'a_share_full_market' ? '今日成交额第一' : '候选池成交额第一'
      } catch {
        // 回退到稳定示例代码，但仍尝试拉真实行情。
      }

      try {
        const quote = await api.getQuote(code, 60, 'day', 0)
        applyQuote(code, scopeLabel, quote)
      } catch {
        if (code === '600519') return
        try {
          const fallback = await api.getQuote('600519', 60, 'day', 0)
          applyQuote('600519', '首页示例', fallback)
        } catch {
          // 保留默认静态占位布局。
        }
      }
    }

    const loadDesk = async () => {
      try {
        const [rankings, flash, hot, sentiment] = await Promise.all([
          api.get<{ gainers?: RankingItem[]; losers?: RankingItem[]; turnover?: RankingItem[] }>('/api/market/rankings'),
          api.get<{ news?: FlashItem[] }>('/api/news/flash?limit=6'),
          api.getHotStocks(),
          api.get<{ ladder?: SentimentItem[] }>('/api/market/sentiment'),
        ])
        if (cancelled) return
        setDesk({
          gainers: rankings.gainers || [],
          losers: rankings.losers || [],
          turnover: rankings.turnover || [],
          flashNews: flash.news || [],
          hotStocks: hot || [],
          ladder: sentiment.ladder || [],
        })
      } catch {
        if (cancelled) return
      }
    }

    const load = async () => {
      await Promise.all([loadPreview(), loadDesk()])
    }

    load()
    const timer = window.setInterval(load, 60000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  const brief = (preview.quote?.brief as LandingBrief | undefined) ?? {}
  const symbolName = brief.name || '贵州茅台'
  const statusText = preview.quote?.is_today ? 'near realtime' : 'market snapshot'
  const providerName = preview.quote?.metadata?.brief?.provider_name || preview.quote?.metadata?.kline?.provider_name || '--'
  const updateAt = preview.quote?.metadata?.brief?.as_of || preview.quote?.metadata?.kline?.as_of || preview.quote?.data_date || '--'
  const chart = useMemo(() => buildChartPoints(preview.quote?.kline), [preview.quote?.kline])
  const metrics = [
    { label: '开盘', value: formatNumber(brief.open) },
    { label: '最高', value: formatNumber(brief.high) },
    { label: '最低', value: formatNumber(brief.low) },
  ]

  const focusCards = [
    {
      key: 'turnover',
      label: '成交额龙头',
      item: desk.turnover[0],
      foot: desk.turnover[0] ? `成交额 ${formatAmountYi(desk.turnover[0].amount)}` : '市场主线强弱参考',
    },
    {
      key: 'gainers',
      label: '涨幅居前',
      item: desk.gainers[0],
      foot: desk.gainers[0] ? `现价 ${formatNumber(desk.gainers[0].price)}` : '追踪最强方向',
    },
    {
      key: 'losers',
      label: '跌幅居前',
      item: desk.losers[0],
      foot: desk.losers[0] ? `现价 ${formatNumber(desk.losers[0].price)}` : '观察风险释放',
    },
    {
      key: 'ladder',
      label: '连板焦点',
      item: desk.ladder[0],
      foot: desk.ladder[0] ? `${desk.ladder[0].boards || 0} 板 · ${desk.ladder[0].reason || '题材跟踪'}` : '查看情绪高度',
    },
  ]

  return (
    <article className="landing-page">
      <section className="landing-hero" aria-labelledby="landing-title">
        <div>
          <span className="landing-kicker">AI 驱动的个人投研工作台 / RESEARCH OS</span>
          <h1 id="landing-title">先看证据，再做判断。</h1>
          <p>
            FinanceCrew 把盘面、财务、新闻、技术面与市场情绪放进同一张研究工作台，
            让你先快速看到今天最值得研究的方向，再进入深度分析与持续跟踪。
          </p>
          <div className="landing-actions">
            <button className="research-primary" onClick={onAnalyze}>开始智能投研</button>
            <button className="ghost" onClick={onQuote}>查看实时行情</button>
          </div>
          <small>支持 A 股、港股与美股研究 · 结果仅供研究参考，不构成投资建议</small>
          <div className="landing-trust-strip" aria-label="产品特性">
            <span>今日工作台</span>
            <span>多角色交叉验证</span>
            <span>研究记录可复盘</span>
          </div>
        </div>
        <div className="landing-terminal" aria-label="研究终端预览">
          <div className="landing-terminal-head">
            <strong>RESEARCH / {preview.code}</strong>
            <span className="landing-terminal-status">{statusText}</span>
          </div>
          <div className="landing-terminal-body">
            <div className="landing-terminal-tape" aria-hidden="true">
              <span>市场: {preview.marketLabel}</span>
              <span>来源: {providerName}</span>
              <span>更新: {updateAt}</span>
            </div>
            <div className="landing-symbol"><strong>{symbolName} · {preview.code}</strong><span>{formatPercent(brief.change_pct)}</span></div>
            <svg className="landing-chart" viewBox="0 0 520 150" role="img" aria-label="股票走势预览" preserveAspectRatio="none">
              <polyline points={chart.points} />
              <circle cx={chart.marker.x} cy={chart.marker.y} r="4" />
            </svg>
            <div className="landing-metrics">
              <div><span>现价</span><strong>{formatNumber(brief.price)}</strong></div>
              <div><span>涨跌幅</span><strong>{formatPercent(brief.change_pct)}</strong></div>
              <div><span>定位</span><strong>{preview.scopeLabel}</strong></div>
            </div>
            <div className="landing-agents">
              {metrics.map((item) => <div key={item.label}><span>{item.label}</span><strong>{item.value}</strong></div>)}
            </div>
          </div>
        </div>
      </section>

      <section className="landing-section" aria-labelledby="landing-desk-title">
        <div className="landing-section-head">
          <div>
            <span className="landing-kicker">TODAY DESK</span>
            <h2 id="landing-desk-title">今天先看什么，系统先帮你排好。</h2>
          </div>
          <button className="ghost" onClick={() => jumpToQuote(preview.code)}>查看当前标的</button>
        </div>
        <div className="landing-focus-grid">
          {focusCards.map((card) => (
            <button key={card.key} className="landing-focus-card" onClick={() => jumpToQuote(card.item?.code)}>
              <span className="landing-focus-label">{card.label}</span>
              <strong>{card.item?.name || '--'}</strong>
              <div className={`landing-focus-change ${(card.item?.change_pct ?? 0) >= 0 ? 'up' : 'down'}`}>
                {formatPercent(card.item?.change_pct)}
              </div>
              <p>{card.foot}</p>
            </button>
          ))}
        </div>
        <div className="landing-quick-actions">
          <button className="landing-quick-action" onClick={() => { window.location.hash = `#/analyze?symbol=${encodeURIComponent(preview.code)}&topic=${encodeURIComponent('短线异动值不值得追？')}` }}>
            <span>立即研究</span>
            <strong>直接进入深度投研</strong>
            <p>带着当前盘面关注点，生成多角色研究报告。</p>
          </button>
          <button className="landing-quick-action" onClick={onQuote}>
            <span>盘中看盘</span>
            <strong>进入完整行情工作台</strong>
            <p>K 线、分时、对比、资金流、行业与形态集中查看。</p>
          </button>
          <button className="landing-quick-action" onClick={() => { window.location.hash = '/market' }}>
            <span>全市场扫描</span>
            <strong>查看板块、榜单与快讯</strong>
            <p>把热点、异动、北向、融资融券和条件选股放到一页里。</p>
          </button>
        </div>
      </section>

      <section className="landing-section landing-desk-panels" aria-labelledby="landing-panels-title">
        <div>
          <span className="landing-kicker">HOT LIST</span>
          <h2 id="landing-panels-title">重点观察清单</h2>
          <div className="landing-watchlist">
            {desk.hotStocks.slice(0, 6).map((item) => (
              <button key={item.code} className="landing-watch-item" onClick={() => jumpToQuote(item.code)}>
                <div>
                  <strong>{item.name}</strong>
                  <span>{item.code}</span>
                </div>
                <em className={(item.change_pct ?? 0) >= 0 ? 'up' : 'down'}>{formatPercent(item.change_pct)}</em>
              </button>
            ))}
            {desk.hotStocks.length === 0 && <div className="empty">暂无热门股票数据</div>}
          </div>
        </div>
        <div>
          <span className="landing-kicker">FLASH NEWS</span>
          <h2>快讯雷达</h2>
          <div className="landing-flash-list">
            {desk.flashNews.slice(0, 6).map((item, index) => (
              <a key={`${item.title}-${index}`} className="landing-flash-item" href={item.url || undefined} target={item.url ? '_blank' : undefined} rel={item.url ? 'noreferrer' : undefined}>
                <span>{shortTime(item.published_at || item.time)}</span>
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.source || '快讯'}</p>
                </div>
              </a>
            ))}
            {desk.flashNews.length === 0 && <div className="empty">暂无快讯数据</div>}
          </div>
        </div>
      </section>

      <section className="landing-section landing-flow" aria-labelledby="landing-flow">
        <span className="landing-kicker">RESEARCH LOOP / 03 STEPS</span>
        <h2 id="landing-flow">看到机会后，用三步走完整个研究闭环。</h2>
        <ol>
          <li><span>01</span><div><strong>先看今天最活跃的方向</strong><p>用今日工作台快速锁定强势题材、成交额核心股和关键快讯。</p></div></li>
          <li><span>02</span><div><strong>再进入深度投研</strong><p>多角色分析师围绕同一标的交叉验证，输出共识、风控和交易计划。</p></div></li>
          <li><span>03</span><div><strong>把判断沉淀下来</strong><p>把结果转成投资论文、预警和定时分析，让后续跟踪自动跑起来。</p></div></li>
        </ol>
      </section>

      <section className="landing-cta" aria-labelledby="landing-cta">
        <div><span className="landing-kicker">START WITH A TICKER</span><h2 id="landing-cta">让每一次研究，都留下可验证的依据。</h2></div>
        <button className="research-primary" onClick={onAnalyze}>进入投研工作台</button>
      </section>
    </article>
  )
}
