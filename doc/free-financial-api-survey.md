# 免费金融数据 API 调研报告

> 调研日期：2026-06-16  
> 目的：评估 Finnhub、Financial Modeling Prep (FMP)、yfinance 三个免费数据源的覆盖范围，为项目后续扩展 ETF 持仓、费率、基本面等能力选型。

---

## 1. 背景

GlobalAssetHistory 当前只做价格历史（涨跌幅），数据源是 Yahoo Finance / Binance / OKX / CoinGecko / East Money。用户想进一步了解 ETF 的**底层持仓权重**和**管理费率**，因此我们对三个免费 API 做了摸底测试。

---

## 2. 测试环境

| 数据源 | API Key / 方式 | 免费额度 |
|--------|---------------|---------|
| **Finnhub** | `d8oebu9r01qrbffl3erg...` | 60 次/分钟 |
| **FMP** | `TsMs6WXwVdLzmvXGAzRXE...` | 250 次/天 |
| **yfinance** | 无需 key（Python 库） | 无硬限制（非官方） |

---

## 3. 各数据源详细实测

### 3.1 Finnhub

**免费版可用：**

| 端点 | 说明 | 示例 |
|------|------|------|
| `/api/v1/quote` | 实时报价（c/d/dp/h/l/o/pc） | SPY → $754.83, +1.76% |
| `/api/v1/stock/profile2` | 公司档案：行业、市值、上市日、流通股 | AAPL → Technology, $4.35T |
| `/api/v1/stock/metric` | 核心指标：beta、52周高低、多周期回报率 | beta=1.017, 52W return=22.86% |
| `/api/v1/stock/recommendation` | 月度分析师评级汇总 | strongBuy/buy/hold/sell/strongSell |
| `/api/v1/stock/peers` | 同行业可比公司列表 | AAPL → DELL, HPE, SMCI... |
| `/api/v1/stock/insider-transactions` | 内部人交易记录 | 名称/价格/数量/日期 |
| `/api/v1/stock/earnings` | 历史盈利惊喜 | 实际 EPS vs 预估、surprise% |
| `/api/v1/calendar/earnings` | 未来财报日历 | 日期/symbol/预估 EPS |
| `/api/v1/company-news` | 按 symbol + 日期范围的新闻 | 标题/摘要/来源/图片 |
| `/api/v1/news` | 综合市场新闻（不需要 symbol） | 通用财经新闻 |
| `/api/v1/press-releases` | 公司官方新闻稿 | 官方 PR |
| `/api/v1/stock/market-status` | 交易所开盘状态 | isOpen/session/holiday |
| `/api/v1/fda-advisory-committee-calendar` | FDA 新药审批日程 | 日期/会议描述 |

**免费版不可用：**

| 端点 | 说明 |
|------|------|
| `/api/v1/stock/candle` | 日线 K 线 → "Market data subscription required" |
| `/api/v1/etf/profile` | ETF 费率/档案 → "You don't have access" |
| `/api/v1/etf/holdings` | ETF 持仓权重 → "You don't have access" |
| `/api/v1/crypto/candle` | 加密 K 线 → Premium |
| `/api/v1/forex/rates` | 外汇汇率 → Premium |
| `/api/v1/stock/social-sentiment` | Reddit/Twitter 情绪 → Premium |
| `/api/v1/scan/pattern` | 技术形态识别 → Premium |
| `/api/v1/scan/support-resistance` | 支撑阻力 → Premium |
| `/api/v1/stock/financials` | 三大财报 → Premium |

---

### 3.2 Financial Modeling Prep (FMP)

> ⚠️ FMP 在 2025 年 8 月 31 日后废弃了全部 v3 和 v4 旧端点，新路径为 `/stable/`。旧文档大量 404，新 API 免费版覆盖面显著缩水。

**免费版可用（`/stable/` 前缀）：**

| 端点 | 说明 | 示例 |
|------|------|------|
| `/stable/profile?symbol=AAPL` | 公司档案（描述/行业/MC/beta/网站/ISIN/CIK） | Apple Inc., Consumer Electronics |
| `/stable/quote?symbol=AAPL` | 实时报价（含 50/200 日均价） | $296.42, avg50=$286.30 |
| `/stable/income-statement?symbol=AAPL` | 年度利润表（营收/毛利/净利润/EPS） | Rev=$416B, NI=$112B, EPS=$7.49 |
| `/stable/key-metrics?symbol=AAPL` | 关键指标（部分字段可用） | marketCap 正常返回 |
| `/stable/financial-growth?symbol=AAPL` | 多维度增长率（营收/毛利/净利 YoY） | Rev growth=6.4%, NI growth=19.5% |
| `/stable/enterprise-values?symbol=AAPL` | 企业价值/市值/股本历史 | 5 条记录 |
| `/stable/dividends?symbol=AAPL` | 完整分红历史（含收益率/频率） | 91 条记录，含 yield% |
| `/stable/splits?symbol=AAPL` | 拆股历史 | 5 次拆股（1987-2020） |

**免费版不可用（返回空数组 `[]` 或空 JSON）：**

| 端点 | 说明 |
|------|------|
| `/stable/etf-holdings` | ETF 持仓 → `[]` |
| `/stable/etf-info` | ETF 费率/档案 → `[]` |
| `/stable/etf-sector-weightings` | ETF 行业权重 → 空 |
| `/stable/etf-country-weightings` | ETF 国家权重 → 空 |
| `/stable/etf-stock-exposure` | ETF 个股风险敞口 → 空 |
| `/stable/historical-prices` | 日线 K 线 → `[]` |
| `/stable/historical-price-full` | 全量历史 → `[]` |
| `/stable/balance-sheet` | 资产负债表 → `[]` |
| `/stable/cash-flow` | 现金流量表 → `[]` |
| `/stable/analyst-estimates` | 分析师预估 → 空 JSON |
| `/stable/rating` / `/stable/grade` | 综合评分 → `[]` |
| `/stable/price-target` | 目标价 → `[]` |
| `/stable/ownership-institutional` | 机构持仓 → `[]` |
| `/stable/insider-trading` | 内部交易 → `[]` |
| `/stable/sp500-constituents` | S&P 500 成分股 → `[]` |
| `/stable/symbols-list` | 全量标的列表 → `[]` |
| `/stable/search` | 搜索 → 空返回 |
| `/stable/peers` | 同业对比 → `[]` |

**重要限制：**
- 免费版**不支持批量查询**（多 symbol 用逗号分隔返回空）
- 所有 ETF 相关端点空返回
- 分析类端点（评级/目标价/机构）全部不可用

---

### 3.3 yfinance

项目已在使用，基于 Yahoo Finance 非官方 API。

**项目中有用的新字段：**

| 字段 | 说明 |
|------|------|
| `Ticker.info["annualReportExpenseRatio"]` | ETF 管理费率（如 SPY=0.0945%） |
| `Ticker.info["category"]` | ETF 分类 |
| `Ticker.info["fundFamily"]` | 基金公司 |
| `Ticker.info["fundInceptionDate"]` | 成立日期 |
| `Ticker.info["totalAssets"]` | 管理规模 AUM |
| `Ticker.info["yield"]` | 分红收益率 |
| `Ticker.info["holdingsCount"]` | 持仓数量（无明细） |

**限制：**
- 没有详细的持仓权重列表
- API 非官方，字段名可能随 Yahoo 前端变动
- 获取 ETF 费率顺手可得，不用额外 API key

---

## 4. 综合对比矩阵

| 能力 | Finnhub 免费 | FMP 免费 | yfinance |
|------|:--:|:--:|:--:|
| 实时报价 | ✅ | ✅ | ✅ |
| 日线 K 线（OHLCV） | ❌ | ❌ | ✅ |
| 公司档案/行业 | ✅ | ✅ | ✅ |
| 利润表 | ❌ | ✅ | ❌ |
| 资产负债表 | ❌ | ❌ | ❌ |
| 现金流量表 | ❌ | ❌ | ❌ |
| 增长率（YoY） | ❌ | ✅ | ❌ |
| 分红历史 | ❌ | ❌ | ✅ |
| 拆股历史 | ❌ | ❌ | ✅ |
| 内部交易 | ✅ | ❌ | ❌ |
| 公司新闻 | ✅ | ❌ | ❌ |
| 综合市场新闻 | ✅ | ❌ | ❌ |
| 分析师评级汇总 | ✅ | ❌ | ❌ |
| 盈利惊喜 | ✅ | ❌ | ❌ |
| 财报日历 | ✅ | ❌ | ❌ |
| 可比公司 | ✅ | ❌ | ❌ |
| 市场开盘状态 | ✅ | ❌ | ❌ |
| FDA 日历 | ✅ | ❌ | ❌ |
| ETF 费率 | ❌ | ❌ | ✅* |
| **ETF 持仓权重** | ❌ | ❌ | ❌ |
| ETF 行业/国家分布 | ❌ | ❌ | ❌ |
| 机构持仓 | ❌ | ❌ | ❌ |
| 技术形态扫描 | ❌ | ❌ | ❌ |

> \* yfinance ETF 费率字段：`info["annualReportExpenseRatio"]`

---

## 5. ETF 持仓数据的替代方案

三家免费 API 都拿不到 ETF 持仓权重。以下是可行替代：

### 方案 A：ETF 发行人官网（推荐，免费）

主流 ETF 发行人直接在官网提供持仓 CSV：

| 发行人 | 持仓下载地址 |
|--------|------------|
| **SPDR** (SPY) | `https://www.ssga.com/us/en/intermediary/etfs/spdr-sp-500-etf-trust-spy` → Holdings → Download |
| **iShares** (IVV/IWM) | `https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf` → Holdings → Export |
| **Vanguard** (VOO/VTI) | `https://investor.vanguard.com/investment-products/etfs/profile/voo#portfolio-composition` |

优点：数据最权威、免费、有 CSV 格式  
缺点：每个发行人格式不同，需要逐个适配解析器

### 方案 B：FMP 付费版

`$19/月 (Starter)` 起，ETF holdings + info + sector/country weightings 全有。

### 方案 C：SSGA/iShares 的 JSON API

部分发行人有关联的 JSON endpoint（前端用的），可以 F12 抓取。比 HTML 稳定，但不是公开 API。

---

## 6. 建议策略

### 当前项目就用 yfinance

```
ETF 费率 → yfinance.Ticker.info["annualReportExpenseRatio"]（零成本）
```

### 如果需要 ETF 持仓明细

优先用 **方案 A**（ETF 发行人官网抓 CSV），因为持仓数据不需要实时更新（通常一个季度才变一次），写个定时脚本即可。

只覆盖 `core_us_etf` 里的 8 个标的的话，写 3 个发行人的 parser（SSGA/Vanguard/iShares）就能全搞定。

### 如果未来需要基本面筛选

- **利润表/增长率** → FMP 免费版（够用）
- **新闻/分析师/内部交易** → Finnhub 免费版（覆盖面最全）
- **K 线/分红/拆股** → yfinance（已有）

---

## 7. API Keys

> ⚠️ 以下 key 为免费版，已记录于 2026-06-16。

| 服务 | Key | 免费限制 |
|------|-----|---------|
| Finnhub | `d8oebu9r01qrbffl3ergd8oebu9r01qrbffl3es0` | 60 req/min |
| FMP | `TsMs6WXwVdLzmvXGAzRXEaOIZAkgSN6i` | 250 req/day |
