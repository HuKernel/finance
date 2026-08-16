import { useQuery } from '@tanstack/react-query'

// ========== K线形态卡片 ==========
export default function PatternCard({ code }: { code: string }) {
  const { data } = useQuery({
    queryKey: ['patterns', code],
    queryFn: async () => {
      const r = await fetch(`/api/patterns/${code}`, {
        credentials: 'same-origin',
      })
      return r.json()
    },
  })

  if (!data || !data.pattern) return null

  const dir = data.direction
  const dirClass = dir === '看涨' ? 'text-up' : dir === '看跌' ? 'text-down' : 'text-neutral'

  return (
    <div className="qp-card">
      <span className="qp-card-title">K线形态</span>
      <div className="qp-card-row">
        <span className={dirClass}>{data.pattern}</span>
        <span className={`qp-badge ${dir === '看涨' ? 'badge-up' : dir === '看跌' ? 'badge-down' : 'badge-neutral'}`}>{dir}</span>
      </div>
      <p className="qp-card-desc">{data.description}</p>
      {data.all_patterns && data.all_patterns.length > 1 && (
        <div className="qp-pattern-list">
          {data.all_patterns.slice(0, 4).map((p: any, i: number) => (
            <div key={i} className="qp-pattern-item">
              <span className="qp-pattern-date">{p.date.slice(5)}</span>
              <span className={p.direction === '看涨' ? 'text-up' : p.direction === '看跌' ? 'text-down' : 'text-neutral'}>
                {p.name}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
