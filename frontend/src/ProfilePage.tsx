import { useEffect, useState } from 'react'
import { api } from './api'
import type { LLMConfig, UserProfile } from './types'

type Section = 'membership' | 'llm' | 'profile' | 'analysts' | 'password'

export default function ProfilePage() {
  const [section, setSection] = useState<Section>('membership')

  return (
    <div className="pane profile-page">
      <div className="pane-head">
        <h2>个人中心</h2>
      </div>

      <div className="profile-sections">
        <div className="profile-nav">
          <button className={section === 'membership' ? 'active' : ''} onClick={() => setSection('membership')}>会员服务</button>
          <button className={section === 'llm' ? 'active' : ''} onClick={() => setSection('llm')}>模型配置</button>
          <button className={section === 'profile' ? 'active' : ''} onClick={() => setSection('profile')}>用户画像</button>
          <button className={section === 'analysts' ? 'active' : ''} onClick={() => setSection('analysts')}>分析师配置</button>
          <button className={section === 'password' ? 'active' : ''} onClick={() => setSection('password')}>修改密码</button>
        </div>

        <div className="profile-content">
          {section === 'membership' && <MembershipSection />}
          {section === 'llm' && <LLMConfigSection />}
          {section === 'profile' && <UserProfileSection />}
          {section === 'analysts' && <AnalystConfigSection />}
          {section === 'password' && <PasswordSection />}
        </div>
      </div>
    </div>
  )
}

function MembershipSection() {
  const [config, setConfig] = useState<{plans: {code:string;name:string;amount_fen:number}[];channels: Record<string, boolean>} | null>(null)
  const [membership, setMembership] = useState<{plan:string;membership_expires_at:string|null;model_usage:{used:number;limit:number|null;remaining:number|null}} | null>(null)
  const [plan, setPlan] = useState('monthly')
  const [channel, setChannel] = useState('wechat')
  const [order, setOrder] = useState<{order_no:string;channel:string;status:string;qr_code?:string;pay_url?:string} | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const orderNo = order?.order_no
  const orderStatus = order?.status

  const refresh = () => Promise.all([api.getPaymentConfig(), api.getCapabilities()])
    .then(([payment, capability]) => { setConfig(payment); setMembership(capability) })
    .catch((e) => setErr(e instanceof Error ? e.message : '加载会员信息失败'))

  useEffect(() => { refresh() }, [])

  useEffect(() => {
    if (!orderNo || orderStatus === 'paid') return
    const timer = window.setInterval(() => {
      api.getPaymentOrder(orderNo).then((next) => {
        setOrder((current) => current ? { ...current, ...next } : next)
        if (next.status === 'paid') refresh()
      }).catch(() => {})
    }, 3000)
    return () => window.clearInterval(timer)
  }, [orderNo, orderStatus])

  const buy = async () => {
    setBusy(true); setErr('')
    try {
      const next = await api.createPaymentOrder(plan, channel)
      setOrder(next)
      if (next.pay_url) window.open(next.pay_url, '_blank', 'noopener,noreferrer')
    } catch (e) {
      setErr(e instanceof Error ? e.message : '创建支付订单失败')
    } finally { setBusy(false) }
  }

  if (!config || !membership) return <div className="profile-loading">加载中...</div>
  const isMember = membership.plan !== 'free'
  return (
    <div className="config-section membership-section">
      <div className="membership-current">
        <strong>{isMember ? '专业会员' : '免费用户'}</strong>
        <span>{isMember ? `有效期至 ${membership.membership_expires_at?.slice(0, 10) || '长期'}` : `本月 AI 剩余 ${membership.model_usage.remaining ?? 0} 次`}</span>
      </div>
      <div className="plan-cards">
        {config.plans.map(item => <button key={item.code} className={plan === item.code ? 'active' : ''} onClick={() => setPlan(item.code)}>
          <strong>{item.name}</strong><span>¥{(item.amount_fen / 100).toFixed(0)}</span>
        </button>)}
      </div>
      <div className="payment-channels">
        <label><input type="radio" checked={channel === 'wechat'} onChange={() => setChannel('wechat')} />微信支付</label>
        <label><input type="radio" checked={channel === 'alipay'} onChange={() => setChannel('alipay')} />支付宝</label>
      </div>
      {!config.channels[channel] && <p className="hint">该渠道尚未配置商户信息，配置后即可购买。</p>}
      <button className="btn-primary" disabled={busy || !config.channels[channel]} onClick={buy}>{busy ? '创建订单中...' : '立即购买'}</button>
      {order?.qr_code && <div className="payment-code"><img src={order.qr_code} alt="微信支付二维码" /><span>请使用微信扫码支付</span></div>}
      {order?.pay_url && order.status !== 'paid' && <a className="payment-link" href={order.pay_url} target="_blank" rel="noreferrer">重新打开支付宝收银台</a>}
      {order?.status === 'paid' && <span className="ok-msg">支付成功，会员已开通</span>}
      {err && <span className="err-msg">{err}</span>}
    </div>
  )
}

/* ---------------- 模型配置（per-user） ---------------- */

function LLMConfigSection() {
  const [cfg, setCfg] = useState<LLMConfig | null>(null)
  const [providers, setProviders] = useState<Record<string, { base_url: string; model: string }>>({})
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    Promise.all([api.getUserLLMConfig(), api.getProviders()])
      .then(([c, p]) => { setCfg(c); setProviders(p) })
      .catch((e) => setErr(e instanceof Error ? e.message : '加载配置失败'))
  }, [])

  const set = (patch: Partial<LLMConfig>) => setCfg((c) => (c ? { ...c, ...patch } : c))

  const pickProvider = (provider: string) => {
    if (!cfg) return
    const p = providers[provider]
    set({ provider, base_url: p?.base_url ?? '', model: p?.model ?? '' })
  }

  const save = async () => {
    if (!cfg) return
    setSaving(true); setMsg(''); setErr('')
    try {
      const saved = await api.saveUserLLMConfig(cfg)
      setCfg(saved)
      setMsg('配置已保存（API Key 加密存储）')
    } catch (e) {
      setErr(e instanceof Error ? e.message : '保存失败')
    } finally { setSaving(false) }
  }

  if (!cfg) return <div className="profile-loading">加载中...</div>

  return (
    <div className="config-section">
      <p className="hint">每个用户的 API Key 独立保存，使用 AES-256-GCM 加密存储在数据库中。前端始终脱敏显示。</p>

      <label>服务商
        <select value={cfg.provider} onChange={(e) => pickProvider(e.target.value)}>
          {Object.keys(providers).map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </label>

      <label>接口地址
        <input value={cfg.base_url} onChange={(e) => set({ base_url: e.target.value })} placeholder="https://api.deepseek.com/v1" />
      </label>

      <label>API Key
        <input value={cfg.api_key} onChange={(e) => set({ api_key: e.target.value })} placeholder="留空保留原值" type="password" />
      </label>

      <label>模型名称
        <input value={cfg.model} onChange={(e) => set({ model: e.target.value })} placeholder="deepseek-chat" />
      </label>

      <label>温度
        <input type="number" step="0.1" min="0" max="2" value={cfg.temperature} onChange={(e) => set({ temperature: Number(e.target.value) })} />
      </label>

      <div className="config-actions">
        <button className="btn-primary" onClick={save} disabled={saving}>{saving ? '保存中...' : '保存配置'}</button>
        {msg && <span className="ok-msg">{msg}</span>}
        {err && <span className="err-msg">{err}</span>}
      </div>
    </div>
  )
}

/* ---------------- 用户画像 ---------------- */

function UserProfileSection() {
  const [risk, setRisk] = useState('balanced')
  const [watchlistText, setWatchlistText] = useState('')
  const [, setProfile] = useState<UserProfile | null>(null)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.getProfile()
      .then((p) => {
        setProfile(p)
        setRisk(p.risk_preference)
        setWatchlistText((p.watchlist || []).join(', '))
      })
      .catch(() => {})
  }, [])

  const save = async () => {
    setBusy(true); setMsg(''); setErr('')
    try {
      const watchlist = watchlistText.split(/[,，\s]+/).filter(Boolean).map((s) => s.replace(/\D/g, '').slice(0, 6)).filter(Boolean)
      const updated = await api.saveProfile({ risk_preference: risk, watchlist })
      setProfile(updated)
      setMsg('画像已保存')
    } catch (e) {
      setErr(e instanceof Error ? e.message : '保存失败')
    } finally { setBusy(false) }
  }

  return (
    <div className="config-section">
      <p className="hint">画像用于个性化投研建议（风险偏好影响仓位建议）。</p>

      <label>风险偏好
        <select value={risk} onChange={(e) => setRisk(e.target.value)}>
          <option value="conservative">保守（低仓位，重止损）</option>
          <option value="balanced">平衡（默认）</option>
          <option value="aggressive">激进（可高仓位）</option>
        </select>
      </label>

      <label>自选股（逗号分隔）
        <input value={watchlistText} onChange={(e) => setWatchlistText(e.target.value)} placeholder="600519, 000001, 300750" />
      </label>

      <div className="config-actions">
        <button className="btn-primary" onClick={save} disabled={busy}>{busy ? '保存中...' : '保存画像'}</button>
        {msg && <span className="ok-msg">{msg}</span>}
        {err && <span className="err-msg">{err}</span>}
      </div>
    </div>
  )
}

/* ---------------- 修改密码 ---------------- */

function PasswordSection() {
  const [oldPwd, setOldPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [confirmPwd, setConfirmPwd] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!oldPwd || !newPwd) { setErr('请填写完整'); return }
    if (newPwd.length < 6) { setErr('新密码至少6位'); return }
    if (newPwd !== confirmPwd) { setErr('两次密码不一致'); return }
    setBusy(true); setMsg(''); setErr('')
    try {
      await api.changePassword(oldPwd, newPwd)
      setMsg('密码修改成功')
      setOldPwd(''); setNewPwd(''); setConfirmPwd('')
    } catch (e) {
      setErr(e instanceof Error ? e.message : '修改失败')
    } finally { setBusy(false) }
  }

  return (
    <div className="config-section">
      <p className="hint">修改密码后需要重新登录。密码使用 PBKDF2-SHA256 哈希存储。</p>

      <label>旧密码
        <input type="password" value={oldPwd} onChange={(e) => setOldPwd(e.target.value)} placeholder="当前密码" />
      </label>
      <label>新密码
        <input type="password" value={newPwd} onChange={(e) => setNewPwd(e.target.value)} placeholder="至少6位" />
      </label>
      <label>确认新密码
        <input type="password" value={confirmPwd} onChange={(e) => setConfirmPwd(e.target.value)} placeholder="再输入一次" />
      </label>

      <div className="config-actions">
        <button className="btn-primary" onClick={submit} disabled={busy}>{busy ? '修改中...' : '修改密码'}</button>
        {msg && <span className="ok-msg">{msg}</span>}
        {err && <span className="err-msg">{err}</span>}
      </div>
    </div>
  )
}

function AnalystConfigSection() {
  const [analysts, setAnalysts] = useState<{role:string;title:string}[]>([])
  const [enabled, setEnabled] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    Promise.all([
      fetch('/api/analysts').then(r => r.json()),
      fetch('/api/auth/profile', { headers: { Authorization: 'Bearer ' + localStorage.getItem('financecrew_token') } }).then(r => r.json()),
    ]).then(([aList, profile]) => {
      setAnalysts(aList || [])
      const config = profile?.analyst_config
      setEnabled(Array.isArray(config) && config.length > 0 ? config : (aList || []).map((a:any) => a.role))
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const toggle = (role: string) => {
    setEnabled(prev => prev.includes(role) ? prev.filter(r => r !== role) : [...prev, role])
  }

  const save = async () => {
    if (enabled.length === 0) { setMsg('至少保留一个分析师'); return }
    setSaving(true); setMsg('')
    try {
      const r = await fetch('/api/auth/analyst-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + localStorage.getItem('financecrew_token') },
        body: JSON.stringify({ enabled_analysts: enabled }),
      })
      if (r.ok) { setMsg('保存成功') } else { setMsg('保存失败') }
    } catch { setMsg('网络错误') } finally { setSaving(false) }
  }

  if (loading) return <div style={{ padding: 20, color: '#888' }}>加载中...</div>

  return (
    <div className="config-section">
      <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 16 }}>
        选择投研分析时启用的分析师。未启用的分析师不会参与分析和投票。
      </p>
      <div className="analyst-list">
        {analysts.map(a => (
          <label key={a.role} className="analyst-item">
            <input type="checkbox" checked={enabled.includes(a.role)} onChange={() => toggle(a.role)} />
            <span className="analyst-title">{a.title}</span>
            <span className="analyst-role">{a.role}</span>
          </label>
        ))}
      </div>
      <div className="config-actions">
        <button className="btn-primary" onClick={save} disabled={saving}>
          {saving ? '保存中...' : '保存配置'}
        </button>
        {msg && <span className={msg === '保存成功' ? 'ok-msg' : 'err-msg'}>{msg}</span>}
      </div>
    </div>
  )
}
