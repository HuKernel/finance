import { useEffect, useState } from 'react'
import { api, setToken } from './api'
import { useModal } from './Modal'
import type { AuthResponse } from './types'

export default function LoginPage({ onLogin, onCancel }: { onLogin: (r: AuthResponse) => void; onCancel?: () => void }) {
  const { prompt } = useModal()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState(localStorage.getItem('fc_remember_user') || '')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [mfaCode, setMfaCode] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [remember, setRemember] = useState(!!localStorage.getItem('fc_remember_user'))
  const [error, setError] = useState(() => new URLSearchParams(window.location.search).get('oauth_error') ? 'GitHub 登录失败，请重试' : '')
  const [busy, setBusy] = useState(false)
  const [githubEnabled, setGithubEnabled] = useState(false)
  const [agreementsAccepted, setAgreementsAccepted] = useState(false)

  useEffect(() => {
    api.authProviders().then(result => setGithubEnabled(result.github)).catch(() => {})
    if (new URLSearchParams(window.location.search).get('oauth_error')) window.history.replaceState({}, '', window.location.pathname)
  }, [])

  const submit = async () => {
    if (!username.trim() || !password) {
      setError('请输入用户名和密码')
      return
    }
    setBusy(true)
    setError('')
    try {
      const r = mode === 'login'
        ? await api.login(username.trim(), password, mfaCode)
        : await api.register(username.trim(), password, inviteCode.trim(), email.trim(), agreementsAccepted)
      setToken(r.token)
      if (remember) {
        localStorage.setItem('fc_remember_user', username.trim())
        // 安全：不再明文存储密码，只记住用户名
      } else {
        localStorage.removeItem('fc_remember_user')
      }
      onLogin(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="login-brand">
          <div className="brand-mark"><img src="/favicon.svg" alt="" /></div>
          <h1>FinanceCrew</h1>
          <p>金融智能体投研团队</p>
        </div>
        <div className="tabs tabs-fill">
          <button className={`ghost ${mode === 'login' ? 'active' : ''}`} onClick={() => { setMode('login'); setError('') }}>登录</button>
          <button className={`ghost ${mode === 'register' ? 'active' : ''}`} onClick={() => { setMode('register'); setError('') }}>注册</button>
        </div>
        <input aria-label="用户名" autoComplete="username" placeholder="用户名" value={username} onChange={(e) => setUsername(e.target.value)} />
        <input aria-label="密码" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} placeholder="密码（至少 6 位）" type="password" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && submit()} />
        {mode === 'register' && <input aria-label="邮箱" type="email" placeholder="邮箱（用于验证和找回密码）" value={email} onChange={e => setEmail(e.target.value)} />}
        {mode === 'login' && <input aria-label="MFA 验证码" inputMode="numeric" placeholder="已启用 MFA 时填写 6 位验证码" value={mfaCode} onChange={e => setMfaCode(e.target.value)} />}
        {mode === 'register' && (
          <input aria-label="邀请码" placeholder="邀请码（如需要）" value={inviteCode} onChange={(e) => setInviteCode(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && submit()} />
        )}
        {mode === 'register' && <label className="login-remember"><input type="checkbox" checked={agreementsAccepted} onChange={e => setAgreementsAccepted(e.target.checked)} /><span>我已阅读并同意<a href="/terms.html" target="_blank">用户服务协议</a>和<a href="/privacy.html" target="_blank">隐私政策</a></span></label>}
        <label className="login-remember">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          <span>记住用户名</span>
        </label>
        {error && <div className="error-box" role="alert">{error}</div>}
        <button onClick={submit} disabled={busy} className="login-btn">
          {busy ? '处理中...' : mode === 'login' ? '登录' : '注册并登录'}
        </button>
        {mode === 'login' && <button className="ghost" onClick={async () => { const value = await prompt('请输入注册邮箱', { placeholder: '邮箱地址' }); if (value?.trim()) { try { await api.forgotPassword(value.trim()); setError('如果邮箱存在，重置链接已发送') } catch { setError('请求失败，请稍后重试') } } }}>忘记密码</button>}
        {githubEnabled && <>
          <div className="login-divider"><span>或</span></div>
          <button className="github-login" onClick={() => { window.location.href = '/api/auth/github/start' }}>
            <span aria-hidden="true">GitHub</span> 使用 GitHub 登录
          </button>
        </>}
        {onCancel && <button className="ghost login-cancel" onClick={onCancel}>暂不登录，继续浏览</button>}
      </div>
    </div>
  )
}
