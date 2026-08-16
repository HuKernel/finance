import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App.tsx'
import { ModalProvider } from './Modal'
// 样式按区段拆分：引入顺序 = 原 App.css 的级联顺序，不可调整
import './styles/base.css'
import './styles/analyze.css'
import './styles/login.css'
import './styles/chat.css'
import './styles/quote.css'
import './styles/markdown.css'
import './styles/alerts.css'
import './styles/portfolio.css'
import './styles/common.css'
import './styles/profile.css'
import './styles/quote-layout.css'
import './styles/backtest.css'
import './styles/thesis.css'
import './styles/market.css'
import './styles/theme.css'

// 全局数据层：缓存/去重/重试/轮询统一交给 react-query
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ModalProvider>
        <App />
      </ModalProvider>
    </QueryClientProvider>
  </StrictMode>,
)
