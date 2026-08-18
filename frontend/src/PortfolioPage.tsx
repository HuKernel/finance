import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { useModal } from './Modal'
import type { PortfolioPosition, PortfolioSummary, TransactionItem } from './types'

function toMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return value.toLocaleString()
}

function openAnalyze(symbol: string, topic = '这只持仓现在适合继续持有吗？') {
  window.location.hash = `#/analyze?symbol=${encodeURIComponent(symbol)}&topic=${encodeURIComponent(topic)}`
}

function openQuote(symbol: string) {
  window.location.hash = `#/quote?symbol=${encodeURIComponent(symbol)}`
}

function openBacktest(symbol: string) {
  window.location.hash = `#/backtest?symbol=${encodeURIComponent(symbol)}`
}

// 投资组合页面
export default function PortfolioPage() {
  const { toast, confirm } = useModal()
  const [positions, setPositions] = useState<PortfolioPosition[]>([])
  const [summary, setSummary] = useState<PortfolioSummary | null>(null)
  const [transactions, setTransactions] = useState<TransactionItem[]>([])
  const [events, setEvents] = useState<{ symbol: string; name: string; period: string; date: string; status: string }[]>([])
  const [loadError, setLoadError] = useState('')
  const [eventsError, setEventsError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [view, setView] = useState<'holdings' | 'history'>('holdings')

  const load = async () => {
    try {
      setLoadError('')
      const [p, t] = await Promise.all([api.getPortfolio(), api.getTransactions()])
      setPositions(p.positions)
      setSummary(p.summary)
      setTransactions(t)
    } catch (error) { setLoadError(error instanceof Error ? error.message : '组合数据加载失败') }
  }

  useEffect(() => { load() }, [])
  useEffect(() => {
    api.getCompanyEvents()
      .then(result => setEvents(result.items))
      .catch(error => setEventsError(error instanceof Error ? error.message : '公司事件加载失败'))
  }, [])

  // 15秒定时刷新盈亏
  useEffect(() => {
    const timer = setInterval(load, 15000)
    return () => clearInterval(timer)
  }, [])

  const exposure = useMemo(() => {
    const total = summary?.total_market_value || 0
    const priced = positions.filter(p => p.market_value != null && p.market_value > 0)
    const best = [...priced].sort((a, b) => (b.pnl_pct ?? -Infinity) - (a.pnl_pct ?? -Infinity))[0] || null
    const worst = [...priced].sort((a, b) => (a.pnl_pct ?? Infinity) - (b.pnl_pct ?? Infinity))[0] || null
    const concentration = total > 0 && best?.market_value ? (best.market_value / total) * 100 : 0
    const lossCount = priced.filter(p => (p.pnl_pct ?? 0) < 0).length
    const gainCount = priced.filter(p => (p.pnl_pct ?? 0) >= 0).length
    return { best, worst, concentration, lossCount, gainCount }
  }, [positions, summary])

  const recentActivity = useMemo(() => transactions.slice(0, 5), [transactions])

  const handleDeleteTransaction = async (id: number) => {
    if (!await confirm('确定撤销这笔交易吗？持仓会按剩余流水重新计算。', { danger: true, confirmText: '撤销' })) return
    try { await api.deleteTransaction(id); await load() } catch (e: any) { toast(e.message || '撤销失败', 'error') }
  }

  return (
    <div className="pane">
      <div className="pane-head">
        <h2>投资组合</h2>
        <button className="btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? '取消' : '+ 记录交易'}
        </button>
      </div>
      {loadError && <div className="error-box">{loadError}</div>}

      {summary && (
        <div className="portfolio-summary">
          <div className="kpi-card">
            <span className="kpi-label">总市值</span>
            <span className="kpi-value">{summary.total_market_value.toLocaleString()}</span>
          </div>
          <div className="kpi-card">
            <span className="kpi-label">总成本</span>
            <span className="kpi-value">{summary.total_cost.toLocaleString()}</span>
          </div>
          <div className="kpi-card">
            <span className="kpi-label">总盈亏</span>
            <span className={`kpi-value ${summary.total_pnl >= 0 ? 'up' : 'down'}`}>
              {summary.total_pnl >= 0 ? '+' : ''}{summary.total_pnl.toLocaleString()}
            </span>
          </div>
          <div className="kpi-card">
            <span className="kpi-label">收益率</span>
            <span className={`kpi-value ${summary.total_pnl_pct >= 0 ? 'up' : 'down'}`}>
              {summary.total_pnl_pct >= 0 ? '+' : ''}{summary.total_pnl_pct}%
            </span>
          </div>
        </div>
      )}
      {summary && summary.unpriced_count > 0 && (
        <div className="alert-error">{summary.unpriced_count} 项持仓暂时无法获取行情，总市值和总盈亏仅统计有报价的持仓。</div>
      )}

      {summary && (
        <div className="portfolio-workbench">
          <div className="portfolio-workbench-grid">
            <div className="portfolio-panel">
              <span className="portfolio-panel-label">集中度</span>
              <strong>{exposure.concentration ? `${exposure.concentration.toFixed(1)}%` : '--'}</strong>
              <p>{exposure.best ? `${exposure.best.symbol_name} 是当前最大已定价持仓` : '暂无可计算持仓集中度'}</p>
            </div>
            <div className="portfolio-panel">
              <span className="portfolio-panel-label">盈利 / 亏损</span>
              <strong>{exposure.gainCount} / {exposure.lossCount}</strong>
              <p>快速判断组合内部扩散程度，而不是只看总收益。</p>
            </div>
            <div className="portfolio-panel">
              <span className="portfolio-panel-label">最佳持仓</span>
              <strong>{exposure.best ? `${exposure.best.symbol_name} ${exposure.best.pnl_pct ?? 0}%` : '--'}</strong>
              <div className="portfolio-inline-actions">
                {exposure.best && <button className="ghost" onClick={() => openAnalyze(exposure.best!.symbol, '这只盈利持仓现在要不要继续拿？')}>继续研究</button>}
                {exposure.best && <button className="ghost" onClick={() => openQuote(exposure.best!.symbol)}>看行情</button>}
              </div>
            </div>
            <div className="portfolio-panel">
              <span className="portfolio-panel-label">最弱持仓</span>
              <strong>{exposure.worst ? `${exposure.worst.symbol_name} ${exposure.worst.pnl_pct ?? 0}%` : '--'}</strong>
              <div className="portfolio-inline-actions">
                {exposure.worst && <button className="ghost" onClick={() => openAnalyze(exposure.worst!.symbol, '这只亏损持仓是否应该减仓或退出？')}>复盘风险</button>}
                {exposure.worst && <button className="ghost" onClick={() => openBacktest(exposure.worst!.symbol)}>做回测</button>}
              </div>
            </div>
          </div>

          <div className="portfolio-split">
            <div className="portfolio-panel">
              <div className="portfolio-panel-head">
                <span className="portfolio-panel-label">最近动作</span>
                <button className="ghost" onClick={() => setView('history')}>看全部流水</button>
              </div>
              <div className="portfolio-activity-list">
                {recentActivity.length === 0 && <div className="empty">暂无交易记录</div>}
                {recentActivity.map(item => (
                  <div key={item.id} className="portfolio-activity-item">
                    <div>
                      <strong>{item.symbol_name}</strong>
                      <span>{item.date} · {item.action === 'buy' ? '买入' : '卖出'} {item.shares} 股</span>
                    </div>
                    <em>{toMoney(item.total)}</em>
                  </div>
                ))}
              </div>
            </div>
            <div className="portfolio-panel">
              <div className="portfolio-panel-head">
                <span className="portfolio-panel-label">公司事件</span>
                <button className="ghost" onClick={() => setView('holdings')}>回持仓</button>
              </div>
              <div className="portfolio-activity-list">
                {events.length === 0 && <div className="empty">暂无公司事件</div>}
                {events.slice(0, 5).map(event => (
                  <div key={`${event.symbol}-${event.period}`} className="portfolio-activity-item">
                    <div>
                      <strong>{event.name}</strong>
                      <span>{event.date || '日期待定'} · {event.status}</span>
                    </div>
                    <button className="ghost" onClick={() => openQuote(event.symbol)}>看标的</button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {showForm && <TradeForm onDone={() => { setShowForm(false); load() }} />}

      {eventsError && <div className="hint">公司事件日历暂不可用：{eventsError}</div>}

      <div className="tabs">
        <button className={view === 'holdings' ? 'active' : ''} onClick={() => setView('holdings')}>持仓</button>
        <button className={view === 'history' ? 'active' : ''} onClick={() => setView('history')}>交易记录</button>
      </div>

      {view === 'holdings' ? (
        <table className="portfolio-table">
          <thead>
            <tr>
              <th>股票</th><th>持仓</th><th>成本</th><th>现价</th><th>市值</th><th>盈亏</th><th>收益率</th><th>动作</th>
            </tr>
          </thead>
          <tbody>
            {positions.length === 0 && (
              <tr><td colSpan={8} className="empty-row">暂无持仓，点击"记录交易"添加</td></tr>
            )}
            {positions.map(p => (
              <tr key={p.id}>
                <td className="pf-name">{p.symbol_name} <span className="pf-code">{p.symbol}</span></td>
                <td>{p.shares}</td>
                <td>{p.avg_cost}</td>
                <td>{p.current_price || '-'}</td>
                <td>{p.market_value ? p.market_value.toLocaleString() : '-'}</td>
                <td className={p.pnl != null && p.pnl >= 0 ? 'up' : 'down'}>
                  {p.pnl != null ? (p.pnl >= 0 ? '+' : '') + p.pnl.toLocaleString() : '-'}
                </td>
                <td className={p.pnl_pct != null && p.pnl_pct >= 0 ? 'up' : 'down'}>
                  {p.pnl_pct != null ? (p.pnl_pct >= 0 ? '+' : '') + p.pnl_pct + '%' : '-'}
                </td>
                <td>
                  <div className="portfolio-table-actions">
                    <button className="ghost" onClick={() => openAnalyze(p.symbol)}>研究</button>
                    <button className="ghost" onClick={() => openQuote(p.symbol)}>行情</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <table className="portfolio-table">
          <thead>
            <tr><th>日期</th><th>股票</th><th>操作</th><th>数量</th><th>价格</th><th>手续费</th><th>净额</th><th></th></tr>
          </thead>
          <tbody>
            {transactions.length === 0 && (
              <tr><td colSpan={8} className="empty-row">暂无交易记录</td></tr>
            )}
            {transactions.map(t => (
              <tr key={t.id}>
                <td>{t.date}</td>
                <td className="pf-name">{t.symbol_name}</td>
                <td className={t.action === 'buy' ? 'up' : 'down'}>{t.action === 'buy' ? '买入' : '卖出'}</td>
                <td>{t.shares}</td>
                <td>{t.price}</td>
                <td>{t.fee || 0}</td>
                <td>{t.total.toLocaleString()}</td>
                <td><button className="pf-del" onClick={() => handleDeleteTransaction(t.id)}>撤销</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function TradeForm({ onDone }: { onDone: () => void }) {
  const [symbol, setSymbol] = useState('')
  const [action, setAction] = useState<'buy' | 'sell'>('buy')
  const [shares, setShares] = useState('')
  const [price, setPrice] = useState('')
  const [fee, setFee] = useState('')
  const [date, setDate] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    if (!symbol.trim() || !shares || !price) { setError('请填写完整'); return }
    setLoading(true); setError('')
    try {
      if (action === 'buy') {
        await api.buyStock(symbol.trim(), parseFloat(shares), parseFloat(price), date, parseFloat(fee) || 0, note)
      } else {
        await api.sellStock(symbol.trim(), parseFloat(shares), parseFloat(price), date, parseFloat(fee) || 0, note)
      }
      setSymbol(''); setShares(''); setPrice(''); setFee(''); setDate(''); setNote('')
      onDone()
    } catch (e: any) { setError(e.message || '操作失败') }
    finally { setLoading(false) }
  }

  return (
    <div className="trade-form">
      <input className="alert-input" placeholder="股票代码（如 600519）" value={symbol} onChange={e => setSymbol(e.target.value)} />
      <select className="alert-select" value={action} onChange={e => setAction(e.target.value as 'buy' | 'sell')}>
        <option value="buy">买入</option>
        <option value="sell">卖出</option>
      </select>
      <input className="alert-input" placeholder="数量（股）" type="number" value={shares} onChange={e => setShares(e.target.value)} />
      <input className="alert-input" placeholder="价格" type="number" step="0.01" value={price} onChange={e => setPrice(e.target.value)} />
      <input className="alert-input" placeholder="手续费（可选）" type="number" min="0" step="0.01" value={fee} onChange={e => setFee(e.target.value)} />
      <input className="alert-input" aria-label="交易日期" type="date" value={date} onChange={e => setDate(e.target.value)} />
      <input className="alert-input" placeholder="备注（可选）" value={note} onChange={e => setNote(e.target.value)} />
      {error && <span className="alert-error">{error}</span>}
      <button className="btn-primary" onClick={submit} disabled={loading}>{loading ? '处理中...' : '确认'}</button>
    </div>
  )
}
