# FinanceCrew - 多智能体金融投研平台

多智能体驱动的 A股/港股/美股 投研平台：**对话式智能体 + 多智能体深度研报 + 多市场行情可视化 + 投资组合管理 + 策略回测 + 投资论文追踪**。

## 核心功能

### 智能体
- **智能对话**：LangGraph ReAct 智能体，自主调用 12 种工具（行情/K线/财务/龙虎榜/新闻/搜索/行业对比/情绪面/估值/投研流水线/历史投研搜索/网页搜索），基于真实数据回答
- **意图识别**：自动检测用户消息中的分析意图（"分析茅台""调研苹果短线"），直接触发完整投研流水线
- **长期记忆**：跨会话记住用户关注的标的和偏好（只从用户消息提取，不污染AI回复）
- **多智能体投研**：5 位分析师（宏观/基本面/技术面/情绪面/资金面）独立研判 → 多空辩论 → 共识评分 → 风控审查 → 交易计划
- **Agentic 模式**：分析师可自主调用工具（联网搜索、行情查询），不限于预设数据
- **投研知识库**：搜索用户历史投研分析记录，AI 可引用过去的研究结论
- **运行追踪**：每次投研保存 run ID、模型、节点时间线、Agentic 工具调用和最终状态；历史报告可展开查看，失败记录同样保留
- **多模型对比**：最多 5 个 OpenAI 兼容模型并发调用，分别返回耗时、Provider usage、可选成本和证据完整度启发式；单模型失败不影响其他结果
- **报告证据分层**：报告明确标注原始事实、确定性计算和 AI 判断，并保存数据源、截止时间、复权口径、关键假设与报告版本

### 行情与数据
- **三市场覆盖**：A股/港股/美股行情、K线（日K/周K/月K/5分/15分/30分/60分 + 当日分时）、技术指标（MA/MACD/KDJ/BOLL/RSI/ATR/ADX）；实时性以页面元数据为准
- **美股数据源**：日K使用新浪，分钟K使用 yfinance；当日分时按东财 → Polygon.io（可选 API Key）→ 腾讯 → 新浪顺序 fallback
- **分时图**：A股/港股/美股分时，美股时间自动转北京时间，跨午夜时间轴正确映射
- **数据可信层**：行情页展示行情源/图表源、数据截止时间、近实时/延迟/日终、复权方式、清洗行数和备用源状态
- **Provider 契约**：Quote、Bar、Fundamental、News 使用统一元数据字段；`/api/data/providers` 可查询免费/增值访问方式、API Key 和数据能力
- **自选股**：侧栏 watchlist + 行情卡片星标按钮，三处同步
- **热门股票**：每日动态排序（涨幅前6），不固定列表
- **情绪面分析**：A股用东财人气榜+雪球+量价资金；港股/美股用联网搜索获取舆情
- **DCF估值**：三阶段现金流折现模型，支持A股/港股/美股
- **市场数据**：板块轮动、条件选股（自定义筛选条件）、融资融券、北向资金（沪股通/深股通实时排行）

### 投资管理
- **投资组合**：持仓追踪（买入加权成本/卖出减仓）、实时盈亏、交易历史
- **策略回测**：9种策略（MA均线交叉/双均线/MACD/KDJ/BOLL/RSI/网格/买入持有/AI情景模拟），含超额收益/最大回撤/胜率/权益曲线；规则策略按前收盘信号、次日开盘成交，计入滑点、佣金最低收费、印花税和过户费；每次运行可导出执行假设与数据/结果指纹
- **回测深度分析**：蒙特卡洛模拟、分层测试、参数敏感度热力图、Walk-Forward验证、CPCV/PBO稳健性检验
- **ML 信号诊断**：复用 18 维特征和三重壁垒标签，展示固定时间切分下的样本外买入精度、超额收益、特征重要性和质量警告
- **投资论文追踪**：记录投资逻辑（thesis）和偏离度（drift detection）；可关联最近一次 AI 分析、可复现回测数据指纹及后续 Reflection 状态

### 预警与定时
- **价格预警**：4种类型（价格突破/跌破、涨跌幅超限），30秒轮询 + 弹窗通知
- **定时分析**：自定义定时任务（cron表达式），自动执行投研分析并保存
- **反思引擎**：记录每次投研决策，N天后自动结算实际收益，反思决策质量

### 安全
- **per-user LLM Key**：每个用户独立 API Key，使用 Fernet 认证加密存储，前端永远脱敏
- **登录安全**：频率限制（5次失败锁定15分钟）、密码 PBKDF2-SHA256 哈希
- **游客访问**：行情和市场数据无需登录；分析、诊断、回测、对话及反馈提交按需登录
- **反爬限流**：全局请求频率限制（200次/分钟），CORS 白名单
- **数据隔离**：所有用户数据（对话/组合/预警/分析/记忆）按 user_id 隔离

### UI/UX
- **极简风格**：直角/细线/大留白/克制配色（翠绿强调色 #10b981，参考 Linear/Bloomberg Terminal）
- **暗色/亮色主题**：一键切换
- **自定义弹窗系统**：全局 toast（成功/失败/警告）+ confirm 确认框，不使用原生 alert/confirm
- **ErrorBoundary**：组件级错误边界，单页崩溃不白屏
- **移动端适配**：@media 断点（平板1024px/手机768px），导航抽屉、对话列表折叠、表格滚动、表单单列
- **K线图**：基于 lightweight-charts（日K蜡烛图+分时折线+成交量+MACD/KDJ+多周期+多日分时），支持十字光标、缩放和全屏
- **懒加载**：katex/backtest图表按需加载，减小首屏体积
- **PDF导出**：投研报告打印优化
- **Docker部署**：多阶段构建，一行启动

技术栈：LangChain + LangGraph + FastAPI + React 19/Vite/TypeScript + SQLite + 腾讯/东财/akshare/Polygon.io 数据。

## 快速开始

### 1. 启动后端

```bash
cd backend
uv venv .venv
uv pip install -r requirements.txt
# 可选：启用 Polygon 美股分时 fallback
# 在项目根目录 .env 中填写：POLYGON_API_KEY=你的新API Key
.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2. 构建前端

```bash
cd frontend
npm install
npm run build
```

### 3. 使用

打开 http://localhost:8000 ，注册账号登录，在"个人中心 > 模型配置"填写大模型 API Key，然后进入"智能对话"直接提问（如：分析一下 600519）。

### 4. Docker 部署

```bash
docker build -t financecrew .
docker run -p 8000:8000 -v financecrew-data:/app/data financecrew
```

## 项目结构

```
backend/
  app/
    main.py              # FastAPI 入口（路由注册 + 中间件 + 静态托管）
    deps.py              # 共享依赖（认证守卫，避免循环导入）
    pipeline.py          # 投研流水线薄封装（LangGraph 状态图）
    config.py            # LLM 配置管理 + DB 连接
    db_migrations.py     # 数据库索引迁移（幂等）
    llm.py               # LangChain ChatOpenAI 客户端
    auth.py              # JWT 认证 + 用户画像 + per-user LLM Key 加密
    cache.py             # SQLite 数据缓存层（TTL 过期）
    valuation.py         # DCF 现金流折现估值模型
    portfolio.py         # 投资组合管理
    alert.py             # 价格预警系统
    tools.py             # 智能体工具集（12种工具）
    analysis_trace.py    # 投研运行追踪（run ID/节点/工具/耗时）
    scheduler.py         # 定时分析调度器
    reflection_engine.py # 反思引擎（决策记录 + N天结算）
    thesis_tracker.py    # 投资论文追踪 + 偏离检测
    knowledge_base.py    # 投研知识库（历史分析检索）
    ic_evaluator.py      # 信号IC评估
    routes/              # API 路由（13个模块）
      system.py          # 健康/配置/LLM对比
      auth.py            # 注册/登录/用户管理
      analysis.py        # 投研分析（SSE流式）
      market.py          # 行情/K线/对比
      portfolio.py       # 组合/交易
      backtest.py        # 回测/深度分析
      alerts.py          # 预警CRUD
      chat.py            # 对话（SSE流式）
      scheduler.py       # 定时任务管理
      thesis.py          # 投资论文
      knowledge.py       # 知识库搜索
      reflection.py      # 反思结算
      market_data.py     # 板块/选股/融资融券/北向资金
    chat/                # 对话模块（从 chat.py 拆分）
      prompts.py         # 系统提示词定义
      db.py              # 会话/消息 CRUD + build_agent
      memory.py          # 长期记忆管理（只从用户消息提取）
      intent.py          # 意图识别（触发投研分析）
      peers.py           # 行业同行管理
      streaming.py       # SSE 流式对话
    graph/               # LangGraph 投研流水线
      state.py           # 状态定义
      nodes.py           # 节点（collect_data/analysts/debate/consensus/risk/trader）
      builder.py         # 图构建器
    agents/              # 分析师/风控/交易员角色
      analysts.py        # 标准分析师（5角色）
      agentic_analyst.py # Agentic 分析师（自主调工具）
      base.py            # 分析师基类
    data/                # 数据层
      fetcher.py         # 兼容入口（重导出全部公共函数）
      a_stock.py         # A股数据兼容shim
      stock_data.py      # A股行情/K线/分时
      tech_signals.py    # 技术指标计算
      financials.py      # 财务/龙虎榜
      search.py          # 股票搜索
      hk_us_stock.py     # 港股/美股（多接口fallback + 时区转换）
      polygon_us.py      # Polygon.io 美股数据源
      news.py            # 新闻/快讯
      sentiment.py       # 社交情绪
      market.py          # 行业对比/热门
      utils.py           # 通用工具函数
      north_flow.py      # 北向资金
      sector_flow.py     # 板块轮动
      stock_screener.py  # 条件选股
      margin_data.py     # 融资融券
    backtest/            # 策略回测包
      strategies.py      # 9种策略信号生成器
      indicators.py      # 技术指标计算
      metrics.py         # 统计指标（夏普/回撤/胜率等）
      engine.py          # 回测执行引擎
    backtest_analysis/   # 回测深度分析包
      scoring.py         # 综合评分
      monte_carlo.py     # 蒙特卡洛模拟
      layered.py         # 分层测试
      sensitivity.py     # 参数敏感度
      walk_forward.py    # Walk-Forward验证
      cpcv.py            # 组合交叉验证
      pbo.py             # 过拟合概率
      full_analysis.py   # 完整分析流水线
    ml_signal/           # ML信号诊断（特征/标签/时序切分/训练/评估）
  test/                  # pytest 单元测试
frontend/
  src/
    App.tsx              # 主界面（12个标签页 + 按需登录守卫 + ErrorBoundary）
    ChatPage.tsx         # 智能对话（流式 + 热门轮播 + 行情卡片）
    QuotePage.tsx        # 行情页（K线 + 对比 + 分时实时刷新）
    QuoteCard.tsx        # 行情卡片（K线/分时切换 + 星标）
    KLineChart.tsx       # lightweight-charts（日K/分时/MACD/KDJ/多周期/跨午夜）
    marketTime.ts        # 交易所时间到图表时间的无偏移映射
    Markdown.tsx         # Markdown 渲染（katex懒加载）
    BacktestPage.tsx     # 策略回测（图表懒加载）
    BacktestAnalysis.tsx # 回测深度分析
    MLSignalPage.tsx     # ML信号样本外诊断
    MarketDataPage.tsx   # 市场数据（4Tab：板块/选股/融资/北向）
    PortfolioPage.tsx    # 投资组合
    ThesisPage.tsx       # 投资论文
    SchedulerPage.tsx    # 定时分析
    ProfilePage.tsx      # 个人中心
    AdminPage.tsx        # 管理后台
    Modal.tsx            # 自定义弹窗系统（toast/confirm）
    ErrorBoundary.tsx    # 错误边界
    HistoryPage.tsx      # 投研历史
    AlertBell.tsx        # 全局预警
    LoginPage.tsx        # 登录/注册
    FeedbackWidget.tsx   # 全局用户反馈（登录后提交）
.github/workflows/
  ci.yml                 # CI（后端 pytest + 前端 lint/build/Playwright + Docker build）
```

## 智能体工具（12种）

| 工具 | 功能 | A股 | 港股 | 美股 |
|------|------|:---:|:---:|:---:|
| get_quote | 近实时行情快照 | OK | OK | OK |
| get_kline | K线数据（多周期） | OK | OK | OK |
| get_financials | 财务摘要 | OK | OK | OK |
| get_news | 个股新闻 | OK | OK | OK |
| search_stock | 搜索股票代码 | OK | OK | OK |
| web_search | 联网搜索（DuckDuckGo） | OK | OK | OK |
| compare_industry | 行业对比 | OK | OK | OK |
| get_sentiment | 社交情绪 | OK | OK | OK |
| get_valuation | DCF估值 | OK | OK | OK |
| run_research | 完整投研流水线 | OK | OK | OK |
| search_my_research | 搜索历史投研记录 | OK | OK | OK |
| get_lhb | 龙虎榜（A股独有） | OK | - | - |

## API 一览（95+ 端点）

| 模块 | 接口 | 说明 |
|------|------|------|
| 认证 | /api/auth/register, /login, /me, /profile, /change-password | 注册/登录/用户画像/密码 |
| 反馈 | /api/feedback, /api/admin/feedback | 登录用户提交反馈、管理员查看记录 |
| LLM配置 | /api/auth/llm-config | per-user LLM Key（加密） |
| 对话 | /api/chat, /api/chat/stream, /api/chat/session(s) | ReAct 智能体 + SSE + 会话管理 |
| 投研 | /api/analysis, /api/analysis/stream | 多智能体分析（SSE流式 + 持久化运行追踪） |
| 行情 | /api/quote/{symbol}, /api/search/{q}, /api/hot | 行情/K线/搜索/热门 |
| 数据源 | /api/data/providers, /api/fundamentals/{symbol} | Provider 能力与统一财务元数据 |
| 新闻 | /api/news/{symbol}, /api/flash | 个股新闻/快讯 |
| 行业 | /api/industry/{symbol}, /api/industry/peers | 行业对比/同行管理 |
| 情绪 | /api/sentiment/{symbol} | 社交情绪面 |
| 估值 | /api/dcf/{symbol} | DCF估值 |
| 组合 | /api/portfolio, /buy, /sell, /transactions | 持仓/买卖/交易历史 |
| 回测 | /api/backtest/{symbol}, /api/backtest-analysis/* | 回测/蒙特卡洛/分层/敏感度 |
| 信号诊断 | /api/ml-signal/{symbol} | ML样本外分类/策略/特征重要性诊断 |
| 预警 | /api/alerts, /check, /{id}/reactivate | 预警CRUD/检查/重新激活 |
| 知识库 | /api/knowledge/search, /stats | 历史投研检索/统计 |
| 论文 | /api/theses, /api/theses/{id}/experiments, /api/thesis-drift/{ticker} | 投资论文/回测实验/偏离检测 |
| 反思 | /api/reflection/settle/{ticker} | 手动结算pending决策 |
| 定时 | /api/scheduled-tasks | 定时分析任务管理 |
| 市场数据 | /api/market/sectors, /screener, /margin, /north-flow | 板块/选股/融资/北向 |
| LLM对比 | /api/llm-compare | 并行对比耗时/token/可选成本/证据指标 |

## 免责声明

本项目为投资研究辅助工具，输出由 AI 智能体自动生成，仅供参考，不构成任何投资建议。市场有风险，投资需谨慎，盈亏自负。
