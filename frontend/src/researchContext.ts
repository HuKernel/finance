export type ResearchContext = {
  symbol: string
  topic: string
  updatedAt: string
}

const STORAGE_KEY = 'financecrew_research_context'

export function getResearchContext(): ResearchContext {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return {
        symbol: typeof parsed.symbol === 'string' ? parsed.symbol : '',
        topic: typeof parsed.topic === 'string' ? parsed.topic : '',
        updatedAt: typeof parsed.updatedAt === 'string' ? parsed.updatedAt : '',
      }
    }
  } catch { /* ignore malformed local state */ }
  return { symbol: '', topic: '', updatedAt: '' }
}

export function setResearchContext(patch: Partial<ResearchContext>): ResearchContext {
  const next = { ...getResearchContext(), ...patch, updatedAt: new Date().toISOString() }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  window.dispatchEvent(new CustomEvent('financecrew:research-context', { detail: next }))
  return next
}

export function clearResearchContext() {
  localStorage.removeItem(STORAGE_KEY)
  window.dispatchEvent(new CustomEvent('financecrew:research-context', { detail: { symbol: '', topic: '', updatedAt: '' } }))
}

export function contextHash(symbol: string, topic = '') {
  const params = new URLSearchParams()
  if (symbol) params.set('symbol', symbol)
  if (topic) params.set('topic', topic)
  return params.toString()
}
