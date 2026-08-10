# FinanceCrew UI v3 Design QA

## 对比基准

- 视觉真值：`runtime_cache/redesign-audit/00-selected-option-3.png`
- 实现截图：`runtime_cache/redesign-audit/11-cockpit-desktop.png`
- 移动端截图：`runtime_cache/redesign-audit/13-cockpit-mobile.png`
- 全屏并排对比：`runtime_cache/redesign-audit/22-comparison-pass-3.png`（左侧设计，右侧实现）
- 聚焦区域对比：`runtime_cache/redesign-audit/23-focused-main-and-actions.png`（主图表与右侧操作栏）
- 设计原图像素：`1487 × 1058`
- 实现截图像素 / CSS viewport：`1440 × 1024`
- 移动端截图像素 / CSS viewport：`390 × 844`
- `deviceScaleFactor`：`1`
- 密度归一化：设计原图在并排对比中缩放为 `1440 × 1024`
- 状态：已登录、亮色主题、投研分析默认页、标的 `600519`

## Findings

本轮最终对比没有待处理的 P0、P1 或 P2 问题。

- 字体与排版：实现使用项目既有系统字体栈，标题、正文、金融数字的字号和权重与设计方向一致；中文没有截断或异常换行。
- 间距与布局：桌面端形成左侧导航、中央证据区、右侧操作栏三层结构；主 K 线和操作栏比例接近视觉真值。移动端按“先操作、后证据”单列重排，无横向溢出。
- 颜色与 tokens：默认亮色、冷灰底、白色内容面、深色正文和克制的 emerald 主色已统一；涨跌仍沿用项目现有语义色，避免改变既有业务约定。
- 图像与资产：页面没有装饰性位图需求；K 线、指标和行情来自项目现有真实组件与接口，没有使用静态占位图、CSS 图形或伪造数据替代。
- 文案与内容：静态文案围绕“证据 → 投研 → 回测”任务组织；设计图中的预测财务、催化剂和风险清单未在分析前伪造，真实分析完成后继续使用现有报告组件展示。
- 图标：保留已有通知和自选控件；导航使用清晰文本，没有为了贴图新增图标依赖或手工 SVG。
- 交互与状态：已验证默认亮色、亮/暗主题往返切换、投研进入回测、桌面和移动端导航。未激活业务页面不再后台挂载或消耗行情接口额度。
- 可访问性：保留跳转主内容链接、语义化 `nav`/`main`、`aria-current`、表单标签、键盘焦点和 reduced-motion 规则；移动端点击目标可用。

## 对比历史

1. Pass 1：发现 P1——中央区域缺少选中方案的市场证据和 K 线，页面明显过空。
   - 修复：复用现有 `QuoteCard` 与真实行情接口；同时修正所有隐藏页面同时挂载造成的后台请求。
   - 证据：`runtime_cache/redesign-audit/20-comparison-pass-1.png` → `21-comparison-pass-2.png`。
2. Pass 2：发现 P1——研究输入仍占据中央主区，右侧操作栏只有按钮，与视觉真值的任务结构不一致。
   - 修复：将标的、研究问题、模式选择和主操作移入右栏，中央区域专注真实市场证据。
   - 证据：`runtime_cache/redesign-audit/21-comparison-pass-2.png` → `22-comparison-pass-3.png`。
3. Pass 3：未发现可执行的 P0/P1/P2 差异。

## 浏览器验证

- Playwright：通过本机 Chrome 验证。
- 桌面端：`scrollWidth = viewport = 1440`。
- 移动端：`scrollWidth = viewport = 390`。
- 主交互：注册登录、默认进入投研、投研跳转策略回测、主题切换。
- 页面脚本错误：无 `pageerror`；移动端无 console error。桌面端记录到一条未关联任何 HTTP response 的 Chrome 通用 `404` 日志，不影响页面资源、交互或接口，列为非阻塞 P3 观察项。

## Follow-up Polish

- P3：后续若已有统一图标库，可为左侧导航补充与视觉真值一致的线性图标；当前文本导航更轻量且不影响可用性。
- P3：若后端以后提供低成本的批量自选行情接口，可增加视觉真值中的上下文自选列表；当前不为装饰目的放大数据源请求量。

final result: passed
