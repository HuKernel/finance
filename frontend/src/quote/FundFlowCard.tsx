import { useQuery } from '@tanstack/react-query'
import { getToken } from '../api'
import { Loading } from '../States'

// ========== 资金流向卡片 ==========
export default function FundFlowCard({ code }: { code: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['fund-flow', code],
    queryFn: async () => {
      // 后端API获取资金流向（服务器环境直连东财，本地开发可能被代理拦截）
      const token = getToken()
      const r = await fetch(`/api/fund-flow/${code}?days=5`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      return r.json()
    },
  })

  if (isLoading) return <div className="qp-card"><span className="qp-card-title">资金流向</span><Loading label="资金流向加载中..." /></div>
  if (!data || data.error || data.latest_main_net == null) return (
    <div className="qp-card">
      <span className="qp-card-title">资金流向</span>
      <span className="qp-card-empty">东财接口被代理拦截，服务器部署后可用</span>
    </div>
  )

  const mainNet = data.latest_main_net ?? 0
  const isPositive = mainNet >= 0
  const history = (data.history ?? []).slice(-5).reverse()

  return (
    <div className="qp-card">
      <span className="qp-card-title">资金流向 {data.latest_date}</span>
      <div className="qp-card-row">
        <span className={isPositive ? 'text-up' : 'text-down'}>
          {isPositive ? '▲' : '▼'} 主力{isPositive ? '净流入' : '净流出'} {Math.abs(mainNet)}亿
        </span>
      </div>
      <div className="qp-card-row">
        <span>超大单 {data.latest_super_net >= 0 ? '+' : ''}{data.latest_super_net}亿</span>
        <span>大单 {data.latest_large_net >= 0 ? '+' : ''}{data.latest_large_net}亿</span>
      </div>
      {history.length > 1 && (
        <div className="qp-card-mini-chart">
          {history.map((h: any, i: number) => (
            <div key={i} className="qp-bar-item">
              <div
                className={`qp-bar ${h.main_net >= 0 ? 'up' : 'down'}`}
                style={{ height: `${Math.min(Math.abs(h.main_net) * 8, 24)}px` }}
                title={`${h.date}: ${h.main_net}亿`}
              />
              <span className="qp-bar-date">{h.date.slice(5)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
