import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, LineSeries,
  createChart, type CandlestickData, type HistogramData, type IChartApi,
  type LineData, type MouseEventParams, type Time, type UTCTimestamp,
} from 'lightweight-charts'
import type { KlineBar, MinutePoint } from './types'
import { chartTime, formatChartTime } from './marketTime'

interface Props {
  bars: KlineBar[]
  minute?: MinutePoint[]
  lastClose?: number | null
  currentPrice?: number | null
  symbol: string
  mode: 'day' | 'minute'
  onMode?: (mode: 'day' | 'minute') => void
  dataDate?: string
  isToday?: boolean
  subIndicator?: 'macd' | 'kdj'
  onSubIndicator?: (value: 'macd' | 'kdj') => void
  fullscreen?: boolean
  onFullscreen?: (value: boolean) => void
}

const sma = (values: number[], period: number) => values.map((_, index) => {
  if (index < period - 1) return null
  return values.slice(index - period + 1, index + 1).reduce((sum, value) => sum + value, 0) / period
})

const ema = (values: number[], period: number) => {
  const result: (number | null)[] = []
  const factor = 2 / (period + 1)
  let previous: number | null = null
  values.forEach((value, index) => {
    if (index < period - 1) result.push(null)
    else if (previous === null) {
      previous = values.slice(0, period).reduce((sum, item) => sum + item, 0) / period
      result.push(previous)
    } else {
      previous = value * factor + previous * (1 - factor)
      result.push(previous)
    }
  })
  return result
}

function indicators(bars: KlineBar[]) {
  const closes = bars.map(bar => bar.close)
  const ma5 = sma(closes, 5)
  const ma20 = sma(closes, 20)
  const ema12 = ema(closes, 12)
  const ema26 = ema(closes, 26)
  const dif = closes.map((_, index) => ema12[index] == null || ema26[index] == null ? null : ema12[index]! - ema26[index]!)
  const dea: (number | null)[] = []
  let previousDea: number | null = null
  dif.forEach(value => {
    if (value == null) dea.push(null)
    else {
      previousDea = previousDea == null ? value : value * 0.2 + previousDea * 0.8
      dea.push(previousDea)
    }
  })
  const macd = dif.map((value, index) => value == null || dea[index] == null ? null : (value - dea[index]!) * 2)

  const k: (number | null)[] = [], d: (number | null)[] = [], j: (number | null)[] = []
  let previousK = 50, previousD = 50
  bars.forEach((bar, index) => {
    if (index < 8) { k.push(null); d.push(null); j.push(null); return }
    const window = bars.slice(index - 8, index + 1)
    const high = Math.max(...window.map(item => item.high))
    const low = Math.min(...window.map(item => item.low))
    const rsv = high === low ? 50 : (bar.close - low) / (high - low) * 100
    previousK = previousK * 2 / 3 + rsv / 3
    previousD = previousD * 2 / 3 + previousK / 3
    k.push(previousK); d.push(previousD); j.push(previousK * 3 - previousD * 2)
  })
  return { ma5, ma20, dif, dea, macd, k, d, j }
}

const asLineData = (bars: KlineBar[], values: (number | null)[]): LineData<Time>[] =>
  values.flatMap((value, index) => value == null ? [] : [{ time: chartTime(bars[index].date), value }])

export default function KLineChart({
  bars, minute = [], lastClose, currentPrice, symbol, mode, dataDate,
  subIndicator = 'macd', fullscreen = false, onFullscreen,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const [hover, setHover] = useState<KlineBar | null>(null)
  const [themeVersion, setThemeVersion] = useState(0)
  const calculated = useMemo(() => indicators(bars), [bars])
  const intradayBars = mode === 'day' && bars.some(bar => bar.date.length > 10)

  useEffect(() => {
    const observer = new MutationObserver(() => setThemeVersion(value => value + 1))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const container = containerRef.current
    if (!container || (mode === 'day' ? bars.length === 0 : minute.length === 0)) return
    const style = getComputedStyle(document.documentElement)
    const color = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback
    const up = color('--up', '#22c55e')
    const down = color('--down', '#ef4444')
    const text = color('--text-2', '#64748b')
    const border = color('--border', '#dbe1e8')
    const surface = color('--surface', '#ffffff')
    const chart = createChart(container, {
      autoSize: true,
      height: fullscreen ? Math.max(window.innerHeight - 110, 520) : 460,
      layout: { background: { type: ColorType.Solid, color: surface }, textColor: text, fontFamily: 'IBM Plex Sans, sans-serif' },
      grid: { vertLines: { color: border }, horzLines: { color: border } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: border },
      timeScale: { borderColor: border, timeVisible: mode === 'minute' || intradayBars, secondsVisible: false, rightOffset: 3, barSpacing: 7, minBarSpacing: 2 },
      handleScroll: true,
      handleScale: true,
    })
    chartRef.current = chart

    if (mode === 'day') {
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: up, downColor: down, wickUpColor: up, wickDownColor: down,
        borderUpColor: up, borderDownColor: down,
      }, 0)
      candleSeries.setData(bars.map(bar => ({
        time: chartTime(bar.date), open: bar.open, high: bar.high, low: bar.low, close: bar.close,
      })) as CandlestickData<Time>[])
      const ma5 = chart.addSeries(LineSeries, { color: '#d69e00', lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, 0)
      const ma20 = chart.addSeries(LineSeries, { color: '#0891b2', lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, 0)
      ma5.setData(asLineData(bars, calculated.ma5))
      ma20.setData(asLineData(bars, calculated.ma20))

      const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: false }, 1)
      volume.setData(bars.map(bar => ({
        time: chartTime(bar.date), value: bar.volume, color: bar.close >= bar.open ? up : down,
      })) as HistogramData<Time>[])

      if (subIndicator === 'macd') {
        const histogram = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, 2)
        histogram.setData(calculated.macd.flatMap((value, index) => value == null ? [] : [{
          time: chartTime(bars[index].date), value, color: value >= 0 ? up : down,
        }]) as HistogramData<Time>[])
        const dif = chart.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, 2)
        const dea = chart.addSeries(LineSeries, { color: '#10b981', lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, 2)
        dif.setData(asLineData(bars, calculated.dif)); dea.setData(asLineData(bars, calculated.dea))
      } else {
        const colors = ['#a855f7', '#10b981', '#f59e0b']
        ;[calculated.k, calculated.d, calculated.j].forEach((values, index) => {
          const series = chart.addSeries(LineSeries, { color: colors[index], lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, 2)
          series.setData(asLineData(bars, values))
        })
      }
      const panes = chart.panes()
      panes[0]?.setStretchFactor(4)
      panes[1]?.setStretchFactor(1)
      panes[2]?.setStretchFactor(1.3)
      chart.subscribeCrosshairMove((event: MouseEventParams<Time>) => {
        const item = event.seriesData.get(candleSeries) as CandlestickData<Time> | undefined
        if (!item || !('open' in item)) { setHover(null); return }
        setHover({ date: formatChartTime(event.time), open: item.open, high: item.high, low: item.low, close: item.close, volume: 0 })
      })
    } else {
      const baseDate = dataDate || new Date().toISOString().slice(0, 10)
      const [year, month, day] = baseDate.split('-').map(Number)
      const base = Date.UTC(year, month - 1, day) / 1000
      let dayOffset = 0, previousMinute = -1
      const points = minute.map(point => {
        const hour = Number(point.time.slice(0, 2)), minuteValue = Number(point.time.slice(2, 4))
        const minuteOfDay = hour * 60 + minuteValue
        if (previousMinute >= 0 && minuteOfDay < previousMinute) dayOffset += 1
        previousMinute = minuteOfDay
        return { point, time: (base + dayOffset * 86400 + minuteOfDay * 60) as UTCTimestamp }
      })
      const price = chart.addSeries(LineSeries, { color: up, lineWidth: 2, priceLineVisible: true }, 0)
      price.setData(points.map(({ point, time }) => ({ time, value: point.price })))
      const average = chart.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, 0)
      average.setData(points.flatMap(({ point, time }) => point.avg == null ? [] : [{ time, value: point.avg }]))
      const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: false }, 1)
      volume.setData(points.flatMap(({ point, time }, index) => point.volume == null ? [] : [{
        time, value: point.volume, color: point.price >= (points[index - 1]?.point.price ?? lastClose ?? point.price) ? up : down,
      }]))
      chart.panes()[0]?.setStretchFactor(4)
      chart.panes()[1]?.setStretchFactor(1)
    }
    chart.timeScale().fitContent()
    return () => { chartRef.current = null; chart.remove() }
  }, [bars, calculated, dataDate, fullscreen, intradayBars, lastClose, minute, mode, subIndicator, themeVersion])

  const zoom = (factor: number) => {
    const range = chartRef.current?.timeScale().getVisibleLogicalRange()
    if (!range || !chartRef.current) return
    const center = (range.from + range.to) / 2
    const half = (range.to - range.from) * factor / 2
    chartRef.current.timeScale().setVisibleLogicalRange({ from: center - half, to: center + half })
  }

  const latestBar = bars[bars.length - 1]
  const latestMinute = minute[minute.length - 1]
  const price = currentPrice ?? latestMinute?.price ?? latestBar?.close
  const base = lastClose ?? latestBar?.open ?? price
  const change = price != null && base ? (price - base) / base * 100 : null

  if (mode === 'day' && !bars.length) return <div className="kline-empty">暂无K线数据</div>
  if (mode === 'minute' && !minute.length) return <div className="kline-empty">暂无分时数据</div>

  return (
    <section className={`kline-wrap professional-kline ${fullscreen ? 'kline-fullscreen' : ''}`} aria-label={`${symbol}${mode === 'day' ? 'K线' : '分时'}图`}>
      <div className="kline-head">
        <span className="kline-symbol">{symbol}</span>
        {price != null && <span className="kline-price" style={{ color: change != null && change < 0 ? 'var(--down)' : 'var(--up)' }}>
          {price.toFixed(2)} {change != null && <small>{change >= 0 ? '+' : ''}{change.toFixed(2)}%</small>}
        </span>}
        <span className="kline-legend">MA5 <i className="legend-ma5" /> MA20 <i className="legend-ma20" /> 成交量 · {subIndicator.toUpperCase()}</span>
        <span className="kline-range">
          <button className="ghost" onClick={() => zoom(1.35)} aria-label="缩小K线图">−</button>
          <button className="ghost" onClick={() => chartRef.current?.timeScale().fitContent()}>重置</button>
          <button className="ghost" onClick={() => zoom(0.72)} aria-label="放大K线图">＋</button>
          {fullscreen && <button className="ghost" onClick={() => onFullscreen?.(false)}>退出全屏</button>}
        </span>
      </div>
      {hover && <div className="kline-ohlc">
        <strong>{hover.date}</strong><span>开 {hover.open}</span><span>高 {hover.high}</span><span>低 {hover.low}</span><span>收 {hover.close}</span>
      </div>}
      <div ref={containerRef} className="kline-canvas" role="img" tabIndex={0} aria-label={`${symbol}${mode === 'day' ? '日K、成交量和技术指标' : '分时价格和成交量'}`} />
      <a className="chart-attribution" href="https://www.tradingview.com/" target="_blank" rel="noreferrer">Charts by TradingView</a>
    </section>
  )
}
