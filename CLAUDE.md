# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## ⚠️ 最高优先级注意事项

### 1. 新增功能必须写测试用例

每次新增功能或修改核心逻辑时，**必须编写对应的测试用例**。

- **后端测试**：使用 pytest，覆盖接口、数据处理、缓存逻辑
- **前端测试**：如涉及关键交互逻辑（如热力图布局算法、数据计算），需提供测试说明或示例验证步骤
- **如果确实无法编写测试**：必须明确说明原因（如临时脚本、纯 UI 调整、外部依赖不可测等）

测试是保证系统稳定性的基石，避免改动引入回归问题。

### 2. 新增路由必须检查 vercel.json

每次在 `backend/app.py` 或 `backend/routes/` 中新增路由路径时，**必须同步检查 `vercel.json` 的 `rewrites`**：

- 新增页面路径 → 添加 rewrite 规则，destination 指向 `/api/index`
- 新增子路径参数 → 在已有正则中补充
- **遗漏会导致 Vercel 上 404**，本地开发不受影响因此容易被忽略

检查清单：
1. 确认新增路由路径
2. 打开 `vercel.json`，在 `rewrites` 数组中添加或更新规则
3. 本地测试通过后，再次确认 `vercel.json` 已同步更新

### 3. 改动页面内容必须同步更新 SEO lastmod 日期

`sitemap.xml` 和文章 JSON-LD 的日期是**固定常量**（故意不取 `datetime.now()`——Google 会降低"永远今天"的 sitemap 的信任度）。当**真正改动**页面 HTML/内容时，必须手动更新对应日期，否则 lastmod 会失真：

- 首页改版 → 更新 `app.py` 的 `INDEX_LASTMOD`
- ETF 市场页改版 → 更新 `app.py` 的 `ETF_MARKET_LASTMOD`
- 单篇知识文章内容改动 → 更新 `KNOWLEDGE_ARTICLES` 中该文章的 `updated` 字段（`published` 仅在首次发布时设）

检查清单：
1. 确认本次改动是否影响某个页面的可见内容/HTML 结构
2. 若是，找到对应的 lastmod 常量/字段并更新为当天日期
3. 仅改后端逻辑/缓存/测试、不影响页面渲染的改动**无需**更新 lastmod
4. 对应测试见 `backend/tests/routes/test_seo.py`，会校验 lastmod 来自固定常量集

---

## 项目概述

GlobalAssetHistory 是一个独立的资产历史收益分析工具。

- 后端：Python 3 + Flask
- 前端：原生 HTML / CSS / JS 单页面
- 图表：原生 SVG
- 数据源：美股（Yahoo Finance）、数字货币（Binance → OKX → CoinGecko）、A 股指数（East Money）

核心功能：

- 年 → 月 → 日三级钻取
- 基于日线的单资产回测（一次性 / 按日 / 按周 / 按月策略）

## 核心架构

### 1. 日线数据是统一基础层

所有核心能力都建立在 `PriceSeries` 之上：

- `yearly` / `monthly` / `daily` / `backtest`
- 统一入口：`_fetch_daily_series_cached(symbol, asset_type)`
- 缓存策略：成功 6 小时 / 失败 5 分钟

### 2. 三层缓存架构

- **L1 进程内存**：快但易失，过期立即删除
- **L2 Redis**：跨实例共享，扛冷启动（Upstash Redis REST）
- **L3 本地文件**：持久化兜底，写入时自动清理旧版本

### 3. Fetcher 注册表

`backend/service/price_change/fetchers.py`：

- `_FETCHERS`：旧式 yearly fetcher
- `_DAILY_SERIES_FETCHERS`：新版日线 fetcher（优先使用）

新增资产类型时优先接 daily-series fetcher。

### 4. Flask 蓝图架构

项目采用蓝图（Blueprint）模块化架构：

- **price_change_bp** (`/api/price-change`)：历史收益分析、定投回测、暴跌统计、VIX 对比、热力图
- **etf_market_bp** (`/api/etf-market`)：A 股 ETF 实时行情、估值分析、QDII 基金、历史数据
- **wishes_bp** (`/api/wishes`)：心愿墙系统、验证码、管理员功能

每个蓝图独立管理路由和缓存，互不干扰。

### 5. 前端静态托管

- 托管静态文件：`frontend/` 目录
- 路由规则：`/` → `price-change.html`、`/etf-market` → `etf-market.html`
- 前端使用相对路径请求 API（`API_BASE = ""`）

## 开发指南

### 命令速查

```bash
./start.sh                          # 交互式启动
./start.sh start                    # 后台启动
PORT=8080 ./start.sh debug          # 指定端口前台启动
```

依赖安装：

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r requirements.txt
```

### 修改原则

1. **后端能力**：保持 `PriceSeries` 为唯一基础数据结构
2. **前端图表**：延续 SVG 手工渲染风格，不引入图表库
3. **无框架依赖**：前端使用 classic script，不引入 React/Vue

## 其他注意事项

### 缓存清理机制

- **进程内存**：过期立即 `del`，不保留任何过期数据
- **磁盘快照**：写入新文件前，用 `glob` 模式删除同标的所有旧版本
- **降级策略**：依赖 L2 Redis 和 L3 文件，不依赖过期的 L1 内存

### 启动脚本特性

- `start.sh` 会自动释放端口占用
- `backend/app.py` 使用 `debug=True`
- Flask reloader 会导致 `logs/server.pid` 与真实进程不一致

## 经验教训

### 参数校准

- 小参数差异会导致系统性误差（如仓位 1% 差异 → 估值偏 0.03%）
- 用大波动日数据反推参数，再回归验证

### 验证策略

- 单点验证 ≠ 系统验证，要在足够多数据点上验证
- 逐层检查中间值，不要过早下结论

### 缓存架构

- **缓存降级层级要清晰**：L1 → L2 → L3
- **过期即删除，不留后路**：不为"可能的降级"牺牲架构合理性
- **测试适配架构**：修改错误的测试，而非妥协正确的架构

### 并发优化

- 网络 IO 瓶颈用 `ThreadPoolExecutor` 并发
- 每个标的只写自己的 dict，避免竞态
- 单标的失败只记日志不拖垮整批

## 沟通偏好

- 与用户使用中文交流
- 代码注释保持英文

### Git 提交规则

- **禁止自作主张提交代码**：除非用户明确说"提交"、"commit"、"推送"等关键词
- 遵循 Conventional Commits：`feat:` / `fix:` / `refactor:` / `chore:` / `docs:` 等
- 结尾附加 `Co-Authored-By: Claude <noreply@anthropic.com>`
