import { useEffect, useState, lazy, Suspense } from 'react'
import { api, getToken, setToken } from './api'
import type { AuthResponse } from './types'
import LoginPage from './LoginPage'
import AlertBell from './AlertBell'
import FeedbackWidget from './FeedbackWidget'
import { ErrorBoundary } from './ErrorBoundary'
import './App.css'

// 懒加载页面组件 - 只挂载当前页面，避免隐藏页面消耗行情接口额度
const ChatPage = lazy(() => import('./ChatPage'))
const LandingPage = lazy(() => import('./LandingPage'))
const QuotePage = lazy(() => import('./QuotePage'))
const AnalyzePane = lazy(() => import('./AnalyzePage'))
const HistoryPane = lazy(() => import('./HistoryPage'))
const PortfolioPage = lazy(() => import('./PortfolioPage'))
const BacktestPage = lazy(() => import('./BacktestPage'))
const MLSignalPage = lazy(() => import('./MLSignalPage'))
const MarketDataPage = lazy(() => import('./MarketDataPage'))
const ProfilePage = lazy(() => import('./ProfilePage'))
const AdminPage = lazy(() => import('./AdminPage'))
const SchedulerPage = lazy(() => import('./SchedulerPage'))
const ThesisPage = lazy(() => import('./ThesisPage'))

type Tab = 'home' | 'chat' | 'quote' | 'market' | 'analyze' | 'portfolio' | 'backtest' | 'signal' | 'scheduler' | 'thesis' | 'history' | 'profile' | 'admin'

const PUBLIC_TABS = new Set<Tab>(['home', 'quote', 'market'])

const NAV_GROUPS: { label: string; items: { tab: Tab; label: string }[] }[] = [
  { label: '开始', items: [{ tab: 'home', label: '产品首页' }] },
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
    { tab: 'signal', label: '信号诊断' },
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
  const [tab, setTab] = useState<Tab>('home')
  const [navOpen, setNavOpen] = useState(false)
  const [auth, setAuth] = useState<AuthResponse | null>(null)
  const [booted, setBooted] = useState(false)
  const [isAdmin, setIsAdmin] = useState(false)
  const [loginTarget, setLoginTarget] = useState<Tab | null>(null)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [feedbackAfterLogin, setFeedbackAfterLogin] = useState(false)
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

  useEffect(() => {
    if (!navOpen) return
    const close = (event: KeyboardEvent) => event.key === 'Escape' && setNavOpen(false)
    document.addEventListener('keydown', close)
    return () => document.removeEventListener('keydown', close)
  }, [navOpen])

  useEffect(() => {
    const requireAuth = () => setLoginTarget(tab)
    window.addEventListener('financecrew:auth-required', requireAuth)
    return () => window.removeEventListener('financecrew:auth-required', requireAuth)
  }, [tab])

  if (!booted) return <div className="boot-screen">加载中...</div>

  const navigate = (next: Tab) => {
    setNavOpen(false)
    if (!auth && !PUBLIC_TABS.has(next)) {
      setLoginTarget(next)
      return
    }
    setTab(next)
  }

  const handleLogin = (result: AuthResponse) => {
    setAuth(result)
    if (loginTarget) setTab(loginTarget)
    setLoginTarget(null)
    if (feedbackAfterLogin) {
      setFeedbackAfterLogin(false)
      setFeedbackOpen(true)
    }
    api.isAdmin().then(res => setIsAdmin(res.is_admin)).catch(() => {})
  }

  const logout = () => {
    setToken(null)
    setAuth(null)
    setIsAdmin(false)
    setTab('home')
  }

  const visibleGroups = isAdmin
    ? [...NAV_GROUPS, { label: '系统', items: [{ tab: 'admin' as Tab, label: '管理后台' }] }]
    : NAV_GROUPS
  const activeLabel = visibleGroups.flatMap(group => group.items).find(item => item.tab === tab)?.label
  const activePage = (() => {
    switch (tab) {
      case 'home': return <LandingPage onAnalyze={() => navigate('analyze')} onQuote={() => navigate('quote')} />
      case 'chat': return <ChatPage />
      case 'quote': return <QuotePage />
      case 'market': return <MarketDataPage />
      case 'analyze': return <AnalyzePane onBacktest={() => navigate('backtest')} onQuote={() => navigate('quote')} />
      case 'portfolio': return <PortfolioPage />
      case 'backtest': return <BacktestPage />
      case 'signal': return <MLSignalPage />
      case 'scheduler': return <SchedulerPage />
      case 'thesis': return <ThesisPage />
      case 'history': return <HistoryPane onPick={() => navigate('analyze')} />
      case 'profile': return <ProfilePage />
      case 'admin': return isAdmin ? <AdminPage /> : null
    }
  })()

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <aside className={`sidebar${navOpen ? ' open' : ''}`}>
        <div className="brand">
          <div className="brand-mark">FC</div>
          <h1>FinanceCrew<small>个人投研工作台</small></h1>
        </div>
        <nav aria-label="主导航" className="side-nav">
          {visibleGroups.map(group => (
            <div className="nav-group" key={group.label}>
              <div className="nav-group-label">{group.label}</div>
              {group.items.map(item => (
                <button key={item.tab} aria-current={tab === item.tab ? 'page' : undefined} className={tab === item.tab ? 'active' : ''} onClick={() => navigate(item.tab)}>{item.label}</button>
              ))}
            </div>
          ))}
        </nav>
      </aside>
      <button className={`nav-backdrop${navOpen ? ' open' : ''}`} aria-label="关闭导航菜单" onClick={() => setNavOpen(false)} />
      <div className="workspace">
        <header className="workspace-header">
          <button className="mobile-menu-btn" aria-label="打开导航菜单" aria-expanded={navOpen} onClick={() => setNavOpen(true)}>菜单</button>
          <div className="workspace-title">
            <div className="workspace-eyebrow">FinanceCrew / {activeLabel}</div>
            <h2>{activeLabel}</h2>
          </div>
        <div className="user-menu">
          {auth && <AlertBell />}
          <button className="ghost" onClick={toggle} title="切换主题">{theme === 'dark' ? '亮色' : '暗色'}</button>
          {auth ? (
            <>
              <span className="user-name">{auth.user.username}</span>
              <button className="ghost" onClick={logout}>退出</button>
            </>
          ) : <button className="ghost" onClick={() => setLoginTarget(tab)}>登录</button>}
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
      <FeedbackWidget
        open={feedbackOpen}
        page={activeLabel || tab}
        onOpen={() => {
          if (auth) setFeedbackOpen(true)
          else {
            setFeedbackAfterLogin(true)
            setLoginTarget(tab)
          }
        }}
        onClose={() => setFeedbackOpen(false)}
      />
      {loginTarget && (
        <div className="login-overlay" role="dialog" aria-modal="true" aria-label="登录">
          <LoginPage
            onLogin={handleLogin}
            onCancel={() => {
              setLoginTarget(null)
              setFeedbackAfterLogin(false)
            }}
          />
        </div>
      )}
    </div>
  )
}

export default App
