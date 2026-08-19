# CLAUDE.md

本文档供在本仓库中工作的代码助手使用。以实际代码为最终事实来源；理解代码时先阅读相关模块和测试确认实现细节。

## 最高优先级规则

### 1. 修改功能必须补测试

新增功能或修改核心逻辑时，必须编写对应测试：

- 后端使用 pytest，覆盖接口、计算、数据处理和缓存分支。
- 前端关键算法或交互应提供可复现的验证步骤；适合抽离的纯函数应增加测试。
- 若无法自动测试，必须说明原因和手动验证方法。

完整测试命令：

```bash
./start.sh test
```

或：

```bash
PYTHONPATH=backend backend/.venv/bin/python3 -m pytest backend/tests -q
```

当前测试套件收集 510 个测试，覆盖计算、服务、路由、基本面、数据下载、ETF/QDII、持仓解析、SEO、统计、运行日志和交付流程。

### 2. 产品交付门禁（强制）

任何 AI 大模型或代码助手修改产品后，交付前必须完成以下闭环：

1. 首先执行 `./start.sh debug`。禁止用直接运行 `python backend/app.py` 等方式绕过启动脚本。
2. `debug`、`start`、`restart` 都会先强制运行完整 pytest；测试失败时必须停止启动并修复，不得跳过或增加绕过参数。
3. 启动后访问本次修改涉及的页面和 `/api/health`，检查终端输出，并执行 `./start.sh logs` 复盘持久化日志。
4. 日志中必须能看到 `event=app_start` 和健康检查对应的 `event=http_request`；出现异常、Traceback 或无法解释的 Warning 时必须先处理或明确说明。
5. 涉及核心金融业务时，必须同时检查数据源、标的、缓存命中/降级、数量、耗时和异常日志，确认核心流程真实运行，而不只是页面能打开。
6. 在浏览器中验证本次改动涉及的桌面端和移动端；涉及 UI、主题或国际化时同时检查深浅色和中英文。

未完成“完整测试 → 启动 → 页面/API 验证 → 启动与核心业务日志复盘”闭环时，不得声称产品已交付完成。

日志不得记录 Token、Cookie、完整 IP、心愿正文等敏感内容。允许记录请求 ID、脱敏路径、标的、数据源、缓存层级、结果数量、状态码和耗时。

### 3. 新增页面或路由必须检查 `vercel.json`

Vercel 只会将 `vercel.json` 已匹配的路径交给 Flask。新增或调整以下路径后必须同步检查 rewrite：

- Flask 页面路由
- 语言前缀页面
- 带路径参数的文章或 ETF 页面
- `robots.txt`、`sitemap.xml` 等动态资源

遗漏 rewrite 常表现为本地正常、Vercel 404。普通 `/api/*` 子路由已由统一规则覆盖，但仍需确认没有被静态路径或规则顺序影响。

### 4. 页面内容变化必须维护固定 SEO 日期

Sitemap 和 Article JSON-LD 故意使用固定日期，不使用 `datetime.now()`：

- 首页内容变化：更新 `backend/app.py` 的 `INDEX_LASTMOD`
- ETF 市场页变化：更新 `ETF_MARKET_LASTMOD`
- 知识文章变化：更新 `KNOWLEDGE_ARTICLES` 对应条目的 `updated`
- `published` 只在首次发布时设置

仅修改后端逻辑、缓存或测试且不影响页面可见内容时，无需更新日期。相关测试位于 `backend/tests/routes/test_seo.py`。

### 5. 不要擅自提交代码

除非用户明确要求 commit、提交或推送，否则不要创建提交或推送。提交信息遵循 Conventional Commits：`feat:`、`fix:`、`refactor:`、`chore:`、`docs:` 等。

## 项目概览

GlobalAssetHistory 是 Flask + 原生前端实现的金融数据分析站点，不是 Kotlin/Android 项目，也没有 Node.js 前端构建流程。

- 后端：Python 3、Flask、Blueprint
- 前端：原生 HTML/CSS/classic JavaScript
- 图表：原生 SVG，自实现折线图、热力图和 Treemap
- 部署：Vercel 静态资源 + Python Serverless Function
- 国际化：`frontend/locales/zh-CN.json`、`zh-TW.json` 和 `en.json`（简体、繁体、英文，无前缀路径默认跟随浏览器语言）

主要功能包括多市场热力图、历史收益钻取、单标的详情和基本面历史、美股对比、多周期数据下载、投资回测、暴跌统计、VIX/VXN 对比与阈值研究、汇率损失与汇率计算器、A 股场内 ETF、QDII 基金及持仓地区配置、知识文章、心愿墙和站点统计。

统一资产类型为：

- `stock`：美股和美股 ETF
- `hk_stock`：港股
- `global_stock`：带 Yahoo 交易所后缀的全球股票
- `crypto`：数字货币
- `cn_stock`：A 股指数和股票

## 核心架构

### 统一日线数据层

`backend/service/price_change/common.py` 中的 `PriceSeries` 是核心基础数据结构。以下能力均从日线数据派生：

- yearly / monthly / monthly-batch / daily / detail
- stock-compare / history-download
- backtest
- crash-stats / crash-chart
- heatmap 的周期收益
- VIX/VXN comparison / fear-threshold-stats

统一入口位于 `price_change_service.py` 的日线缓存获取逻辑。新增资产类型时优先扩展 `fetchers.py` 的 `DAILY_SERIES_FETCHERS`，不要为每个统计接口重复抓取逻辑。

`fundamentals-history` 不属于 `PriceSeries` 日线派生能力；它由 `backend/service/price_change/fundamentals_history.py` 单独抓取和合并历史 PE、PB、ROE。不要把价格缓存与基本面时间序列缓存混为一套。

### 多级缓存

核心日线缓存：

- L1：进程内存，热实例快速响应
- L2：Upstash Redis REST 或兼容 Vercel KV，跨实例共享
- L3：`backend/data/` JSON 快照，冷启动和上游失败兜底

核心日线成功 TTL 为 6 小时，错误 TTL 为 5 分钟。ETF 历史、净值和 QDII 的主要 TTL 为 4 小时；具体值以代码常量为准。

过期的 L1 数据应删除，不应依赖过期内存作为降级。磁盘快照写入新版本时会清理同标的旧版本。

### Flask 模块

- `backend/app.py`：应用入口、前端响应、SEO/GEO、健康检查、诊断、访问和点击统计
- `backend/seo_rendering.py`：根据请求路径裁剪 `price-change.html`，仅保留当前面板、语言文章和必要脚本，并增强语义标签
- `price_change_bp` (`/api/price-change`)：标的搜索、收益、详情、基本面历史、美股对比、数据下载、回测、暴跌、热力图、VIX/VXN、汇率（`exchange-loss` / `exchange-rates`）
- `etf_market_bp` (`/api/etf-market`)：ETF 报价和估值、ETF 历史、自然年/月价格与 NAV 收益矩阵、QDII 基金、QDII 定期报告持仓
- `wishes_bp` (`/api/wishes`)：验证码、心愿提交和管理
- `api/index.py`：Vercel 导入并暴露 Flask `app`

### 前端

- `frontend/price-change.html`：主页面、各功能 Tab 和知识文章内容
- `frontend/etf-market.html`：ETF 市场独立页面
- `frontend/css/app.css`：共享样式
- `frontend/js/api.js`：同源 API 常量，`API_BASE = ""`
- `frontend/js/i18n.js`：语言切换
- `frontend/js/feature-updates.js`：按配置版本展示一次性功能更新通知
- `price-change.js` / `drilldown.js` / `charts.js`：历年收益、月日钻取和共享图表
- `price-detail.js`：单标的收益、质量、估值、基本面历史、收益日历和年度分红数据
- `stock-compare.js` / `data-download.js` / `backtest.js` / `crash-stats.js`：独立研究工具
- `heatmap.js` / `etf-market.js` / `qdii-funds.js` / `vix-chart.js` / `exchange-loss.js` / `fx-calculator.js`：市场分析与汇率工具
- `wishes.js` / `visitor-stats.js` / `header-trend.js`：互动、统计和页头装饰

全部脚本都是 classic script，并通过加载顺序共享全局常量、函数和状态。新增脚本时必须检查 `price-change.html` 底部的加载顺序。

功能更新通知由 `frontend/config/feature-updates.json` 手动控制。配置是按时间排列的版本数组，最后一项为最新版本；发布时只需在数组末尾追加包含数字 `version`、`date`、`zh` 和 `en` 的对象，`date` 固定使用 `YYYY.MM.DD` 格式，双语内容均为字符串列表。空数组会关闭提醒。用户只有点击确认按钮后才会在 localStorage 记录最新版本，弹窗可切换查看全部历史更新。

### 用户功能与代码入口

| 功能 | 页面路径 | 主要前端模块 | 主要 API |
| --- | --- | --- | --- |
| 市场热力图 | `/heatmap` | `heatmap.js` | `market-pulse`、`heatmap` |
| 历年涨跌幅（收益 + 最大回撤双指标、回撤风险分级着色及双面板趋势图） | `/yearly` | `price-change.js`、`drilldown.js`、`charts.js` | `yearly`、`monthly-batch`、`daily` |
| 股票详情 | `/detail` | `price-detail.js` | `detail`、`fundamentals-history` |
| 美股对比 | `/stock-compare` | `stock-compare.js` | `symbol-search`、`stock-compare` |
| 数据下载 | `/download` | `data-download.js` | `symbol-search`、`history-download` |
| 投资回测（详情 + 多标的对比 + 动画录制） | `/backtest` | `backtest.js` | `backtest`（详情单标的多序列；对比面板并行调用同接口多标的动画对比，可录制含图表与图例的 mp4） |
| 暴跌统计 | `/crash` | `crash-stats.js` | `crash-stats`、`crash-chart` |
| 场内 ETF | `/etf` | `etf-market.js` | `/api/etf-market/quote`、`valuation`、`history`、`returns-matrix` |
| 场外 QDII | `/qdii-funds` | `qdii-funds.js` | `/api/etf-market/qdii-funds`、`qdii-funds/<code>/holdings` |
| VIX/VXN | `/vix` | `vix-chart.js` | `vix-comparison`、`fear-threshold-stats` |
| 汇率损失 | `/exchange-loss` | `exchange-loss.js`、`fx-calculator.js` | `exchange-loss`、`exchange-rates` |
| 数据科普 | `/knowledge/...`、`/us-etf/...` | `price-change.html` 内嵌文章和路由映射 | 专题 CSV 接口（部分文章） |
| 心愿墙 | `/wishes` | `wishes.js` | `/api/wishes` |

不要引入 React/Vue 或构建工具，除非用户明确要求进行架构迁移。新增图表应延续现有 SVG 风格，并注意移动端和深浅色主题。

## 本地开发

```bash
./start.sh debug                 # 完整测试通过后，前台调试启动
./start.sh start                 # 完整测试通过后，后台生产启动
./start.sh restart               # 完整测试通过后，重启后台生产服务
./start.sh test                  # 仅运行完整测试
./start.sh stop
./start.sh status
./start.sh logs                  # 查看最近 80 行持久化日志
```

默认端口为 8730。`debug` 固定开启 Flask debug/reloader，并固定监听 `127.0.0.1`；`start` 和 `restart` 固定关闭 Flask debug。启动命令不接受额外参数，非法参数必须直接报错。

指定端口：

```bash
PORT=8080 ./start.sh debug
```

`start.sh` 会创建 `backend/.venv`、安装根目录 `requirements.txt`、加载 `.env.local`、强制运行完整测试，并在测试通过后释放目标端口。调试和生产输出都会写入 `logs/server.log`。

## 环境变量

- `HOST` / `PORT`：本地 Flask 地址和端口
- `FLASK_DEBUG`：是否开启 Flask debug/reloader
- `REQUEST_LOG`：是否记录脱敏后的结构化 API 请求日志，默认开启
- `SITE_URL`：SEO 绝对站点地址
- `WISH_ADMIN_TOKEN`：心愿管理和 `/api/stats` 鉴权
- `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN`：首选共享缓存变量
- `KV_REST_API_URL` / `KV_REST_API_TOKEN`：兼容变量

不要提交 `.env.local` 或任何 Token。生产 Serverless 环境应使用 Redis；本地文件只适合开发和数据兜底，无法保证跨实例持久化。

## SEO 与路由约定

Flask 会根据请求语言和路径动态替换：

- title、description、keywords、robots
- canonical 和 hreflang
- Open Graph、Twitter Card
- Organization、WebSite、WebApplication、Article、BreadcrumbList 与 Dataset JSON-LD
- `X-Robots-Tag`

`/zh/...` 和 `/en/...` 是 sitemap 中的 canonical 版本。无语言前缀 URL 不进入 sitemap。可索引工具由 `INDEXABLE_TOOL_PATHS` 管理；知识文章和专题 ETF 页面由 `KNOWLEDGE_ARTICLES` 管理。其他内部工具通常为 `noindex,follow`。

`price-change.html` 是统一内容源，但 Flask 响应必须通过 `seo_rendering.py` 按路由裁剪，避免每个 URL 输出全部 Tab、双语文章和无关脚本。每个公开页面应有且仅有一个页面级 H1；品牌名称使用 `.site-brand-name`。工具页将当前激活 Tab 渲染为 H1，知识文章将当前文章子 Tab（VIX 专题为一级 Tab）渲染为 H1；不要为 SEO 另加占空间的标题卡、作者日期或说明块。邀请链接仍需保留 `rel="sponsored nofollow"` 关系标记。

公开、可引用的数据集放在 `/datasets/*`，不要放在被 `robots.txt` 整体屏蔽的 `/api/*` 下；兼容旧 API 路径时可同时注册别名。机器发现入口由 `/llms.txt` 提供，新增该类动态资源时必须同步 `vercel.json`。

旧知识路径保留兼容，但必须 canonical 到新路径并保持 `noindex,follow`。新增知识文章、专题 ETF 页面或可索引工具需同步处理：

1. `KNOWLEDGE_ARTICLES` 或 `INDEXABLE_TOOL_PATHS`
2. 必要的 `legacy_paths`
3. Flask 路由
4. `vercel.json` 的文章路径正则
5. 前端文章内容和 Tab 映射
6. locale 中的 SEO 文案
7. SEO 测试

SEO 分享图片必须实际存在于 `frontend/doc/screenshot/`，因为 Vercel 只发布 `frontend/` 静态目录。

## 数据与抓取约定

- 美股优先使用 Yahoo Finance 相关接口。
- 港股优先使用 Yahoo/East Money；进入统一日线层前必须使用 `normalize_asset_symbol()` 规范化代码。
- 全球股票使用 Yahoo 交易所后缀代码，例如 `7203.T`、`005930.KS`、`2330.TW`；不要把它们按美股代码截断。
- 数字货币按 Binance → OKX → CoinGecko 回退。
- 汇率计算器参考汇率使用 Frankfurter（欧洲央行，EUR 基准，160+ 币种）；汇率损失页历史走势仍用 Yahoo FX。
- A 股指数、场内 ETF、净值和 QDII 使用 East Money/Tencent 等接口。
- QDII 地区配置来自最新定期报告；直接股票/存托凭证、基金/ETF 仓位必须分开呈现，不能在未穿透时把基金仓位直接归入某个地区。
- 单个上游失败不应拖垮批量请求；网络 IO 可使用 `ThreadPoolExecutor` 并发。
- 外部数据结构变化时，要先保存/构造样例并增加解析测试。
- 不要用单个数据点校准金融参数；应检查中间值并用多日期回归验证。

## 修改检查清单

### 后端接口或计算

1. 保持 `PriceSeries` 为统一数据基础。
2. 校验输入和错误响应。
3. 检查缓存键、TTL、跨实例行为和陈旧快照策略。
4. 增加 pytest 测试。
5. 新路由检查 `vercel.json`。

### 页面或前端

1. 保持无构建、classic script 的加载顺序。
2. 检查中文、英文、深浅色和移动端。
3. 检查浏览器历史、canonical 和 Tab URL 映射。
4. 可见内容变化时更新对应 SEO `lastmod`。
5. 若改变 OG 图片，确保文件位于 `frontend/` 下。
6. 新增用户可见功能时同步更新 `README.md` 的功能总览/API 表，以及本文件的“用户功能与代码入口”。

### 完成前

1. 执行 `./start.sh debug`，由启动脚本强制运行完整测试。
2. 访问 `/api/health` 和本次改动涉及的页面/API，完成浏览器验证。
3. 观察终端并执行 `./start.sh logs`，复盘 `event=app_start`、`event=http_request` 和核心业务日志。
4. 检查 `git diff`，避免修改数据快照、日志、环境文件或无关用户改动。
5. 明确说明未能自动验证的部分；未完成交付门禁时不得声称完成。

## 沟通偏好

- 与用户使用中文交流。
- 代码注释保持英文。
- 说明结果、验证情况和真实风险，不要把推测写成事实。
