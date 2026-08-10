import { useEffect, useState, lazy, Suspense } from 'react'
import { api, getToken, setToken } from './api'
import type { AuthResponse } from './types'
import LoginPage from './LoginPage'
import AlertBell from './AlertBell'
import { ErrorBoundary } from './ErrorBoundary'
import './App.css'

// 懒加载页面组件 - 只挂载当前页面，避免隐藏页面消耗行情接口额度
const ChatPage = lazy(() => import('./ChatPage'))
const QuotePage = lazy(() => import('./QuotePage'))
const AnalyzePane = lazy(() => import('./AnalyzePage'))
const HistoryPane = lazy(() => import('./HistoryPage'))
const PortfolioPage = lazy(() => import('./PortfolioPage'))
const BacktestPage = lazy(() => import('./BacktestPage'))
const MarketDataPage = lazy(() => import('./MarketDataPage'))
const ProfilePage = lazy(() => import('./ProfilePage'))
const AdminPage = lazy(() => import('./AdminPage'))
const SchedulerPage = lazy(() => import('./SchedulerPage'))
const ThesisPage = lazy(() => import('./ThesisPage'))

type Tab = 'chat' | 'quote' | 'market' | 'analyze' | 'portfolio' | 'backtest' | 'scheduler' | 'thesis' | 'history' | 'profile' | 'admin'

const NAV_GROUPS: { label: string; items: { tab: Tab; label: string }[] }[] = [
  { label: '研究', items: [
    { tab: 'analyze', label: '投研分析' },
    { tab: 'chat', label: '智能对话' },
    { tab: 'thesis', label: '投资论文' },
  ] },
  { label: '市场与资产', items: [
    { tab: 'quote', label: '行情' },
    { tab: 'market', label: '市场数据' },
    { tab: 'portfolio', label: '投资组合' },
  ] },
  { label: '策略', items: [
    { tab: 'backtest', label: '策略回测' },
    { tab: 'scheduler', label: '定时分析' },
  ] },
  { label: '我的', items: [
    { tab: 'history', label: '历史记录' },
    { tab: 'profile', label: '个人中心' },
  ] },
]

function useTheme() {
  const [theme, setTheme] = useState(() => localStorage.getItem('fc_theme_v3') || 'light')
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('fc_theme_v3', theme)
  }, [theme])
  return { theme, toggle: () => setTheme(t => t === 'dark' ? 'light' : 'dark') }
}

function App() {
  const [tab, setTab] = useState<Tab>('analyze')
  const [auth, setAuth] = useState<AuthResponse | null>(null)
  const [booted, setBooted] = useState(false)
  const [isAdmin, setIsAdmin] = useState(false)
  const { theme, toggle } = useTheme()

  // 启动时校验 token
  useEffect(() => {
    if (!getToken()) { setBooted(true); return }
    api.me()
      .then((r) => {
        setAuth({ token: getToken()!, user: r.user, profile: r.profile })
        setTab('analyze')
        // 检查管理员权限
        api.isAdmin().then(res => setIsAdmin(res.is_admin)).catch(() => {})
      })
      .catch(() => setToken(null))
      .finally(() => setBooted(true))
  }, [])

  if (!booted) return <div className="boot-screen">加载中...</div>

  if (!auth) {
    return <LoginPage onLogin={(r) => {
      setAuth(r); setTab('analyze')
      // 登录后检查管理员权限
      api.isAdmin().then(res => setIsAdmin(res.is_admin)).catch(() => {})
    }} />
  }

  const logout = () => {
    setToken(null)
    setAuth(null)
  }

  const visibleGroups = isAdmin
    ? [...NAV_GROUPS, { label: '系统', items: [{ tab: 'admin' as Tab, label: '管理后台' }] }]
    : NAV_GROUPS
  const activeLabel = visibleGroups.flatMap(group => group.items).find(item => item.tab === tab)?.label
  const activePage = (() => {
    switch (tab) {
      case 'chat': return <ChatPage />
      case 'quote': return <QuotePage />
      case 'market': return <MarketDataPage />
      case 'analyze': return <AnalyzePane onBacktest={() => setTab('backtest')} onQuote={() => setTab('quote')} />
      case 'portfolio': return <PortfolioPage />
      case 'backtest': return <BacktestPage />
      case 'scheduler': return <SchedulerPage />
      case 'thesis': return <ThesisPage />
      case 'history': return <HistoryPane onPick={() => setTab('analyze')} />
      case 'profile': return <ProfilePage />
      case 'admin': return isAdmin ? <AdminPage /> : null
    }
  })()

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">FC</div>
          <h1>FinanceCrew<small>个人投研工作台</small></h1>
        </div>
        <nav aria-label="主导航" className="side-nav">
          {visibleGroups.map(group => (
            <div className="nav-group" key={group.label}>
              <div className="nav-group-label">{group.label}</div>
              {group.items.map(item => (
                <button key={item.tab} aria-current={tab === item.tab ? 'page' : undefined} className={tab === item.tab ? 'active' : ''} onClick={() => setTab(item.tab)}>{item.label}</button>
              ))}
            </div>
          ))}
        </nav>
      </aside>
      <div className="workspace">
        <header className="workspace-header">
          <div>
            <div className="workspace-eyebrow">FinanceCrew / {activeLabel}</div>
            <h2>{activeLabel}</h2>
          </div>
        <div className="user-menu">
          <AlertBell />
          <button className="ghost" onClick={toggle} title="切换主题">{theme === 'dark' ? '亮色' : '暗色'}</button>
          <span className="user-name">{auth.user.username}</span>
          <button className="ghost" onClick={logout}>退出</button>
        </div>
        </header>
      <main id="main-content" className="workspace-main" tabIndex={-1}>
        <ErrorBoundary>
        <Suspense fallback={<div style={{padding:'40px',textAlign:'center',color:'var(--text-2)'}}>加载中...</div>}>
          {activePage}
        </Suspense>
        </ErrorBoundary>
      </main>
      </div>
    </div>
  )
}

export default App
