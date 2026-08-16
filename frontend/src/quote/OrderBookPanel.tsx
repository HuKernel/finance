import type { ReactNode } from 'react'

// ========== 右栏：盘口数据表 ==========
export default function OrderBookPanel({ brief }: { brief: Record<string, unknown> }) {
  const b = brief as {
    name?: string
    open?: number; pre_close?: number; high?: number; low?: number
    limit_up?: number; limit_down?: number
    volume?: number; amount?: number; turnover?: number; volume_ratio?: number
    pe?: number; pb?: number; market_cap?: number
    circ_market_cap?: number
    price?: number; change_pct?: number
  }
  // 港股/美股没有涨跌停概念，按是否存在判断
  const hasLimit = b.limit_up != null || b.limit_down != null

  // 单元格：label + value，涨跌上色（红涨绿跌中国习惯 = up/down 变量）
  const Cell = ({ label, value, tone }: { label: string; value: ReactNode; tone?: 'up' | 'down' }) => (
    <div className="qp-ob-cell">
      <span className="qp-ob-label">{label}</span>
      <span className={`qp-ob-value ${tone ?? ''}`}>{value}</span>
    </div>
  )

  const fmtNum = (v?: number) => (v == null ? '--' : v.toFixed(2))
  const fmtVol = (v?: number) => (v == null ? '--' : v >= 10000 ? (v / 10000).toFixed(2) + '万手' : v.toFixed(0) + '手')
  const fmtAmt = (v?: number) => (v == null ? '--' : v >= 10000 ? (v / 10000).toFixed(2) + '亿' : v.toFixed(0) + '万')
  const fmtCap = (v?: number) => (v == null ? '--' : v >= 10000 ? (v / 10000).toFixed(2) + '万亿' : v.toFixed(1) + '亿')

  return (
    <div className="qp-orderbook">
      <div className="qp-ob-row">
        <Cell label="今开" value={fmtNum(b.open)} tone={b.open != null && b.pre_close != null ? (b.open >= b.pre_close ? 'up' : 'down') : undefined} />
        <Cell label="昨收" value={fmtNum(b.pre_close)} />
        <Cell label="最高" value={fmtNum(b.high)} tone={b.high != null && b.pre_close != null ? (b.high >= b.pre_close ? 'up' : 'down') : undefined} />
        <Cell label="最低" value={fmtNum(b.low)} tone={b.low != null && b.pre_close != null ? (b.low >= b.pre_close ? 'up' : 'down') : undefined} />
        <Cell label="涨停" value={hasLimit ? fmtNum(b.limit_up) : '--'} tone="up" />
        <Cell label="跌停" value={hasLimit ? fmtNum(b.limit_down) : '--'} tone="down" />
      </div>
      <div className="qp-ob-row">
        <Cell label="成交量" value={fmtVol(b.volume)} />
        <Cell label="成交额" value={fmtAmt(b.amount)} />
        <Cell label="换手率" value={b.turnover != null ? `${b.turnover}%` : '--'} />
        <Cell label="量比" value={fmtNum(b.volume_ratio)} />
        <Cell label="PE" value={fmtNum(b.pe)} />
        <Cell label="PB" value={fmtNum(b.pb)} />
      </div>
      <div className="qp-ob-row">
        <Cell label="总市值" value={fmtCap(b.market_cap)} />
        <Cell label="流通市值" value={fmtCap(b.circ_market_cap)} />
        <Cell label="现价" value={fmtNum(b.price)} tone={b.change_pct != null ? (b.change_pct >= 0 ? 'up' : 'down') : undefined} />
        <Cell label="涨跌幅" value={b.change_pct != null ? `${b.change_pct >= 0 ? '+' : ''}${b.change_pct}%` : '--'} tone={b.change_pct != null ? (b.change_pct >= 0 ? 'up' : 'down') : undefined} />
      </div>
    </div>
  )
}
