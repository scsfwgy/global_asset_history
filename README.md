# GlobalAssetHistory — 全球资产历史收益分析工具

GlobalAssetHistory 是一个 Apache-2.0 开源、可自行部署的跨资产历史收益查询、市场分析与投资研究站点，覆盖美股、港股、全球股票、数字货币、A 股指数、场内 ETF 和 QDII 基金。

项目采用轻量架构：Flask 提供 API、动态页面与 SEO 响应，前端使用原生 HTML/CSS/JavaScript 和 SVG，不需要 Node.js 或前端构建步骤。生产环境面向 Vercel Serverless Functions。

线上站点：[qqq.tools24.uk](https://qqq.tools24.uk) · [参与贡献](CONTRIBUTING.md) · [安全政策](SECURITY.md) · [AI 路线图](ROADMAP.md)

> 本项目用于研究和教育，不构成个性化投资建议、收益承诺或自动交易服务。市场数据可能延迟、缺失或被修订，重要决策请以交易所、发行人或其他权威来源为准。

## 功能总览

主站提供 12 个用户功能入口；同一个功能可通过简体 `/zh/...`、繁体 `/zh-TW/...`、英文 `/en/...` 或无语言前缀路径访问（无前缀时默认跟随浏览器语言）。

| 功能 | 路径 | 主要能力 |
| --- | --- | --- |
| 市场热力图 | `/heatmap` | 全球大盘情绪；美股、港股、全球热门股票、数字货币和 A 股 Treemap；支持日/周/月/季/年周期和成交额/市值/涨跌幅权重 |
| 历年涨跌幅 | `/yearly` | 多资产年度/月度收益与最大回撤热力表、跟随涨跌配色的五档回撤风险标记、聚焦/完整坐标的收益-回撤双面板趋势图、年 → 月 → 日钻取、预设组合和 CSV 导出 |
| 股票详情 | `/detail` | 收益概览、CAGR、波动率、回撤与修复、收益质量、收益日历、复权 OHLC 图、估值快照及美股历史 PE/PB/ROE |
| 美股对比 | `/stock-compare` | 同时比较 2–8 只美股的年度综合收益、涨跌幅、税后分红、最大回撤和二维聚合结果 |
| 数据下载 | `/download` | 按代码或名称搜索标的，预览并下载多周期 OHLCV JSON；周/月/年数据由日线聚合 |
| 投资回测 | `/backtest` | 详情：一次性或按日/周/月/年投入；资产、投入和盈亏曲线；资金加权年化收益（IRR）及逐笔成交明细；对比：多标的一次性投入动画对比，可切总资产/总收益曲线，动画可一键录制为标准 16:9 / 9:16 mp4 视频（仅含图表与图例） |
| 暴跌统计 | `/crash` | 日 K、N 日 K、周 K、月 K 暴跌检测；触底、修复率、恢复天数和单次事件走势图 |
| 场内 ETF 追踪 | `/etf` | A 股场内 ETF 实时报价、费率、溢价成本、跟踪误差、估值误差、单只历史图、多 ETF 聚合分析，以及按自然年/月对比价格收益与 NAV 收益 |
| 场外 QDII 追踪 | `/qdii-funds` | 纳指100、标普500和主动 QDII；申购状态、限额、费率、多周期收益、基金经理及最新报告持仓地区配置 |
| VIX/VXN 分析 | `/vix` | SPY/QQQ/VIX/VXN 多周期走势、情绪分位和相关性，以及恐慌指数达到阈值后的远期收益统计 |
| 汇率损失 | `/exchange-loss` | 多法币历史交叉汇率走势、跨币种持有盈亏计算，以及汇率计算器子工具（任意币对多目标折算、正反向汇率、搜索选择器与历史记录） |
| 数据科普 | `/knowledge` | 价值投资、美股购买、核心 ETF、纳指 ETF、市场数据研究、金融术语及专题 ETF 文章 |
| 心愿墙 | `/wishes` | SVG 验证码、匿名心愿、频率限制，以及管理员回复和删除 |

### 跨资产能力

- 统一支持 `stock`、`hk_stock`、`global_stock`、`crypto`、`cn_stock` 五类标的。
- 历年收益、股票详情、数据下载和投资回测覆盖全部五类资产；暴跌统计覆盖美股、港股、全球股票、数字货币和 A 股。
- 标的输入支持代码规范化；股票对比和数据下载支持按公司名称或代码搜索。
- 页面会在浏览器本地保存常用标的、参数、筛选条件、主题和涨跌颜色偏好。
- 股票详情、回测、暴跌统计和数据下载支持本地历史记录，点击记录可回填代码与资产类型；记录同时展示标的代码与名称。

### 内容、体验与运营

- 简体中文、繁体中文、英文界面和语言前缀 URL。
- 深色/浅色主题、绿涨红跌/红涨绿跌切换，以及桌面端和移动端适配。
- 版本化功能更新弹窗集中展示近期更新；用户确认后同一版本不再提醒。
- 金融知识文章、独立工具落地页、按路由裁剪的服务端 HTML、Article/Dataset JSON-LD、Open Graph 和多语言 SEO/GEO。
- `llms.txt` 与不受 `/api/` robots 规则影响的公开 CSV 数据集，便于搜索引擎和生成式搜索系统发现、理解与引用。
- 访问次数、匿名用户、网站/设备语言、Tab 浏览、设置操作和外链点击统计。
- 心愿墙管理员操作和受 Token 保护的站点统计页。

## 技术架构

| 层 | 实现 |
| --- | --- |
| 后端 | Python 3、Flask 3、Flask Blueprint |
| 前端 | 原生 HTML、CSS、classic JavaScript |
| 图表 | 原生 SVG，自实现折线图、热力图和 Treemap 布局 |
| 数据请求 | `requests`、`curl_cffi`（可用时模拟浏览器 TLS） |
| 缓存 | L1 进程内存 + L2 Upstash Redis/Vercel KV + L3 JSON 快照 |
| 测试 | pytest，当前收集 510 个测试 |
| 部署 | Vercel 静态资源 + Python Serverless Function |

### 后端模块

- `backend/app.py`：Flask 入口、页面托管、SEO/GEO、健康检查和站点统计
- `backend/seo_rendering.py`：按路由裁剪单页 HTML，只输出当前面板、文章语言和必要脚本
- `backend/routes/price_change.py`：标的搜索、收益、详情、基本面历史、美股对比、数据下载、回测、暴跌、热力图和 VIX/VXN API
- `backend/routes/etf_market.py`：场内 ETF 报价/估值、历史收益矩阵、ETF 历史、QDII 基金和定期报告持仓 API
- `backend/routes/wishes.py`：心愿墙 API
- `backend/service/price_change/`：数据抓取、统一日线模型、计算、缓存和诊断
- `backend/service/wishes/`：验证码和心愿业务逻辑

所有核心收益能力均建立在统一的 `PriceSeries` 日线数据上。新增资产类型时，应优先实现 daily-series fetcher，再复用年度、月度、日度、详情、下载、回测、暴跌和比较计算。

### 数据源

| 类型 | 主要来源 | 降级策略 |
| --- | --- | --- |
| 美股/美股 ETF | Yahoo Finance | 多种 Yahoo 接口互相回退 |
| 港股 | Yahoo Finance、East Money | 统一补全港股交易所后缀并按数据类型回退 |
| 全球股票 | Yahoo Finance | 使用带交易所后缀的 Yahoo 标的代码 |
| 数字货币 | Binance | Binance → OKX → CoinGecko |
| A 股指数/股票 | East Money、Tencent Finance | 按数据类型回退 |
| A 股场内 ETF | Tencent Finance、East Money | 本地历史与净值快照兜底 |
| QDII 基金 | East Money 移动端接口 | Redis/本地快照兜底 |

核心日线缓存成功结果保留 6 小时，错误结果保留 5 分钟。ETF 历史、净值和 QDII 数据的主要 TTL 为 4 小时。

Apache-2.0 仅覆盖项目贡献者原创的软件与文档，不会重新许可第三方 API、行情、基金快照、商标或内容。使用、缓存或再分发相关数据前，请阅读[第三方数据与内容说明](THIRD_PARTY_DATA.md)并核对来源方条款。

## 本地启动

需要 Python 3、`venv`、`pip`、`curl` 和常见 Unix 工具。推荐直接使用启动脚本：

```bash
./start.sh debug
```

首次运行会创建 `backend/.venv`、安装根目录 `requirements.txt`，并在测试全部通过后启动服务。

默认地址：

- 首页：<http://127.0.0.1:8730>
- 健康检查：<http://127.0.0.1:8730/api/health>
- 数据源诊断：<http://127.0.0.1:8730/api/diag>

### 启动命令

| 命令 | 说明 |
| --- | --- |
| `./start.sh` | 打开交互式菜单 |
| `./start.sh debug` | 强制完整测试后，开启 debug/reloader 并前台启动 |
| `./start.sh start` | 强制完整测试后，以生产模式后台启动 |
| `./start.sh stop` | 停止后台服务 |
| `./start.sh restart` | 强制完整测试后，重启后台生产服务 |
| `./start.sh status` | 查看 PID 状态 |
| `./start.sh test` | 运行完整测试套件 |
| `./start.sh logs` | 查看最近服务日志，`LOG_LINES` 可指定行数 |

`debug` 固定监听 `127.0.0.1` 并开启 Flask debug/reloader；`start` 和 `restart` 固定关闭 Flask debug。所有启动命令都会先执行完整 pytest，失败时不会启动。启动命令不接受额外参数。

自定义地址和端口：

```bash
HOST=127.0.0.1 PORT=8080 ./start.sh debug
```

交付验证应使用 `start.sh`，不要直接运行 Flask 入口绕过测试和日志流程。调试与生产日志都会写入 `logs/server.log`。

## 测试

```bash
./start.sh test
```

或：

```bash
PYTHONPATH=backend backend/.venv/bin/python3 -m pytest backend/tests -q
```

测试覆盖收益计算、基本面历史、数据下载、回测、缓存、API、ETF/QDII、持仓解析、SEO、站点统计、运行日志和交付流程。新增功能或修改核心逻辑时必须补充对应测试。

## 配置

### 环境变量

本地可将敏感变量写入不会提交的 `.env.local`，`start.sh` 会自动加载。

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | 本地 Flask 监听地址 |
| `PORT` | `8730` | 本地 Flask 端口 |
| `FLASK_DEBUG` | 由脚本控制 | `debug` 固定开启，`start` / `restart` 固定关闭 |
| `REQUEST_LOG` | `1` | 记录带请求 ID、脱敏路径、状态码和耗时的 API 日志 |
| `SITE_URL` | 站点配置值 | canonical、Open Graph、sitemap 的绝对域名 |
| `WISH_ADMIN_TOKEN` | 无 | 心愿管理和 `/api/stats` 管理员鉴权 |
| `UPSTASH_REDIS_REST_URL` | 无 | Upstash Redis REST 地址 |
| `UPSTASH_REDIS_REST_TOKEN` | 无 | Upstash Redis REST Token |
| `KV_REST_API_URL` | 无 | 兼容 Vercel KV 的 Redis 地址 |
| `KV_REST_API_TOKEN` | 无 | 兼容 Vercel KV 的 Token |

Redis 两套变量会自动识别，优先使用 `UPSTASH_*`。

### 业务配置

`backend/config/price_change_config.json` 包含：

- 资产预设组
- 热力图颜色范围
- CoinGecko 币种映射
- 外部数据源地址
- 站点基础配置

`frontend/config/feature-updates.json` 控制功能更新弹窗：

- 配置是一个版本数组，数组最后一项就是本次更新；发布时只需在末尾追加一项。
- 每个版本只包含数字 `version`、`date`、`zh` 和 `en`；日期格式固定为 `YYYY.MM.DD`，两种语言都使用字符串列表维护更新内容。
- 用户确认后会记住最后一项的版本号，同一版本只显示一次；后续追加新版本会再次提醒。
- 弹窗中的“查看历史更新”会按新到旧展示整个数组；将数组设为空即可关闭提醒。

```json
[
  {
    "version": 1,
    "date": "2026.08.01",
    "zh": ["功能一", "功能二"],
    "en": ["Feature one", "Feature two"]
  },
  {
    "version": 2,
    "date": "2026.08.03",
    "zh": ["本次更新"],
    "en": ["Latest update"]
  }
]
```

`backend/data/` 存放 ETF 费率、QDII 及行情快照。这些文件既是数据资产，也是 Serverless 冷启动时的 L3 兜底。

## API 概览

### 历史收益 `/api/price-change`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/config` | 站点、资产组和颜色配置 |
| GET | `/symbol-search` | 按代码或名称搜索受支持标的 |
| GET | `/market-pulse` | 上证、KOSPI、标普500、纳指100和 BTC 最新价格及日涨跌幅 |
| POST | `/yearly` | 多资产年度收益与最大回撤 |
| POST | `/monthly` | 单资产月度收益与最大回撤 |
| POST | `/monthly-batch` | 多资产批量月度收益与最大回撤 |
| POST | `/daily` | 单资产指定月份日收益 |
| POST | `/detail` | 单标的收益概览、质量、估值和日/月/年明细 |
| POST | `/fundamentals-history` | 美股历史 PE、PB 和年度 ROE |
| POST | `/stock-compare` | 2–8 只美股的年度收益、分红和回撤比较 |
| POST | `/history-download` | 指定标的、周期和日期范围的 OHLCV JSON 数据 |
| POST | `/backtest` | 投资回测 |
| POST | `/crash-stats` | 暴跌统计 |
| POST | `/crash-chart` | 暴跌图表数据 |
| POST | `/heatmap` | 美股、港股、全球股票、数字货币和 A 股市场热力图 |
| POST | `/vix-comparison` | SPY、QQQ、VIX 和 VXN 多周期对比 |
| POST | `/fear-threshold-stats` | VIX/VXN 达到阈值后的 SPY/QQQ 远期收益统计 |
| POST | `/exchange-loss` | 指定持有/目标货币对的历史交叉汇率（以 USD 为枢纽计算） |
| GET | `/exchange-rates` | Frankfurter（欧洲央行）参考汇率，EUR 基准 160+ 币种（供汇率计算器折算任意币对） |
| GET | `/header-trend` | 页头市场趋势 |

### ETF 市场 `/api/etf-market`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/quote` | 场内 ETF 报价 |
| GET | `/valuation` | ETF 估值和跟踪分析 |
| GET | `/qdii-funds` | QDII 基金数据 |
| GET | `/qdii-funds/<code>/holdings` | QDII 最新定期报告持仓和地区配置 |
| GET | `/history` | ETF 历史行情 |
| GET | `/returns-matrix` | 纳指100/标普500基准与场内 ETF 的自然年/月价格收益和 NAV 收益矩阵 |

### 心愿墙 `/api/wishes`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 获取心愿列表 |
| POST | `/` | 提交心愿 |
| GET | `/captcha` | 获取 SVG 验证码 |
| POST | `/verify-admin` | 验证管理员 Token |
| PATCH | `/<wish_id>/reply` | 管理员回复 |
| DELETE | `/<wish_id>` | 管理员删除 |

其他系统接口包括 `/api/health`、`/api/diag`、`/api/visits`、`/api/track`、专题 CSV 下载和管理员统计页 `/api/stats?token=...`。公开数据集使用 `/datasets/qqqm-holdings.csv` 与 `/datasets/tqqq-historical-prices.csv`；原 `/api/assets/...` 地址继续兼容。

## Vercel 部署

项目不需要前端构建。`vercel.json` 指定：

- `frontend/` 为静态输出目录
- `api/index.py` 为 Flask Serverless 入口
- `/api/*`、`/datasets/*`、页面路径、语言路径、`robots.txt`、`sitemap.xml` 和 `llms.txt` rewrite 到 Flask
- Function 使用 512 MB 内存、30 秒超时
- 默认区域为香港 `hkg1`

部署时至少应配置 `SITE_URL`；生产环境强烈建议连接 Upstash Redis，并配置 `WISH_ADMIN_TOKEN`。

Redis 提供跨实例共享缓存和原子计数。未配置时，项目会降级到进程内存和本地文件，但 Vercel 的临时文件系统无法保证跨实例或冷启动持久化。

新增 Flask 页面路由时必须同步检查 `vercel.json` 的 rewrite，否则可能出现“本地正常、Vercel 404”。

## SEO

动态 HTML 响应提供：

- 简体 `/zh/...`、繁体 `/zh-TW/...`、英文 `/en/...` canonical URL
- `title`、description、keywords 和 robots
- Open Graph 与 Twitter Card
- `zh-CN`、`zh-TW`、`en`、`x-default` hreflang
- Organization、WebSite、WebApplication、Article、BreadcrumbList 与 Dataset JSON-LD
- `robots.txt`、`sitemap.xml`、`llms.txt` 和 `X-Robots-Tag`
- 旧知识文章路径 canonical 到新路径并设为 `noindex,follow`

Flask 会在响应阶段按路由裁剪主站单页文档：只保留当前功能面板、当前语言文章和必要脚本。工具页直接复用当前激活 Tab 作为唯一 H1；知识文章复用当前文章子 Tab（VIX 专题复用一级 Tab）作为 H1。页面不额外插入占空间的 SEO 标题卡或作者日期说明块，源文件仍是统一的 UI 内容定义；邀请链接通过 `rel="sponsored nofollow"` 保留机器可读的关系标记。

Sitemap 只列语言前缀的 canonical URL，避免无前缀页面造成重复收录。

页面内容发生实质变化时，需要更新 `backend/app.py` 中对应的固定日期：

- 首页：`INDEX_LASTMOD`
- ETF 市场页：`ETF_MARKET_LASTMOD`
- 知识文章：`KNOWLEDGE_ARTICLES` 对应条目的 `updated`

不要用 `datetime.now()` 动态生成 `lastmod`。SEO 回归测试位于 `backend/tests/routes/test_seo.py`。

## 项目结构

```text
├── api/index.py                    # Vercel Python Function 入口
├── backend/
│   ├── app.py                      # Flask 应用、页面、SEO、统计
│   ├── seo_rendering.py            # 路由级 HTML 裁剪与语义增强
│   ├── config/
│   ├── data/                       # ETF/QDII/净值历史快照
│   ├── routes/                     # 三个业务 Blueprint
│   ├── service/                    # 抓取、计算、缓存、心愿服务
│   ├── scripts/                    # ETF 费率采集脚本
│   └── tests/                      # pytest 测试
├── frontend/
│   ├── price-change.html           # 主站及知识内容
│   ├── etf-market.html             # ETF 市场独立页
│   ├── landing.html                # tools24.uk Host 的落地页
│   ├── health.html
│   ├── css/
│   ├── js/
│   ├── locales/
│   └── doc/screenshot/             # 线上 SEO 分享图
├── scripts/capture_screenshots.py
├── requirements.txt
├── start.sh
└── vercel.json
```

## 开源许可与贡献

项目原创代码和文档采用 [Apache License 2.0](LICENSE) 开源。第三方数据与内容不因本项目许可证而改变其权利状态，详见[第三方数据与内容说明](THIRD_PARTY_DATA.md)。

欢迎提交缺陷修复、新数据源、测试、文档与无障碍改进。开始前请阅读[贡献指南](CONTRIBUTING.md)；安全漏洞请通过[私密渠道](SECURITY.md)报告，不要创建公开 issue。

项目正在规划开源的数据适配器维护助手和可审计的双语自然语言研究层。设计原则、交付物、评估方式与明确排除的用途见 [AI 路线图](ROADMAP.md)。
