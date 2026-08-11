import { useState } from 'react'
import { api } from './api'

interface MLSignalResult {
  symbol: string
  backend: string
  n_raw_rows: number
  n_samples: number
  split_sizes: Record<string, number>
  split_ranges: Record<string, { start: string; end: string } | null>
  classification: Record<string, number>
  strategy: Record<string, number>
  feature_importance: { name: string; value: number }[]
  data_metadata: { source?: string; as_of?: string; delay?: string }
  flags: { level: string; code: string; message: string }[]
  verdict: string
  disclaimer: string
}

const pct = (value?: number) => value == null ? '--' : `${(value * 100).toFixed(1)}%`

export default function MLSignalPage() {
  const [symbol, setSymbol] = useState('600519')
  const [days, setDays] = useState(500)
  const [model, setModel] = useState('auto')
  const [result, setResult] = useState<MLSignalResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const run = async () => {
    if (!symbol.trim()) return
    setLoading(true); setError(''); setResult(null)
    try {
      setResult(await api.getMLSignal<MLSignalResult>(symbol.trim(), days, model))
    } catch (e) {
      setError(e instanceof Error ? e.message : '诊断失败')
    } finally {
      setLoading(false)
    }
  }

  const maxImportance = result?.feature_importance[0]?.value || 1

  return (
    <div className="pane ml-signal-page">
      <div className="pane-head">
        <div>
          <span className="section-kicker">Out-of-sample diagnostics</span>
          <h2>ML 信号诊断</h2>
          <p>用固定时间切分检查现有特征是否产生样本外 Alpha，不用于自动交易。</p>
        </div>
      </div>

      <div className="ml-controls">
        <input aria-label="信号诊断股票代码" value={symbol} onChange={e => setSymbol(e.target.value)} placeholder="股票代码" />
        <select aria-label="信号诊断样本天数" value={days} onChange={e => setDays(Number(e.target.value))}>
          <option value={250}>250天</option><option value={400}>400天</option><option value={500}>500天</option>
        </select>
        <select aria-label="信号诊断模型" value={model} onChange={e => setModel(e.target.value)}>
          <option value="auto">自动选择</option><option value="rf">Random Forest</option><option value="gb">Gradient Boosting</option><option value="logit">Logistic</option><option value="numpy">Numpy Logistic</option>
        </select>
        <button className="btn-primary" onClick={run} disabled={loading || !symbol.trim()}>{loading ? '诊断中...' : '开始诊断'}</button>
      </div>
      {error && <div className="error-box">{error}</div>}

      {result && <>
        <div className={`ml-verdict ${result.flags.length ? 'warning' : 'ok'}`}>
          <strong>{result.verdict}</strong>
          <span>{result.backend} · 有效样本 {result.n_samples}/{result.n_raw_rows}</span>
        </div>

        <div className="kpi-grid">
          <div className="kpi-card"><span className="kpi-label">买入精度</span><span className="kpi-value">{pct(result.classification.buy_precision)}</span><span className="kpi-sub">预测买入中真实上涨</span></div>
          <div className="kpi-card"><span className="kpi-label">买入召回</span><span className="kpi-value">{pct(result.classification.buy_recall)}</span><span className="kpi-sub">上涨样本被捕获比例</span></div>
          <div className="kpi-card"><span className="kpi-label">样本外超额</span><span className={`kpi-value ${result.strategy.excess_return_pct >= 0 ? 'up' : 'down'}`}>{result.strategy.excess_return_pct}%</span><span className="kpi-sub">相对买入持有</span></div>
          <div className="kpi-card"><span className="kpi-label">最大回撤</span><span className="kpi-value down">-{result.strategy.max_drawdown_pct}%</span><span className="kpi-sub">样本外策略</span></div>
        </div>

        <div className="ml-grid">
          <section className="ml-panel">
            <h3>时间切分</h3>
            {(['train', 'val', 'test'] as const).map(name => <div className="ml-split" key={name}>
              <strong>{{ train: '训练集', val: '验证集', test: '测试集' }[name]}</strong>
              <span>{result.split_ranges[name]?.start ?? '--'} → {result.split_ranges[name]?.end ?? '--'}</span>
              <span>{result.split_sizes[name]} 条</span>
            </div>)}
          </section>
          <section className="ml-panel">
            <h3>诊断提示</h3>
            {result.flags.length ? result.flags.map(flag => <div className="ml-flag" key={flag.code}>{flag.message}</div>) : <div className="ml-ok">未触发基础质量警告</div>}
          </section>
        </div>

        <section className="ml-panel">
          <h3>特征重要性</h3>
          {result.feature_importance.length ? result.feature_importance.map(item => <div className="feature-row" key={item.name}>
            <span>{item.name}</span><i><b style={{ width: `${item.value / maxImportance * 100}%` }} /></i><strong>{item.value.toFixed(4)}</strong>
          </div>) : <div className="empty">当前模型没有可用的特征重要性</div>}
        </section>

        <div className="data-status" aria-label="信号诊断数据状态">
          <span>数据源 {result.data_metadata.source ?? '未知'}</span>
          {result.data_metadata.as_of && <span>截至 {result.data_metadata.as_of}</span>}
          {result.data_metadata.delay && <span>时效 {result.data_metadata.delay}</span>}
        </div>
        <div className="disclaimer">{result.disclaimer}</div>
      </>}
    </div>
  )
}
