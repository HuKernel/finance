// 后端 API 封装
import type {
  AnalysisResult, AuthResponse, ChatMessage, ChatReply, ChatSession,
  HistoryItem, LLMConfig, NewsItem, QuoteResponse, SearchItem, UserProfile,
  AlertItem, SentimentData, DCFResult, PortfolioPosition, PortfolioSummary,
  TransactionItem, BacktestResult, DataMetadata, NotificationItem,
} from './types'

const TOKEN_KEY = 'financecrew_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}
export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

// 登录态内存标记：启动时由 /api/auth/me 确认，登录/登出时更新
let _loggedIn = false
export function setLoggedIn(v: boolean) {
  _loggedIn = v
  if (!v) setToken(null)
}

export function requireLogin(): boolean {
  if (_loggedIn) return true
  window.dispatchEvent(new Event('financecrew:auth-required'))
  return false
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const resp = await fetch(url, { credentials: 'same-origin', headers, ...options })
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try {
      const data = await resp.json()
      if (data.detail) {
        detail = typeof data.detail === 'string'
          ? data.detail
          : Array.isArray(data.detail)
            ? data.detail.map((e: any) => e.msg || JSON.stringify(e)).join('; ')
            : JSON.stringify(data.detail)
      }
    } catch { /* ignore */ }
    if (resp.status === 401 && !url.includes('/auth/')) {
      setLoggedIn(false)
    }
    throw new Error(detail)
  }
  return resp.json() as Promise<T>
}

export const api = {
  // 通用 GET / POST（带 token，自动 json）
  get: <T = any>(url: string) => request<T>(url),
  post: <T = any>(url: string, body?: any) =>
    request<T>(url, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),

  getConfig: () => request<LLMConfig & { api_key_configured?: boolean }>('/api/config'),

  saveConfig: (cfg: LLMConfig) =>
    request<LLMConfig & { api_key_configured?: boolean }>('/api/config', { method: 'PUT', body: JSON.stringify(cfg) }),

  getProviders: () => request<Record<string, { base_url: string; model: string }>>('/api/providers'),

  runAnalysis: (ticker: string, topic?: string) =>
    request<AnalysisResult>('/api/analysis', {
      method: 'POST',
      body: JSON.stringify({ ticker, topic: topic || null }),
    }),

  streamAnalysis: async (
    ticker: string, topic: string | undefined,
    onEvent: (ev: any) => void,
    mode: string = 'standard'
  ): Promise<void> => {
    const token = getToken()
    const resp = await fetch('/api/analysis/stream', {
      credentials: 'same-origin',
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) },
      body: JSON.stringify({ ticker, topic: topic || null, mode }),
    })
    if (!resp.ok) {
      const data = await resp.json().catch(() => null)
      throw new Error(data?.detail || `HTTP ${resp.status}`)
    }
    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const parts = buf.split('\n\n')
      buf = parts.pop() ?? ''
      for (const part of parts) {
        const line = part.trim()
        if (!line.startsWith('data: ')) continue
        try { onEvent(JSON.parse(line.slice(6))) } catch { /* skip */ }
      }
    }
  },

  getAnalysis: (id: number) => request<{ result: AnalysisResult | null }>(`/api/analysis/${id}`),

  getHistory: () => request<HistoryItem[]>('/api/history'),

  deleteHistory: (id: number) => request<{ status: string }>(`/api/history/${id}`, { method: 'DELETE' }),

  getQuote: (symbol: string, days = 60, mode = 'day', fresh = 0, all = 0) =>
    request<QuoteResponse>(`/api/quote/${symbol}?days=${days}&mode=${mode}&fresh=${fresh}&all=${all}`),

  getNews: (symbol: string) => request<{ symbol: string; news: NewsItem[]; metadata?: DataMetadata }>(`/api/news/${symbol}`),

  getIndustry: (symbol: string) => request<{ peers: { code: string; name: string; pe: number; pb: number; change_pct: number; market_cap: number; is_target: boolean }[]; avg_pe: number | null; avg_pb: number | null }>(`/api/industry/${symbol}`),

  search: (q: string) => request<{ query: string; results: SearchItem[] }>(`/api/search/${encodeURIComponent(q)}`),

  health: () => request<{ status: string }>('/api/health'),

  getHotStocks: () => request<{ code: string; name: string; change_pct: number }[]>('/api/hot'),

  getTopTurnoverStock: () => request<{ code: string; name: string; amount: number; unit: string; scope: string; as_of: string }>('/api/market/top-turnover'),

  submitFeedback: (body: { category: string; content: string; page: string }) =>
    request<{ id: number; status: string }>('/api/feedback', {
      method: 'POST', body: JSON.stringify(body),
    }),
  listFeedback: (page: number = 1, pageSize: number = 10) =>
    request<{ items: any[]; total: number; page: number; page_size: number }>(`/api/feedback?page=${page}&page_size=${pageSize}`),

  // 认证
  register: (username: string, password: string, inviteCode?: string, email?: string, agreementsAccepted = false) =>
    request<AuthResponse>('/api/auth/register', { method: 'POST', body: JSON.stringify({ username, password, invite_code: inviteCode || '', email: email || '', agreements_accepted: agreementsAccepted }) }),

  login: (username: string, password: string, mfaCode?: string) =>
    request<AuthResponse>('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password, mfa_code: mfaCode || '' }) }),

  authProviders: () => request<{github:boolean}>('/api/auth/providers'),
  forgotPassword: (email: string) => request<{status:string}>('/api/auth/forgot-password', { method: 'POST', body: JSON.stringify({email}) }),
  createUserInvite: (note: string) => request<{code:string}>('/api/auth/invite-codes', { method: 'POST', body: JSON.stringify({note}) }),
  myInvites: () => request<any[]>('/api/auth/invite-codes'),

  me: () => request<{ user: { id: number; username: string }; profile: UserProfile }>('/api/auth/me'),

  getProfile: () => request<UserProfile>('/api/auth/profile'),

  saveProfile: (patch: Partial<UserProfile>) =>
    request<UserProfile>('/api/auth/profile', { method: 'PUT', body: JSON.stringify(patch) }),

  getCapabilities: () => request<{plan:string;is_admin:boolean;membership_expires_at:string|null;model_usage:{used:number;limit:number|null;remaining:number|null}}>('/api/auth/capabilities'),

  getPaymentConfig: () => request<{plans:{code:string;name:string;amount_fen:number}[];channels:Record<string,boolean>}>('/api/payments/config'),

  createPaymentOrder: (plan: string, channel: string, paymentAgreementAccepted = false) =>
    request<{order_no:string;channel:string;status:string;qr_code?:string;pay_url?:string}>('/api/payments/orders', { method: 'POST', body: JSON.stringify({ plan, channel, payment_agreement_accepted: paymentAgreementAccepted }) }),

  getPaymentOrder: (orderNo: string) =>
    request<{order_no:string;channel:string;status:string;qr_code?:string;pay_url?:string}>(`/api/payments/orders/${orderNo}`),

  // 对话
  newChat: () => request<{ session_id: number }>('/api/chat/session', { method: 'POST' }),

  listChats: () => request<ChatSession[]>('/api/chat/sessions'),

  deleteChat: (sessionId: number) =>
    request<{ deleted: number }>(`/api/chat/${sessionId}`, { method: 'DELETE' }),

  chatMessages: (sessionId: number) => request<ChatMessage[]>(`/api/chat/${sessionId}/messages`),

  searchChat: (q: string) => request<{ id: number; session_id: number; role: string; content: string; created_at: string; session_title: string }[]>(`/api/chat/search?q=${encodeURIComponent(q)}`),

  logout: () => request<{ status: string }>('/api/auth/logout', { method: 'POST' }),

  sendChat: (message: string, sessionId?: number) =>
    request<ChatReply>(`/api/chat`, { method: 'POST', body: JSON.stringify({ message, session_id: sessionId }) }),

  // 流式对话（SSE）：返回解析后的完整回复
  streamChat: async (message: string, sessionId: number | undefined, onEvent: (ev: any) => void): Promise<string> => {
    const token = getToken()
    const resp = await fetch('/api/chat/stream', {
      credentials: 'same-origin',
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) },
      body: JSON.stringify({ message, session_id: sessionId }),
    })
    if (!resp.ok) {
      const data = await resp.json().catch(() => null)
      throw new Error(data?.detail || `HTTP ${resp.status}`)
    }
    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    let reply = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const parts = buf.split('\n\n')
      buf = parts.pop() ?? ''
      for (const part of parts) {
        const line = part.trim()
        if (!line.startsWith('data: ')) continue
        try {
          const ev = JSON.parse(line.slice(6))
          if (ev.type === 'msg') reply = ev.content
          onEvent(ev)
        } catch { /* 忽略坏帧 */ }
      }
    }
    return reply
  },

  // 价格预警
  listAlerts: (status = 'all') =>
    request<AlertItem[]>(`/api/alerts?status=${status}`),

  createAlert: (symbol: string, symbolName: string, alertType: string, threshold: number) =>
    request<AlertItem>('/api/alerts', {
      method: 'POST',
      body: JSON.stringify({ symbol, symbol_name: symbolName, alert_type: alertType, threshold }),
    }),

  deleteAlert: (id: number) =>
    request<{ status: string }>(`/api/alerts/${id}`, { method: 'DELETE' }),

  reactivateAlert: (id: number) =>
    request<{ status: string }>(`/api/alerts/${id}/reactivate`, { method: 'POST' }),

  checkAlerts: () =>
    request<{ triggered: AlertItem[]; count: number }>('/api/alerts/check', { method: 'POST' }),

  listNotifications: () =>
    request<{ items: NotificationItem[]; unread: number }>('/api/notifications'),

  markNotificationsRead: () =>
    request<{ status: string }>('/api/notifications/read-all', { method: 'POST' }),

  deleteNotification: (id: number) =>
    request<{ status: string }>(`/api/notifications/${id}`, { method: 'DELETE' }),

  // 情绪面数据
  getSentiment: (symbol: string) =>
    request<SentimentData>(`/api/sentiment/${symbol}`),

  // DCF估值
  getDCF: (symbol: string) =>
    request<DCFResult>(`/api/dcf/${symbol}`),

  // 投资组合
  getPortfolio: () =>
    request<{ positions: PortfolioPosition[]; summary: PortfolioSummary }>(`/api/portfolio`),

  getCompanyEvents: () =>
    request<{ items: { symbol: string; name: string; period: string; date: string; status: string }[]; periods: string[]; source: string; as_of: string }>('/api/company-events'),

  buyStock: (symbol: string, shares: number, price: number, date?: string, fee: number = 0, note: string = '') =>
    request<{ symbol: string; action: string }>(`/api/portfolio/buy`, {
      method: 'POST', body: JSON.stringify({ symbol, shares, price, date: date || '', fee, note }),
    }),

  sellStock: (symbol: string, shares: number, price: number, date?: string, fee: number = 0, note: string = '') =>
    request<{ symbol: string; action: string }>(`/api/portfolio/sell`, {
      method: 'POST', body: JSON.stringify({ symbol, shares, price, date: date || '', fee, note }),
    }),

  removePosition: (symbol: string) =>
    request<{ status: string }>(`/api/portfolio/${symbol}`, { method: 'DELETE' }),

  getTransactions: () =>
    request<TransactionItem[]>(`/api/portfolio/transactions`),

  deleteTransaction: (id: number) =>
    request<{ status: string }>(`/api/portfolio/transactions/${id}`, { method: 'DELETE' }),

  // 回测
  getBacktest: (symbol: string, strategy: string, days: number, enable_cost: number = 1, params?: Record<string, any>) => {
    let url = `/api/backtest/${symbol}?strategy=${strategy}&days=${days}&enable_cost=${enable_cost}`
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null && v !== '') url += `&${k}=${v}`
      }
    }
    return request<BacktestResult>(url)
  },

  getMLSignal: <T = any>(symbol: string, days: number, model: string) =>
    request<T>(`/api/ml-signal/${encodeURIComponent(symbol)}?days=${days}&model=${model}`),

  // 多LLM对比
  compareLLM: (prompt: string, models: { name: string; base_url: string; api_key: string; model: string; input_cost_per_million?: number; output_cost_per_million?: number }[]) =>
    request<{ results: { name: string; model: string; response: string; latency_ms: number; usage: { input_tokens: number; output_tokens: number; total_tokens: number } | null; cost_usd: number | null; cost_status: string; evidence: { citation_count: number; numeric_claim_count: number; completeness_score: number | null; status: string; method: string }; error: string }[]; execution: { mode: string; model_count: number; wall_latency_ms: number } }>(
      '/api/llm-compare', { method: 'POST', body: JSON.stringify({ prompt, models }) }
    ),

  // 修改密码
  changePassword: (oldPassword: string, newPassword: string) =>
    request<{ status: string }>('/api/auth/change-password', {
      method: 'POST', body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
    }),
  setupMFA: () => request<{secret:string;otpauth:string}>('/api/auth/mfa/setup', { method: 'POST' }),
  getSecurity: () => request<{email:string|null; email_verified:number; mfa_enabled:number}>('/api/auth/security'),
  enableMFA: (code: string) => request<{status:string}>('/api/auth/mfa/enable', { method: 'POST', body: JSON.stringify({code}) }),
  disableMFA: (code: string) => request<{status:string}>('/api/auth/mfa/disable', { method: 'POST', body: JSON.stringify({code}) }),

  // per-user LLM 配置
  getUserLLMConfig: () =>
    request<LLMConfig & { api_key: string }>('/api/auth/llm-config'),

  saveUserLLMConfig: (cfg: Partial<LLMConfig>) =>
    request<LLMConfig & { api_key: string }>('/api/auth/llm-config', {
      method: 'PUT', body: JSON.stringify(cfg),
    }),

  // 管理员
  isAdmin: () => request<{ is_admin: boolean }>('/api/auth/is-admin'),
  adminUsers: (page = 1) => request<{items:any[];total:number;page:number;page_size:number}>(`/api/admin/users?page=${page}&page_size=20`),
  deleteUser: (id: number) => request<{status:string}>(`/api/admin/users/${id}`, { method: 'DELETE' }),
  toggleUserActive: (id: number) => request<{ status: string }>(`/api/admin/users/${id}/toggle-active`, { method: 'POST' }),
  setUserAdmin: (id: number, isAdmin: boolean) => request<{ status: string }>(`/api/admin/users/${id}/set-admin`, { method: 'POST', body: JSON.stringify({ is_admin: isAdmin }) }),
  createInvite: (note: string) => request<{ code: string }>('/api/admin/invite-codes', { method: 'POST', body: JSON.stringify({ note }) }),
  adminInvites: () => request<any[]>('/api/admin/invite-codes'),
  adminInviteSettings: () => request<{invite_required:boolean}>('/api/admin/invite-settings'),
  saveAdminInviteSettings: (invite_required: boolean) => request<{invite_required:boolean}>('/api/admin/invite-settings', { method: 'PUT', body: JSON.stringify({ invite_required }) }),
  adminAuditLogs: (page = 1) => request<{items:any[];total:number;page:number;page_size:number}>(`/api/admin/audit-logs?page=${page}&page_size=20`),
  adminFeedback: (page: number = 1, pageSize: number = 20) =>
    request<{ items: any[]; total: number; page: number; page_size: number }>(`/api/admin/feedback?page=${page}&page_size=${pageSize}`),
  updateFeedback: (id: number, body: { status?: string; reply?: string }) =>
    request<{ status: string }>(`/api/admin/feedback/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteFeedback: (id: number) =>
    request<{ status: string }>(`/api/admin/feedback/${id}`, { method: 'DELETE' }),
  adminStats: () => request<Record<string, any>>('/api/admin/stats'),
  adminPaymentConfig: () => request<{values:Record<string,string>;configured:Record<string,boolean>;channels:Record<string,boolean>}>('/api/admin/payment-config'),
  saveAdminPaymentConfig: (values: Record<string, string>) =>
    request<{values:Record<string,string>;configured:Record<string,boolean>;channels:Record<string,boolean>}>('/api/admin/payment-config', { method: 'PUT', body: JSON.stringify(values) }),
  adminGithubOAuth: () => request<{values:Record<string,string>;client_secret_configured:boolean;enabled:boolean}>('/api/admin/github-oauth'),
  adminMail: () => request<any>('/api/admin/mail'),
  saveAdminMail: (values: Record<string,string>) => request<any>('/api/admin/mail', { method: 'PUT', body: JSON.stringify(values) }),
  saveAdminGithubOAuth: (values: Record<string,string>) =>
    request<{values:Record<string,string>;client_secret_configured:boolean;enabled:boolean}>('/api/admin/github-oauth', { method: 'PUT', body: JSON.stringify(values) }),

  // 定时/自动化分析
  listScheduledTasks: () => request<any[]>('/api/scheduled-tasks'),
  createScheduledTask: (body: { name: string; symbols: string[]; mode: string; cron_hour: number; cron_minute: number }) =>
    request<any>('/api/scheduled-tasks', { method: 'POST', body: JSON.stringify(body) }),
  updateScheduledTask: (id: number, body: any) =>
    request<any>(`/api/scheduled-tasks/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteScheduledTask: (id: number) =>
    request<any>(`/api/scheduled-tasks/${id}`, { method: 'DELETE' }),
  runScheduledTaskNow: (id: number) =>
    request<any>(`/api/scheduled-tasks/${id}/run`, { method: 'POST' }),
  getScheduledResults: (id: number) => request<any[]>(`/api/scheduled-tasks/${id}/results`),
  checkTradingDay: () => request<{ trading_day: boolean; date: string }>('/api/scheduled-tasks/trading-day'),

  // 投资论文追踪
  listTheses: (status?: string) =>
    request<any[]>(`/api/theses${status ? `?status=${status}` : ''}`),
  createThesis: (body: { ticker: string; name: string; thesis_text: string; key_assumptions?: string[]; invalidation_conditions?: string[]; score?: number; horizon?: string }) =>
    request<any>('/api/theses', { method: 'POST', body: JSON.stringify(body) }),
  updateThesis: (id: number, body: any) =>
    request<any>(`/api/theses/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteThesis: (id: number) =>
    request<any>(`/api/theses/${id}`, { method: 'DELETE' }),
  checkThesis: (id: number) =>
    request<any>(`/api/theses/${id}/check`, { method: 'POST' }),
  checkAllTheses: () =>
    request<any[]>('/api/theses/check-all', { method: 'POST' }),
  getThesisChecks: (id: number) => request<any[]>(`/api/theses/${id}/checks`),
  getThesisExperiments: (id: number) => request<any[]>(`/api/theses/${id}/experiments`),
  createThesisExperiment: (id: number, strategy: string, days: number) =>
    request<any>(`/api/theses/${id}/experiments`, {
      method: 'POST', body: JSON.stringify({ strategy, days }),
    }),
  getThesisDrift: (ticker: string) => request<any>(`/api/thesis-drift/${ticker}`),

  // 投研知识库
  searchKnowledge: (q: string, limit = 20) => request<any[]>(`/api/knowledge/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  getKnowledgeStock: (ticker: string) => request<any[]>(`/api/knowledge/stock/${ticker}`),
  listKnowledge: (limit = 50, offset = 0) => request<any[]>(`/api/knowledge/list?limit=${limit}&offset=${offset}`),
  getKnowledgeStats: () => request<any>('/api/knowledge/stats'),
}
