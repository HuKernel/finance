import { expect, test } from '@playwright/test'

test('游客可浏览行情，受保护功能和反馈会要求登录', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.removeItem('financecrew_token')
    localStorage.setItem('fc_theme_v3', 'light')
  })
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    let body: unknown = {}
    if (path === '/api/market/top-turnover') body = { code: '600519', name: '贵州茅台', amount: 1, unit: '元', scope: 'a_share_full_market', as_of: '2026-08-11' }
    else if (path === '/api/hot') body = []
    else if (path === '/api/auth/profile') body = { watchlist: [] }
    else if (path === '/api/auth/login') body = { token: 'guest-token', user: { id: 8, username: 'visitor' }, profile: { watchlist: [] } }
    else if (path === '/api/auth/is-admin') body = { is_admin: false }
    else if (path === '/api/alerts') body = []
    else if (path === '/api/feedback') body = route.request().method() === 'GET'
      ? { items: [], total: 0, page: 1, page_size: 10 }
      : { id: 1, status: 'received' }
    else if (path.startsWith('/api/quote/')) body = {
      brief: { name: '贵州茅台', price: 1500, change_pct: 1.2, pre_close: 1482 },
      kline: [{ date: '2026-08-11', open: 1480, close: 1500, high: 1510, low: 1470, volume: 1000 }],
      tech: {}, metadata: {},
    }
    else if (path.startsWith('/api/news/')) body = { symbol: '600519', news: [] }
    else if (path.startsWith('/api/industry/')) body = { peers: [], avg_pe: null, avg_pb: null }

    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })

  await page.goto('/')
  await expect(page.getByRole('heading', { name: '让多角色 AI 团队，帮你完成一轮有证据的股票研究' })).toBeVisible()
  await page.getByRole('button', { name: '查看实时行情' }).click()
  await expect(page.getByRole('heading', { name: '行情', exact: true })).toBeVisible()

  await page.getByRole('button', { name: '信号诊断' }).click()
  await expect(page.getByRole('dialog', { name: '登录' })).toBeVisible()
  await page.getByRole('button', { name: '暂不登录，继续浏览' }).click()
  await expect(page.getByRole('heading', { name: '行情', exact: true })).toBeVisible()

  await page.getByRole('button', { name: '反馈', exact: true }).click()
  await page.getByRole('textbox', { name: '用户名', exact: true }).fill('visitor')
  await page.getByLabel('密码').fill('password')
  await page.getByRole('button', { name: '登录', exact: true }).last().click()
  await expect(page.getByRole('dialog', { name: '意见反馈' })).toBeVisible()

  await page.getByLabel('反馈类型').selectOption('data')
  await page.getByLabel('反馈内容').fill('港股行情时间显示不正确')
  const requestPromise = page.waitForRequest(request => new URL(request.url()).pathname === '/api/feedback')
  await page.getByRole('button', { name: '提交反馈' }).click()
  const request = await requestPromise

  expect(request.headers().authorization).toBe('Bearer guest-token')
  expect(request.postDataJSON()).toEqual({ category: 'data', content: '港股行情时间显示不正确', page: '行情' })
  await expect(page.getByText('反馈已提交，感谢你的建议')).toBeVisible()
})
