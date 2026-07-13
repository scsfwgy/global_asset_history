# GlobalAssetHistory — 全球资产历史收益分析工具

GlobalAssetHistory 是一个跨资产历史收益查询、市场分析与投资回测站点，覆盖美股、数字货币、A 股指数、场内 ETF 和 QDII 基金。

项目采用轻量架构：Flask 提供 API、动态页面与 SEO 响应，前端使用原生 HTML/CSS/JavaScript 和 SVG，不需要 Node.js 或前端构建步骤。生产环境面向 Vercel Serverless Functions。

## 主要功能

### 历史收益与回测

- 多资产历年涨跌幅热力表和年度走势图
- 年 → 月 → 日三级钻取，展示涨跌幅与收盘价
- 一次性、每日、每周、每月投入策略回测
- 总资产、累计投入、收益曲线和逐笔投入明细
- CSV 导出和浏览器本地状态保存

### 市场分析

- 历史暴跌区间、频率和修复统计
- VIX 恐慌指数与资产价格对比
- 美股市场 Treemap 热力图
- A 股场内 ETF 实时报价、费率、溢价率和跟踪误差
- QDII 基金净值、收益、费率与限购状态

### 内容与互动

- 中文、英文界面和语言前缀 URL
- 金融知识文章及 Article JSON-LD
- 心愿墙、SVG 验证码、管理员回复和删除
- 访问次数、Tab 浏览、设置操作和链接点击统计

## 技术架构

| 层 | 实现 |
| --- | --- |
| 后端 | Python 3、Flask 3、Flask Blueprint |
| 前端 | 原生 HTML、CSS、classic JavaScript |
| 图表 | 原生 SVG，自实现折线图、热力图和 Treemap 布局 |
| 数据请求 | `requests`、`curl_cffi`（可用时模拟浏览器 TLS） |
| 缓存 | L1 进程内存 + L2 Upstash Redis/Vercel KV + L3 JSON 快照 |
| 测试 | pytest，当前收集 260 个测试 |
| 部署 | Vercel 静态资源 + Python Serverless Function |

### 后端模块

- `backend/app.py`：Flask 入口、页面托管、SEO、健康检查和站点统计
- `backend/routes/price_change.py`：收益、回测、暴跌、热力图、VIX 等 API
- `backend/routes/etf_market.py`：场内 ETF、QDII 和历史行情 API
- `backend/routes/wishes.py`：心愿墙 API
- `backend/service/price_change/`：数据抓取、统一日线模型、计算、缓存和诊断
- `backend/service/wishes/`：验证码和心愿业务逻辑

所有核心收益能力均建立在统一的 `PriceSeries` 日线数据上。新增资产类型时，应优先实现 daily-series fetcher，再复用年度、月度、日度、回测和暴跌计算。

### 数据源

| 类型 | 主要来源 | 降级策略 |
| --- | --- | --- |
| 美股/美股 ETF | Yahoo Finance | 多种 Yahoo 接口互相回退 |
| 数字货币 | Binance | Binance → OKX → CoinGecko |
| A 股指数/股票 | East Money、Tencent Finance | 按数据类型回退 |
| A 股场内 ETF | Tencent Finance、East Money | 本地历史与净值快照兜底 |
| QDII 基金 | East Money 移动端接口 | Redis/本地快照兜底 |

核心日线缓存成功结果保留 6 小时，错误结果保留 5 分钟。ETF 历史、净值和 QDII 数据的主要 TTL 为 4 小时。

## 本地启动

需要 Python 3、`venv`、`pip`、`curl` 和常见 Unix 工具。推荐直接使用启动脚本：

```bash
./start.sh debug
```

首次运行会创建 `backend/.venv` 并安装根目录 `requirements.txt`。

默认地址：

- 首页：<http://127.0.0.1:8730>
- 健康检查：<http://127.0.0.1:8730/api/health>
- 数据源诊断：<http://127.0.0.1:8730/api/diag>

### 启动命令

| 命令 | 说明 |
| --- | --- |
| `./start.sh` | 打开交互式菜单 |
| `./start.sh debug` | 前台启动，便于查看日志 |
| `./start.sh start` | 后台启动 |
| `./start.sh stop` | 停止后台服务 |
| `./start.sh restart` | 重启后台服务 |
| `./start.sh status` | 查看 PID 状态 |
| `./start.sh test` | 运行完整测试套件 |
| `./start.sh start --test` | 测试通过后后台启动 |
| `./start.sh debug --test` | 测试通过后前台启动 |

`debug` 命令指“前台运行”，Flask debug/reloader 默认并不开启。如需自动重载：

```bash
FLASK_DEBUG=1 ./start.sh debug
```

自定义地址和端口：

```bash
HOST=127.0.0.1 PORT=8080 ./start.sh debug
```

也可以手动启动：

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r requirements.txt
PYTHONPATH=backend backend/.venv/bin/python3 backend/app.py
```

## 测试

```bash
./start.sh test
```

或：

```bash
PYTHONPATH=backend backend/.venv/bin/python3 -m pytest backend/tests -q
```

测试覆盖收益计算、回测、缓存、API、ETF/QDII、SEO 和站点统计。新增功能或修改核心逻辑时必须补充对应测试。

## 配置

### 环境变量

本地可将敏感变量写入不会提交的 `.env.local`，`start.sh` 会自动加载。

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | 本地 Flask 监听地址 |
| `PORT` | `8730` | 本地 Flask 端口 |
| `FLASK_DEBUG` | 关闭 | 设为 `1/true/yes/on` 开启 debug 和 reloader |
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

`backend/data/` 存放 ETF 费率、QDII 及行情快照。这些文件既是数据资产，也是 Serverless 冷启动时的 L3 兜底。

## API 概览

### 历史收益 `/api/price-change`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/config` | 站点、资产组和颜色配置 |
| POST | `/yearly` | 多资产年度收益 |
| POST | `/monthly` | 单资产月度收益 |
| POST | `/monthly-batch` | 多资产批量月度收益 |
| POST | `/daily` | 单资产指定月份日收益 |
| POST | `/detail` | 资产明细 |
| POST | `/backtest` | 投资回测 |
| POST | `/crash-stats` | 暴跌统计 |
| POST | `/crash-chart` | 暴跌图表数据 |
| POST | `/heatmap` | 美股市场热力图 |
| POST | `/vix-comparison` | VIX 对比 |
| GET | `/header-trend` | 页头市场趋势 |

### ETF 市场 `/api/etf-market`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/quote` | 场内 ETF 报价 |
| GET | `/valuation` | ETF 估值和跟踪分析 |
| GET | `/qdii-funds` | QDII 基金数据 |
| GET | `/history` | ETF 历史行情 |

### 心愿墙 `/api/wishes`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 获取心愿列表 |
| POST | `/` | 提交心愿 |
| GET | `/captcha` | 获取 SVG 验证码 |
| POST | `/verify-admin` | 验证管理员 Token |
| PATCH | `/<wish_id>/reply` | 管理员回复 |
| DELETE | `/<wish_id>` | 管理员删除 |

其他系统接口包括 `/api/health`、`/api/diag`、`/api/visits`、`/api/track` 和管理员统计页 `/api/stats?token=...`。

## Vercel 部署

项目不需要前端构建。`vercel.json` 指定：

- `frontend/` 为静态输出目录
- `api/index.py` 为 Flask Serverless 入口
- `/api/*`、页面路径、语言路径、`robots.txt` 和 `sitemap.xml` rewrite 到 Flask
- Function 使用 512 MB 内存、30 秒超时
- 默认区域为香港 `hkg1`

部署时至少应配置 `SITE_URL`；生产环境强烈建议连接 Upstash Redis，并配置 `WISH_ADMIN_TOKEN`。

Redis 提供跨实例共享缓存和原子计数。未配置时，项目会降级到进程内存和本地文件，但 Vercel 的临时文件系统无法保证跨实例或冷启动持久化。

新增 Flask 页面路由时必须同步检查 `vercel.json` 的 rewrite，否则可能出现“本地正常、Vercel 404”。

## SEO

动态 HTML 响应提供：

- 中文 `/zh/...`、英文 `/en/...` canonical URL
- `title`、description、keywords 和 robots
- Open Graph 与 Twitter Card
- `zh-CN`、`en`、`x-default` hreflang
- Website/Article JSON-LD
- `robots.txt`、`sitemap.xml` 和 `X-Robots-Tag`
- 旧知识文章路径 canonical 到新路径并设为 `noindex,follow`

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

## License

MIT
