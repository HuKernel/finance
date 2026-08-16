// 单条消息：行情卡片只在助手回复下面展示（基于工具调用确定相关股票）
import { useState } from 'react'
import type { ChatMessage } from '../types'
import QuoteCard from '../QuoteCard'
import Markdown from '../Markdown'
import { TOOL_LABEL } from './FlowPanel'

// 单条消息：行情卡片只在助手回复下面展示（基于工具调用确定相关股票）
export function MessageItem({ m, codes = [], onRegenerate }: { m: ChatMessage; codes?: string[]; onRegenerate?: () => void }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(m.content).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) })
  }
  return (
    <div className={`msg ${m.role}`}>
      <div className="msg-bubble">
        <div className="msg-text"><Markdown text={m.content} /></div>
        {m.tool_calls && m.tool_calls.length > 0 && (
          <div className="msg-tools">
            {m.tool_calls.map((t, j) => (
              <span key={j}>{TOOL_LABEL[t.name] || t.name}</span>
            ))}
          </div>
        )}
        {m.role === 'assistant' && (
          <div className="msg-actions">
            <button className="msg-action-btn" title="复制" onClick={copy}>{copied ? '已复制' : '复制'}</button>
            {onRegenerate && <button className="msg-action-btn" title="重新生成" onClick={onRegenerate}>重新生成</button>}
          </div>
        )}
      </div>
      {codes.length > 0 && (
        <div className="msg-quotes">
          {codes.map((code) => <QuoteCard key={code} code={code} />)}
        </div>
      )}
    </div>
  )
}
