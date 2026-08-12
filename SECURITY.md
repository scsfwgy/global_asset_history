# 安全政策 / Security Policy

## 报告漏洞 / Reporting a vulnerability

请不要为未修复的安全漏洞创建公开 issue。优先使用 GitHub 的私密漏洞报告：

<https://github.com/scsfwgy/global_asset_history/security/advisories/new>

报告中请包含受影响的版本或 commit、复现步骤、影响范围，以及在不暴露敏感数据前提下的日志或最小样例。维护者会尽快确认报告、评估影响并协调修复与披露时间。请在修复公开前保持信息私密。

Do not open a public issue for an unpatched vulnerability. Prefer GitHub private vulnerability reporting at the URL above. Include the affected version or commit, reproduction steps, impact, and sanitized evidence. Please keep the report private until a fix is available.

## 重点风险 / Security priorities

项目特别关注：

- 管理员 Token、Redis 凭据和其他秘密泄露；
- 心愿墙、统计接口和缓存键的鉴权绕过；
- SVG、HTML、CSV/JSON 输出中的注入或跨站脚本；
- 服务端请求伪造、恶意重定向和不受控上游地址；
- 上游市场数据污染、缓存投毒和解析器资源耗尽；
- 日志中的 Token、Cookie、完整 IP 或用户正文泄露；
- AI 工具调用中的提示注入、越权执行或未标注的模型生成结论。

## 金融与 AI 安全边界 / Financial and AI safety boundaries

GlobalAssetHistory 是研究和教育工具，不提供个性化投资建议、收益承诺或自动交易。市场数据可能延迟、缺失、被上游修订或因复权口径而不同；重要决定应回到交易所、发行人或其他权威来源核验。

未来的自然语言功能必须生成类型化、白名单化的分析计划，并由现有确定性计算引擎执行。结果应披露标的、日期范围、来源、公式和限制。模型不得直接执行交易、预测保证收益，或绕过服务端参数验证。实现细节见 [路线图](ROADMAP.md)。

GlobalAssetHistory is a research and education tool, not personalized investment advice, a return guarantee, or an automated trading system. Market data may be delayed, missing, revised, or affected by adjustment methodology. Verify consequential decisions with exchanges, issuers, or other authoritative sources.
