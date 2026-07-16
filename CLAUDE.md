# CLAUDE.md

本文档供在本仓库中工作的代码助手使用。以实际代码为最终事实来源；修改前先阅读相关模块和测试。

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

当前测试套件收集 306 个测试，覆盖计算、服务、路由、ETF/QDII、SEO、统计、运行日志和交付流程。

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
- 国际化：`frontend/locales/zh-CN.json` 和 `en.json`

主要功能包括历史收益钻取、投资回测、暴跌统计、VIX 对比、美股热力图、A 股 ETF、QDII 基金、知识文章、心愿墙和站点统计。

## 核心架构

### 统一日线数据层

`backend/service/price_change/common.py` 中的 `PriceSeries` 是核心基础数据结构。以下能力均从日线数据派生：

- yearly / monthly / monthly-batch / daily / detail
- backtest
- crash-stats / crash-chart
- VIX comparison

统一入口位于 `price_change_service.py` 的日线缓存获取逻辑。新增资产类型时优先扩展 `fetchers.py` 的 `DAILY_SERIES_FETCHERS`，不要为每个统计接口重复抓取逻辑。

### 多级缓存

核心日线缓存：

- L1：进程内存，热实例快速响应
- L2：Upstash Redis REST 或兼容 Vercel KV，跨实例共享
- L3：`backend/data/` JSON 快照，冷启动和上游失败兜底

核心日线成功 TTL 为 6 小时，错误 TTL 为 5 分钟。ETF 历史、净值和 QDII 的主要 TTL 为 4 小时；具体值以代码常量为准。

过期的 L1 数据应删除，不应依赖过期内存作为降级。磁盘快照写入新版本时会清理同标的旧版本。

### Flask 模块

- `backend/app.py`：应用入口、前端响应、SEO、健康检查、诊断、访问和点击统计
- `price_change_bp` (`/api/price-change`)：收益、回测、暴跌、热力图、VIX
- `etf_market_bp` (`/api/etf-market`)：ETF 报价、估值、QDII、历史数据
- `wishes_bp` (`/api/wishes`)：验证码、心愿提交和管理
- `api/index.py`：Vercel 导入并暴露 Flask `app`

### 前端

- `frontend/price-change.html`：主页面、各功能 Tab 和知识文章内容
- `frontend/etf-market.html`：ETF 市场独立页面
- `frontend/css/app.css`：共享样式
- `frontend/js/api.js`：同源 API 常量，`API_BASE = ""`
- `frontend/js/i18n.js`：语言切换
- 其他 JS 按功能拆分，全部是 classic script，共享全局状态

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
- Website/Article JSON-LD
- `X-Robots-Tag`

`/zh/...` 和 `/en/...` 是 sitemap 中的 canonical 版本。无语言前缀 URL 不进入 sitemap。工具型内部 Tab 通常 `noindex,follow`；知识文章和两个主要落地页可索引。

旧知识路径保留兼容，但必须 canonical 到新路径并保持 `noindex,follow`。新增知识文章需同步处理：

1. `KNOWLEDGE_ARTICLES`
2. 必要的 `legacy_paths`
3. Flask 路由
4. `vercel.json` 的文章路径正则
5. 前端文章内容和 Tab 映射
6. locale 中的 SEO 文案
7. SEO 测试

SEO 分享图片必须实际存在于 `frontend/doc/screenshot/`，因为 Vercel 只发布 `frontend/` 静态目录。

## 数据与抓取约定

- 美股优先使用 Yahoo Finance 相关接口。
- 数字货币按 Binance → OKX → CoinGecko 回退。
- A 股指数、场内 ETF、净值和 QDII 使用 East Money/Tencent 等接口。
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
