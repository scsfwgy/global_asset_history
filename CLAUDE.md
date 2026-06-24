# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## 项目概述

GlobalAssetHistory 是一个独立的资产历史收益分析工具。

- 后端：Python 3 + Flask
- 前端：原生 HTML / CSS / JS 单页面
- 图表：原生 SVG
- 数据源：
  - 美股：Yahoo Finance / yfinance fallback
  - 数字货币：Binance → OKX → CoinGecko
  - A 股指数：East Money

当前不仅支持历年涨跌幅，还支持：

- 年 → 月 → 日三级钻取
- 基于日线的单资产回测
- 一次性 / 按日 / 按周 / 按月策略

## 命令速查

```bash
./start.sh
./start.sh start
./start.sh debug
./start.sh stop
./start.sh restart
./start.sh status
```

端口：

```bash
PORT=8080 ./start.sh debug
```

依赖安装：

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r requirements.txt
```

## 启动脚本注意事项

`start.sh` 在启动前会尝试释放端口占用。

但要注意：

- `backend/app.py` 仍然是 `debug=True`
- 即使通过 `./start.sh start` 后台启动，也会触发 Flask reloader
- 因此 `logs/server.pid` 与真实监听进程有时会不一致
- `status` 可能提示 “PID 文件残留”

如果要修生产稳定性，优先改这里。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | `8730` | Flask 服务端口 |
| `HOST` | `0.0.0.0` | Flask 监听地址 |
| `UPSTASH_REDIS_REST_URL` | 无 | 共享缓存（Upstash Redis REST）地址，未配置则降级为进程内缓存 |
| `UPSTASH_REDIS_REST_TOKEN` | 无 | Upstash Redis REST token |
| `KV_REST_API_URL` | 无 | Vercel KV 地址（与 Upstash 命名二选一，自动识别） |
| `KV_REST_API_TOKEN` | 无 | Vercel KV token |

### 共享缓存（Upstash Redis）

`backend/service/price_change/cache_store.py` 是一个无新依赖（仅用 `requests`）的
Upstash REST 客户端，作为两级缓存的 L2：

- L1 = 进程内 dict（热实例快，但 Serverless 冷启动被清空、多实例不共享）
- L2 = 共享 Redis（跨实例、扛冷启动）

接入后每个标的在 TTL（成功 6h / 错误 5min）内**全局最多向上游拉一次**，是
Serverless 高并发下避免公共数据源限频的关键。访问计数器同样优先走 Redis 原子
`INCR`。**未配置环境变量时全部优雅降级**，本地开发行为不变。

Vercel 上接入：Marketplace → Upstash → 建 Redis → 连接到项目（自动注入上述
环境变量）→ 重新部署，无需改代码。


## 修改建议

1. 改后端能力时，优先保持 `PriceSeries` 为唯一基础数据结构。
2. 改前端图表时，优先延续当前 SVG 手工渲染风格，不要引图表库。
3. 回测若继续增强，建议按这个顺序：
   - 手续费 / 滑点
   - 多资产组合
   - 权重与再平衡
   - 最大回撤 / 波动率 / IRR
4. 如果改 `start.sh`，要一起考虑：
   - 端口释放
   - reloader
   - PID 管理

## 注意事项

### 新增路由必须检查 vercel.json

每次在 `backend/app.py` 或 `backend/routes/` 中新增路由路径时，必须同步检查 `vercel.json` 的 `rewrites` 是否需要对应配置：

- 新增页面路径（如 `/etf-market`、`/robots.txt`）→ 需要在 `vercel.json` 中添加 rewrite 规则，destination 指向 `/api/index`
- 新增子路径参数（如 `/knowledge/:sub` 的 `terms`）→ 需要在已有正则中补充
- 遗漏会导致 Vercel 上该路径返回 404，本地开发不受影响因此容易被忽略

### 旧版路由兼容（vercel.json 历史）

早期 rewrite destination 为 `/price-change.html`（静态文件直出）。SEO 优化后统一改为 `/api/index`，由 Flask 后端注入动态站点 URL。

## 经验教训

### 参数校准

- 仓位 95% → 96% 的 1% 差异，导致估值误差系统性偏 0.03%
- 用参考方大波动日数据（|指数|≥1%，噪声小）反推参数，再回归验证，不要凭经验猜

### 验证脚本日期对齐

- 写验证代码前先画清楚数据流向图（哪个日期的净值配哪个日期的指数收益）
- NAV 日期是 T-1（QDII ETF 净值 T+1 发布），映射错一天就会产生离谱结果

### 验证策略

- 不要过早下结论：单点验证不等于系统验证，要在足够多数据点上验证
- 逐层检查中间值：NAV 日期映射 → 基准指数收益 → 仓位参数 → 最终结果
- 最小残差不可消除原因：指数显示精度（2 位小数 vs 全精度）、USD/CNY 汇率波动（±0.05%/天）

### 并发优化

- 瓶颈在网络 IO 时，用 `ThreadPoolExecutor` 并发把"累加"变"取最大"
- 每个标的只写自己的 dict 互不交叉；共享资源预热提到线程启动前避免竞态
- 单标的失败只记日志不拖垮整批
- 实测：冷缓存 5 标的 ~6.3s → 2.8s，热缓存 0.41s

### 缓存泄漏排查与修复（2026-06-24）

#### 问题定位

1. **系统性排查，不要遗漏**：用 `grep` 全局搜索所有 `_cache`/`_CACHE` dict 变量，逐个检查清理逻辑
2. **区分内存泄漏和磁盘堆积**：进程内存 dict 和磁盘快照文件是两个独立问题，需要分别修复
3. **测试先行**：修复前先写测试验证问题存在，修复后用测试验证修复有效

#### 架构设计原则

1. **缓存降级层级要清晰**：L1 进程内存（快但易失）→ L2 Redis（跨实例共享）→ L3 本地文件（持久化兜底）
2. **过期即删除，不留后路**：进程内存过期数据应立即删除，降级应依赖 L2/L3，而非保留过期的 L1 数据
3. **不要为了"可能的降级"牺牲架构合理性**：过期数据占内存是不可接受的设计缺陷

#### 修复策略

1. **进程内存缓存**：检测到过期立即 `del`，不保留任何过期数据
2. **磁盘快照文件**：写入新文件前，用 `glob` 模式删除同标的所有旧版本
3. **测试适配**：修改测试用例适应正确的架构设计，而非妥协架构去适应错误的测试

#### 测试与验证

1. **测试失败是信号**：测试失败时，先分析是修复逻辑错误，还是测试本身的设计问题
2. **不要盲目保守**：当测试期望"保留过期内存数据作为降级"时，应该修改测试，而非削弱清理逻辑
3. **全量测试验证**：修复后运行全部测试，确保没有破坏其他功能

#### 清理历史数据

1. **自动清理只作用于新数据**：修复代码部署后，只有新写入的数据才会触发清理
2. **历史数据需要一次性清理**：旧文件需要单独脚本清理，或等待自然过期后重新拉取
3. **验证清理逻辑**：手动触发一次写入，验证旧文件确实被删除

#### 最终成果

- 修复 10 处进程内存缓存泄漏（日线数据、市值、频率限制、ETF 历史、跟踪误差、NAV、QDII、热力图）
- 修复 2 处磁盘文件堆积（ETF NAV 快照、ETF 历史快照）
- 磁盘文件从 94 个减少到 20 个（78% 减少）
- 所有 187 个测试通过
- 缓存系统不再无限增长

## 沟通偏好

- 与用户使用中文交流
- 代码注释保持英文

### Git 提交规则

- **禁止自作主张提交代码**：除非用户明确说"提交"、"commit"、"推送"等关键词，否则禁止执行 `git commit` / `git add` + `git commit`
- 即使调用 `/git-common-flow` 技能，也必须严格遵循用户的参数（如「不推送到远端」）
