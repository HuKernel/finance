import { useState } from 'react'
import { api } from './api'
import { useModal } from './Modal'

export default function FeedbackWidget({
  open,
  page,
  onOpen,
  onClose,
}: {
  open: boolean
  page: string
  onOpen: () => void
  onClose: () => void
}) {
  const [category, setCategory] = useState('suggestion')
  const [content, setContent] = useState('')
  const [busy, setBusy] = useState(false)
  const { toast } = useModal()

  const submit = async () => {
    const text = content.trim()
    if (text.length < 5) {
      toast('请至少填写 5 个字', 'warning')
      return
    }
    setBusy(true)
    try {
      await api.submitFeedback({ category, content: text, page })
      setContent('')
      onClose()
      toast('反馈已提交，感谢你的建议', 'success')
    } catch (error) {
      toast(error instanceof Error ? error.message : '反馈提交失败', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button className="feedback-trigger" onClick={onOpen} aria-haspopup="dialog">反馈</button>
      {open && (
        <div className="feedback-panel" role="dialog" aria-modal="true" aria-labelledby="feedback-title">
          <div className="feedback-head">
            <div><strong id="feedback-title">意见反馈</strong><span>当前页面：{page}</span></div>
            <button className="ghost" onClick={onClose} aria-label="关闭反馈">关闭</button>
          </div>
          <label>
            反馈类型
            <select value={category} onChange={event => setCategory(event.target.value)}>
              <option value="suggestion">功能建议</option>
              <option value="bug">问题反馈</option>
              <option value="data">数据问题</option>
              <option value="other">其他</option>
            </select>
          </label>
          <label>
            反馈内容
            <textarea
              value={content}
              maxLength={1000}
              rows={5}
              placeholder="请描述遇到的问题或建议（至少 5 个字）"
              onChange={event => setContent(event.target.value)}
            />
          </label>
          <button className="feedback-submit" disabled={busy} onClick={submit}>
            {busy ? '提交中...' : '提交反馈'}
          </button>
        </div>
      )}
    </>
  )
}
