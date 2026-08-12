// Markdown 渲染组件：聊天气泡与报告文本的美化渲染
// katex 懒加载：只有遇到公式时才动态加载（减小首屏 chunk ~200KB）
// 支持：标题 / 加粗 / 斜体 / 行内代码 / 围栏代码块 / 链接 / 表格 / 公式 / 列表（含缩进嵌套）/ 引用 / 分割线
import React from 'react'
import 'katex/dist/katex.min.css'

// katex 动态加载缓存
let _katex: any = null
let _katexPromise: Promise<any> | null = null

async function loadKatex(): Promise<any> {
  if (_katex) return _katex
  if (!_katexPromise) {
    _katexPromise = import('katex').then((mod) => {
      _katex = mod.default || mod
      return _katex
    })
  }
  return _katexPromise
}

// 同步渲染：如果katex已加载则用，否则返回原始文本（下次渲染时katex已就绪）
function renderMath(tex: string, displayMode: boolean): string {
  if (!_katex) {
    // 首次遇到公式时触发异步加载，当前先返回原始文本
    loadKatex()
    return tex
  }
  try {
    return _katex.renderToString(tex, { displayMode, throwOnError: false, output: 'html' })
  } catch {
    return tex
  }
}

type Block = { type: 'text' | 'table' | 'math' | 'code'; lines: string[]; tex?: string; lang?: string }

// 内联格式化：**加粗** / *斜体* / _斜体_ / `行内代码` / $公式$ / [文字](链接) / 裸 URL
// 交替顺序按起始字符区分，粗体优先于斜体，避免 ** 被误判为两个 *
function formatInline(text: string): React.ReactNode {
  const pattern = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\[[^\]\n]+\]\([^)\n]+\))|(https?:\/\/[^\s<>"')\]]+)|(\$[^$\n]+\$)|(\*[^*\s][^*\n]*\*)|(_[^_\s][^_\n]*_)/g
  const out: React.ReactNode[] = []
  let last = 0
  let key = 0
  let m: RegExpExecArray | null
  while ((m = pattern.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const tok = m[0]
    if (m[1]) {
      out.push(<code key={key++}>{tok.slice(1, -1)}</code>)
    } else if (m[2]) {
      out.push(<strong key={key++}>{formatInline(tok.slice(2, -2))}</strong>)
    } else if (m[3]) {
      const mm = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok)
      out.push(mm
        ? <a key={key++} href={mm[2]} target="_blank" rel="noopener noreferrer">{formatInline(mm[1])}</a>
        : tok)
    } else if (m[4]) {
      out.push(<a key={key++} href={tok} target="_blank" rel="noopener noreferrer">{tok}</a>)
    } else if (m[5]) {
      out.push(<span key={key++} dangerouslySetInnerHTML={{ __html: renderMath(tok.slice(1, -1), false) }} />)
    } else if (m[6] || m[7]) {
      out.push(<em key={key++}>{formatInline(tok.slice(1, -1))}</em>)
    }
    last = m.index + tok.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

export default function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, '\n').split('\n')

  // 逐行分块：空行直接跳过（天然压缩段落间距，不再产生大空隙）；
  // 围栏代码块内部空行原样保留
  const blocks: Block[] = []
  let i = 0
  while (i < lines.length) {
    const t = lines[i].trim()

    if (!t) { i++; continue }

    // 围栏代码块 ```lang ... ```（流式未闭合时收集到末尾，优雅降级）
    if (t.startsWith('```')) {
      const lang = t.slice(3).trim()
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i])
        i++
      }
      if (i < lines.length) i++ // 跳过结束围栏
      blocks.push({ type: 'code', lines: codeLines, lang: lang || undefined })
      continue
    }

    // 块级公式 $$...$$（单行）
    if (t.startsWith('$$') && t.endsWith('$$') && t.length > 4) {
      blocks.push({ type: 'math', lines: [], tex: t.slice(2, -2) })
      i++
      continue
    }
    // 块级公式（多行）
    if (t.startsWith('$$')) {
      const mathLines: string[] = [t.slice(2)]
      i++
      while (i < lines.length && !lines[i].trim().endsWith('$$')) {
        mathLines.push(lines[i])
        i++
      }
      if (i < lines.length) {
        mathLines.push(lines[i].trim().slice(0, -2))
        i++
      }
      blocks.push({ type: 'math', lines: [], tex: mathLines.join('\n') })
      continue
    }

    // 表格：连续 | 行
    if (t.startsWith('|') && t.endsWith('|')) {
      const tableLines: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        tableLines.push(lines[i].trim())
        i++
      }
      blocks.push({ type: 'table', lines: tableLines })
      continue
    }

    // 普通文本行
    blocks.push({ type: 'text', lines: [lines[i]] })
    i++
  }

  // 渲染表格
  function renderTable(tableLines: string[]) {
    const dataLines = tableLines.filter(l => !/^\|[\s-:|]+\|$/.test(l))
    if (dataLines.length === 0) return null
    const rows = dataLines.map(l => l.split('|').slice(1, -1).map(c => c.trim()))
    const [header, ...body] = rows
    return (
      <div className="md-table-wrap">
        <table className="md-table">
          <thead>
            <tr>{header.map((c, ci) => <th key={ci}>{formatInline(c)}</th>)}</tr>
          </thead>
          <tbody>
            {body.map((row, ri) => (
              <tr key={ri}>{row.map((c, ci) => <td key={ci}>{formatInline(c)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  // 渲染单个文本行：标题 / 列表 / 引用 / 分割线 / 段落
  function renderLine(line: string, key: string) {
    const t = line.trim()
    if (!t) return null
    const indent = (line.match(/^\s*/) as RegExpMatchArray)[0].length

    const h = /^(#{1,4})\s+(.*)$/.exec(t)
    if (h) {
      const level = h[1].length
      const content = formatInline(h[2])
      if (level === 1) return <h1 key={key}>{content}</h1>
      if (level === 2) return <h2 key={key}>{content}</h2>
      if (level === 3) return <h3 key={key}>{content}</h3>
      return <h4 key={key}>{content}</h4>
    }
    if (/^[-*]\s/.test(t)) {
      return <div key={key} className="md-li" style={{ marginLeft: indent * 10 }}>{formatInline(t.replace(/^[-*]\s+/, ''))}</div>
    }
    const om = /^(\d+)\.\s+(.*)$/.exec(t)
    if (om) {
      return <div key={key} className="md-oli" style={{ marginLeft: indent * 10 }}><span className="md-oli-num">{om[1]}.</span>{formatInline(om[2])}</div>
    }
    if (t.startsWith('> ')) {
      return <blockquote key={key}>{formatInline(t.slice(2))}</blockquote>
    }
    if (t === '---' || t === '***') {
      return <hr key={key} />
    }
    return <p key={key}>{formatInline(t)}</p>
  }

  return (
    <div className="md-body">
      {blocks.map((block, bi) => {
        if (block.type === 'math') {
          return <div key={bi} className="md-math" dangerouslySetInnerHTML={{ __html: renderMath(block.tex || '', true) }} />
        }
        if (block.type === 'code') {
          return (
            <div key={bi} className="md-codeblock">
              {block.lang && <div className="md-codeblock-lang">{block.lang}</div>}
              <pre><code>{block.lines.join('\n')}</code></pre>
            </div>
          )
        }
        if (block.type === 'table') return <React.Fragment key={bi}>{renderTable(block.lines)}</React.Fragment>
        return block.lines.map((line, li) => renderLine(line, `${bi}-${li}`))
      })}
    </div>
  )
}
