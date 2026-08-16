import { useEffect, useState, lazy, Suspense } from 'react'
import {
  Activity, Briefcase, CalendarClock, CandlestickChart, FileSearch, FlaskConical,
  Globe, History, Home, MessageSquare, PanelLeftClose, PanelLeftOpen,
  ScrollText, Shield, User, type LucideIcon,
} from 'lucide-react'
import { api, setLoggedIn } from './api'
import type { AuthResponse } from './types'
import LoginPage from './LoginPage'
import AlertBell from './AlertBell'
import FeedbackWidget from './FeedbackWidget'
import { ErrorBoundary } from './ErrorBoundary'

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
const ALL_TABS: Tab[] = ['home', 'chat', 'quote', 'market', 'analyze', 'portfolio', 'backtest', 'signal', 'scheduler', 'thesis', 'history', 'profile', 'admin']

// hash 路由：#/quote 形式，刷新/分享链接/浏览器前进后退均可恢复页面
function tabFromHash(): Tab | null {
  const h = window.location.hash.replace(/^#\/?/, '').split('?')[0]
  return (ALL_TABS as string[]).includes(h) ? (h as Tab) : null
}

const NAV_ICONS: Record<Tab, LucideIcon> = {
  home: Home,
  analyze: FileSearch,
  chat: MessageSquare,
  thesis: ScrollText,
  quote: CandlestickChart,
  market: Globe,
  portfolio: Briefcase,
  backtest: FlaskConical,
  signal: Activity,
  scheduler: CalendarClock,
  history: History,
  profile: User,
  admin: Shield,
}

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
]
// 个人中心/管理后台保持独立页面，入口在头像菜单；历史记录走抽屉

function useTheme() {
  const [theme, setTheme] = useState(() => localStorage.getItem('fc_theme_v3') || 'light')
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('fc_theme_v3', theme)
  }, [theme])
  return { theme, toggle: () => setTheme(t => t === 'dark' ? 'light' : 'dark') }
}

function App() {
  const [tab, setTab] = useState<Tab>(() => tabFromHash() ?? 'home')
  // 桌面端默认展开侧边栏并记住用户选择；移动端保持抽屉式
  const [navOpen, setNavOpen] = useState(() => {
    if (!window.matchMedia('(min-width: 769px)').matches) return false
    const stored = localStorage.getItem('fc_nav_open')
    return stored === null ? true : stored === '1'
  })
  const persistNav = (open: boolean) => {
    setNavOpen(open)
    localStorage.setItem('fc_nav_open', open ? '1' : '0')
  }
  const [auth, setAuth] = useState<AuthResponse | null>(null)
  const [booted, setBooted] = useState(false)
  const [isAdmin, setIsAdmin] = useState(false)
  const [loginTarget, setLoginTarget] = useState<Tab | null>(null)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [feedbackAfterLogin, setFeedbackAfterLogin] = useState(false)
  const { theme, toggle } = useTheme()

  // 启动时通过 /api/auth/me 确认登录态（HttpOnly Cookie 认证，前端不保存 token）
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('oauth_error')) setLoginTarget('home')
    api.me()
      .then((r) => {
        if (!r?.user) { setLoggedIn(false); return }
        setLoggedIn(true)
        setAuth({ token: 'cookie', user: r.user, profile: r.profile })
        // replaceState 不触发 hashchange，避免与下方监听器竞争
        const initial = tabFromHash()
        if (!initial) window.history.replaceState({}, '', '#/analyze')
        setTab(initial ?? 'analyze')
        // 检查管理员权限
        api.isAdmin().then(res => setIsAdmin(res.is_admin)).catch(() => {})
      })
      .catch(() => setLoggedIn(false))
      .finally(() => setBooted(true))
  }, [])

  useEffect(() => {
    if (!navOpen) return
    const close = (event: KeyboardEvent) => event.key === 'Escape' && setNavOpen(false)
    document.addEventListener('keydown', close)
    return () => document.removeEventListener('keydown', close)
  }, [navOpen])

  // 头像菜单：点击外部或 Escape 关闭
  useEffect(() => {
    if (!userMenuOpen) return
    const close = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest('.sidebar-footer')) setUserMenuOpen(false)
    }
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setUserMenuOpen(false)
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc) }
  }, [userMenuOpen])

  // 视口状态：≤768px 为抽屉模式（自动收起），桌面为 rail/常驻模式
  const [isCompact, setIsCompact] = useState(() => window.matchMedia('(max-width: 768px)').matches)
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)')
    const onChange = () => { setIsCompact(mq.matches); if (mq.matches) setNavOpen(false) }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  useEffect(() => {
    const requireAuth = () => setLoginTarget(tab)
    window.addEventListener('financecrew:auth-required', requireAuth)
    return () => window.removeEventListener('financecrew:auth-required', requireAuth)
  }, [tab])

  // 浏览器前进/后退时同步 tab
  useEffect(() => {
    const onHashChange = () => {
      const next = tabFromHash()
      if (!next || next === tab) return
      if (!auth && !PUBLIC_TABS.has(next)) {
        setLoginTarget(next)
        window.history.replaceState({}, '', `#/${tab}`)
        return
      }
      setTab(next)
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [tab, auth])

  if (!booted) return <div className="boot-screen"><span className="loading loading-center">加载中...</span></div>

  const navigate = (next: Tab) => {
    // 移动端抽屉模式下导航后收起；桌面常驻模式不受影响
    if (window.matchMedia('(max-width: 768px)').matches) setNavOpen(false)
    if (!auth && !PUBLIC_TABS.has(next)) {
      setLoginTarget(next)
      return
    }
    // pushState 不触发 hashchange，避免与监听器闭包中的旧 auth 状态竞争
    window.history.pushState({}, '', `#/${next}`)
    setTab(next)
  }

  const handleLogin = (result: AuthResponse) => {
    setAuth(result)
    if (loginTarget) {
      window.history.pushState({}, '', `#/${loginTarget}`)
      setTab(loginTarget)
    }
    setLoginTarget(null)
    if (feedbackAfterLogin) {
      setFeedbackAfterLogin(false)
      setFeedbackOpen(true)
    }
    api.isAdmin().then(res => setIsAdmin(res.is_admin)).catch(() => {})
  }

  const logout = () => {
    api.logout().catch(() => {})
    setLoggedIn(false)
    setAuth(null)
    setIsAdmin(false)
    window.history.pushState({}, '', '#/home')
    setTab('home')
  }

  // 游客可见全部主导航（受保护页面点击时才弹登录）；原「我的」分组已并入头像菜单
  const visibleGroups = NAV_GROUPS
  const activeLabel = visibleGroups.flatMap(group => group.items).find(item => item.tab === tab)?.label
    ?? (tab === 'profile' ? '个人中心' : tab === 'admin' ? '管理后台' : undefined)
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
      case 'profile': return <ProfilePage />
      case 'admin': return isAdmin ? <AdminPage /> : null
    }
  })()

  return (
    <div className={`app-shell${navOpen ? ' nav-open' : ''}`}>
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <aside id="main-navigation" className={`sidebar${navOpen ? ' open' : ''}`}>
        <div className="brand">
          {/* 收起态：品牌图标位置换成展开按钮，操作点固定不动 */}
          {!navOpen && !isCompact ? (
            <button className="brand-mark brand-expand" aria-label="展开侧边栏" title="展开侧边栏" onClick={() => persistNav(true)}><PanelLeftOpen aria-hidden="true" size={18} strokeWidth={1.8} /></button>
          ) : (
            <div className="brand-mark"><img src="/favicon.svg" alt="" /></div>
          )}
          <h1>FinanceCrew<small>个人投研工作台</small></h1>
          {navOpen && <button className="sidebar-close" aria-label="收起侧边栏" title="收起侧边栏" onClick={() => persistNav(false)}><PanelLeftClose aria-hidden="true" size={18} strokeWidth={1.8} /></button>}
        </div>
        <nav aria-label="主导航" className="side-nav">
          {visibleGroups.map(group => (
            <div className="nav-group" key={group.label}>
              <div className="nav-group-label">{group.label}</div>
              {group.items.map(item => {
                const Icon = NAV_ICONS[item.tab]
                return (
                  <button key={item.tab} aria-current={tab === item.tab ? 'page' : undefined} title={item.label} className={tab === item.tab ? 'active' : ''} onClick={() => navigate(item.tab)}>
                    <Icon aria-hidden="true" size={16} strokeWidth={1.8} />
                    <span>{item.label}</span>
                  </button>
                )
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          {!navOpen && !isCompact ? null : auth ? (
            <>
              <button
                className="sidebar-user"
                aria-haspopup="menu"
                aria-expanded={userMenuOpen}
                onClick={() => setUserMenuOpen(v => !v)}
              >
                <span className="sidebar-avatar" aria-hidden="true">{auth.user.username[0]?.toUpperCase() || '?'}</span>
                <span className="sidebar-username">{auth.user.username}</span>
                <span className={`sidebar-user-caret${userMenuOpen ? ' open' : ''}`} aria-hidden="true">▴</span>
              </button>
              {userMenuOpen && (
                <div className="user-popover" role="menu">
                  <button role="menuitem" onClick={() => { setUserMenuOpen(false); navigate('profile') }}>
                    <User aria-hidden="true" size={14} strokeWidth={1.8} /><span>个人中心</span>
                  </button>
                  <button role="menuitem" onClick={() => { setUserMenuOpen(false); setHistoryOpen(true) }}>
                    <History aria-hidden="true" size={14} strokeWidth={1.8} /><span>历史记录</span>
                  </button>
                  {isAdmin && (
                    <button role="menuitem" onClick={() => { setUserMenuOpen(false); navigate('admin') }}>
                      <Shield aria-hidden="true" size={14} strokeWidth={1.8} /><span>管理后台</span>
                    </button>
                  )}
                  <div className="user-popover-divider" />
                  <button role="menuitem" onClick={toggle}>
                    <span>{theme === 'dark' ? '切换亮色' : '切换暗色'}</span>
                  </button>
                  <button role="menuitem" className="danger" onClick={() => { setUserMenuOpen(false); logout() }}>
                    <span>退出登录</span>
                  </button>
                </div>
              )}
            </>
          ) : (
            <div className="sidebar-guest-row">
              <button className="sidebar-login" onClick={() => setLoginTarget(tab)}>登录</button>
              <button className="ghost" onClick={toggle} title={theme === 'dark' ? '切换亮色' : '切换暗色'}>{theme === 'dark' ? '亮色' : '暗色'}</button>
            </div>
          )}
        </div>
      </aside>
      <button className={`nav-backdrop${navOpen ? ' open' : ''}`} aria-hidden="true" tabIndex={-1} onClick={() => setNavOpen(false)} />
      <div className="workspace">
        <header className="workspace-header">
          {!navOpen && isCompact && <button className="sidebar-trigger" aria-label="展开侧边栏" aria-controls="main-navigation" aria-expanded="false" onClick={() => persistNav(true)}><PanelLeftOpen aria-hidden="true" size={18} strokeWidth={1.8} /></button>}
          <div className="workspace-title">
            <div className="workspace-eyebrow">FinanceCrew / {activeLabel}</div>
            <h2>{activeLabel}</h2>
          </div>
        {auth && (
          <div className="user-menu">
            <AlertBell />
          </div>
        )}
        </header>
      <main id="main-content" className="workspace-main" tabIndex={-1}>
        <ErrorBoundary>
        <Suspense fallback={<div className="loading loading-center">加载中...</div>}>
          {activePage}
        </Suspense>
        </ErrorBoundary>
      </main>
      </div>
      {historyOpen && (
        <div className="drawer-overlay" role="dialog" aria-modal="true" aria-label="历史记录" onClick={() => setHistoryOpen(false)}>
          <div className="drawer-panel" onClick={e => e.stopPropagation()}>
            <div className="drawer-head">
              <h3>历史记录</h3>
              <button className="ghost" aria-label="关闭" onClick={() => setHistoryOpen(false)}>✕</button>
            </div>
            <div className="drawer-body">
              <Suspense fallback={<div className="loading loading-center">加载中...</div>}>
                <HistoryPane onPick={() => { setHistoryOpen(false); navigate('analyze') }} />
              </Suspense>
            </div>
          </div>
        </div>
      )}
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
