# 历年涨跌幅

Web3PanelV2 独立摘出的历年涨跌幅功能。支持美股、数字货币、A 股的历年收益和月度涨跌幅查询。

## 启动

```bash
chmod +x start.sh
./start.sh
```

首次运行会自动创建虚拟环境并安装依赖。

访问 http://127.0.0.1:8730

## 功能

- **历年汇总** — 查看各代码历年涨跌幅热力图
- **指定年份** — 查看某年各月涨跌幅（支持输入任意年份）
- **预设组合** — 一键加载常用代码组
- **回测** — 模拟给定起始年份的复利增长
- **着色范围** — 自定义热力图颜色映射区间
- **数据源**
  - 美股: Yahoo Finance
  - 数字货币: Binance → OKX → CoinGecko (自动 fallback)
  - A 股: East Money

## 配置

服务端口通过环境变量 `PORT` 配置（默认 8730）：

```bash
PORT=8080 ./start.sh
```

## 技术栈

- **后端**: Python 3 + Flask
- **前端**: 原生 HTML + CSS + JS（Apple 设计风格）
- **数据**: requests + yfinance（可选）
