import { useEffect, useState } from 'react'
import { api } from './api'
import { useModal } from './Modal'
import type { PortfolioPosition, PortfolioSummary, TransactionItem } from './types'

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

      {showForm && <TradeForm onDone={() => { setShowForm(false); load() }} />}

      {events.length > 0 && (
        <details className="company-events">
          <summary>公司事件日历（{events.length}）</summary>
          <div className="company-event-list">
            {events.map(event => (
              <div key={`${event.symbol}-${event.period}`}>
                <strong>{event.date || '日期待定'}</strong>
                <span>{event.name}（{event.symbol}）</span>
                <em>{event.status}</em>
              </div>
            ))}
          </div>
        </details>
      )}
      {eventsError && <div className="hint">公司事件日历暂不可用：{eventsError}</div>}

      <div className="tabs">
        <button className={view === 'holdings' ? 'active' : ''} onClick={() => setView('holdings')}>持仓</button>
        <button className={view === 'history' ? 'active' : ''} onClick={() => setView('history')}>交易记录</button>
      </div>

      {view === 'holdings' ? (
        <table className="portfolio-table">
          <thead>
            <tr>
              <th>股票</th><th>持仓</th><th>成本</th><th>现价</th><th>市值</th><th>盈亏</th><th>收益率</th>
            </tr>
          </thead>
          <tbody>
            {positions.length === 0 && (
              <tr><td colSpan={7} className="empty-row">暂无持仓，点击"记录交易"添加</td></tr>
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
