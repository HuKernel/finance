import { useEffect, useState } from 'react'
import { api } from './api'
import type { BacktestResult } from './types'
import { lazy, Suspense } from 'react'

function symbolFromHash(): string {
  const hash = window.location.hash || ''
  const [, query = ''] = hash.split('?')
  return new URLSearchParams(query).get('symbol')?.trim() || ''
}

const BacktestAnalysis = lazy(() => import('./BacktestAnalysis'))
// 图表组件懒加载：recharts 库很大(~300KB)，只有回测出结果后才加载
const EquityChart = lazy(() => import('./BacktestCharts').then(m => ({ default: m.EquityChart })))
const DrawdownChart = lazy(() => import('./BacktestCharts').then(m => ({ default: m.DrawdownChart })))
const MonthlyHeatmap = lazy(() => import('./BacktestCharts').then(m => ({ default: m.MonthlyHeatmap })))

const STRATEGIES = [
  { key: 'ma_cross', label: 'MA均线交叉', params: [
    { key: 'fast_period', label: '快线', default: 5 },
    { key: 'slow_period', label: '慢线', default: 20 },
  ]},
  { key: 'dual_ma', label: '双均线(可调)', params: [
    { key: 'fast_period', label: '快线', default: 10 },
    { key: 'slow_period', label: '慢线', default: 30 },
  ]},
  { key: 'macd', label: 'MACD交叉', params: [] },
  { key: 'kdj', label: 'KDJ金叉', params: [] },
  { key: 'boll', label: 'BOLL带突破', params: [
    { key: 'boll_period', label: '周期', default: 20 },
  ]},
  { key: 'rsi', label: 'RSI超买超卖', params: [
    { key: 'rsi_period', label: '周期', default: 14 },
    { key: 'rsi_oversold', label: '超卖线', default: 30 },
    { key: 'rsi_overbought', label: '超买线', default: 70 },
  ]},
  { key: 'grid', label: '网格交易', params: [
    { key: 'grid_pct', label: '间距%', default: 5 },
  ]},
  { key: 'hold', label: '买入持有(基准)', params: [] },
  { key: 'ai', label: 'AI情景模拟（非严格回测）', params: [] },
]

type PageTab = 'basic' | 'analysis'

export default function BacktestPage() {
  const [pageTab, setPageTab] = useState<PageTab>('basic')
  const [symbol, setSymbol] = useState('')
  const [strategy, setStrategy] = useState('ma_cross')
  const [days, setDays] = useState(120)
  const [enableCost, setEnableCost] = useState(true)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [params, setParams] = useState<Record<string, string>>({})

  useEffect(() => {
    const next = symbolFromHash()
    if (next) setSymbol(next)
  }, [])

  const currentStrategy = STRATEGIES.find(s => s.key === strategy)

  const run = async () => {
    if (!symbol.trim()) { setError('请输入股票代码'); return }
    setLoading(true); setError('')
    try {
      // 转换参数
      const numParams: Record<string, any> = {}
      if (currentStrategy) {
        for (const p of currentStrategy.params) {
          const val = params[`${strategy}_${p.key}`] ?? String(p.default)
          numParams[p.key] = val
        }
      }
      const r = await api.getBacktest(symbol.trim(), strategy, days, enableCost ? 1 : 0, { ...numParams, ...riskNumParams })
      setResult(r)
    } catch (e: any) { setError(e.message || '回测失败') }
    finally { setLoading(false) }
  }

  // 风控退出参数（止损/止盈/ATR追踪，0=关闭）
  const riskParams = [
    { key: 'stop_loss_pct', label: '止损%', default: 0 },
    { key: 'take_profit_pct', label: '止盈%', default: 0 },
    { key: 'atr_trailing_mult', label: 'ATR追踪倍数', default: 0 },
  ]
  const riskNumParams: Record<string, any> = {}
  for (const p of riskParams) {
    const val = parseFloat(params[`risk_${p.key}`] ?? '0')
    if (val > 0) riskNumParams[p.key] = val
  }
  const REASON_LABEL: Record<string, string> = {
    signal: '策略信号', stop_loss: '止损', take_profit: '止盈', eod_liquidation: '期末平仓',
  }

  const downloadRun = () => {
    if (!result?.run_manifest) return
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `backtest_${result.symbol}_${result.strategy}_${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="pane">
      <div className="pane-head">
        <h2>策略回测</h2>
        <div className="tabs">
          <button className={pageTab === 'basic' ? 'active' : ''} onClick={() => setPageTab('basic')}>基础回测</button>
          <button className={pageTab === 'analysis' ? 'active' : ''} onClick={() => setPageTab('analysis')}>深度分析</button>
        </div>
      </div>

      {pageTab === 'analysis' ? (
        <Suspense fallback={<div className="loading loading-center">加载分析模块...</div>}>
          <BacktestAnalysis />
        </Suspense>
      ) : (
      <>
      <div className="backtest-controls">
        <input aria-label="回测股票代码" className="alert-input" placeholder="股票代码（如 600519）"
          value={symbol} onChange={e => setSymbol(e.target.value)} />
        <select aria-label="回测策略" className="alert-select" value={strategy} onChange={e => { setStrategy(e.target.value); setParams({}) }}>
          {STRATEGIES.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
        <select aria-label="回测周期" className="alert-select" value={days} onChange={e => setDays(parseInt(e.target.value))}>
          <option value={60}>60天</option>
          <option value={120}>120天</option>
          <option value={250}>250天</option>
          <option value={500}>500天</option>
        </select>
        <label className="bt-cost-toggle">
          <input type="checkbox" checked={enableCost} onChange={e => setEnableCost(e.target.checked)} />
          <span>含手续费</span>
        </label>
        <button className="btn-primary" onClick={run} disabled={loading}>
          {loading ? (strategy === 'ai' ? 'AI模拟中(较慢)...' : '回测中...') : (strategy === 'ai' ? '开始模拟' : '开始回测')}
        </button>
      </div>

      {/* 策略参数面板 */}
      {currentStrategy && currentStrategy.params.length > 0 && (
        <div className="bt-params">
          <span className="bt-params-label">{currentStrategy.label} 参数：</span>
          {currentStrategy.params.map(p => (
            <label key={p.key} className="bt-param-item">
              <span>{p.label}</span>
              <input type="number" className="bt-param-input"
                value={params[`${strategy}_${p.key}`] ?? p.default}
                onChange={e => setParams(prev => ({ ...prev, [`${strategy}_${p.key}`]: e.target.value }))} />
            </label>
          ))}
        </div>
      )}

      {/* 风控退出参数（对所有策略生效） */}
      <div className="bt-params">
        <span className="bt-params-label">风控退出（0=关闭）：</span>
        {riskParams.map(p => (
          <label key={p.key} className="bt-param-item">
            <span>{p.label}</span>
            <input type="number" className="bt-param-input"
              value={params[`risk_${p.key}`] ?? p.default}
              onChange={e => setParams(prev => ({ ...prev, [`risk_${p.key}`]: e.target.value }))} />
          </label>
        ))}
      </div>

      {error && <span className="alert-error">{error}</span>}

      {result && !result.error && (
        <>
          {result.warnings?.map((warning, i) => (
            <div key={i} className="alert-error">{warning}</div>
          ))}
          {/* KPI 卡片 - 按 收益 / 风险 / 交易 分组 */}
          <div className="kpi-groups">
            <div>
              <div className="kpi-group-label">收益</div>
              <div className="backtest-summary">
            <div className="kpi-card">
              <span className="kpi-label">策略收益</span>
              <span className={`kpi-value ${result.total_return >= 0 ? 'up' : 'down'}`}>
                {result.total_return >= 0 ? '+' : ''}{result.total_return}%
              </span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">基准(持有)</span>
              <span className={`kpi-value ${result.benchmark_return >= 0 ? 'up' : 'down'}`}>
                {result.benchmark_return >= 0 ? '+' : ''}{result.benchmark_return}%
              </span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">超额收益</span>
              <span className={`kpi-value ${result.excess_return >= 0 ? 'up' : 'down'}`}>
                {result.excess_return >= 0 ? '+' : ''}{result.excess_return}%
              </span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">年化收益</span>
              <span className={`kpi-value ${(result.annual_return ?? 0) >= 0 ? 'up' : 'down'}`}>
                {(result.annual_return ?? 0) >= 0 ? '+' : ''}{(result.annual_return ?? 0).toFixed(1)}%
              </span>
            </div>
              </div>
            </div>
            <div>
              <div className="kpi-group-label">风险</div>
              <div className="backtest-summary">
            <div className="kpi-card">
              <span className="kpi-label">最大回撤</span>
              <span className="kpi-value down">-{result.max_drawdown}%</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">夏普比率</span>
              <span className="kpi-value">{(result.sharpe_ratio ?? 0).toFixed(2)}</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">Sortino</span>
              <span className="kpi-value">{(result.sortino_ratio ?? 0).toFixed(2)}</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">Calmar</span>
              <span className="kpi-value">{(result.calmar_ratio ?? 0).toFixed(2)}</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">波动率</span>
              <span className="kpi-value">{(result.annual_volatility ?? 0).toFixed(1)}%</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">EWMA夏普</span>
              <span className="kpi-value">{(result.ewm_sharpe ?? 0).toFixed(2)}</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">CVaR(95%)</span>
              <span className="kpi-value down">{(result.cvar_95 ?? 0).toFixed(2)}%</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">偏度/峰度</span>
              <span className="kpi-value">{(result.skewness ?? 0).toFixed(2)}/{(result.kurtosis ?? 0).toFixed(2)}</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">回撤恢复</span>
              <span className="kpi-value">{result.max_dd_duration ?? '-'}天</span>
            </div>
              </div>
            </div>
            <div>
              <div className="kpi-group-label">交易</div>
              <div className="backtest-summary">
            <div className="kpi-card">
              <span className="kpi-label">交易次数</span>
              <span className="kpi-value">{result.trades}</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">胜率</span>
              <span className="kpi-value">{result.win_rate}%</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">最大连亏</span>
              <span className="kpi-value">{result.max_consecutive_losses ?? '-'}次</span>
            </div>
              </div>
            </div>
          </div>

          {/* 逐笔交易明细（买入→卖出配对，含成本与净盈亏） */}
          {(result as any).round_trips?.length > 0 && (
            <details className="bt-round-trips">
              <summary>逐笔交易明细（{(result as any).round_trips.length} 笔）</summary>
              <table className="portfolio-table">
                <thead><tr>
                  <th>买入日</th><th>卖出日</th><th>持股天数</th><th>买入价</th><th>卖出价</th>
                  <th>股数</th><th>毛利</th><th>费用</th><th>净盈亏</th><th>收益率</th><th>退出原因</th>
                </tr></thead>
                <tbody>
                  {(result as any).round_trips.map((rt: any, i: number) => (
                    <tr key={i}>
                      <td>{rt.entry_date}</td>
                      <td>{rt.exit_date}</td>
                      <td>{rt.holding_days}</td>
                      <td>{rt.entry_price}</td>
                      <td>{rt.exit_price}</td>
                      <td>{rt.shares}</td>
                      <td className={rt.gross_pnl >= 0 ? 'up' : 'down'}>{rt.gross_pnl}</td>
                      <td>{rt.costs}</td>
                      <td className={rt.net_pnl >= 0 ? 'up' : 'down'}>{rt.net_pnl}</td>
                      <td className={rt.return_pct >= 0 ? 'up' : 'down'}>{rt.return_pct}%</td>
                      <td>{REASON_LABEL[rt.reason] || rt.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}

          <div className="backtest-period">
            期间: {result.period} | 初始资金: {result.initial_capital.toLocaleString()} | 终值: {result.final_value.toLocaleString()}
            {result.run_manifest && (
              <> | 数据指纹: {result.run_manifest.data.fingerprint.slice(0, 12)}…{' '}
                <button className="btn-primary" onClick={downloadRun}>导出运行记录</button>
              </>
            )}
          </div>

          <div className="backtest-equity">
            <h4>权益曲线</h4>
            <Suspense fallback={<div className="chart-loading">加载图表...</div>}>
              <EquityChart curve={result.equity_curve} initialCapital={result.initial_capital} tradesLog={result.trades_log} />
            </Suspense>
          </div>

          <div className="backtest-equity">
            <h4>回撤水下图 (Underwater)</h4>
            <Suspense fallback={<div className="chart-loading">加载图表...</div>}>
              <DrawdownChart curve={result.equity_curve} />
            </Suspense>
          </div>

          <div className="backtest-equity">
            <h4>月度收益热力图</h4>
            <Suspense fallback={<div className="chart-loading">加载图表...</div>}>
              <MonthlyHeatmap curve={result.equity_curve} />
            </Suspense>
          </div>

          {result.trades_log.length > 0 && (
            <div className="backtest-trades">
              <h4>交易记录（最近{Math.min(result.trades_log.length, 20)}笔）</h4>
              <table className="portfolio-table">
                <thead>
                  <tr><th>日期</th><th>操作</th><th>价格</th><th>数量</th>{strategy === 'ai' && <th>AI理由</th>}</tr>
                </thead>
                <tbody>
                  {result.trades_log.slice(-20).map((t, i) => (
                    <tr key={i}>
                      <td>{t.date}</td>
                      <td className={t.action === 'BUY' ? 'up' : 'down'}>{t.action === 'BUY' ? '买入' : '卖出'}</td>
                      <td>{t.price}</td>
                      <td>{t.shares}</td>
                      {strategy === 'ai' && <td className="pf-code">{t.reason || ''}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
      </>
      )}
    </div>
  )
}
