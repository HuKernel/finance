import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import type { AnalysisResult, HistoryItem } from './types'
import { ReportView } from './AnalyzePage'
import { useModal } from './Modal'
import { EmptyState, ErrorState, Skeleton } from './States'

/* ---------------- 历史记录 ---------------- */

function HistoryPane({ onPick }: { onPick: () => void }) {
  const { confirm, toast } = useModal()
  const [items, setItems] = useState<HistoryItem[] | null>(null)
  const [error, setError] = useState('')
  const [detail, setDetail] = useState<AnalysisResult | null>(null)
  const [loadingId, setLoadingId] = useState<number | null>(null)

  const load = useCallback(async () => {
    try {
      setItems(await api.getHistory())
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    }
  }, [])

  useEffect(() => { load() }, [load])

  const viewDetail = async (id: number) => {
    setLoadingId(id)
    try {
      const r = await api.getAnalysis(id)
      if (r.result) setDetail(r.result)
    } catch { /* skip */ }
    finally { setLoadingId(null) }
  }

  // 详情视图
  if (detail) {
    return (
      <div className="pane">
        <button className="ghost back-to-list" onClick={() => setDetail(null)} style={{ marginBottom: 12 }}>返回列表</button>
        <ReportView result={detail} />
      </div>
    )
  }

  const stats = items ? {
    total: items.length,
    completed: items.filter(item => item.status === 'completed' || item.status === 'success').length,
    errors: items.filter(item => item.status === 'error' || item.status === 'failed').length,
    symbols: new Set(items.map(item => item.ticker)).size,
  } : null

  return (
    <div className="pane">
      {error && <ErrorState message={error} onRetry={load} />}
      {stats && items && items.length > 0 && <div className="history-insights">
        <div><span>分析总数</span><strong>{stats.total}</strong><p>已保存的研究记录</p></div>
        <div><span>覆盖标的</span><strong>{stats.symbols}</strong><p>不同股票数量</p></div>
        <div><span>已完成</span><strong>{stats.completed}</strong><p>可回看完整结论</p></div>
        <div><span>异常记录</span><strong className={stats.errors ? 'down' : 'up'}>{stats.errors}</strong><p>需要检查模型或数据配置</p></div>
      </div>}
      {!error && items === null && <Skeleton variant="table" lines={5} />}
      {items?.length === 0 && (
        <EmptyState title="暂无分析记录" hint="去「投研分析」页跑一次，结果会自动保存到这里" />
      )}
      {items && items.length > 0 && (
        <table className="history-table">
          <thead>
            <tr><th>ID</th><th>代码</th><th>时间</th><th>状态</th><th></th></tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.id}>
                <td>{it.id}</td>
                <td>{it.ticker}</td>
                <td>{it.created_at}</td>
                <td>{it.status}</td>
                <td>
                  <button className="ghost" onClick={() => viewDetail(it.id)} disabled={loadingId === it.id}>
                    {loadingId === it.id ? '加载...' : '查看'}
                  </button>
                  <button onClick={onPick}>再分析</button>
                  <button className="ghost hist-del-btn" onClick={async () => {
                    if (!await confirm(`确定删除记录 #${it.id}？`, { danger: true, confirmText: '删除' })) return
                    try { await api.deleteHistory(it.id); setItems(prev => (prev ?? []).filter(x => x.id !== it.id)) } catch { toast('删除失败', 'error') }
                  }}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default HistoryPane
