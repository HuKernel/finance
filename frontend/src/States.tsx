/**
 * 统一状态组件：Loading / Skeleton / EmptyState / ErrorState
 * 替代各页面自写的 "加载中..." 文本与各自的空态样式。
 */
import type { CSSProperties, ReactNode } from 'react'

export function Loading({ label = '加载中...', center = true }: { label?: string; center?: boolean }) {
  return (
    <div className={`loading${center ? ' loading-center' : ''}`} role="status" aria-live="polite">
      <span className="loading-dot" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

/** 骨架屏：lines = 文本行数；variant 控制形态 */
export function Skeleton({ lines = 3, variant = 'text', style }: { lines?: number; variant?: 'text' | 'card' | 'table'; style?: CSSProperties }) {
  const rows = variant === 'card'
    ? [<div key="head" className="skeleton skeleton-head" />]
    : variant === 'table'
      ? Array.from({ length: lines }, (_, i) => <div key={i} className="skeleton skeleton-row" />)
      : []
  return (
    <div className={`skeleton-box skeleton-${variant}`} style={style} aria-hidden="true">
      {rows}
      {variant === 'text' && Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton skeleton-line" style={{ width: `${88 - i * (64 / Math.max(lines, 1))}%` }} />
      ))}
    </div>
  )
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="state-box empty-box" role="status">
      <div className="state-title">{title}</div>
      {hint && <div className="state-hint">{hint}</div>}
      {action}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state-box error-box" role="alert">
      <div className="state-title">出错了</div>
      <div className="state-hint">{message}</div>
      {onRetry && <button className="ghost" onClick={onRetry}>重试</button>}
    </div>
  )
}
