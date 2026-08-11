export default function LandingPage({
  onAnalyze,
  onQuote,
}: {
  onAnalyze: () => void
  onQuote: () => void
}) {
  return (
    <article className="landing-page">
      <section className="landing-hero" aria-labelledby="landing-title">
        <div>
          <span className="landing-kicker">AI 驱动的个人投研工作台</span>
          <h1 id="landing-title">让多角色 AI 团队，帮你完成一轮有证据的股票研究</h1>
          <p>
            FinanceCrew 聚合行情、财务、新闻、技术面与市场情绪，让不同分析角色独立研判、交叉辩论，
            最终给出可追溯的共识、风控意见和交易计划。
          </p>
          <div className="landing-actions">
            <button className="research-primary" onClick={onAnalyze}>开始智能投研</button>
            <button className="ghost" onClick={onQuote}>查看实时行情</button>
          </div>
          <small>分析结果仅供研究参考，不构成投资建议。</small>
        </div>
        <div className="landing-report" aria-label="研究流程示意">
          <div><span>01</span><strong>多维数据</strong><em>行情 · 财务 · 新闻 · 情绪</em></div>
          <div><span>02</span><strong>角色研判</strong><em>基本面 · 技术面 · 资金面</em></div>
          <div><span>03</span><strong>风险审查</strong><em>仓位 · 止损 · 风险提示</em></div>
          <div><span>04</span><strong>持续跟踪</strong><em>预警 · 论文 · 定时分析</em></div>
        </div>
      </section>

      <section className="landing-section" aria-labelledby="landing-value">
        <span className="landing-kicker">为什么使用 FinanceCrew</span>
        <h2 id="landing-value">把分散的信息，变成可复盘的研究流程</h2>
        <div className="landing-grid">
          <div><strong>多角色交叉验证</strong><p>不同分析角色独立打分并展开多空辩论，减少单一视角造成的偏差。</p></div>
          <div><strong>证据与判断分离</strong><p>保留数据来源、关键计算和运行追踪，方便核对结论依据。</p></div>
          <div><strong>从研究走向行动</strong><p>一键保存投资论文、创建价格预警，并安排交易日定时跟踪。</p></div>
        </div>
      </section>

      <section className="landing-section landing-flow" aria-labelledby="landing-flow">
        <span className="landing-kicker">三步完成研究</span>
        <h2 id="landing-flow">输入标的，查看证据，持续验证</h2>
        <ol>
          <li><span>1</span><div><strong>输入股票与研究问题</strong><p>支持 A 股、港股和美股代码，聚焦你真正关心的问题。</p></div></li>
          <li><span>2</span><div><strong>获得多角色研究报告</strong><p>查看观点分歧、共识评分、风控审查与交易计划。</p></div></li>
          <li><span>3</span><div><strong>记录并跟踪投资假设</strong><p>通过投资论文、预警和定时分析持续验证原始判断。</p></div></li>
        </ol>
      </section>

      <section className="landing-section landing-faq" aria-labelledby="landing-faq">
        <span className="landing-kicker">常见问题</span>
        <h2 id="landing-faq">开始之前，你可能想知道</h2>
        <details><summary>FinanceCrew 能直接告诉我该买哪只股票吗？</summary><p>不能。它用于整理证据、展示不同观点和记录研究过程，不承诺收益，也不替代持牌投资顾问。</p></details>
        <details><summary>支持哪些市场？</summary><p>目前主要支持 A 股，并提供港股、美股的行情和部分研究能力；具体数据覆盖以页面实际展示为准。</p></details>
        <details><summary>历史分析会被再次利用吗？</summary><p>会。系统可在当前用户范围内检索历史投研记录，为后续分析提供上下文，但不会公开知识库页面。</p></details>
      </section>

      <section className="landing-cta" aria-labelledby="landing-cta">
        <div><span className="landing-kicker">从下一只股票开始</span><h2 id="landing-cta">让研究过程更完整，也更容易复盘</h2></div>
        <button className="research-primary" onClick={onAnalyze}>进入投研工作台</button>
      </section>
    </article>
  )
}
