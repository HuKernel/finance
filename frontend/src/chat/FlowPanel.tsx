// 智能体工作流面板 + 思考动画 + 工具名映射
import { useEffect, useState } from 'react'

export const TOOL_LABEL: Record<string, string> = {
  get_quote: '查询实时行情',
  get_kline: '拉取K线数据',
  get_financials: '查询财务数据',
  get_lhb: '查询龙虎榜',
  get_news: '读取个股新闻',
  get_stock_news: '读取个股新闻',
  get_market_news: '获取实时快讯',
  run_research: '运行多智能体投研',
  search_stock: '搜索股票代码',
  web_search: '联网搜索',
  compare_industry: '行业对比分析',
  get_sentiment: '查询情绪面数据',
  get_valuation: 'DCF估值计算',
}

export interface FlowStep { name: string; args: Record<string, unknown>; status: 'running' | 'done' }

// 智能体工作流面板：实时步骤 + 默认折叠
export function FlowPanel({ steps, collapsed, onToggle }: {
  steps: FlowStep[]; collapsed: boolean; onToggle: () => void
}) {
  const doneCount = steps.filter((s) => s.status === 'done').length
  return (
    <div className="flow-panel">
      <button className="flow-head" onClick={onToggle}>
        <span className="flow-title">智能体工作流</span>
        {steps.length > 0 && (
          <span className="flow-status">
            {doneCount === steps.length && steps.length > 0
              ? `完成 ${steps.length} 步`
              : `执行中 ${doneCount}/${steps.length}`}
          </span>
        )}
        <span className={`flow-arrow ${collapsed ? '' : 'open'}`}>▾</span>
      </button>
      {!collapsed && (
        <div className="flow-body">
          {steps.length === 0 && <div className="flow-empty"><span className="thinking-dots"><i></i><i></i><i></i></span> 正在规划...</div>}
          {steps.map((s, i) => (
            <div key={i} className={`flow-step ${s.status}`}>
              <span className="flow-step-icon">{s.status === 'done' ? '✓' : '◌'}</span>
              <span className="flow-step-name">{TOOL_LABEL[s.name] || s.name}</span>
              {s.status === 'running' && <span className="flow-step-spin" />}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// 思考动画：三个跳动的小圆点
export function ThinkingDots() {
  return <span className="thinking-dots"><i></i><i></i><i></i></span>
}

// 耗时计时器
export function ThinkingTimer({ startTime }: { startTime: number }) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const t = window.setInterval(() => setElapsed(Date.now() - startTime), 100)
    return () => window.clearInterval(t)
  }, [startTime])
  return <span className="think-time">{(elapsed / 1000).toFixed(1)}s</span>
}
