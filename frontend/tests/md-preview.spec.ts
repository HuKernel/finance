import { expect, test, type Page } from '@playwright/test'

const RICH = [
  '# 研究结论：贵州茅台',
  '## 一、核心观点',
  '公司基本面**稳健**，高端白酒护城河深厚。当前估值处于历史*中低位*，配置价值凸显。',
  '',
  '## 二、关键数据',
  '| 指标 | 2024 | 2025E | 同比 |',
  '|------|------|-------|------|',
  '| 营收（亿） | 1741 | 1920 | +10.3% |',
  '| 归母净利（亿） | 862 | 950 | +10.2% |',
  '| PE | 22.1 | 19.8 | - |',
  '',
  '## 三、多空逻辑',
  '- 看多因素',
  '  - 品牌力与提价权稳固',
  '  - 现金流充沛，分红率提升',
  '- 看空因素',
  '  - 批价波动与库存压力',
  '',
  '### 操作建议',
  '1. 逢低分批建仓',
  '2. 关注批价企稳信号',
  '3. 控制单一持仓比例',
  '',
  '## 四、代码示例',
  '```python',
  'def pe_band(pe, low=15, high=35):',
  '    """估值分位计算"""',
  '    return (pe - low) / (high - low)',
  '',
  'print(pe_band(19.8))',
  '```',
  '',
  '## 五、引用与来源',
  '> 投资有风险，入市需谨慎。本结论仅供研究参考。',
  '',
  '详见 [公司年报](https://example.com/annual) 以及 https://example.com/disclosure ，',
  '折现模型使用 `DCF` 方法，其中 $WACC = 8.5\\%$，目标价 $$P = \\frac{FCF}{WACC - g}$$',
  '',
  '---',
  '综合评级：**增持**（信心度 ★★★★☆）',
].join('\n')

async function mockApi(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('financecrew_token', 'e2e-token')
  })
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    let body: unknown = {}
    if (path === '/api/auth/me') body = { user: { id: 1, username: 'e2e' }, profile: { watchlist: [] } }
    else if (path === '/api/auth/is-admin') body = { is_admin: false }
    else if (path === '/api/auth/profile') body = { watchlist: [] }
    else if (path === '/api/alerts') body = []
    else if (path === '/api/notifications') body = { items: [], unread: 0 }
    else if (path === '/api/chat/sessions') body = [{ id: 1, title: '茅台研究', created_at: '2026-08-12T10:00:00', msg_count: 2 }]
    else if (path === '/api/chat/1/messages') body = [
      { role: 'user', content: '帮我研究一下茅台', created_at: '2026-08-12T10:00:00' },
      { role: 'assistant', content: RICH, created_at: '2026-08-12T10:00:05' },
    ]
    else if (path === '/api/hot') body = []
    else if (path.startsWith('/api/news/')) body = { symbol: '600519', news: [] }
    else if (path === '/api/market/top-turnover') body = { code: '600519', name: '贵州茅台', amount: 1, unit: '元', scope: 'a_share_full_market', as_of: '2026-08-12' }
    else if (path.startsWith('/api/quote/')) body = {
      brief: { name: '贵州茅台', price: 1500, change_pct: 1.2, pre_close: 1482 },
      kline: [],
      tech: {},
      metadata: {},
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
}

async function gotoChat(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: '智能对话', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '向 FinanceCrew 提问' })).toBeVisible({ timeout: 10000 })
  await page.getByRole('button', { name: '茅台研究' }).click()
  await expect(page.locator('.msg.assistant .msg-bubble')).toBeVisible({ timeout: 10000 })
}

test('模型回答 Markdown 渲染（暗色）', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('fc_theme_v3', 'dark'))
  await mockApi(page)
  await gotoChat(page)
  await page.waitForTimeout(400)
  await page.locator('.msg.assistant .msg-bubble').screenshot({ path: 'runtime_cache/md-preview-dark.png' })
  await page.screenshot({ path: 'runtime_cache/md-preview-dark-full.png' })
})

test('模型回答 Markdown 渲染（亮色）', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('fc_theme_v3', 'light'))
  await mockApi(page)
  await gotoChat(page)
  await page.waitForTimeout(400)
  await page.locator('.msg.assistant .msg-bubble').screenshot({ path: 'runtime_cache/md-preview-light.png' })
  await page.screenshot({ path: 'runtime_cache/md-preview-light-full.png' })
})
