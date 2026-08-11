import { useState } from 'react'
import { api } from './api'
import type { AnalysisResult } from './types'
import Markdown from './Markdown'
import { useModal } from './Modal'
import QuoteCard from './QuoteCard'

function AnalyzePane({ onBacktest, onQuote }: { onBacktest: () => void; onQuote: () => void }) {
  const { toast } = useModal()
  const [ticker, setTicker] = useState('600519')
  const [topic, setTopic] = useState('')
  const [mode, setMode] = useState<'standard' | 'agentic'>('standard')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [steps, setSteps] = useState<{ label: string; status: 'running' | 'done' }[]>([])
  const [analystViews, setAnalystViews] = useState<{ role: string; title: string; summary: string; score: number }[]>([])
  const [riskReview, setRiskReview] = useState<{ approved: boolean; verdict: string; max_position_pct: number; stop_loss_pct: number } | null>(null)
  const [reflections, setReflections] = useState<any[]>([])
  const [reflectionLoading, setReflectionLoading] = useState(false)
  const quoteCode = /^(?:\d{6}|(?:hk|us)[a-z0-9]{2,8})$/i.test(ticker.trim()) ? ticker.trim() : ''

  const loadReflections = async (t: string) => {
    setReflectionLoading(true)
    try {
      const d = await api.get<any>(`/api/reflection/${t}`)
      setReflections(d.memos || [])
    } catch { setReflections([]) }
    finally { setReflectionLoading(false) }
  }

  const run = async () => {
    setLoading(true)
    setError('')
    setResult(null)
    setRiskReview(null)
    setSteps([{ label: '数据收集', status: 'running' }])
    setAnalystViews([])
    try {
      await api.streamAnalysis(ticker, topic, (ev) => {
        if (ev.type === 'step') {
          setSteps((prev) => {
            const idx = prev.findIndex(s => s.label === ev.label)
            if (idx >= 0) {
              const copy = [...prev]; copy[idx] = { label: ev.label, status: ev.status }; return copy
            }
            return [...prev.filter(s => s.status === 'done'), { label: ev.label, status: ev.status }]
          })
        } else if (ev.type === 'analyst') {
          setAnalystViews((prev) => [...prev, { role: ev.role, title: ev.title, summary: ev.summary, score: ev.score }])
        } else if (ev.type === 'risk_review') {
          setRiskReview({ approved: ev.approved, verdict: ev.verdict, max_position_pct: ev.max_position_pct, stop_loss_pct: ev.stop_loss_pct })
        } else if (ev.type === 'result') {
          setResult(ev.data)
        } else if (ev.type === 'error') {
          setError(ev.message)
        }
      }, mode)
      loadReflections(ticker)
    } catch (e) {
      setError(e instanceof Error ? e.message : '分析失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="research-cockpit">
      <div className="research-cockpit-head">
        <div>
          <div className="workspace-eyebrow">研究 Cockpit / {ticker || '选择标的'}</div>
          <h1>从证据到决策</h1>
          <p>输入研究对象和关注问题，由多角色分析师完成数据、观点与风控交叉验证。</p>
        </div>
        <div className="research-object">
          <span>当前研究对象</span>
          <strong>{ticker || '--'}</strong>
        </div>
      </div>
      <div className="research-layout">
      <section className="pane research-main">
        <div className="research-section-head">
          <div>
            <span className="section-kicker">实时市场上下文</span>
            <h2>{ticker || '选择标的'} 的研究证据</h2>
          </div>
          <span className="research-status">数据与结论可追溯</span>
        </div>
      <div className="research-market-context">
        <div>
          <p>当前页面只加载这一只标的的价格、K 线和新闻，切换到其他功能后自动停止刷新。</p>
        </div>
        <button className="ghost" onClick={onQuote}>查看完整行情</button>
      </div>
      {quoteCode && <div className="research-quote"><QuoteCard code={quoteCode} /></div>}
      {error && <div className="error-box">{error}</div>}
      {loading && (
        <div className="research-live">
          <div className="research-steps">
            {steps.map((s, i) => (
              <div key={i} className={`research-step ${s.status}`}>
                <span className="step-icon">{s.status === 'done' ? '✓' : '◌'}</span>
                <span>{s.label}</span>
              </div>
            ))}
          </div>
          {analystViews.length > 0 && (
            <div className="research-analysts">
              {analystViews.map((a, i) => (
                <div key={i} className="research-analyst">
                  <span className={`analyst-score ${a.score >= 0 ? 'up' : 'down'}`}>{a.score > 0 ? '+' : ''}{a.score}</span>
                  <span className="analyst-title">{a.title}</span>
                  <span className="analyst-summary">{a.summary.slice(0, 80)}{a.summary.length > 80 ? '...' : ''}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {riskReview && !result && (
        <div className={`risk-review-card ${riskReview.approved ? 'approved' : 'blocked'}`}>
          <div className="risk-review-head">
            风控审查{riskReview.approved ? '通过' : '否决'}
          </div>
          <div className="risk-review-verdict">{riskReview.verdict}</div>
          {riskReview.approved && (
            <div className="risk-review-meta">
              建议最大仓位 {riskReview.max_position_pct}% | 止损 {riskReview.stop_loss_pct}%
            </div>
          )}
        </div>
      )}
      {result && <ReportView result={result} />}

      {(result || reflections.length > 0) && (
        <div className="pane" style={{ marginTop: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <h3 className="section-title" style={{ margin: 0 }}>历史决策反思</h3>
            {reflections.length > 0 && (
              <button className="ghost" style={{ fontSize: 11 }}
                onClick={async () => {
                  try {
                    const res = await api.post<any>(`/api/reflection/settle/${ticker}`, { force: true })
                    loadReflections(ticker)
                    toast(`已结算 ${res.settled ?? 0} 条pending决策`, 'success')
                  } catch { toast('结算失败', 'error') }
                }}>
                手动结算pending决策
              </button>
            )}
            {reflections.length === 0 && !reflectionLoading && (
              <button className="ghost" style={{ fontSize: 11 }}
                onClick={async () => {
                  try {
                    await api.post<any>(`/api/reflection/settle/${ticker}`, {})
                    loadReflections(ticker)
                  } catch { toast('结算失败', 'error') }
                }}>
                刷新反思记录
              </button>
            )}
          </div>
          {reflectionLoading ? (
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>加载中...</div>
          ) : reflections.length > 0 ? (
            <table className="portfolio-table">
              <thead>
                <tr>
                  <th>日期</th><th>分析师</th><th>评分</th><th>实际涨跌</th>
                  <th>超额收益</th><th>判断</th><th>反思</th>
                </tr>
              </thead>
              <tbody>
                {reflections.map((m, i) => (
                  <tr key={i}>
                    <td style={{ fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' }}>{m.decision_date}</td>
                    <td>{m.role}</td>
                    <td className={m.decision_score >= 0 ? 'up' : 'down'} style={{ fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' }}>
                      {m.decision_score > 0 ? '+' : ''}{m.decision_score}
                    </td>
                    <td className={m.raw_return >= 0 ? 'up' : 'down'} style={{ fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' }}>
                      {m.raw_return > 0 ? '+' : ''}{m.raw_return?.toFixed(2)}%
                    </td>
                    <td className={m.alpha_return >= 0 ? 'up' : 'down'} style={{ fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' }}>
                      {m.alpha_return > 0 ? '+' : ''}{m.alpha_return?.toFixed(2)}%
                    </td>
                    <td>
                      <span className={`qp-badge ${m.verdict === 'correct' ? 'badge-up' : m.verdict === 'wrong' ? 'badge-down' : 'badge-neutral'}`}>
                        {m.verdict === 'correct' ? '正确' : m.verdict === 'wrong' ? '错误' : '待定'}
                      </span>
                    </td>
                    <td style={{ maxWidth: 300, fontSize: 12, color: 'var(--text-2)' }}>{m.reflection}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>暂无历史决策记录</div>
          )}
        </div>
      )}
      </section>
      <aside className="research-action-panel">
        <div>
          <span className="section-kicker">深度投研</span>
          <h2>生成多角色研究报告</h2>
          <p>标准模式适合快速判断；Agent 模式会自主调用更多工具，耗时更长。</p>
        </div>
        <div className="research-side-inputs">
          <input
            aria-label="股票代码或名称"
            className="ticker-input"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder="股票代码，如 600519"
          />
          <textarea
            aria-label="分析主题（可选）"
            className="topic-input"
            rows={4}
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="研究问题（可选），例如：未来两年增长来自哪里？"
          />
        </div>
        <div className="research-mode-row research-side-modes">
          <label>
            <input type="radio" value="standard" checked={mode === 'standard'} onChange={() => setMode('standard')} />
            标准模式
          </label>
          <label>
            <input type="radio" value="agentic" checked={mode === 'agentic'} onChange={() => setMode('agentic')} />
            Agent 模式
          </label>
        </div>
        <button className="research-primary" onClick={run} disabled={loading || !ticker.trim()}>
          {loading ? '分析中...' : '开始深度投研'}
        </button>
        <div className="research-action-divider" />
        <div>
          <span className="section-kicker">策略验证</span>
          <h3>把研究假设交给历史数据</h3>
          <p>前往策略回测，验证收益、回撤与交易成本。</p>
        </div>
        <button className="ghost" onClick={onBacktest}>进入策略回测</button>
      </aside>
      </div>
    </div>
  )
}

function ReportView({ result }: { result: AnalysisResult }) {
  const score = result.consensus_score
  const trend = score >= 3 ? '偏多' : score <= -3 ? '偏空' : '中性'
  const plan = result.trade_plan
  const risk = result.risk_review
  // gauge 标记位置：-10 ~ +10 映射到 0% ~ 100%
  const gaugeLeft = `${((score + 10) / 20) * 100}%`

  const price = result.price
  const changePct = result.change_pct
  const trace = result.raw?.trace

  return (
    <div className="report">
      <div className="report-head">
        <div>
          <h2>{result.name || result.ticker} <span className="ticker-code">{result.ticker}</span></h2>
          <div className="meta">{result.created_at}</div>
        </div>
        <div className={`score-display ${trend === '偏多' ? 'up' : trend === '偏空' ? 'down' : 'neutral'}`}>
          {score > 0 ? '+' : ''}{score}
        </div>
        <button className="ghost report-export-btn" onClick={() => window.print()}>导出PDF</button>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">现价</div>
          <div className="kpi-value">{price ?? '--'}</div>
          <div className="kpi-sub">人民币</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">涨跌幅</div>
          <div className={`kpi-value ${(changePct ?? 0) >= 0 ? 'up' : 'down'}`}>{changePct != null ? `${changePct > 0 ? '+' : ''}${changePct}%` : '--'}</div>
          <div className="kpi-sub">当日</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">共识评分</div>
          <div className={`kpi-value ${trend === '偏多' ? 'up' : trend === '偏空' ? 'down' : 'neutral'}`}>{score}</div>
          <div className="kpi-sub">{trend}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">分析师</div>
          <div className="kpi-value">{result.analyst_views.length}</div>
          <div className="kpi-sub">五位角色独立研判</div>
        </div>
      </div>

      <div className="consensus">
        <div className="consensus-head">
          <h3>共识结论 / CONSENSUS</h3>
          <span className={`score-display ${trend === '偏多' ? 'up' : trend === '偏空' ? 'down' : 'neutral'}`} style={{ fontSize: 22 }}>
            {score > 0 ? '+' : ''}{score}
          </span>
        </div>
        <div className="gauge-track">
          <div className="gauge-marker" style={{ left: gaugeLeft }} />
        </div>
        <div className="gauge-labels"><span>-10 看空</span><span>0 中性</span><span>+10 看多</span></div>
        <div className="consensus-text"><Markdown text={result.consensus_verdict || '（无）'} /></div>
      </div>

      <h3 className="section-title">分析师观点</h3>
      <div className="views-grid">
        {result.analyst_views.map((v) => (
          <div className="view-card" key={v.role}>
            <div className="view-head">
              <span className="view-title">{v.title}</span>
              <span className={`view-score ${v.score >= 3 ? 'up' : v.score <= -3 ? 'down' : 'neutral'}`}>
                {v.score > 0 ? '+' : ''}{v.score}
              </span>
            </div>
            <p className="view-summary">{v.summary}</p>
            {v.evidence.length > 0 && (
              <ul className="evidence">{v.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul>
            )}
            {v.risk_points.length > 0 && (
              <div className="risk-points">{v.risk_points.map((r, i) => <span key={i}>{r}</span>)}</div>
            )}
          </div>
        ))}
      </div>

      {result.debate.length > 0 && (
        <>
          <h3 className="section-title">多空辩论</h3>
          <div className="debate">
            {result.debate.map((d, i) => (
              <div key={i}>
                <div className="debate-topic">{d.topic}</div>
                <ul>{d.positions.map((p, j) => <li key={j}>{p}</li>)}</ul>
              </div>
            ))}
          </div>
        </>
      )}

      {risk && (
        <>
          <h3 className="section-title">风控审查</h3>
          <div className={`risk-box ${risk.approved ? 'ok' : 'blocked'}`}>
            <div className="risk-verdict">{risk.approved ? '通过' : '否决'}：{risk.verdict}</div>
            <div className="risk-detail">最大建议仓位 {risk.max_position_pct}% | 止损位 {risk.stop_loss_pct}%</div>
          </div>
        </>
      )}

      {plan && (
        <>
          <h3 className="section-title">交易计划</h3>
          <div className={`plan-box action-${plan.action}`}>
            <div className="plan-action">{plan.action}</div>
            <div className="plan-detail">
              建议仓位 {plan.position_pct}%{plan.target_price ? ` | 目标价 ${plan.target_price}` : ''}
              {plan.stop_loss ? ` | 止损价 ${plan.stop_loss}` : ''}
            </div>
            <p>{plan.reasoning}</p>
            {plan.risk_warnings.length > 0 && (
              <ul>{plan.risk_warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
            )}
          </div>
        </>
      )}

      {trace && (
        <details className="analysis-trace">
          <summary>
            运行追踪 · {trace.provider}/{trace.model} · {(trace.duration_ms / 1000).toFixed(1)}s
          </summary>
          <div className="trace-run-id">Run ID: {trace.run_id}</div>
          <div className="trace-steps">
            {trace.steps.map((step, index) => (
              <div className="trace-step" key={`${step.name}-${index}`}>
                <span>{step.label}{step.detail ? ` · ${step.detail}` : ''}</span>
                <span>T+{step.at_ms}ms</span>
              </div>
            ))}
          </div>
          {trace.tools.length > 0 && (
            <div className="trace-tools">
              工具：{trace.tools.map(tool => `${tool.role ? `${tool.role}/` : ''}${tool.name}`).join('、')}
            </div>
          )}
          {trace.error && <div className="error-box">{trace.error}</div>}
        </details>
      )}

      <div className="disclaimer">{result.disclaimer}</div>
    </div>
  )
}

export default AnalyzePane
export { ReportView }
