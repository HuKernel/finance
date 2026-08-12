import { useEffect, useState } from 'react'
import { api } from './api'
import { useModal } from './Modal'

type AdminTab = 'stats' | 'users' | 'invites' | 'feedback' | 'payment' | 'audit'

export default function AdminPage() {
  const [isAdmin, setIsAdmin] = useState(false)
  const [checked, setChecked] = useState(false)
  const [tab, setTab] = useState<AdminTab>('stats')

  useEffect(() => {
    api.isAdmin().then(r => { setIsAdmin(r.is_admin); setChecked(true) }).catch(() => setChecked(true))
  }, [])

  if (!checked) return <div className="pane">检查权限中...</div>
  if (!isAdmin) return <div className="pane"><p className="hint">需要管理员权限才能访问此页面。</p></div>

  const tabs: { key: AdminTab; label: string }[] = [
    { key: 'stats', label: '系统概览' },
    { key: 'users', label: '用户管理' },
    { key: 'invites', label: '邀请码' },
    { key: 'feedback', label: '用户反馈' },
    { key: 'payment', label: '支付配置' },
    { key: 'audit', label: '审计日志' },
  ]

  return (
    <div className="pane admin-page">
      <div className="pane-head"><h2>管理后台</h2></div>
      <div className="admin-tabs">
        {tabs.map(t => (
          <button key={t.key} className={tab === t.key ? 'active' : ''} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="admin-tab-content">
        {tab === 'stats' && <StatsSection />}
        {tab === 'users' && <UsersSection />}
        {tab === 'invites' && <InviteSection />}
        {tab === 'feedback' && <FeedbackSection />}
        {tab === 'payment' && <PaymentConfigSection />}
        {tab === 'audit' && <AuditSection />}
      </div>
    </div>
  )
}

const PAYMENT_LABELS: Record<string, string> = {
  MEMBERSHIP_MONTHLY_PRICE: '月卡价格（元）', MEMBERSHIP_YEARLY_PRICE: '年卡价格（元）',
  PAYMENT_NOTIFY_BASE_URL: '支付回调 HTTPS 根地址',
  WECHAT_APP_ID: '微信 AppID', WECHAT_MCH_ID: '微信商户号', WECHAT_CERT_SERIAL_NO: '微信商户证书序列号',
  WECHAT_PRIVATE_KEY_PATH: '微信商户 API 私钥 PEM', WECHAT_API_V3_KEY: '微信 API v3 Key',
  WECHAT_PAY_PUBLIC_KEY_ID: '微信支付公钥 ID', WECHAT_PAY_PUBLIC_KEY_PATH: '微信支付公钥 PEM',
  ALIPAY_APP_ID: '支付宝 AppID', ALIPAY_PRIVATE_KEY_PATH: '支付宝应用私钥 PEM',
  ALIPAY_PUBLIC_KEY_PATH: '支付宝公钥 PEM', ALIPAY_SELLER_ID: '支付宝 Seller ID（可选）',
  ALIPAY_GATEWAY: '支付宝网关',
}
const PAYMENT_SECRET_FIELDS = new Set(['WECHAT_PRIVATE_KEY_PATH', 'WECHAT_API_V3_KEY', 'WECHAT_PAY_PUBLIC_KEY_PATH', 'ALIPAY_PRIVATE_KEY_PATH', 'ALIPAY_PUBLIC_KEY_PATH'])

function PaymentConfigSection() {
  const { toast } = useModal()
  const [values, setValues] = useState<Record<string, string>>({})
  const [configured, setConfigured] = useState<Record<string, boolean>>({})
  const [channels, setChannels] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)

  const applyConfig = (result: {values:Record<string,string>;configured:Record<string,boolean>;channels:Record<string,boolean>}) => {
    setValues(result.values); setConfigured(result.configured); setChannels(result.channels)
  }
  useEffect(() => {
    api.adminPaymentConfig().then(applyConfig).catch(() => toast('支付配置加载失败', 'error'))
  }, [toast])

  const save = async () => {
    setSaving(true)
    try {
      const result = await api.saveAdminPaymentConfig(values)
      setValues(result.values); setConfigured(result.configured); setChannels(result.channels)
      toast('支付配置已保存', 'success')
    } catch (e) { toast(e instanceof Error ? e.message : '保存失败', 'error') }
    finally { setSaving(false) }
  }

  return <div className="payment-admin-config">
    <div className="payment-config-status">
      <span className={channels.wechat ? 'up' : 'down'}>微信支付：{channels.wechat ? '可用' : '未完成'}</span>
      <span className={channels.alipay ? 'up' : 'down'}>支付宝：{channels.alipay ? '可用' : '未完成'}</span>
    </div>
    <p className="hint">私钥和 API v3 Key 加密保存，页面不会回显原文；留空表示保留已有密钥。</p>
    <div className="payment-config-grid">
      {Object.entries(PAYMENT_LABELS).map(([key, label]) => {
        const secret = PAYMENT_SECRET_FIELDS.has(key)
        const multiline = key.includes('PRIVATE_KEY') || key.includes('PUBLIC_KEY')
        return <label key={key}>{label}{secret && configured[key] && <small>已配置</small>}
          {multiline
            ? <textarea rows={4} value={values[key] || ''} placeholder={configured[key] ? '已配置，留空保持不变' : '粘贴完整 PEM 内容'} onChange={e => setValues(current => ({...current, [key]: e.target.value}))} />
            : <input type={key.includes('PRICE') ? 'number' : key === 'WECHAT_API_V3_KEY' ? 'password' : 'text'} min={key.includes('PRICE') ? '0.01' : undefined} step={key.includes('PRICE') ? '0.01' : undefined} value={values[key] || ''} placeholder={secret && configured[key] ? '已配置，留空保持不变' : ''} onChange={e => setValues(current => ({...current, [key]: e.target.value}))} />}
        </label>
      })}
    </div>
    <button className="btn-primary" disabled={saving} onClick={save}>{saving ? '保存中...' : '保存支付配置'}</button>
  </div>
}

const FEEDBACK_CATEGORY: Record<string, string> = {
  suggestion: '功能建议', bug: '问题反馈', data: '数据问题', other: '其他',
}

function FeedbackSection() {
  const { toast, confirm } = useModal()
  const [items, setItems] = useState<any[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [replies, setReplies] = useState<Record<number, string>>({})
  const load = (targetPage: number = page) => {
    api.adminFeedback(targetPage).then(result => {
      setItems(result.items)
      setTotal(result.total)
      setPage(result.page)
    }).catch(() => {})
  }
  useEffect(() => { load(1) }, [])

  const updateStatus = async (id: number, status: string) => {
    try { await api.updateFeedback(id, { status }); load() }
    catch { toast('状态更新失败', 'error') }
  }
  const reply = async (id: number) => {
    const text = replies[id]?.trim()
    if (!text) return toast('请输入回复内容', 'warning')
    try {
      await api.updateFeedback(id, { reply: text })
      setReplies(current => ({ ...current, [id]: '' }))
      load()
      toast('回复已保存', 'success')
    } catch { toast('回复失败', 'error') }
  }
  const remove = async (id: number) => {
    if (!await confirm('确定删除这条反馈吗？', { danger: true })) return
    try { await api.deleteFeedback(id); load() }
    catch { toast('删除失败', 'error') }
  }

  return (
    <>
    <table className="portfolio-table">
      <thead><tr><th>时间</th><th>用户</th><th>类型</th><th>页面</th><th>反馈内容</th><th>状态</th><th>回复</th><th>操作</th></tr></thead>
      <tbody>
        {items.length === 0 && <tr><td colSpan={8} className="empty-row">暂无用户反馈</td></tr>}
        {items.map(item => (
          <tr key={item.id}>
            <td>{(item.created_at || '').slice(0, 19)}</td>
            <td className="pf-name">{item.username}</td>
            <td>{FEEDBACK_CATEGORY[item.category] || item.category}</td>
            <td>{item.page || '-'}</td>
            <td className="admin-feedback-content">{item.content}</td>
            <td>
              <select value={item.status} onChange={event => updateStatus(item.id, event.target.value)}>
                <option value="new">待处理</option>
                <option value="processing">处理中</option>
                <option value="resolved">已解决</option>
              </select>
            </td>
            <td>
              {item.admin_reply && <div className="admin-feedback-reply">{item.admin_reply}</div>}
              <textarea
                rows={2}
                maxLength={1000}
                placeholder="回复用户"
                value={replies[item.id] ?? ''}
                onChange={event => setReplies(current => ({ ...current, [item.id]: event.target.value }))}
              />
              <button className="admin-action-btn" onClick={() => reply(item.id)}>回复</button>
            </td>
            <td><button className="admin-action-btn danger" onClick={() => remove(item.id)}>删除</button></td>
          </tr>
        ))}
      </tbody>
    </table>
    {total > 20 && (
      <div className="feedback-pagination">
        <button disabled={page <= 1} onClick={() => load(page - 1)}>上一页</button>
        <span>{page} / {Math.ceil(total / 20)}，共 {total} 条</span>
        <button disabled={page * 20 >= total} onClick={() => load(page + 1)}>下一页</button>
      </div>
    )}
    </>
  )
}

function StatsSection() {
  const [stats, setStats] = useState<Record<string, any>>({})
  useEffect(() => { api.adminStats().then(setStats).catch(() => {}) }, [])

  return (
    <div className="portfolio-summary">
      <div className="kpi-card"><span className="kpi-label">数据库大小</span><span className="kpi-value">{stats.db_size_mb || 0} MB</span></div>
      <div className="kpi-card"><span className="kpi-label">注册用户</span><span className="kpi-value">{stats.users?.total || 0}</span></div>
      <div className="kpi-card"><span className="kpi-label">活跃用户</span><span className="kpi-value">{stats.users?.active || 0}</span></div>
      <div className="kpi-card"><span className="kpi-label">投研报告</span><span className="kpi-value">{stats.analyses || 0}</span></div>
      <div className="kpi-card"><span className="kpi-label">预警规则</span><span className="kpi-value">{stats.alerts || 0}</span></div>
      <div className="kpi-card"><span className="kpi-label">持仓记录</span><span className="kpi-value">{stats.portfolios || 0}</span></div>
    </div>
  )
}

function UsersSection() {
  const { toast } = useModal()
  const [users, setUsers] = useState<any[]>([])
  const load = () => { api.adminUsers().then(setUsers).catch(() => {}) }
  useEffect(() => { load() }, [])

  const toggleActive = async (id: number) => { try { await api.toggleUserActive(id); load() } catch { toast('操作失败', 'error') } }
  const setAdmin = async (id: number, val: boolean) => { try { await api.setUserAdmin(id, val); load() } catch { toast('设置失败', 'error') } }

  return (
    <table className="portfolio-table">
      <thead><tr><th>ID</th><th>用户名</th><th>注册时间</th><th>管理员</th><th>状态</th><th>投研数</th><th>操作</th></tr></thead>
      <tbody>
        {users.map(u => (
          <tr key={u.id}>
            <td>{u.id}</td>
            <td className="pf-name">{u.username}</td>
            <td>{(u.created_at || '').slice(0, 10)}</td>
            <td>
              <label className="admin-toggle">
                <input type="checkbox" checked={!!u.is_admin} onChange={e => setAdmin(u.id, e.target.checked)} />
                <span>{u.is_admin ? '管理员' : '普通'}</span>
              </label>
            </td>
            <td className={u.is_active ? 'up' : 'down'}>{u.is_active ? '正常' : '禁用'}</td>
            <td>{u.analysis_count}</td>
            <td><button className="admin-action-btn" onClick={() => toggleActive(u.id)}>{u.is_active ? '禁用' : '启用'}</button></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function InviteSection() {
  const { toast } = useModal()
  const [codes, setCodes] = useState<any[]>([])
  const [note, setNote] = useState('')
  const load = () => { api.adminInvites().then(setCodes).catch(() => {}) }
  useEffect(() => { load() }, [])
  const create = async () => { try { await api.createInvite(note); setNote(''); load() } catch { toast('创建邀请码失败', 'error') } }

  return (
    <>
      <div className="trade-form" style={{ marginBottom: 16 }}>
        <input className="alert-input" placeholder="备注（可选）" value={note} onChange={e => setNote(e.target.value)} />
        <button className="btn-primary" onClick={create}>生成邀请码</button>
      </div>
      <table className="portfolio-table">
        <thead><tr><th>邀请码</th><th>创建人</th><th>创建时间</th><th>使用人</th><th>状态</th></tr></thead>
        <tbody>
          {codes.length === 0 && <tr><td colSpan={5} className="empty-row">暂无邀请码（空表时注册不需要邀请码）</td></tr>}
          {codes.map(c => (
            <tr key={c.code}>
              <td className="pf-code">{c.code}</td>
              <td>{c.created_by_name || c.created_by}</td>
              <td>{(c.created_at || '').slice(0, 16)}</td>
              <td>{c.used_by || '-'}</td>
              <td className={c.used_by ? '' : 'up'}>{c.used_by ? '已使用' : '可用'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

function AuditSection() {
  const [logs, setLogs] = useState<any[]>([])
  useEffect(() => { api.adminAuditLogs().then(setLogs).catch(() => {}) }, [])

  return (
    <table className="portfolio-table">
      <thead><tr><th>时间</th><th>用户</th><th>操作</th><th>详情</th><th>IP</th></tr></thead>
      <tbody>
        {logs.length === 0 && <tr><td colSpan={5} className="empty-row">暂无日志</td></tr>}
        {logs.map(l => (
          <tr key={l.id}>
            <td>{(l.created_at || '').slice(0, 19)}</td>
            <td className="pf-name">{l.username || l.user_id}</td>
            <td>{l.action}</td>
            <td className="pf-code">{l.detail}</td>
            <td className="pf-code">{l.ip}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
