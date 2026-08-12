# 第三方数据与内容 / Third-party Data and Content

## 许可范围 / License scope

仓库的 [Apache License 2.0](LICENSE) 适用于项目贡献者原创的软件代码和文档。它不授予任何第三方名称、商标、API、行情、基金数据、文章、图片或其他内容的权利，也不会改变这些材料原有的许可或使用条款。

The repository's [Apache License 2.0](LICENSE) covers original software and documentation contributed to this project. It does not grant rights to third-party names, trademarks, APIs, quotes, fund data, articles, images, or other content, and it does not replace their original licenses or terms.

## 当前数据来源 / Current sources

项目会按功能和可用性使用以下公开网络来源：

| 数据类别 | 主要提供方 | 项目用途 |
| --- | --- | --- |
| 美股、港股、全球股票、外汇 | Yahoo Finance | 日线、公司事件、估值和历史研究 |
| 数字货币 | Binance、OKX、CoinGecko | 日线行情与降级数据源 |
| A 股、场内 ETF、QDII | East Money、Tencent Finance | 行情、净值、基金资料和定期报告 |
| 参考汇率 | Frankfurter / European Central Bank reference rates | 多币种参考换算 |
| 基金和证券披露 | 发行人、交易所及监管机构网站 | 费率、持仓、上市信息和公开披露核验 |

具体接口与回退顺序以代码和 `backend/config/price_change_config.json` 为准。第三方接口可能随时改变、限流或停止服务；项目不代表、隶属于或获得上述提供方背书。

Exact endpoints and fallback order are defined by the code and `backend/config/price_change_config.json`. Third-party services may change, throttle, or disappear without notice. This project is not affiliated with or endorsed by those providers.

## 快照、缓存与再分发 / Snapshots, caching, and redistribution

`backend/data/` 中的行情、净值和基金快照用于可用性降级、解析验证和可复现测试。快照中的事实数据仍可能受其来源方的条款、数据库权利或当地法律约束。下游使用者应自行确认其场景是否允许下载、缓存、展示和再分发，不应将 Apache-2.0 误解为第三方数据许可。

项目只应提交运行和回归测试所必需的最小数据；新增 fixture 必须脱敏并尽量缩减。不得提交付费数据、绕过访问控制获取的数据、API Token、Cookie 或个人信息。如权利方认为仓库包含不应再分发的内容，请通过 [安全报告渠道](SECURITY.md) 联系维护者并提供具体路径与权利依据。

Files under `backend/data/` support fallback availability, parser verification, and reproducible tests. Factual data in those snapshots may remain subject to provider terms, database rights, or local law. Downstream users are responsible for confirming that their use permits downloading, caching, display, and redistribution. Apache-2.0 must not be interpreted as a license to third-party data.
