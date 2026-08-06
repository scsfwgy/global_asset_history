# Graph Report - GlobalAssetHistory  (2026-08-05)

## Corpus Check
- 126 files · ~499,773 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2165 nodes · 4197 edges · 132 communities (117 shown, 15 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 196 edges (avg confidence: 0.73)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `f451b90e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- _to_timestamp
- heatmap.js
- _etf_symbols_by_group
- price-detail.js
- price_change.py
- Main Price Change Page — historical returns & backtest UI
- date
- TestEtfEstDate
- fetch_heatmap_data
- price-change.js
- backtest.js
- test_fundamentals_history.py
- TestEventTracking
- wishes.py
- fundamentals_history.py
- computation/conftest.py
- etf-market.js
- qdii-funds.js
- vix-chart.js
- TestBuildEquityCurve
- app.py
- System Health Dashboard Page
- stock-compare.js
- fetchers.py
- cache_store.py
- TestBuildHeatmapToday
- date
- patch
- TestFetchStockComparison
- fetch_return_detail
- TestHtmlMeta
- TestCache
- track_coverage
- normalize_asset_symbol
- diagnostics.py
- history
- PriceSeries
- TestHeaderTrendEndpoint
- start.sh
- init
- etf_market.py
- qdii_funds
- test_intraday_fetchers.py
- test_price_change.py
- TestDailyEndpoint
- TestRunCrashStats
- TestComputeYearlyReturns
- patch
- TestVixComparisonEndpoint
- ._series
- route
- _read_etf_history_cache
- visitor_stats.py
- data-download.js
- wishes.js
- etf_market
- _fetch_qdii_fund_info
- price_change_service.py
- captcha.py
- exchange-loss.js
- test_etf_market_qdii.py
- .test_cross_month_prev_close
- TestFetchMonthlyReturns
- ._isolate_fetcher_state
- _record_unique_visit
- TestFundamentalsHistoryEndpoint
- .test_valid_frequencies
- TestReturnDetailEndpoint
- TestComputeMonthlyReturns
- TestMonthlyEndpoint
- config.py
- Monthly Return Breakdown Feature
- fetchData
- TestYahooQuoteBatch
- TestExchangeLossEndpoint
- test_visitor_stats.py
- header-trend.js
- vercel.json
- _fetch_all_qdii_fund_groups
- _cn_secid
- TestYearlyEndpoint
- TestBacktestEndpoint
- _enrich_detail_fundamentals_from_series
- search_asset_symbols
- TestFetchDailyReturns
- stats_dashboard
- feature-updates.js
- ThreadLocalSession
- test_symbol_persistence.py
- TestGetCrashChartData
- Multi-Asset Yearly Total Returns (% per calendar year)
- Bitget Stock Trading Fee Schedule
- Yearly Heatmap / Treemap Visualization
- capture_screenshots.py
- TestFetchHeatmapToday
- binance_base_url
- qdii_fund_holdings
- routes/conftest.py
- TestMonthlyBatchEndpoint
- Monthly Trend Analysis Page Screenshot
- Backtest tab rendering in price-change.html: HTML structure for the backtest parameter form, results display area, SVG chart container, and stat/metric card layout. The screenshot is a rendering of this tab.
- TestHistoryDownloadEndpoint
- test_feature_updates.py
- Backtest Detail View
- charts.js
- drilldown.js
- i18n.js
- renderTable
- history.js
- scrape_fund_profile
- routes/test_operational_logging.py
- TestFetcherRegistration
- test_delivery_workflow.py
- Yearly Heatmap Visualization — SVG-based color-coded grid displaying annual percentage returns for multiple global asset classes (equities, bonds, commodities, crypto) across multiple years, with color intensity proportional to return magnitude
- S&P 500 Annual Returns Visualization
- AGENTS.md — delegates to CLAUDE.md
- Conventional Commits format
- wishes_bp — /api/wishes Blueprint
- Content & Interaction — articles, wish wall, stats
- Project Directory Structure
- test_qdii_holdings_ui.py
- add_seo_headers
- Flask-Cors 5.0.0 — CORS support
- TestDetailFundamentals
- TestRunFearThresholdStats

## God Nodes (most connected - your core abstractions)
1. `track_coverage()` - 213 edges
2. `PriceSeries` - 92 edges
3. `diagnose()` - 63 edges
4. `_to_timestamp()` - 43 edges
5. `_trading_dates()` - 32 edges
6. `normalize_asset_symbol()` - 26 edges
7. `empty_series()` - 25 edges
8. `fetch_return_detail()` - 25 edges
9. `TestHtmlMeta` - 25 edges
10. `_compute_yearly_returns()` - 24 edges

## Surprising Connections (you probably didn't know these)
- `Landing Page — pure static HTML, no JS dependencies` --semantically_similar_to--> `No React/Vue/Build Tools — Classic JS Only`  [INFERRED] [semantically similar]
  frontend/landing.html → CLAUDE.md
- `ETF Quote Table — sortable columns for price, fees, premium, tracking error` --semantically_similar_to--> `Native SVG Charts — no charting library`  [INFERRED] [semantically similar]
  frontend/etf-market.html → CLAUDE.md
- `price_change_bp — /api/price-change Blueprint` --conceptually_related_to--> `Main Price Change Page — historical returns & backtest UI`  [INFERRED]
  CLAUDE.md → frontend/price-change.html
- `etf_market_bp — /api/etf-market Blueprint` --conceptually_related_to--> `ETF Market Page — real-time A-share ETF quotes`  [INFERRED]
  CLAUDE.md → frontend/etf-market.html
- `QDII Fund Tracking — NAV, returns, fees, purchase limits` --conceptually_related_to--> `ETF Market Page — real-time A-share ETF quotes`  [INFERRED]
  README.md → frontend/etf-market.html

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Three-Tier Cache Architecture (L1 Memory → L2 Redis → L3 JSON)** — CLAUDE_l1_memory_cache, CLAUDE_l2_upstash_redis_cache, CLAUDE_l3_json_snapshot_cache, CLAUDE_multilevel_cache [EXTRACTED 1.00]
- **Free Financial API Survey — Three Vendors Evaluated for ETF Data Coverage** — doc_free_financial_api_survey_finnhub, doc_free_financial_api_survey_fmp, doc_free_financial_api_survey_yfinance, doc_free_financial_api_survey_etf_holdings_gap, doc_free_financial_api_survey_comparison_matrix [EXTRACTED 1.00]
- **Flask Application Blueprint Architecture** — CLAUDE_price_change_bp, CLAUDE_etf_market_bp, CLAUDE_wishes_bp, CLAUDE_backend_app_py, CLAUDE_api_index_py [EXTRACTED 1.00]

## Communities (132 total, 15 thin omitted)

### Community 0 - "_to_timestamp"
Cohesion: 0.04
Nodes (61): _build_period_windows(), compute_crash_statistics(), date, Crash detection and recovery analysis using period close returns., Return non-overlapping (candle-start, candle-end) point indices., Find crash events and their recovery metrics. Daily, N-trading-day, weekly, and…, A full month of trading days with rising prices., Only 1 year of data — needs at least 2 year-end closes. (+53 more)

### Community 1 - "heatmap.js"
Cohesion: 0.07
Nodes (53): fetchHeatmap(), fetchMarketPulse(), hasMarketCapData(), hmColor(), hmEmpty, hmError, hmFilterPanel, hmFilterToggle (+45 more)

### Community 2 - "_etf_symbols_by_group"
Cohesion: 0.11
Nodes (16): _etf_symbols_by_group(), _load_fee_codes(), parametrize, Guard tests for the A-share ETF preset groups. These tests lock down two things…, 159652 (commodities theme) must NOT be in sp500., Sector themes and non-NDX/SPX broad indices belong in 'others'., Return {group_key: [symbol, ...]} from the config presets., Every configured ETF code must have fee data, and no orphan fees. (+8 more)

### Community 3 - "price-detail.js"
Cohesion: 0.11
Nodes (51): attachBarChartTooltips(), attachFundamentalsHistoryTooltips(), barChartPoints(), buildAssetResourceLinks(), buildYearSelector(), cellColor(), chartDetailText(), escapeHtml() (+43 more)

### Community 4 - "price_change.py"
Cohesion: 0.07
Nodes (42): backtest(), crash_chart(), crash_stats(), exchange_loss(), fear_threshold_stats(), _get_cached_heatmap(), _get_cached_market_pulse(), get_fundamentals_history() (+34 more)

### Community 5 - "Main Price Change Page — historical returns & backtest UI"
Cohesion: 0.05
Nodes (48): DAILY_SERIES_FETCHERS registry, etf_market_bp — /api/etf-market Blueprint, i18n — zh-CN and en locales, Knowledge Article SEO Addition Checklist, Native SVG Charts — no charting library, No React/Vue/Build Tools — Classic JS Only, price_change_bp — /api/price-change Blueprint, PriceSeries — unified daily price data structure (+40 more)

### Community 6 - "date"
Cohesion: 0.04
Nodes (55): _build_equity_curve(), _compute_daily_returns_for_month(), _compute_money_weighted_annualized_return(), _compute_monthly_returns(), _generate_schedule_dates(), _next_month_anchor(), _normalize_frequency(), date (+47 more)

### Community 8 - "fetch_heatmap_data"
Cohesion: 0.12
Nodes (20): _asset_currency(), _build_heatmap_today(), fetch_heatmap_data(), _fetch_heatmap_watchlist(), _heatmap_currency(), _heatmap_stock_meta(), _market_pulse_yahoo_quotes(), _period_label() (+12 more)

### Community 9 - "price-change.js"
Cohesion: 0.05
Nodes (41): addBtn, btAmount, btAnimSeconds, btBody, btDayOfMonth, btDayOfMonthLabel, btEndDate, btFrequency (+33 more)

### Community 10 - "backtest.js"
Cohesion: 0.10
Nodes (37): backtestCurrencyForType(), _btCashflows, _btEquityByDate, formatBtAxisMoney(), formatBtMoney(), formatBtNumber(), getBacktestAnimMs(), getBacktestSampleSize() (+29 more)

### Community 11 - "test_fundamentals_history.py"
Cohesion: 0.07
Nodes (36): object, Tests for US-stock valuation and profitability history., Dropping negative ROE would hide the companies where the metric matters most., A wrong field dispatch or sign filter must not corrupt PE/PB history., Duplicate revised rows must produce one deterministic chart point., The source adapter must request both historical and latest PE/PB fields., An expired Yahoo crumb should be refreshed before degrading the source., Yahoo's fundamentals endpoint requires a session cookie and crumb pair. (+28 more)

### Community 12 - "TestEventTracking"
Cohesion: 0.06
Nodes (10): fixture, parametrize, Tests for visit counter, event tracking, and admin stats dashboard., GET /api/visits and POST /api/visits/increment, GET /api/stats — admin-only HTML dashboard, POST /api/track for tab_view, ad_click, settings_click, settings_action, TestAdminStatsDashboard, TestEventTracking (+2 more)

### Community 13 - "wishes.py"
Cohesion: 0.10
Nodes (33): _client_ip(), get_captcha(), get_wishes(), post_wish(), route, Wish wall API blueprint — anonymous wishes with CAPTCHA + rate limiting., Admin-only delete. Requires header X-Admin-Token., Best-effort client IP. On Vercel the real IP is the first entry of X-Forwarded-… (+25 more)

### Community 14 - "fundamentals_history.py"
Cohesion: 0.12
Nodes (31): _cache_key(), _cached_payload(), clear_fundamentals_history_cache(), _clear_yahoo_crumb(), _fetch_and_store_fundamentals_history(), _fetch_eastmoney_roe_history(), fetch_fundamentals_history(), _fetch_yahoo_valuation_history() (+23 more)

### Community 15 - "computation/conftest.py"
Cohesion: 0.12
Nodes (23): crash_closes(), crash_data(), crash_ts(), daily_3year(), daily_3year_closes(), daily_3year_ts(), date, fixture (+15 more)

### Community 16 - "etf-market.js"
Cohesion: 0.17
Nodes (30): activeChartType(), addXAxis(), aggregateCacheKey(), appendHistoryStats(), attachAggregateHover(), buildChartBody(), buildRow(), currentAggregateSymbols() (+22 more)

### Community 17 - "qdii-funds.js"
Cohesion: 0.14
Nodes (36): baseRowsForActiveIndex(), cacheStatusLabel(), clearFiltersAndSort(), compareRows(), escapeHtml(), fmtHoldingPct(), fmtMoney(), fmtPct() (+28 more)

### Community 18 - "vix-chart.js"
Cohesion: 0.15
Nodes (31): attachVixInteractions(), fearForwardCell(), fetchFearThresholdStats(), fetchLatestVix(), fetchVixData(), formatDateLabel(), formatFearPercent(), getVixColors() (+23 more)

### Community 19 - "TestBuildEquityCurve"
Cohesion: 0.16
Nodes (8): Equity curve construction from price points and executions., Build executed_points in the format expected by _build_equity_curve. Format:…, 12 monthly executions, 24 months of price data., Initial lump sum, no recurring executions., initial_price=0 should not cause div-by-zero (units not computed)., Neither executions nor initial investment → flat zero curve., After all executions, value should continue tracking price changes., TestBuildEquityCurve

### Community 20 - "app.py"
Cohesion: 0.13
Nodes (25): Vercel serverless entry point — wraps the existing Flask app., _base_request_path(), _canonical_content_path(), _frontend_asset_version(), frontend_files(), index(), index_lang(), _is_indexable_content_path() (+17 more)

### Community 21 - "System Health Dashboard Page"
Cohesion: 0.08
Nodes (27): api/index.py — Vercel Serverless entry point, backend/app.py — Flask app entry, SEO, health, stats, Data Source Fallback Chain, Product Delivery Gate — test→start→verify→logs closed loop, Expired L1 Cache Deletion Policy, L1 Process Memory Cache, L2 Upstash Redis / Vercel KV Cache, L3 JSON Snapshot Disk Cache (+19 more)

### Community 22 - "stock-compare.js"
Cohesion: 0.22
Nodes (25): activate(), addSymbol(), cellColor(), clearSymbols(), escapeHtml(), formatPct(), getTaxRate(), highlightSuggestion() (+17 more)

### Community 23 - "fetchers.py"
Cohesion: 0.07
Nodes (36): _compute_yearly_returns(), Compute yearly returns using YoY change on year-end close prices. For each…, _cn_tencent_symbol(), _fetch_cn_stock(), _fetch_crypto(), _fetch_crypto_okx(), _fetch_daily_closes_cn_stock(), _fetch_daily_series_crypto() (+28 more)

### Community 24 - "cache_store.py"
Cohesion: 0.14
Nodes (23): cache_del(), cache_expire(), cache_get(), cache_hgetall(), cache_hincrby(), cache_incr(), cache_lpush(), cache_lrange() (+15 more)

### Community 25 - "TestBuildHeatmapToday"
Cohesion: 0.10
Nodes (10): Tests for _build_heatmap_today — today fast-path orchestrator., Stub matching _compute_one signature for non-stock entries., All entries are stocks → batch used, no fallback., Batch returns empty for non-empty stocks → return None., include_market_cap=False → market_cap absent from results., Stocks via batch, crypto via compute_fn., No entries → empty data, batch never called., Stock not in batch response → None values, no crash. (+2 more)

### Community 26 - "date"
Cohesion: 0.15
Nodes (20): _build_detail_overview(), _build_stock_history_tables(), _compute_yearly_dividends(), _compute_yearly_drawdowns(), _compute_yearly_runups(), _date_years_before(), _detail_annualized_volatility(), _detail_drawdown_summary() (+12 more)

### Community 27 - "patch"
Cohesion: 0.11
Nodes (9): patch, POST /api/price-change/heatmap cross-instance cache behavior., GET /api/price-change/market-pulse, POST /api/price-change/crash-chart, POST /api/price-change/fear-threshold-stats, TestCrashChartEndpoint, TestFearThresholdStatsEndpoint, TestHeatmapSharedCache (+1 more)

### Community 28 - "TestFetchStockComparison"
Cohesion: 0.13
Nodes (5): object, Company-name and symbol lookup for reusable autocomplete controls., Compact annual comparison data for multiple US stocks., TestFetchStockComparison, TestSearchAssetSymbols

### Community 29 - "fetch_return_detail"
Cohesion: 0.19
Nodes (16): _avg(), _build_detail_quality(), _build_monthly_stats(), _compute_daily_extremes(), _compute_daily_grid(), _compute_return_candles(), fetch_return_detail(), _median() (+8 more)

### Community 30 - "TestHtmlMeta"
Cohesion: 0.05
Nodes (15): client(), fixture, parametrize, Tests for SEO configuration: sitemap.xml, robots.txt, rendered meta tags, JSON-…, Canonical / robots / og:image on rendered pages., Flask test client with a fixed SITE_URL so absolute URLs are stable., og:image screenshots referenced by meta tags must exist under frontend/., GET /sitemap.xml — structure and real lastmod. (+7 more)

### Community 31 - "TestCache"
Cohesion: 0.12
Nodes (8): Two-layer caching (L1 in-memory, L2 Redis)., Uncached symbol should return None., Expired L1 entry should be treated as miss., clear_price_change_cache should empty L1., serialize → deserialize should be lossless., Corrupt serialized data should return None gracefully., When L1 misses but L2 has data, it should warm L1 and return., TestCache

### Community 32 - "track_coverage"
Cohesion: 0.04
Nodes (44): _parse_iso_date(), ISO date string parsing., Feb 30 doesn't exist., Error message should include the field name., TestParseIsoDate, Accessor functions for config values., Reset config cache before each test., The actual config file in the project should load successfully. (+36 more)

### Community 33 - "normalize_asset_symbol"
Cohesion: 0.11
Nodes (26): get_daily_returns(), get_monthly_returns(), header_trend(), history_download(), Return a downsampled full-history daily close series for the header background…, Return monthly returns for a symbol in a given year. Request body: {"symbol":…, Return daily returns for a symbol in a given year and month., Return date-bounded price history as a JSON collection. (+18 more)

### Community 34 - "diagnostics.py"
Cohesion: 0.18
Nodes (11): okx_base_url(), _collect(), _probe(), _probe_coingecko(), _probe_okx(), _probe_tencent(), Live reachability probes for the upstream market-data sources. Each probe makes…, Probe all sources, memoised for _MEMO_TTL seconds unless fresh=True. (+3 more)

### Community 35 - "history"
Cohesion: 0.13
Nodes (20): _etf_history_json_response(), _fetch_etf_est_date(), _fetch_etf_history_rows(), _fetch_live_premium(), history(), _load_fee_data(), _parse_tencent_quote(), route (+12 more)

### Community 36 - "PriceSeries"
Cohesion: 0.13
Nodes (28): empty_series(), PriceSeries, Shared models and low-level HTTP helpers for price change services., series_from_points(), _aggregate_intraday_hours(), _fetch_daily_series_cn_stock(), _fetch_daily_series_cn_stock_eastmoney(), _fetch_daily_series_cn_stock_tencent() (+20 more)

### Community 37 - "TestHeaderTrendEndpoint"
Cohesion: 0.15
Nodes (10): Build a fake PriceSeries-like object with n daily bars (ascending close)., GET /api/price-change/header-trend, Series smaller than target is returned whole (no padding)., No params → defaults: QQQ, target 240., Out-of-range points clamps to [60, 400] (no 400, just clamp)., None closes are dropped before downsampling., Fetcher returns errored series → 200 with empty points., Fetcher raises → 200 with empty points (decoration-only). (+2 more)

### Community 38 - "start.sh"
Cohesion: 0.30
Nodes (17): choose_mode(), interactive_menu(), kill_port_if_needed(), launch_production(), preflight(), restart_production(), run_test_suite(), run_tests() (+9 more)

### Community 39 - "init"
Cohesion: 0.15
Nodes (17): updateBacktestFrequencyUI(), addSymbol(), applySiteConfig(), displayName(), exportCSV(), init(), loadConfigFromServer(), loadPreset() (+9 more)

### Community 40 - "etf_market.py"
Cohesion: 0.12
Nodes (26): _benchmark_for_etf(), _clean_report_fund_name(), _compute_tracking_error_history(), _daily_return_map_from_rows(), _daily_return_map_from_series(), _extract_qdii_pdf_text(), _fetch_latest_qdii_report(), _fetch_qdii_holdings() (+18 more)

### Community 41 - "qdii_funds"
Cohesion: 0.15
Nodes (13): _filter_qdii_response(), qdii_funds(), _qdii_snapshot_age_seconds(), Return public East Money data for Nasdaq-100 / S&P 500 QDII funds. Query…, Return either the full QDII snapshot or a single-index view., Read the locally persisted QDII snapshot, if present and valid., Persist the latest successful QDII snapshot for offline/overseas fallback., Read the cross-instance QDII snapshot from Upstash/Vercel KV. (+5 more)

### Community 42 - "test_intraday_fetchers.py"
Cohesion: 0.24
Nodes (10): object, Unit tests for intraday market-data download fetchers., _response(), test_binance_intraday_parses_ohlcv(), test_eastmoney_a_share_uses_stock_exchange_mapping_and_handles_empty_data(), test_global_stock_daily_fetcher_reuses_yahoo_symbol(), test_hk_stock_daily_fetcher_reuses_yahoo_with_canonical_symbol(), test_hk_stock_symbol_normalization_accepts_common_code_variants() (+2 more)

### Community 43 - "test_price_change.py"
Cohesion: 0.15
Nodes (7): Tests for backend/routes/price_change.py — API endpoint integration tests. All…, GET /api/price-change/config, GET /api/price-change/symbol-search, POST /api/price-change/crash-stats, TestConfigEndpoint, TestCrashStatsEndpoint, TestSymbolSearchEndpoint

### Community 44 - "TestDailyEndpoint"
Cohesion: 0.25
Nodes (4): POST /api/price-change/daily, Missing required fields → 400., Non-integer year/month → 400., TestDailyEndpoint

### Community 45 - "TestRunCrashStats"
Cohesion: 0.12
Nodes (8): Crash statistics analysis., cn_stock (A-share) is a supported crash-stats asset type., Service builds non-overlapping N-day candles., Daily crash detection includes an overnight gap down., Gentle uptrend → no crashes., Various invalid inputs should raise ValueError., Error series → ValueError., TestRunCrashStats

### Community 46 - "TestComputeYearlyReturns"
Cohesion: 0.14
Nodes (8): Data in 2022 and 2024 but not 2023 — compute 2022→2024 directly., Year-over-year returns from year-end close prices., 3-year uptrend data should produce returns for years 2023 and 2024., Empty timestamps and closes should return {}., Year where prev_close == 0 should be skipped (no ZeroDivisionError)., Price going down should produce negative returns., None closes should be ignored; year-end is last valid close., TestComputeYearlyReturns

### Community 47 - "patch"
Cohesion: 0.14
Nodes (5): patch, Return-detail chart data uses compounded period returns., Fixed global benchmark strip., TestFetchReturnDetail, TestMarketPulse

### Community 48 - "TestVixComparisonEndpoint"
Cohesion: 0.17
Nodes (7): POST /api/price-change/vix-comparison This endpoint has inline data-fetching…, Non-existent period → 400., SPY/QQQ expose adjusted candles and both fear indexes are returned., No period specified → defaults to 'daily'., Count should be clamped to valid range., 1hour period should be accepted., TestVixComparisonEndpoint

### Community 49 - "._series"
Cohesion: 0.14
Nodes (4): Date filtering and OHLCV period aggregation for JSON downloads., The detail response carries a human-readable asset name., TestDetailAssetName, TestFetchPriceHistory

### Community 50 - "route"
Cohesion: 0.17
Nodes (13): diag(), health(), route, qqqm_holdings_csv(), Download the dated top-10 QQQM snapshot displayed on the landing page., Generate a machine-readable TQQQ daily price export., Live reachability of upstream data sources + Redis. Read-only; results are…, Record a tracking event. Fire-and-forget — always returns 200. (+5 more)

### Community 51 - "_read_etf_history_cache"
Cohesion: 0.14
Nodes (20): _cache_payload_age_seconds(), _copy_jsonable(), _fetch_etf_nav(), _fetch_etf_nav_cached(), _history_cache_key(), _history_snapshot_path(), _nav_snapshot_path(), Fetch ETF NAV history from East Money fund API. Returns {date_str: nav}. Uses… (+12 more)

### Community 52 - "visitor_stats.py"
Cohesion: 0.26
Nodes (12): _empty_data(), get_language_stats(), normalize_device_language(), normalize_site_language(), Cumulative anonymous language distributions for the admin dashboard., Record both independent language dimensions without failing a visit., Return exact cumulative unique-user counts for both dimensions., Return the canonical supported website language or an empty string. (+4 more)

### Community 53 - "data-download.js"
Cohesion: 0.30
Nodes (15): downloadJson(), enforceIntradayRange(), fetchData(), formValues(), init(), localIsoDate(), preview(), render() (+7 more)

### Community 54 - "wishes.js"
Cohesion: 0.46
Nodes (12): _clearWishMsg(), deleteWish(), _formatWishTime(), _getAdminToken(), _initWishAdmin(), loadCaptcha(), loadWishes(), _renderWishCard() (+4 more)

### Community 55 - "etf_market"
Cohesion: 0.24
Nodes (7): etf_market(), fixture, Tests for ETF market history cache behaviour., When upstream fails, fallback to local snapshot (not expired in-memory cache).…, reset_history_cache(), _sample_history_payload(), TestEtfHistoryCache

### Community 56 - "_fetch_qdii_fund_info"
Cohesion: 0.18
Nodes (12): _fetch_qdii_fund_info(), _fetch_qdii_period_increase(), _parse_fee_pct(), _parse_float(), _parse_qdii_limit(), Parse fee string like '0.60%' → 0.60. Returns None on failure., Parse East Money numeric fields, preserving None for blanks., Parse "单日投资上限100元" from East Money purchase status text. (+4 more)

### Community 57 - "price_change_service.py"
Cohesion: 0.12
Nodes (27): _build_stock_comparison_symbol(), _cache_ttl(), clear_price_change_cache(), _deserialize_series(), _fetch_one_yearly(), fetch_stock_comparison(), fetch_yearly_returns(), _get_cached_daily_series() (+19 more)

### Community 58 - "captcha.py"
Cohesion: 0.24
Nodes (11): generate(), _pop_answer(), _purge_expired(), Dependency-free SVG image CAPTCHA with one-time verification. Answers are…, Issue a new CAPTCHA. Returns (captcha_id, svg_string)., One-time, case-insensitive verification. Consumes the answer on any lookup so a…, Fetch and consume the stored answer (one-time use). Returns None if…, Render the code as a noisy, distorted SVG string. (+3 more)

### Community 59 - "exchange-loss.js"
Cohesion: 0.14
Nodes (38): attachFxInteractions(), buildDetailRows(), calcDates(), clearData(), computeBase(), fetchFxData(), flingStep(), fmtMoney() (+30 more)

### Community 60 - "test_etf_market_qdii.py"
Cohesion: 0.11
Nodes (9): fixture, Tests for QDII fund tracker route and data mapping., reset_qdii_memory_cache(), _sample_holdings(), _sample_payload(), TestQdiiFundInfoMapping, TestQdiiFundsRoute, TestQdiiHoldingsParsing (+1 more)

### Community 61 - ".test_cross_month_prev_close"
Cohesion: 0.25
Nodes (5): Daily returns within a specific month., Month not in data → empty list., Prev_close for March 1 should come from February's last trading day., None closes should not break prev_close chain., TestComputeDailyReturnsForMonth

### Community 62 - "TestFetchMonthlyReturns"
Cohesion: 0.25
Nodes (5): Monthly return computation for a single symbol., Year present in data → 12 months with computed returns., Unknown asset type → 12 None entries., Series with fetch error → 12 None entries., TestFetchMonthlyReturns

### Community 64 - "_record_unique_visit"
Cohesion: 0.25
Nodes (11): _cleanup_unique_visits(), _hash_anonymous_id(), _last_days(), Increment visit count and return new value., _read_unique_visits(), _record_unique_visit(), _unique_visit_key(), _unique_visit_series() (+3 more)

### Community 65 - "TestFundamentalsHistoryEndpoint"
Cohesion: 0.18
Nodes (5): parametrize, POST /api/price-change/fundamentals-history, POST /api/price-change/stock-compare, TestFundamentalsHistoryEndpoint, TestStockCompareEndpoint

### Community 66 - ".test_valid_frequencies"
Cohesion: 0.22
Nodes (7): parametrize, Frequency string normalization and validation., Valid inputs should normalize correctly; None/empty default to 'monthly'., Invalid frequency strings should raise ValueError., Safe integer conversion with fallback default., TestNormalizeFrequency, TestSafeInt

### Community 68 - "TestComputeMonthlyReturns"
Cohesion: 0.14
Nodes (8): Month-over-month returns for a specific year., All 12 months with data should produce 12 entries with computed returns., Months without data should have return=None., January's prev_close comes from December of previous year., All closes are None → all 12 months return None., When prev_close is 0, month return is None (div-by-zero guard)., Requesting a year with no data → all months return None., TestComputeMonthlyReturns

### Community 69 - "TestMonthlyEndpoint"
Cohesion: 0.20
Nodes (5): POST /api/price-change/monthly, Valid request → 200 with monthly data., Missing symbol → 400., Non-integer year → 400., TestMonthlyEndpoint

### Community 70 - "config.py"
Cohesion: 0.13
Nodes (21): config(), Return presets and other config for the frontend., coingecko_base_url(), coingecko_ids(), crypto_config(), get_color_range(), get_color_scheme(), get_presets() (+13 more)

### Community 71 - "Monthly Return Breakdown Feature"
Cohesion: 0.29
Nodes (10): Annual Return Aggregation Column, Green Positive / Red Negative Color Convention, Date Range 2019-2026 (8 Years x 12 Months), Monthly Return Breakdown Feature, Monthly Return Color-Coded Heatmap Grid, Monthly Breakdown Screenshot, Monthly Average Return Row, S&P 500 Index (+2 more)

### Community 72 - "fetchData"
Cohesion: 0.33
Nodes (10): escapeHtml(), fetchData(), fetchMonthlyBatch(), getSelectedYear(), hideYearlySections(), renderMetaInfo(), setConnected(), setLoading() (+2 more)

### Community 73 - "TestYahooQuoteBatch"
Cohesion: 0.17
Nodes (7): Unit tests for _yahoo_quote_batch — batch v7/quote fetching., Valid crumb + 200 response → parsed quote list., None crumb → empty list (no request made)., Non-200 status → empty list for that chunk., Symbol with regularMarketPrice=None is filtered out., Symbols beyond _YH_BATCH (50) are split across multiple requests., TestYahooQuoteBatch

### Community 74 - "TestExchangeLossEndpoint"
Cohesion: 0.13
Nodes (11): _fx_series(), Build a fake PriceSeries-like object with daily closes from base_date., POST /api/price-change/exchange-loss, Default held=USD, target=CNY → cross OHLC equals the CNY=X close (1 /…, USD→EUR is 1 / EURUSD close (direct quote)., CNY→EUR = (1 / CNY=X) / EURUSD=X on shared dates., Cross high = held high / target low; cross low = held low / target high., held == target → fetch once and all rates are 1. (+3 more)

### Community 76 - "header-trend.js"
Cohesion: 0.47
Nodes (8): buildTrendSvg(), fetchAndRender(), init(), readCache(), render(), scheduleInit(), todayKey(), writeCache()

### Community 77 - "vercel.json"
Cohesion: 0.22
Nodes (8): hkg1, maxDuration, memory, functions, api/index.py, outputDirectory, regions, rewrites

### Community 78 - "_fetch_all_qdii_fund_groups"
Cohesion: 0.22
Nodes (9): _build_qdii_summary(), _discover_active_qdii_codes(), _fetch_all_qdii_fund_groups(), _is_active_qdii_candidate(), Fetch all configured QDII fund groups from East Money., Best-effort filter for RMB QDII active funds from East Money code list., Discover RMB active QDII fund codes from East Money's public code list., Put buyable/larger-limit/cheaper rows first for the guide table. (+1 more)

### Community 79 - "_cn_secid"
Cohesion: 0.50
Nodes (4): _cn_secid(), _cn_stock_secid(), Map A-share code to East Money secid format., Map individual A-share stock code to East Money secid format. Individual stock…

### Community 80 - "TestYearlyEndpoint"
Cohesion: 0.33
Nodes (3): POST /api/price-change/yearly, Service exception → 500., TestYearlyEndpoint

### Community 81 - "TestBacktestEndpoint"
Cohesion: 0.33
Nodes (4): POST /api/price-change/backtest, ValueError from service → 400., Unexpected error → 500., TestBacktestEndpoint

### Community 82 - "_enrich_detail_fundamentals_from_series"
Cohesion: 0.33
Nodes (7): _eastmoney_detail_quote(), _enrich_detail_fundamentals_from_series(), _fetch_detail_fundamentals(), _finite_quote_number(), Fill resilient market-snapshot fields from the existing daily series., Fetch and cache a best-effort valuation snapshot for one US symbol., Return a normalized US quote snapshot from East Money as a fallback.

### Community 83 - "search_asset_symbols"
Cohesion: 0.14
Nodes (14): _east_money_symbol_search(), _em_market_cap(), _get_market_caps(), Return a cached Yahoo crumb, priming cookies + crumb hourly., Search Chinese, Hong Kong, and US listings by code or company name., Best-effort Yahoo search for global listings and crypto assets., Return symbol suggestions suitable for the site's asset input controls., Batched Yahoo v7/quote market-cap lookup. Returns {symbol: cap}. (+6 more)

### Community 85 - "TestFetchDailyReturns"
Cohesion: 0.25
Nodes (5): Daily return computation for a specific month., Month with data → list of daily return dicts., Unknown type → empty list., Error series → empty list., TestFetchDailyReturns

### Community 86 - "stats_dashboard"
Cohesion: 0.15
Nodes (13): _check_admin_token(), link_click(), link_clicks(), Record a click on a tracked external link. Body: {"name": "feishu_us_stock"} —…, Return click counts for all tracked links., Verify admin token from ?token= query param. Uses WISH_ADMIN_TOKEN env var., Read current visit count without incrementing., Admin-only stats dashboard. Access with ?token=<WISH_ADMIN_TOKEN>. (+5 more)

### Community 87 - "feature-updates.js"
Cohesion: 0.33
Nodes (8): configUrl(), getSeenVersion(), openDialog(), releaseItems(), rememberVersion(), renderNotice(), showFeatureUpdates(), validReleases()

### Community 88 - "ThreadLocalSession"
Cohesion: 0.40
Nodes (3): Small thread-safe session wrapper for concurrent market-data fetches., ThreadLocalSession, Session

### Community 89 - "test_symbol_persistence.py"
Cohesion: 0.36
Nodes (9): Regression checks for remembered selections and reusable symbol search., _source(), test_backtest_remembers_symbol_and_asset_type(), test_crash_stats_remembers_symbol_and_asset_type(), test_data_download_remembers_all_user_selected_parameters_immediately(), test_data_download_supports_hk_and_global_stocks(), test_heatmap_uses_market_types_without_symbol_or_top_n_controls(), test_hk_and_global_stocks_are_available_across_analysis_modules() (+1 more)

### Community 90 - "TestGetCrashChartData"
Cohesion: 0.25
Nodes (5): Crash chart window data retrieval., Valid pre_crash_date returns a window of prices., Date not in data → ValueError., trading_days out of range → ValueError., TestGetCrashChartData

### Community 91 - "Multi-Asset Yearly Total Returns (% per calendar year)"
Cohesion: 0.48
Nodes (7): Asset Class Rows (US Stocks, International, Emerging, Commodities, Bonds, Cash, Crypto), Calendar Year Columns (~2006-2025 span), Green=Positive Return / Red=Negative Return color encoding with intensity by magnitude, Multi-Asset Yearly Total Returns (% per calendar year), Custom SVG Heatmap Visualization (no external charting library), Yearly Returns Heatmap (年度收益热力图), Yearly Performance Heatmap Screenshot

### Community 92 - "Bitget Stock Trading Fee Schedule"
Cohesion: 0.29
Nodes (7): Bitget Exchange, Platform Fee, Bitget Stock Trading Fee Schedule, Bitget Stock Trading, Trading Commission Fees, Bitget Stock Fee Reference Image, Fee Reference Image Stored as Frontend Static Asset for Display in ETF/Stock Pages

### Community 93 - "Yearly Heatmap / Treemap Visualization"
Cohesion: 0.38
Nodes (7): Global Asset Yearly Returns Data, Native SVG Treemap Rendering, Yearly Heatmap Screenshot, 价值投资交流群扫码入口, QR code image for value-invest-group, Price Change Main Page, Yearly Heatmap / Treemap Visualization

### Community 94 - "capture_screenshots.py"
Cohesion: 0.57
Nodes (6): Screenshot of investment channels comparison knowledge article — comparing BIT, Binance, and Bitget platforms for US stock investing via crypto accounts, capture_backtest(), capture_monthly(), capture_yearly(), main(), wait_for_idle()

### Community 95 - "TestFetchHeatmapToday"
Cohesion: 0.25
Nodes (5): Integration tests: fetch_heatmap_data with period='today'., period='today' routes through _build_heatmap_today., When fast path returns None, fall through to per-symbol OHLCV., period='month' should NOT use the today fast path., TestFetchHeatmapToday

### Community 96 - "binance_base_url"
Cohesion: 0.33
Nodes (7): binance_base_url(), _probe_binance(), _binance_pair(), _fetch_crypto_binance(), _fetch_daily_series_crypto_binance(), Fetch yearly returns via Binance public klines API., Fetch daily close data for crypto via Binance.

### Community 97 - "qdii_fund_holdings"
Cohesion: 0.25
Nodes (9): qdii_fund_holdings(), _qdii_holdings_cache_key(), _qdii_json_response(), Return regional and fund/ETF holdings parsed from the latest report., Return QDII JSON with shared CDN caching for normal reads., Read one fund's parsed periodic-report holdings from shared cache., Keep report data beyond its fresh TTL so it can serve as a fallback., _read_qdii_holdings_shared_cache() (+1 more)

### Community 98 - "routes/conftest.py"
Cohesion: 0.40
Nodes (5): client(), isolate_stats_files(), fixture, Fixtures for API route integration tests., Keep visit/unique-user fallback files out of shared /tmp during tests.

### Community 99 - "TestMonthlyBatchEndpoint"
Cohesion: 0.33
Nodes (3): POST /api/price-change/monthly-batch, Missing symbols → 400., TestMonthlyBatchEndpoint

### Community 100 - "Monthly Trend Analysis Page Screenshot"
Cohesion: 0.47
Nodes (6): Cumulative Return Line Chart (SVG, Below Heatmap), Dark Theme UI Applied to Monthly Trend Page, Monthly Returns Heatmap Grid (Years x Months, Color-Coded Green/Red), Monthly Trend Analysis Page Screenshot, Summary Statistics Dashboard Cards (Avg Return, Win Rate, Best/Worst Month, Max Drawdown, Sharpe), Tab Navigation: 收益详情 > 月度趋势 sub-tab, alongside 概览/年度统计/日收益/详细数据

### Community 101 - "Backtest tab rendering in price-change.html: HTML structure for the backtest parameter form, results display area, SVG chart container, and stat/metric card layout. The screenshot is a rendering of this tab."
Cohesion: 0.40
Nodes (5): Backtest service endpoint: server-side computation engine that takes asset symbol, date range, initial capital, and monthly contribution; fetches daily PriceSeries; simulates periodic investing; computes portfolio equity curve and performance metrics (CAGR, volatility, Sharpe, max drawdown, win rate)., PriceSeries unified daily data structure: the core data layer from which backtest equity curves, periodic returns, and all derived statistics are computed. Backtest endpoint consumes daily OHLCV via this structure., Backtest full-page UI screenshot (2784x5780): investment backtest tab showing parameter inputs (initial capital, monthly contribution, date range), asset/market selector, SVG equity curve chart with log/linear toggle, KPI stat cards (total return, annualized return, max drawdown, Sharpe ratio, etc.), and detailed monthly/yearly return breakdown tables with color-coded heatmap. Demonstrates the complete single-asset backtesting UX from configuration through results to granular decomposition., SVG equity curve chart renderer in classic JavaScript: draws portfolio value line over time from backtest equity data, supports log/linear scale toggle, time-axis labels, and responsive sizing. Part of the native SVG charting system used across the site., Backtest tab rendering in price-change.html: HTML structure for the backtest parameter form, results display area, SVG chart container, and stat/metric card layout. The screenshot is a rendering of this tab.

### Community 103 - "test_feature_updates.py"
Cohesion: 0.39
Nodes (8): Integration checks for the versioned feature-update notice., _source(), test_feature_update_config_is_a_bilingual_release_list(), test_feature_update_config_is_served_with_the_frontend_cache_policy(), test_feature_update_dialog_and_history_controls_are_wired_into_the_main_page(), test_feature_update_script_uses_last_release_and_confirms_once(), test_settings_feature_list_ui_and_copy_are_removed(), test_settings_menu_opens_the_update_dialog_on_demand()

### Community 104 - "Backtest Detail View"
Cohesion: 0.50
Nodes (5): Backtest Performance Metrics Cards, Cumulative Return Line Chart, Period-by-Period Return Breakdown Table, Backtest Detail UI Screenshot, Backtest Detail View

### Community 106 - "drilldown.js"
Cohesion: 0.70
Nodes (4): fetchDaily(), fetchMonthly(), renderDailyBlock(), renderMonthlyCard()

### Community 107 - "i18n.js"
Cohesion: 0.60
Nodes (3): _assetUrl(), _detectLang(), _init()

### Community 108 - "renderTable"
Cohesion: 0.50
Nodes (5): cellColor(), error, formatPct(), renderMonthlyTable(), renderTable()

### Community 109 - "history.js"
Cohesion: 0.50
Nodes (7): _escape(), _load(), _render(), _resolveName(), _same(), _save(), _upsert()

### Community 110 - "scrape_fund_profile"
Cohesion: 0.67
Nodes (3): main(), Scrape management fee and custody fee for a single ETF. Returns: dict with keys…, scrape_fund_profile()

### Community 112 - "TestFetcherRegistration"
Cohesion: 0.33
Nodes (4): Custom fetcher registration., Register a custom fetcher and verify it's used., Register a daily series fetcher and verify., TestFetcherRegistration

### Community 114 - "Yearly Heatmap Visualization — SVG-based color-coded grid displaying annual percentage returns for multiple global asset classes (equities, bonds, commodities, crypto) across multiple years, with color intensity proportional to return magnitude"
Cohesion: 0.67
Nodes (4): Global Asset Class Annual Returns — multi-year performance comparison across asset types including US equities, international equities, bonds, commodities, gold, and cryptocurrencies, sourced from Yahoo Finance and other data providers, Multi-Asset Return Comparison — cross-asset performance analysis allowing users to visually compare annual returns of different asset classes side-by-side in a single heatmap view, highlighting relative winners and losers each year, Yearly Heatmap Visualization — SVG-based color-coded grid displaying annual percentage returns for multiple global asset classes (equities, bonds, commodities, crypto) across multiple years, with color intensity proportional to return magnitude, Yearly Heatmap Screenshot — visual overview of annual returns across global asset classes using a color-coded grid (green=positive, red=negative), demonstrating the heatmap chart feature on the price-change page

### Community 115 - "S&P 500 Annual Returns Visualization"
Cohesion: 0.67
Nodes (3): Bar Chart: Green positive years, Red negative years, Yearly Performance Chart Screenshot, S&P 500 Annual Returns Visualization

### Community 123 - "test_qdii_holdings_ui.py"
Cohesion: 0.53
Nodes (5): Static integration checks for the lazy QDII holdings table UI., _source(), test_qdii_holdings_are_lazy_loaded_and_render_fund_positions(), test_qdii_holdings_copy_exists_in_both_locales(), test_qdii_table_exposes_region_column_and_23_column_detail_row()

### Community 124 - "add_seo_headers"
Cohesion: 0.29
Nodes (7): after_request, add_seo_headers(), mark_request_start(), Return a stable path label without query strings or private wish IDs., _request_log_path(), _should_log_request(), before_request

### Community 132 - "TestRunFearThresholdStats"
Cohesion: 0.22
Nodes (3): parametrize, VIX/VXN threshold-day forward return analysis., TestRunFearThresholdStats

## Knowledge Gaps
- **117 isolated node(s):** `_btCashflows`, `_btEquityByDate`, `LINE_COLORS`, `_chartHidden`, `hmFilterToggle` (+112 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `PriceSeries` connect `PriceSeries` to `_to_timestamp`, `TestDetailFundamentals`, `TestRunFearThresholdStats`, `computation/conftest.py`, `fetchers.py`, `TestBuildHeatmapToday`, `date`, `TestFetchStockComparison`, `fetch_return_detail`, `TestHtmlMeta`, `TestCache`, `track_coverage`, `normalize_asset_symbol`, `TestRunCrashStats`, `patch`, `._series`, `price_change_service.py`, `TestFetchMonthlyReturns`, `TestYahooQuoteBatch`, `_enrich_detail_fundamentals_from_series`, `TestFetchDailyReturns`, `TestGetCrashChartData`, `TestFetchHeatmapToday`, `binance_base_url`, `TestFetcherRegistration`?**
  _High betweenness centrality (0.151) - this node is a cross-community bridge._
- **Why does `_fetch_daily_series_cached()` connect `normalize_asset_symbol` to `price_change.py`, `PriceSeries`, `etf_market.py`, `route`, `app.py`, `price_change_service.py`, `fetch_return_detail`?**
  _High betweenness centrality (0.127) - this node is a cross-community bridge._
- **Why does `track_coverage()` connect `track_coverage` to `_to_timestamp`, `TestRunFearThresholdStats`, `date`, `TestBuildEquityCurve`, `TestBuildHeatmapToday`, `patch`, `TestCache`, `TestHeaderTrendEndpoint`, `test_price_change.py`, `TestDailyEndpoint`, `TestRunCrashStats`, `TestComputeYearlyReturns`, `TestVixComparisonEndpoint`, `.test_cross_month_prev_close`, `TestFetchMonthlyReturns`, `TestFundamentalsHistoryEndpoint`, `.test_valid_frequencies`, `TestReturnDetailEndpoint`, `TestComputeMonthlyReturns`, `TestMonthlyEndpoint`, `config.py`, `TestYahooQuoteBatch`, `TestExchangeLossEndpoint`, `TestYearlyEndpoint`, `TestBacktestEndpoint`, `TestFetchDailyReturns`, `TestGetCrashChartData`, `TestFetchHeatmapToday`, `TestMonthlyBatchEndpoint`, `TestFetcherRegistration`?**
  _High betweenness centrality (0.121) - this node is a cross-community bridge._
- **Are the 25 inferred relationships involving `PriceSeries` (e.g. with `TestHistoricalCsv` and `TestHtmlMeta`) actually correct?**
  _`PriceSeries` has 25 INFERRED edges - model-reasoned connections that need verification._
- **What connects `_btCashflows`, `_btEquityByDate`, `LINE_COLORS` to the rest of the system?**
  _117 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `_to_timestamp` be split into smaller, more focused modules?**
  _Cohesion score 0.04481792717086835 - nodes in this community are weakly interconnected._
- **Should `heatmap.js` be split into smaller, more focused modules?**
  _Cohesion score 0.06778476589797344 - nodes in this community are weakly interconnected._