# 参与贡献 / Contributing

感谢你帮助改进 GlobalAssetHistory。项目欢迎缺陷修复、新数据源、测试、文档和可访问性改进。为保护金融计算的可复现性，所有变更都应说明数据来源、计算口径和验证方式。

Thank you for improving GlobalAssetHistory. Bug fixes, data-source adapters, tests, documentation, and accessibility improvements are welcome. To keep financial calculations reproducible, every change should document its sources, methodology, and verification.

## 开始之前 / Before you start

1. 搜索现有 issue，避免重复工作；较大功能请先创建 issue 讨论范围。
2. 不要提交 API Token、Cookie、个人信息、付费数据或无权再分发的内容。
3. 阅读 [第三方数据说明](THIRD_PARTY_DATA.md)；新增数据源时记录提供方、接口、许可或使用条款链接、缓存策略和降级路径。
4. 金融展示和计算必须保持可审计：明确标的、币种、时区、日期范围、复权方式、公式及缺失数据处理。

1. Search existing issues first; open an issue before starting a large feature.
2. Never commit API tokens, cookies, personal information, paid data, or content you cannot redistribute.
3. Read [Third-party data](THIRD_PARTY_DATA.md). New sources must document the provider, endpoint, license or terms URL, caching, and fallback behavior.
4. Financial output must remain auditable: identify symbols, currency, timezone, date range, adjustment policy, formulas, and missing-data behavior.

## 本地验证 / Local verification

使用项目入口运行完整测试：

```bash
./start.sh test
```

产品变更在提交前还必须完成以下验证：

```bash
./start.sh debug
curl --fail http://127.0.0.1:8730/api/health
./start.sh logs
```

请在桌面端和移动端检查受影响页面；涉及界面、主题或国际化时，同时验证中英文与深浅色主题。

Run the full test suite through the project entry point. Product changes must also be started through `./start.sh debug`, checked through `/api/health`, reviewed in persistent logs, and verified on the affected desktop and mobile views. UI, theme, and localization changes require both languages and both color themes.

## 变更要求 / Change requirements

- 新功能或核心逻辑修改必须包含 pytest 测试。
- 外部响应结构变更应加入脱敏 fixture 和解析回归测试。
- 单个上游失败不能拖垮批量请求；必须覆盖缓存和降级分支。
- 新页面或 Flask 路由必须同步检查 `vercel.json`、SEO 元数据和固定 `lastmod`。
- 不要引入 React、Vue 或构建工具，除非变更本身是经讨论同意的架构迁移。
- AI 生成的代码与文档由贡献者负责审查、测试和授权；请在 Pull Request 中披露实质性的 AI 辅助。

- New features and core logic changes require pytest coverage.
- External schema changes require sanitized fixtures and parser regression tests.
- One upstream failure must not fail a batch; cover cache and fallback paths.
- New pages or Flask routes require matching `vercel.json`, SEO, and fixed `lastmod` updates.
- Do not add React, Vue, or build tooling unless an architectural migration was discussed and accepted.
- Contributors remain responsible for reviewing, testing, and licensing AI-assisted work; disclose material AI assistance in the pull request.

## Pull Request 清单

- [ ] 变更范围单一且提交信息清楚。
- [ ] 新行为有测试或说明无法自动测试的原因。
- [ ] `./start.sh test` 通过。
- [ ] 产品变更已完成启动、页面/API 和日志验证。
- [ ] 未包含凭据、个人信息或无权再分发的数据。
- [ ] 用户可见功能已同步更新 README 和中英文文案。
- [ ] 已注明新数据源、公式、假设和已知限制。

By submitting a contribution, you agree that it is licensed under the repository's [Apache License 2.0](LICENSE). Only submit work you have the right to license.
