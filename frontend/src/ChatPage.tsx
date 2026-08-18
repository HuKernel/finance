// 智能对话页：ReAct 智能体聊天，行情卡片（K线图）跟随消息内嵌
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import type { ChatMessage, ChatSession } from './types'
import Markdown from './Markdown'
import { extractCodes } from './QuoteCard'
import { HotCarousel } from './chat/HotCarousel'
import { FlowPanel, ThinkingDots, ThinkingTimer, type FlowStep } from './chat/FlowPanel'
import { WatchList } from './chat/WatchList'
import { MessageItem } from './chat/MessageItem'
import { getResearchContext, setResearchContext } from './researchContext'

function openAnalyze(symbol: string, topic = '复查这只股票的最新结论') {
  window.location.hash = `#/analyze?symbol=${encodeURIComponent(symbol)}&topic=${encodeURIComponent(topic)}`
}

function openQuote(symbol: string) {
  window.location.hash = `#/quote?symbol=${encodeURIComponent(symbol)}`
}

function openBacktest(symbol: string) {
  window.location.hash = `#/backtest?symbol=${encodeURIComponent(symbol)}`
}

export default function ChatPage() {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmDel, setConfirmDel] = useState<number | null>(null)
  const [searchQ, setSearchQ] = useState('')
  const [sessionsOpen, setSessionsOpen] = useState(false)
  const [searchResults, setSearchResults] = useState<{ id: number; session_id: number; role: string; content: string; created_at: string; session_title: string }[]>([])

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setSearchResults([]); return }
    try {
      const r = await api.searchChat(q.trim())
      setSearchResults(r)
    } catch { setSearchResults([]) }
  }, [])
  const [flowSteps, setFlowSteps] = useState<FlowStep[]>([])
  const [flowCollapsed, setFlowCollapsed] = useState(false)
  const [pendingReply, setPendingReply] = useState('')
  const [thinkStart, setThinkStart] = useState(0)
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  const mentionedCodes = [...new Set(messages.flatMap((m) => extractCodes(m.content)))].slice(0, 6)
  const storedContext = getResearchContext()
  const focusCode = mentionedCodes[mentionedCodes.length - 1] || storedContext.symbol || ''
  const promptTemplates = focusCode
    ? [
        `复查 ${focusCode} 现在适合继续持有吗？`,
        `总结 ${focusCode} 最新风险点`,
        `对比 ${focusCode} 和同行估值`,
        `给我 ${focusCode} 的下一步跟踪计划`,
      ]
    : [
        '分析一下 600519 的基本面',
        '短线异动值不值得追？',
        '最近最值得跟踪的股票有哪些？',
        '给我一份今天的市场主线摘要',
      ]

  const applyPrompt = (text: string) => {
    setInput(text)
  }

  const loadSessions = useCallback(async () => {
    try {
      setSessions(await api.listChats())
    } catch { /* ignore */ }
  }, [])

  useEffect(() => { loadSessions() }, [loadSessions])

  // Auto-scroll: 消息数量变化时才自动滚到底部（不因轮播图/K线变化触发）
  const msgCount = messages.length
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [msgCount, busy, pendingReply])

  const openSession = async (id: number) => {
    setSessionId(id)
    setMessages(await api.chatMessages(id))
    setError('')
    setSessionsOpen(false)
  }

  const removeSession = async (id: number) => {
    try {
      await api.deleteChat(id)
      setSessions((prev) => prev.filter((s) => s.id !== id))
      if (sessionId === id) {
        setSessionId(null)
        setMessages([])
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除失败')
    } finally {
      setConfirmDel(null)
    }
  }

  const newSession = async () => {
    const { session_id } = await api.newChat()
    setSessionId(session_id)
    setMessages([])
    await loadSessions()
    setError('')
    setSessionsOpen(false)
  }

  const send = async (overrideText?: string) => {
    const text = (overrideText ?? input).trim()
    if (!text || busy) return
    const textCodes = extractCodes(text)
    if (textCodes.length > 0) setResearchContext({ symbol: textCodes[textCodes.length - 1], topic: text })
    if (text.length > 200) { setError('每条消息最多输入 200 个字符'); return }
    if (!overrideText) setInput('')
    setBusy(true)
    setError('')
    setFlowSteps([])
    setFlowCollapsed(false)
    setPendingReply('')
    setThinkStart(Date.now())
    setMessages((prev) => [...prev, { role: 'user', content: text, created_at: new Date().toISOString() }])
    try {
      let sid = sessionId
      const reply = await api.streamChat(text, sid ?? undefined, (ev) => {
        if (ev.type === 'tool_start') {
          setFlowSteps((prev) => [...prev, { name: ev.name, args: ev.args, status: 'running' }])
        } else if (ev.type === 'tool_end') {
          // 标记最近一个 running 步骤为 done
          setFlowSteps((prev) => {
            const idx = [...prev].reverse().findIndex((s) => s.status === 'running')
            if (idx === -1) return prev
            const i = prev.length - 1 - idx
            return prev.map((s, j) => (j === i ? { ...s, status: 'done' } : s))
          })
        } else if (ev.type === 'chunk') {
          // 流式输出：逐块追加（打字机效果）
          setPendingReply((prev) => prev + ev.content)
        } else if (ev.type === 'msg') {
          setPendingReply(ev.content)  // 完整回复兜底
        } else if (ev.type === 'done') {
          sid = ev.session_id
        }
      })
      setSessionId(sid)
      setMessages((prev) => [...prev, {
        role: 'assistant', content: reply || pendingReply, created_at: new Date().toISOString(),
      }])
      setPendingReply('')
      await loadSessions()
      // 回复完成：工作流默认折叠
      setFlowCollapsed(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : '发送失败')
    } finally {
      setBusy(false)
    }
  }

  const regenerate = async () => {
    // 找到最后一条 user 消息，删掉其后的 assistant 消息，重新发送
    const lastUserIdx = messages.length - 1 - [...messages].reverse().findIndex(m => m.role === 'user')
    if (lastUserIdx < 0) return
    const userMsg = messages[lastUserIdx].content
    // 删掉这条 user 消息后面的所有消息（包括 assistant 回复）
    setMessages(prev => prev.slice(0, lastUserIdx))
    send(userMsg)
  }

  return (
    <div className="chat-layout">
      <button className="chat-sessions-toggle ghost" aria-expanded={sessionsOpen} onClick={() => setSessionsOpen(v => !v)}>
        {sessionsOpen ? '收起对话列表' : `对话列表${sessions.length ? ` · ${sessions.length}` : ''}`}
      </button>
      <aside className={`chat-side${sessionsOpen ? ' mobile-open' : ''}`}>
        <button className="new-chat-btn" onClick={newSession}>新建对话</button>
        {messages.length > 0 && (
          <button className="ghost chat-export-btn" onClick={() => {
            const text = messages.map(m => `[${m.role === 'user' ? '我' : 'AI'}] ${m.content}`).join('\n\n')
            const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
            const a = document.createElement('a')
            a.href = URL.createObjectURL(blob)
            a.download = `对话记录_${new Date().toISOString().slice(0,10)}.txt`
            a.click()
            URL.revokeObjectURL(a.href)
          }}>导出对话</button>
        )}
        <input
          className="chat-search"
          aria-label="搜索对话内容"
          placeholder="搜索对话内容..."
          value={searchQ}
          onChange={(e) => { setSearchQ(e.target.value); doSearch(e.target.value) }}
        />
        {searchResults.length > 0 ? (
          <div className="chat-list">
            <div className="search-header">搜索结果 ({searchResults.length})</div>
            {searchResults.map((r) => (
              <div key={r.id} className="search-item" onClick={() => { openSession(r.session_id); setSearchQ(''); setSearchResults([]) }}>
                <span className="search-item-title">{r.session_title}</span>
                <span className="search-item-content">{r.content.slice(0, 60)}...</span>
                <span className="search-item-meta">{r.role === 'user' ? '我' : 'AI'} · {r.created_at.slice(5, 16)}</span>
              </div>
            ))}
          </div>
        ) : (
        <div className="chat-list">
          {sessions.map((s) => (
            <div key={s.id} className={`chat-item ${s.id === sessionId ? 'active' : ''}`}>
              <button className="chat-item-main" onClick={() => openSession(s.id)}>
                <span className="chat-item-title">{s.title}</span>
                <span className="chat-item-meta">{s.msg_count} 条</span>
              </button>
              <button
                className={`chat-item-del ${confirmDel === s.id ? 'confirming' : ''}`}
                title="删除对话"
                onClick={(e) => {
                  e.stopPropagation()
                  if (confirmDel === s.id) removeSession(s.id)
                  else { setConfirmDel(s.id); setTimeout(() => setConfirmDel((c) => (c === s.id ? null : c)), 8000) }
                }}
              >{confirmDel === s.id ? '确认？' : '删除'}</button>
            </div>
          ))}
        </div>
        )}
      </aside>

      <div className="chat-main">
        {focusCode && (
          <div className="chat-context-bar">
            <div className="chat-context-head">
              <strong>{`当前研究主线 · ${focusCode}`}</strong>
              <span>围绕同一只股票连续追问、连续跟踪，减少上下文跳转。</span>
            </div>
            {mentionedCodes.length > 0 && (
              <div className="chat-context-codes">
                {mentionedCodes.map(code => <button key={code} className="ghost chat-code-chip" onClick={() => setInput(code)}>{code}</button>)}
              </div>
            )}
            <div className="chat-context-actions">
              <button className="ghost" onClick={() => openAnalyze(focusCode)}>继续研究</button>
              <button className="ghost" onClick={() => openQuote(focusCode)}>看行情</button>
              <button className="ghost" onClick={() => openBacktest(focusCode)}>做回测</button>
            </div>
          </div>
        )}
        <div className="chat-messages" ref={scrollRef}>
          {messages.length === 0 && (
            <div className="chat-welcome">
              <HotCarousel />
              <div className="chat-welcome-prompts">
                {promptTemplates.map((item) => (
                  <button key={item} className="ghost chat-context-prompt" onClick={() => applyPrompt(item)}>{item}</button>
                ))}
              </div>
              <h3>我是 FinanceCrew 投研助理</h3>
              <p>可以问我任何股票问题，例如：</p>
              <ul>
                <li>"分析一下 600519 的基本面"</li>
                <li>"600519 最近为什么涨？"</li>
                <li>"跑一份 000001 的完整投研报告"</li>
                <li>"对比 300750 和 002594 的估值"</li>
              </ul>
              <p className="chat-hint">我会自动查询实时行情、财务、龙虎榜、新闻等真实数据来回答</p>
            </div>
          )}
          {messages.map((m, i) => {
            // 只从助手回复提取代码（用户消息不展示卡片）
            let itemCodes: string[] = []
            if (m.role === 'assistant') {
              itemCodes = extractCodes(m.content)
              // 去重：前面助手消息已展示过的不再展示
              const seenCodes = new Set<string>()
              for (let j = 0; j < i; j++) {
                if (messages[j].role === 'assistant') {
                  extractCodes(messages[j].content).forEach(c => seenCodes.add(c))
                }
              }
              itemCodes = itemCodes.filter(c => !seenCodes.has(c))
            }
            // 最后一条 assistant 消息才显示重新生成按钮
            const isLastAssistant = m.role === 'assistant' && i === messages.length - 1
            return <MessageItem key={i} m={m} codes={itemCodes} onRegenerate={isLastAssistant && !busy ? regenerate : undefined} />
          })}
          {/* 流式回复区：工作流步骤 + 思考动画 + 回复文本，全部在一个 assistant 气泡内 */}
          {busy && (
            <div className="msg assistant">
              <div className="msg-bubble">
                {(flowSteps.length > 0 || !pendingReply) && (
                  <div className="msg-thinking">
                    <div className="think-header">
                      <ThinkingDots />
                      <span className="think-label">{pendingReply ? '' : '思考中'}</span>
                      <ThinkingTimer startTime={thinkStart} />
                    </div>
                    {flowSteps.length > 0 && (
                      <FlowPanel
                        steps={flowSteps}
                        collapsed={flowCollapsed}
                        onToggle={() => setFlowCollapsed((v) => !v)}
                      />
                    )}
                  </div>
                )}
                {pendingReply && (
                  <div className="msg-text"><Markdown text={pendingReply} /></div>
                )}
              </div>
            </div>
          )}
          {error && <div className="error-box">{error}</div>}
          <div ref={bottomRef} />
        </div>

        <div className="chat-input">
          <input
            aria-label="向 FinanceCrew 提问"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            maxLength={200}
            placeholder="输入问题，回车发送（支持直接输入股票代码）"
          />
          <span className="chat-input-count">{input.length}/200</span>
          <button onClick={() => send()} disabled={busy || !input.trim()}>发送</button>
        </div>
      </div>

      <aside className="watch-side">
        <WatchList />
      </aside>
    </div>
  )
}
