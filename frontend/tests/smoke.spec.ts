import { expect, test, type Page } from '@playwright/test'

const bars = Array.from({ length: 30 }, (_, index) => ({
  date: `2026-07-${String(index + 1).padStart(2, '0')}`,
  open: 100 + index,
  close: 101 + index,
  high: 102 + index,
  low: 99 + index,
  volume: 100000 + index,
}))

async function mockApi(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('financecrew_token', 'e2e-token')
    localStorage.setItem('fc_theme_v3', 'light')
  })
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    let body: unknown = {}

    if (path === '/api/auth/me') body = { user: { id: 1, username: 'e2e' }, profile: { watchlist: [] } }
    else if (path === '/api/auth/is-admin') body = { is_admin: false }
    else if (path === '/api/auth/profile') body = { watchlist: [] }
    else if (path === '/api/alerts') body = []
    else if (path === '/api/market/top-turnover') body = { code: '600519', name: '贵州茅台', amount: 1000000000, unit: '元', scope: 'a_share_full_market', as_of: '2026-08-11' }
    else if (path === '/api/hot') body = []
    else if (path === '/api/news/600519') body = { symbol: '600519', news: [] }
    else if (path === '/api/industry/600519') body = { peers: [], avg_pe: null, avg_pb: null }
    else if (path === '/api/fund-flow/600519') body = {}
    else if (path === '/api/patterns/600519') body = {}
    else if (path === '/api/chat/sessions') body = []
    else if (path === '/api/history') body = [{ id: 42, ticker: '600519', created_at: '2026-08-11T13:00:00', status: 'completed' }]
    else if (path === '/api/analysis/42') body = { result: {
      id: 42,
      run_id: 'run-e2e-42',
      ticker: '600519',
      name: '贵州茅台',
      price: 1500,
      change_pct: 1.2,
      created_at: '2026-08-11T13:00:00',
      status: 'completed',
      consensus_score: 2,
      consensus_verdict: '测试结论',
      analyst_views: [],
      debate: [],
      risk_review: null,
      trade_plan: null,
      disclaimer: '测试数据',
      raw: { trace: {
        run_id: 'run-e2e-42', mode: 'standard', provider: 'deepseek', model: 'deepseek-chat', status: 'completed', duration_ms: 1234,
        steps: [{ name: 'collect_data', label: '数据收集', status: 'done', at_ms: 120 }], tools: [],
      } },
    } }
    else if (path.startsWith('/api/quote/')) body = {
      brief: { name: '贵州茅台', price: 1500, change_pct: 1.2, pre_close: 1482 },
      kline: bars,
      tech: {},
      metadata: {
        brief: { source: 'tencent', delay: 'near_realtime' },
        kline: { source: 'tencent_fqkline', as_of: '2026-08-11', delay: 'end_of_day', adjustment: 'qfq', fallback_used: false },
      },
    }
    else if (path.startsWith('/api/kline/')) body = {
      bars: bars.map((bar, index) => ({ ...bar, date: `2026-08-11 ${String(9 + Math.floor(index / 12)).padStart(2, '0')}:${String((index * 5) % 60).padStart(2, '0')}` })),
      tech: {},
      metadata: { source: 'akshare_tencent', as_of: '2026-08-11 15:00', delay: 'delayed', adjustment: 'none', fallback_used: false },
    }
    else if (path.startsWith('/api/backtest/')) body = { error: 'e2e mock' }
    else if (path.startsWith('/api/ml-signal/')) body = {
      symbol: '600519', backend: 'numpy_logit', n_raw_rows: 500, n_samples: 440,
      split_sizes: { train: 280, val: 66, test: 88 },
      split_ranges: { train: { start: '2024-02-01', end: '2025-03-01' }, val: { start: '2025-03-17', end: '2025-06-18' }, test: { start: '2025-07-03', end: '2025-11-05' } },
      classification: { buy_precision: 0.42, buy_recall: 0.38 },
      strategy: { excess_return_pct: 3.2, max_drawdown_pct: 8.4 },
      feature_importance: [{ name: 'momentum_20', value: 0.2 }, { name: 'volatility_20', value: 0.1 }],
      data_metadata: { source: 'tencent_fqkline', as_of: '2025-11-05', delay: 'end_of_day' },
      flags: [], verdict: '样本外结果初步有效，仍需跨标的和滚动验证', disclaimer: '测试免责声明',
    }

    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
}

test.beforeEach(async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '投研分析' })).toBeVisible()
})

test('移动端导航和智能对话输入区可用', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  const menu = page.getByRole('button', { name: '打开导航菜单' })
  await expect(menu).toBeVisible()
  await menu.click()
  await expect(menu).toHaveAttribute('aria-expanded', 'true')
  await page.getByRole('button', { name: '智能对话' }).click()

  const input = page.getByRole('textbox', { name: '向 FinanceCrew 提问' })
  await expect(input).toBeVisible()
  const box = await input.boundingBox()
  expect(box).not.toBeNull()
  expect(box!.x + box!.width).toBeLessThanOrEqual(390)
})

test('K线分钟周期发送正确请求并更新数据状态', async ({ page }) => {
  await page.getByRole('button', { name: '行情' }).click()
  await expect(page.getByLabel('行情数据状态')).toContainText('图表源 腾讯')

  for (const period of ['5min', '15min', '30min', '60min']) {
    const label = period.replace('min', '分')
    const request = page.waitForRequest(req => new URL(req.url()).pathname === '/api/kline/600519' && new URL(req.url()).searchParams.get('period') === period)
    await page.getByRole('button', { name: label, exact: true }).click()
    await request
    await expect(page.getByLabel('行情数据状态')).toContainText('图表源 AKShare/腾讯')
    await expect(page.getByLabel('行情数据状态')).toContainText('复权 不复权')
  }
})

test('A股、港股和美股交易所时间不会被浏览器时区偏移', async ({ page }) => {
  const values = await page.evaluate(async () => {
    const { chartTime, formatChartTime } = await import('/src/marketTime.ts')
    return ['2026-08-11 09:30', '2026-08-11 16:00', '2026-08-11 21:30', '2026-08-12 04:00']
      .map(value => formatChartTime(chartTime(value)))
  })
  expect(values[0]).toContain('09:30')
  expect(values[1]).toContain('16:00')
  expect(values[2]).toContain('21:30')
  expect(values[3]).toContain('04:00')
})

test('策略回测入口提交用户选择的参数', async ({ page }) => {
  await page.getByRole('button', { name: '策略回测' }).click()
  await page.getByRole('textbox', { name: '回测股票代码' }).fill('600519')
  await page.getByRole('combobox', { name: '回测周期' }).selectOption('250')
  const request = page.waitForRequest(req => req.url().includes('/api/backtest/600519') && new URL(req.url()).searchParams.get('days') === '250')
  await page.getByRole('button', { name: '开始回测' }).click()
  await request
})

test('历史报告可以查看持久化运行追踪', async ({ page }) => {
  await page.getByRole('button', { name: '历史记录' }).click()
  await page.getByRole('button', { name: '查看' }).click()
  await expect(page.getByText(/运行追踪 · deepseek\/deepseek-chat/)).toBeVisible()
  await page.getByText(/运行追踪 · deepseek\/deepseek-chat/).click()
  await expect(page.getByText('Run ID: run-e2e-42')).toBeVisible()
  await expect(page.getByText('数据收集')).toBeVisible()
})

test('ML 信号诊断展示样本外区间和质量结论', async ({ page }) => {
  await page.getByRole('button', { name: '信号诊断' }).click()
  const request = page.waitForRequest(req => req.url().includes('/api/ml-signal/600519') && new URL(req.url()).searchParams.get('model') === 'auto')
  await page.getByRole('button', { name: '开始诊断' }).click()
  await request
  await expect(page.getByText('样本外结果初步有效，仍需跨标的和滚动验证')).toBeVisible()
  await expect(page.getByText('2025-07-03 → 2025-11-05')).toBeVisible()
  await expect(page.getByText('momentum_20')).toBeVisible()
})
