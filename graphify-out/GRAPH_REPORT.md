# Graph Report - .  (2026-07-29)

## Corpus Check
- 133 files · ~471,207 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1819 nodes · 3488 edges · 120 communities (107 shown, 13 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 167 edges (avg confidence: 0.76)
- Token cost: 417,567 input · 0 output

## Community Hubs (Navigation)
- Yearly Returns Calculation
- Computation Test Config
- Heatmap Frontend
- Price Change API Routes
- Project Documentation
- SEO Route Tests
- Price Change Frontend Core
- Test Fixtures & Logging
- Price Detail Frontend
- Price Change Config
- Stats Route Tests
- Wishes API Routes
- Equity Curve Calculation
- Crash Statistics Service
- Computation Test Fixtures
- ETF Market Frontend
- QDII Funds Frontend
- Calculation Test Rationales
- Price Change Service Tests
- App Entry & Vercel
- Architecture Documentation
- PriceSeries & CSV Tests
- Price Change Service Core
- Stock Compare Frontend
- Computation Conftest
- Cache Store Service
- VIX Chart Frontend
- Heatmap Data Service
- Stock Detail Service
- Service Test Rationales A
- ETF Market Routes
- Service Test Rationales B
- Start Script
- Calc Test Rationales B
- Monthly Returns Calc
- Detail Quality Service
- Price Change Route Tests A
- Price Change Route Tests B
- Crash Stats Frontend
- ETF Benchmark Service
- QDII Fund Routes
- Diagnostics Service
- Backtest Frontend
- Calc Test Rationales C
- Price Change Frontend Utils
- App Health & Diagnostics
- ETF NAV & Cache
- Visitor Stats Service
- Service Test Fixtures
- Data Download Frontend
- Wishes Frontend
- ETF History Cache Tests
- QDII Fund Info
- Captcha Service
- Calc Test Rationales D
- Calc Test Rationales E
- Calc Test Rationales F
- Config Test Rationales
- QDII Route Tests
- Price Change Route Tests C
- Service Test Rationales C
- Service Test Rationales D
- Anonymous Visit Tracking
- Date Parsing & Tests
- Price Change Data Fetching
- Calc Test Rationales G
- Price Change Route Tests D
- Stock Compare Service Tests
- Monthly Breakdown Screenshot
- QDII Discovery Service
- Price Change Route Tests E
- Intraday Fetcher Tests
- Visitor Stats Tests
- Header Trend Frontend
- Vercel Deployment Config
- Price Change Route Tests F
- Return Detail Tests
- Request Lifecycle Hooks
- Admin Auth & Token
- ETF History Cache Utils
- Stock Fundamentals
- Heatmap Chart Concepts
- Bitget Fee Reference
- Treemap Visualization
- Screenshot Scripts
- Link Click Tracking
- Route Test Conftest
- Stock Compare Tests
- Monthly Batch Tests
- Price Change Route Tests G
- Monthly Trend Screenshot
- Backtest Service
- ThreadLocal Session
- Heatmap Cache Tests
- Backtest Detail Screenshot
- Chart Utilities Frontend
- Drilldown Frontend
- i18n Frontend
- Frontend Format Utils
- ETF Fee Scraper
- China Stock Fetchers
- Chart Detail Service
- Operational Logging Tests
- Delivery Workflow Tests
- Global Assets Concepts
- Yearly Chart Screenshot
- AGENTS & CLAUDE Refs
- Commit Rules
- Wishes BP Docs
- East Money Parser
- README Content
- README Structure
- Flask-CORS

## God Nodes (most connected - your core abstractions)
1. `track_coverage()` - 202 edges
2. `PriceSeries` - 83 edges
3. `diagnose()` - 63 edges
4. `_to_timestamp()` - 43 edges
5. `_trading_dates()` - 32 edges
6. `empty_series()` - 25 edges
7. `_compute_yearly_returns()` - 23 edges
8. `compute_crash_statistics()` - 23 edges
9. `fetch_return_detail()` - 22 edges
10. `_fetch_daily_series_cached()` - 21 edges

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

## Communities (120 total, 13 thin omitted)

### Community 0 - "Yearly Returns Calculation"
Cohesion: 0.07
Nodes (61): _compute_yearly_returns(), Compute yearly returns using YoY change on year-end close prices. For each…, empty_series(), Shared models and low-level HTTP helpers for price change services., series_from_points(), coingecko_base_url(), coingecko_ids(), crypto_config() (+53 more)

### Community 1 - "Computation Test Config"
Cohesion: 0.05
Nodes (32): Accessor functions for config values., Reset config cache before each test., TestConfigAccessors, diagnose(), Record test case count per module for terminal summary., Emit diagnostic info visible with pytest -s or on failure. Call this at key…, track_coverage(), POST /api/price-change/yearly (+24 more)

### Community 2 - "Heatmap Frontend"
Cohesion: 0.06
Nodes (60): fetchHeatmap(), fetchMarketPulse(), hasMarketCapData(), hmAddBtn, hmAddSymbol(), hmClearBtn, hmColor(), hmDisplayName() (+52 more)

### Community 3 - "Price Change API Routes"
Cohesion: 0.06
Nodes (53): backtest(), crash_chart(), crash_stats(), _get_cached_heatmap(), _get_cached_market_pulse(), get_daily_returns(), get_monthly_returns(), get_monthly_returns_batch() (+45 more)

### Community 4 - "Project Documentation"
Cohesion: 0.05
Nodes (48): DAILY_SERIES_FETCHERS registry, etf_market_bp — /api/etf-market Blueprint, i18n — zh-CN and en locales, Knowledge Article SEO Addition Checklist, Native SVG Charts — no charting library, No React/Vue/Build Tools — Classic JS Only, price_change_bp — /api/price-change Blueprint, PriceSeries — unified daily price data structure (+40 more)

### Community 5 - "SEO Route Tests"
Cohesion: 0.06
Nodes (15): client(), fixture, parametrize, Tests for SEO configuration: sitemap.xml, robots.txt, rendered meta tags, JSON-…, Canonical / robots / og:image on rendered pages., Flask test client with a fixed SITE_URL so absolute URLs are stable., og:image screenshots referenced by meta tags must exist under frontend/., GET /sitemap.xml — structure and real lastmod. (+7 more)

### Community 6 - "Price Change Frontend Core"
Cohesion: 0.05
Nodes (41): addBtn, btAmount, btAnimSeconds, btBody, btDayOfMonth, btDayOfMonthLabel, btEndDate, btFrequency (+33 more)

### Community 7 - "Test Fixtures & Logging"
Cohesion: 0.07
Nodes (17): make_series(), Build a PriceSeries from generated daily data. Imported lazily to avoid…, Structured logging contracts for the unified financial data layer., test_daily_series_fetch_success_is_logged(), test_daily_series_l1_cache_hit_is_logged(), patch, Valuation snapshots are normalized and cached independently., Integration tests: fetch_heatmap_data with period='today'. (+9 more)

### Community 8 - "Price Detail Frontend"
Cohesion: 0.15
Nodes (38): attachBarChartTooltips(), barChartPoints(), buildAssetResourceLinks(), buildYearSelector(), cellColor(), chartDetailText(), escapeHtml(), formatCompactNumber() (+30 more)

### Community 9 - "Price Change Config"
Cohesion: 0.09
Nodes (27): config(), Return presets and other config for the frontend., get_color_range(), get_color_scheme(), get_presets(), get_site_base_url(), get_site_config(), load_config() (+19 more)

### Community 10 - "Stats Route Tests"
Cohesion: 0.06
Nodes (10): fixture, parametrize, Tests for visit counter, event tracking, and admin stats dashboard., GET /api/visits and POST /api/visits/increment, GET /api/stats — admin-only HTML dashboard, POST /api/track for tab_view, ad_click, settings_click, settings_action, TestAdminStatsDashboard, TestEventTracking (+2 more)

### Community 11 - "Wishes API Routes"
Cohesion: 0.10
Nodes (33): _client_ip(), get_captcha(), get_wishes(), post_wish(), route, Wish wall API blueprint — anonymous wishes with CAPTCHA + rate limiting., Admin-only delete. Requires header X-Admin-Token., Best-effort client IP. On Vercel the real IP is the first entry of X-Forwarded-… (+25 more)

### Community 12 - "Equity Curve Calculation"
Cohesion: 0.12
Nodes (25): _build_equity_curve(), _compute_daily_returns_for_month(), _compute_money_weighted_annualized_return(), _generate_schedule_dates(), _next_month_anchor(), _normalize_frequency(), date, Return calculations and backtest helpers. (+17 more)

### Community 13 - "Crash Statistics Service"
Cohesion: 0.09
Nodes (20): _build_period_windows(), compute_crash_statistics(), date, Crash detection and recovery analysis using period close returns., Return non-overlapping (candle-start, candle-end) point indices., Find crash events and their recovery metrics. Daily, N-trading-day, weekly, and…, parametrize, Drop exactly at threshold should be a crash. (+12 more)

### Community 14 - "Computation Test Fixtures"
Cohesion: 0.10
Nodes (29): crash_closes(), crash_data(), crash_ts(), daily_3year(), daily_3year_closes(), daily_3year_ts(), fixture, Fixtures for pure-computation tests. (+21 more)

### Community 15 - "ETF Market Frontend"
Cohesion: 0.17
Nodes (30): activeChartType(), addXAxis(), aggregateCacheKey(), appendHistoryStats(), attachAggregateHover(), buildChartBody(), buildRow(), currentAggregateSymbols() (+22 more)

### Community 16 - "QDII Funds Frontend"
Cohesion: 0.16
Nodes (30): baseRowsForActiveIndex(), cacheStatusLabel(), clearFiltersAndSort(), compareRows(), escapeHtml(), fmtMoney(), fmtPct(), fmtRate() (+22 more)

### Community 17 - "Calculation Test Rationales"
Cohesion: 0.09
Nodes (16): date, Data in 2022 and 2024 but not 2023 — compute 2022→2024 directly., DCA schedule generation for all frequency types., Once frequency returns only start_date., Daily interval=1 from Jan 1 to Jan 5., Daily interval=2 skips every other day., Weekly with default weekday (Monday=0)., Weekly on Friday (weekday=4). (+8 more)

### Community 18 - "Price Change Service Tests"
Cohesion: 0.07
Nodes (20): fixture, Tests for backend/service/price_change/price_change_service.py All external…, Crash chart window data retrieval., Date not in data → ValueError., trading_days out of range → ValueError., Custom fetcher registration., Save/restore module-level fetcher dicts so test registrations don't leak into…, Register a daily series fetcher and verify. (+12 more)

### Community 19 - "App Entry & Vercel"
Cohesion: 0.13
Nodes (25): Vercel serverless entry point — wraps the existing Flask app., _base_request_path(), _canonical_content_path(), _frontend_asset_version(), frontend_files(), index(), index_lang(), _is_indexable_content_path() (+17 more)

### Community 20 - "Architecture Documentation"
Cohesion: 0.08
Nodes (27): api/index.py — Vercel Serverless entry point, backend/app.py — Flask app entry, SEO, health, stats, Data Source Fallback Chain, Product Delivery Gate — test→start→verify→logs closed loop, Expired L1 Cache Deletion Policy, L1 Process Memory Cache, L2 Upstash Redis / Vercel KV Cache, L3 JSON Snapshot Disk Cache (+19 more)

### Community 21 - "PriceSeries & CSV Tests"
Cohesion: 0.10
Nodes (12): PriceSeries, TestHistoricalCsv, Crash statistics analysis., Data with known crashes should produce crash events., Service builds non-overlapping N-day candles., Daily crash detection includes an overnight gap down., Gentle uptrend → no crashes., Various invalid inputs should raise ValueError. (+4 more)

### Community 22 - "Price Change Service Core"
Cohesion: 0.13
Nodes (25): _build_stock_comparison_symbol(), _cache_ttl(), clear_price_change_cache(), _deserialize_series(), _fetch_one_yearly(), fetch_stock_comparison(), fetch_yearly_returns(), _get_cached_daily_series() (+17 more)

### Community 23 - "Stock Compare Frontend"
Cohesion: 0.22
Nodes (25): activate(), addSymbol(), cellColor(), clearSymbols(), escapeHtml(), formatPct(), getTaxRate(), highlightSuggestion() (+17 more)

### Community 24 - "Computation Conftest"
Cohesion: 0.11
Nodes (17): date, A deterministic list of (date, close) pairs for execution resolution., sample_price_points(), Only 1 year of data — needs at least 2 year-end closes., Tests for backend/service/price_change/crash_stats.py, Crash that continues lower before recovering., Daily returns include the gap between the prior close and today's open., N-day mode aggregates consecutive, non-overlapping trading days. (+9 more)

### Community 25 - "Cache Store Service"
Cohesion: 0.14
Nodes (23): cache_del(), cache_expire(), cache_get(), cache_hgetall(), cache_hincrby(), cache_incr(), cache_lpush(), cache_lrange() (+15 more)

### Community 26 - "VIX Chart Frontend"
Cohesion: 0.21
Nodes (22): attachVixInteractions(), fetchLatestVix(), fetchVixData(), formatDateLabel(), getVixColors(), init(), initDemoControls(), initPeriodTabs() (+14 more)

### Community 27 - "Heatmap Data Service"
Cohesion: 0.10
Nodes (22): _build_heatmap_today(), _em_market_cap(), fetch_heatmap_data(), _fetch_heatmap_watchlist(), _get_market_caps(), _market_pulse_yahoo_quotes(), _period_label(), _period_start_ts() (+14 more)

### Community 28 - "Stock Detail Service"
Cohesion: 0.15
Nodes (20): _build_detail_overview(), _build_stock_history_tables(), _compute_yearly_dividends(), _compute_yearly_drawdowns(), _compute_yearly_runups(), _date_years_before(), _detail_annualized_volatility(), _detail_drawdown_summary() (+12 more)

### Community 29 - "Service Test Rationales A"
Cohesion: 0.11
Nodes (9): Two-layer caching (L1 in-memory, L2 Redis)., Uncached symbol should return None., Expired L1 entry should be treated as miss., clear_price_change_cache should empty L1., Error series should use shorter TTL (5 min vs 6 hours)., serialize → deserialize should be lossless., Corrupt serialized data should return None gracefully., When L1 misses but L2 has data, it should warm L1 and return. (+1 more)

### Community 30 - "ETF Market Routes"
Cohesion: 0.14
Nodes (18): _etf_history_json_response(), _fetch_etf_history_rows(), _fetch_live_premium(), history(), _load_fee_data(), _parse_tencent_quote(), route, quote() (+10 more)

### Community 31 - "Service Test Rationales B"
Cohesion: 0.11
Nodes (10): Tests for _build_heatmap_today — today fast-path orchestrator., Stub matching _compute_one signature for non-stock entries., All entries are stocks → batch used, no fallback., Batch returns empty for non-empty stocks → return None., include_market_cap=False → market_cap absent from results., Stocks via batch, crypto via compute_fn., No entries → empty data, batch never called., Stock not in batch response → None values, no crash. (+2 more)

### Community 32 - "Start Script"
Cohesion: 0.30
Nodes (17): choose_mode(), interactive_menu(), kill_port_if_needed(), launch_production(), preflight(), restart_production(), run_test_suite(), run_tests() (+9 more)

### Community 33 - "Calc Test Rationales B"
Cohesion: 0.12
Nodes (9): XIRR-style annualized return for DCA cashflows., Single contribution, exactly 1 year later final value 1100 on 1000 → ~10%., 12 monthly contributions of -100, final value 1300 → positive rate., Final value < total invested → negative rate., final_value <= 0 should return None., All amounts are 0 → filtered out, no flows → None., All cashflows on same day → zero duration → None., 3-year DCA should produce a meaningful annualized return. (+1 more)

### Community 34 - "Monthly Returns Calc"
Cohesion: 0.17
Nodes (10): _compute_monthly_returns(), Compute monthly returns for a specific year. Month returns use end-of-month…, Month-over-month returns for a specific year., All 12 months with data should produce 12 entries with computed returns., Months without data should have return=None., January's prev_close comes from December of previous year., All closes are None → all 12 months return None., When prev_close is 0, month return is None (div-by-zero guard). (+2 more)

### Community 35 - "Detail Quality Service"
Cohesion: 0.19
Nodes (16): _avg(), _build_detail_quality(), _build_monthly_stats(), _compute_daily_extremes(), _compute_daily_grid(), _compute_return_candles(), fetch_return_detail(), _median() (+8 more)

### Community 36 - "Price Change Route Tests A"
Cohesion: 0.17
Nodes (7): patch, GET /api/price-change/market-pulse, POST /api/price-change/crash-stats, POST /api/price-change/crash-chart, TestCrashChartEndpoint, TestCrashStatsEndpoint, TestMarketPulseEndpoint

### Community 37 - "Price Change Route Tests B"
Cohesion: 0.15
Nodes (10): Build a fake PriceSeries-like object with n daily bars (ascending close)., GET /api/price-change/header-trend, Series smaller than target is returned whole (no padding)., No params → defaults: QQQ, target 240., Out-of-range points clamps to [60, 400] (no 400, just clamp)., None closes are dropped before downsampling., Fetcher returns errored series → 200 with empty points., Fetcher raises → 200 with empty points (decoration-only). (+2 more)

### Community 38 - "Crash Stats Frontend"
Cohesion: 0.23
Nodes (15): closeResult(), collapseChart(), formatPeriodRange(), getCrashChartColors(), getPeriodLabel(), hideError(), init(), onRowClick() (+7 more)

### Community 39 - "ETF Benchmark Service"
Cohesion: 0.20
Nodes (14): _benchmark_for_etf(), _compute_tracking_error_history(), _daily_return_map_from_rows(), _daily_return_map_from_series(), _index_benchmark_for_etf(), _load_benchmark_map(), A-share ETF real-time market data blueprint using Tencent Finance., Build ETF → benchmark mapping from the shared preset config. (+6 more)

### Community 40 - "QDII Fund Routes"
Cohesion: 0.13
Nodes (15): _filter_qdii_response(), qdii_funds(), _qdii_json_response(), _qdii_snapshot_age_seconds(), Return public East Money data for Nasdaq-100 / S&P 500 QDII funds. Query…, Return either the full QDII snapshot or a single-index view., Read the locally persisted QDII snapshot, if present and valid., Persist the latest successful QDII snapshot for offline/overseas fallback. (+7 more)

### Community 41 - "Diagnostics Service"
Cohesion: 0.16
Nodes (12): binance_base_url(), _collect(), _probe(), _probe_binance(), _probe_coingecko(), _probe_okx(), _probe_tencent(), Live reachability probes for the upstream market-data sources. Each probe makes… (+4 more)

### Community 42 - "Backtest Frontend"
Cohesion: 0.24
Nodes (13): _btCashflows, _btEquityByDate, formatBtMoney(), formatBtNumber(), getBacktestAnimMs(), getBacktestSampleSize(), getChartColors(), renderBacktestCashflowPage() (+5 more)

### Community 43 - "Calc Test Rationales C"
Cohesion: 0.16
Nodes (8): Equity curve construction from price points and executions., Build executed_points in the format expected by _build_equity_curve. Format:…, 12 monthly executions, 24 months of price data., Initial lump sum, no recurring executions., initial_price=0 should not cause div-by-zero (units not computed)., Neither executions nor initial investment → flat zero curve., After all executions, value should continue tracking price changes., TestBuildEquityCurve

### Community 44 - "Price Change Frontend Utils"
Cohesion: 0.16
Nodes (14): addSymbol(), applySiteConfig(), displayName(), exportCSV(), init(), loadConfigFromServer(), loadPreset(), populateYearOptions() (+6 more)

### Community 45 - "App Health & Diagnostics"
Cohesion: 0.17
Nodes (13): diag(), health(), route, qqqm_holdings_csv(), Download the dated top-10 QQQM snapshot displayed on the landing page., Generate a machine-readable TQQQ daily price export., Live reachability of upstream data sources + Redis. Read-only; results are…, Record a tracking event. Fire-and-forget — always returns 200. (+5 more)

### Community 46 - "ETF NAV & Cache"
Cohesion: 0.21
Nodes (13): _cache_payload_age_seconds(), _fetch_etf_nav(), _fetch_etf_nav_cached(), _history_snapshot_path(), _nav_snapshot_path(), Fetch ETF NAV history from East Money fund API. Returns {date_str: nav}. Uses…, Cached wrapper around _fetch_etf_nav with 4-hour L1 + shared cache., _read_etf_history_snapshot() (+5 more)

### Community 47 - "Visitor Stats Service"
Cohesion: 0.26
Nodes (12): _empty_data(), get_language_stats(), normalize_device_language(), normalize_site_language(), Cumulative anonymous language distributions for the admin dashboard., Record both independent language dimensions without failing a visit., Return exact cumulative unique-user counts for both dimensions., Return the canonical supported website language or an empty string. (+4 more)

### Community 48 - "Service Test Fixtures"
Cohesion: 0.21
Nodes (12): error_series(), flat_series(), mock_fetch_daily_series(), fixture, Fixtures for service-layer tests., Returns a MagicMock that can be configured per-test. Usage: def…, A 3-year PriceSeries with trending data., A 1-year PriceSeries with flat prices (all = 100.0). (+4 more)

### Community 49 - "Data Download Frontend"
Cohesion: 0.32
Nodes (12): downloadJson(), enforceIntradayRange(), fetchData(), formValues(), init(), localIsoDate(), preview(), render() (+4 more)

### Community 50 - "Wishes Frontend"
Cohesion: 0.46
Nodes (12): _clearWishMsg(), deleteWish(), _formatWishTime(), _getAdminToken(), _initWishAdmin(), loadCaptcha(), loadWishes(), _renderWishCard() (+4 more)

### Community 51 - "ETF History Cache Tests"
Cohesion: 0.24
Nodes (7): etf_market(), fixture, Tests for ETF market history cache behaviour., When upstream fails, fallback to local snapshot (not expired in-memory cache).…, reset_history_cache(), _sample_history_payload(), TestEtfHistoryCache

### Community 52 - "QDII Fund Info"
Cohesion: 0.18
Nodes (12): _fetch_qdii_fund_info(), _fetch_qdii_period_increase(), _parse_fee_pct(), _parse_float(), _parse_qdii_limit(), Parse fee string like '0.60%' → 0.60. Returns None on failure., Parse East Money numeric fields, preserving None for blanks., Parse "单日投资上限100元" from East Money purchase status text. (+4 more)

### Community 53 - "Captcha Service"
Cohesion: 0.24
Nodes (11): generate(), _pop_answer(), _purge_expired(), Dependency-free SVG image CAPTCHA with one-time verification. Answers are…, Issue a new CAPTCHA. Returns (captcha_id, svg_string)., One-time, case-insensitive verification. Consumes the answer on any lookup so a…, Fetch and consume the stored answer (one-time use). Returns None if…, Render the code as a noisy, distorted SVG string. (+3 more)

### Community 54 - "Calc Test Rationales D"
Cohesion: 0.17
Nodes (7): Date range filtering of price series., Range covering all data should return all valid points., Only points within [start, end] should be returned., start > end should return empty., start == end returns points on that exact date., None closes should be filtered out., TestSeriesPointsInRange

### Community 55 - "Calc Test Rationales E"
Cohesion: 0.17
Nodes (7): Year-over-year returns from year-end close prices., 3-year uptrend data should produce returns for years 2023 and 2024., Empty timestamps and closes should return {}., Year where prev_close == 0 should be skipped (no ZeroDivisionError)., Price going down should produce negative returns., None closes should be ignored; year-end is last valid close., TestComputeYearlyReturns

### Community 56 - "Calc Test Rationales F"
Cohesion: 0.17
Nodes (7): Execution point resolution: map planned dates to actual trading days., When schedule dates match price dates exactly., Scheduled Saturday resolves to next Monday (first available trading day)., Same execution date should not appear twice., Schedule extends past available price data., Empty price points or schedule → empty result., TestResolveExecutionPoints

### Community 57 - "Config Test Rationales"
Cohesion: 0.17
Nodes (7): Configuration loading and caching., The actual config file in the project should load successfully., Second call returns the same object (cached)., When config file is missing, defaults are returned., Corrupt JSON file returns defaults., Config missing 'crypto' key should get defaults merged in., TestLoadConfig

### Community 58 - "QDII Route Tests"
Cohesion: 0.23
Nodes (6): fixture, Tests for QDII fund tracker route and data mapping., reset_qdii_memory_cache(), _sample_payload(), TestQdiiFundInfoMapping, TestQdiiFundsRoute

### Community 59 - "Price Change Route Tests C"
Cohesion: 0.17
Nodes (7): POST /api/price-change/vix-comparison This endpoint has inline data-fetching…, Non-existent period → 400., SPY/QQQ expose adjusted OHLC candles on the same basis as returns., No period specified → defaults to 'daily'., Count should be clamped to valid range., 1hour period should be accepted., TestVixComparisonEndpoint

### Community 60 - "Service Test Rationales C"
Cohesion: 0.17
Nodes (7): Once frequency → single trade., Empty symbol → ValueError., Both amount and initial_amount = 0 → ValueError., end_date < start_date → ValueError., Series with error → ValueError., DCA backtest execution., TestRunDcaBacktest

### Community 61 - "Service Test Rationales D"
Cohesion: 0.17
Nodes (7): Unit tests for _yahoo_quote_batch — batch v7/quote fetching., Valid crumb + 200 response → parsed quote list., None crumb → empty list (no request made)., Non-200 status → empty list for that chunk., Symbol with regularMarketPrice=None is filtered out., Symbols beyond _YH_BATCH (50) are split across multiple requests., TestYahooQuoteBatch

### Community 62 - "Anonymous Visit Tracking"
Cohesion: 0.25
Nodes (11): _cleanup_unique_visits(), _hash_anonymous_id(), _last_days(), Increment visit count and return new value., _read_unique_visits(), _record_unique_visit(), _unique_visit_key(), _unique_visit_series() (+3 more)

### Community 63 - "Date Parsing & Tests"
Cohesion: 0.27
Nodes (5): _parse_iso_date(), ISO date string parsing., Feb 30 doesn't exist., Error message should include the field name., TestParseIsoDate

### Community 64 - "Price Change Data Fetching"
Cohesion: 0.31
Nodes (11): escapeHtml(), fetchData(), fetchMonthlyBatch(), getSelectedYear(), hideYearlySections(), renderMetaInfo(), saveState(), setConnected() (+3 more)

### Community 65 - "Calc Test Rationales G"
Cohesion: 0.20
Nodes (6): Daily returns within a specific month., A full month of trading days with rising prices., Month not in data → empty list., Prev_close for March 1 should come from February's last trading day., None closes should not break prev_close chain., TestComputeDailyReturnsForMonth

### Community 66 - "Price Change Route Tests D"
Cohesion: 0.20
Nodes (5): POST /api/price-change/monthly, Valid request → 200 with monthly data., Missing symbol → 400., Non-integer year → 400., TestMonthlyEndpoint

### Community 67 - "Stock Compare Service Tests"
Cohesion: 0.20
Nodes (3): parametrize, Compact annual comparison data for multiple US stocks., TestFetchStockComparison

### Community 68 - "Monthly Breakdown Screenshot"
Cohesion: 0.29
Nodes (10): Annual Return Aggregation Column, Green Positive / Red Negative Color Convention, Date Range 2019-2026 (8 Years x 12 Months), Monthly Return Breakdown Feature, Monthly Return Color-Coded Heatmap Grid, Monthly Breakdown Screenshot, Monthly Average Return Row, S&P 500 Index (+2 more)

### Community 69 - "QDII Discovery Service"
Cohesion: 0.22
Nodes (9): _build_qdii_summary(), _discover_active_qdii_codes(), _fetch_all_qdii_fund_groups(), _is_active_qdii_candidate(), Best-effort filter for RMB QDII active funds from East Money code list., Discover RMB active QDII fund codes from East Money's public code list., Put buyable/larger-limit/cheaper rows first for the guide table., Fetch all configured QDII fund groups from East Money. (+1 more)

### Community 70 - "Price Change Route Tests E"
Cohesion: 0.22
Nodes (5): Tests for backend/routes/price_change.py — API endpoint integration tests. All…, GET /api/price-change/config, POST /api/price-change/history-download, TestConfigEndpoint, TestHistoryDownloadEndpoint

### Community 71 - "Intraday Fetcher Tests"
Cohesion: 0.36
Nodes (6): Unit tests for intraday market-data download fetchers., _response(), test_binance_intraday_parses_ohlcv(), test_yahoo_daily_preserves_raw_close_with_adjusted_close(), test_yahoo_four_hour_aggregates_hourly_bars(), object

### Community 73 - "Header Trend Frontend"
Cohesion: 0.47
Nodes (8): buildTrendSvg(), fetchAndRender(), init(), readCache(), render(), scheduleInit(), todayKey(), writeCache()

### Community 74 - "Vercel Deployment Config"
Cohesion: 0.22
Nodes (8): hkg1, maxDuration, memory, functions, api/index.py, outputDirectory, regions, rewrites

### Community 75 - "Price Change Route Tests F"
Cohesion: 0.25
Nodes (4): POST /api/price-change/daily, Missing required fields → 400., Non-integer year/month → 400., TestDailyEndpoint

### Community 77 - "Request Lifecycle Hooks"
Cohesion: 0.29
Nodes (7): after_request, add_seo_headers(), mark_request_start(), Return a stable path label without query strings or private wish IDs., _request_log_path(), _should_log_request(), before_request

### Community 78 - "Admin Auth & Token"
Cohesion: 0.29
Nodes (7): _check_admin_token(), Verify admin token from ?token= query param. Uses WISH_ADMIN_TOKEN env var., Read current visit count without incrementing., Admin-only stats dashboard. Access with ?token=<WISH_ADMIN_TOKEN>., _read_counter(), stats_dashboard(), visits()

### Community 79 - "ETF History Cache Utils"
Cohesion: 0.38
Nodes (7): _copy_jsonable(), _history_cache_key(), Return a detached copy for cached JSON-style payloads., _read_etf_history_cache(), _read_etf_history_shared_cache(), _write_etf_history_cache(), _write_etf_history_shared_cache()

### Community 80 - "Stock Fundamentals"
Cohesion: 0.33
Nodes (7): _eastmoney_detail_quote(), _enrich_detail_fundamentals_from_series(), _fetch_detail_fundamentals(), _finite_quote_number(), Fill resilient market-snapshot fields from the existing daily series., Fetch and cache a best-effort valuation snapshot for one US symbol., Return a normalized US quote snapshot from East Money as a fallback.

### Community 81 - "Heatmap Chart Concepts"
Cohesion: 0.48
Nodes (7): Asset Class Rows (US Stocks, International, Emerging, Commodities, Bonds, Cash, Crypto), Calendar Year Columns (~2006-2025 span), Green=Positive Return / Red=Negative Return color encoding with intensity by magnitude, Multi-Asset Yearly Total Returns (% per calendar year), Custom SVG Heatmap Visualization (no external charting library), Yearly Returns Heatmap (年度收益热力图), Yearly Performance Heatmap Screenshot

### Community 82 - "Bitget Fee Reference"
Cohesion: 0.29
Nodes (7): Bitget Exchange, Platform Fee, Bitget Stock Trading Fee Schedule, Bitget Stock Trading, Trading Commission Fees, Bitget Stock Fee Reference Image, Fee Reference Image Stored as Frontend Static Asset for Display in ETF/Stock Pages

### Community 83 - "Treemap Visualization"
Cohesion: 0.38
Nodes (7): Global Asset Yearly Returns Data, Native SVG Treemap Rendering, Yearly Heatmap Screenshot, 价值投资交流群扫码入口, QR code image for value-invest-group, Price Change Main Page, Yearly Heatmap / Treemap Visualization

### Community 84 - "Screenshot Scripts"
Cohesion: 0.57
Nodes (6): Screenshot of investment channels comparison knowledge article — comparing BIT, Binance, and Bitget platforms for US stock investing via crypto accounts, capture_backtest(), capture_monthly(), capture_yearly(), main(), wait_for_idle()

### Community 85 - "Link Click Tracking"
Cohesion: 0.33
Nodes (6): link_click(), link_clicks(), Record a click on a tracked external link. Body: {"name": "feishu_us_stock"} —…, Return click counts for all tracked links., _read_link_clicks(), _write_link_clicks()

### Community 86 - "Route Test Conftest"
Cohesion: 0.40
Nodes (5): client(), isolate_stats_files(), fixture, Fixtures for API route integration tests., Keep visit/unique-user fallback files out of shared /tmp during tests.

### Community 87 - "Stock Compare Tests"
Cohesion: 0.33
Nodes (3): parametrize, POST /api/price-change/stock-compare, TestStockCompareEndpoint

### Community 88 - "Monthly Batch Tests"
Cohesion: 0.33
Nodes (3): POST /api/price-change/monthly-batch, Missing symbols → 400., TestMonthlyBatchEndpoint

### Community 89 - "Price Change Route Tests G"
Cohesion: 0.33
Nodes (4): POST /api/price-change/backtest, ValueError from service → 400., Unexpected error → 500., TestBacktestEndpoint

### Community 90 - "Monthly Trend Screenshot"
Cohesion: 0.47
Nodes (6): Cumulative Return Line Chart (SVG, Below Heatmap), Dark Theme UI Applied to Monthly Trend Page, Monthly Returns Heatmap Grid (Years x Months, Color-Coded Green/Red), Monthly Trend Analysis Page Screenshot, Summary Statistics Dashboard Cards (Avg Return, Win Rate, Best/Worst Month, Max Drawdown, Sharpe), Tab Navigation: 收益详情 > 月度趋势 sub-tab, alongside 概览/年度统计/日收益/详细数据

### Community 91 - "Backtest Service"
Cohesion: 0.40
Nodes (5): Backtest service endpoint: server-side computation engine that takes asset symbol, date range, initial capital, and monthly contribution; fetches daily PriceSeries; simulates periodic investing; computes portfolio equity curve and performance metrics (CAGR, volatility, Sharpe, max drawdown, win rate)., PriceSeries unified daily data structure: the core data layer from which backtest equity curves, periodic returns, and all derived statistics are computed. Backtest endpoint consumes daily OHLCV via this structure., Backtest full-page UI screenshot (2784x5780): investment backtest tab showing parameter inputs (initial capital, monthly contribution, date range), asset/market selector, SVG equity curve chart with log/linear toggle, KPI stat cards (total return, annualized return, max drawdown, Sharpe ratio, etc.), and detailed monthly/yearly return breakdown tables with color-coded heatmap. Demonstrates the complete single-asset backtesting UX from configuration through results to granular decomposition., SVG equity curve chart renderer in classic JavaScript: draws portfolio value line over time from backtest equity data, supports log/linear scale toggle, time-axis labels, and responsive sizing. Part of the native SVG charting system used across the site., Backtest tab rendering in price-change.html: HTML structure for the backtest parameter form, results display area, SVG chart container, and stat/metric card layout. The screenshot is a rendering of this tab.

### Community 92 - "ThreadLocal Session"
Cohesion: 0.40
Nodes (3): Small thread-safe session wrapper for concurrent market-data fetches., ThreadLocalSession, Session

### Community 94 - "Backtest Detail Screenshot"
Cohesion: 0.50
Nodes (5): Backtest Performance Metrics Cards, Cumulative Return Line Chart, Period-by-Period Return Breakdown Table, Backtest Detail UI Screenshot, Backtest Detail View

### Community 96 - "Drilldown Frontend"
Cohesion: 0.70
Nodes (4): fetchDaily(), fetchMonthly(), renderDailyBlock(), renderMonthlyCard()

### Community 97 - "i18n Frontend"
Cohesion: 0.60
Nodes (3): _assetUrl(), _detectLang(), _init()

### Community 98 - "Frontend Format Utils"
Cohesion: 0.50
Nodes (5): cellColor(), error, formatPct(), renderMonthlyTable(), renderTable()

### Community 99 - "ETF Fee Scraper"
Cohesion: 0.67
Nodes (3): main(), Scrape management fee and custody fee for a single ETF. Returns: dict with keys…, scrape_fund_profile()

### Community 100 - "China Stock Fetchers"
Cohesion: 0.50
Nodes (4): _cn_secid(), _cn_stock_secid(), Map A-share code to East Money secid format., Map individual A-share stock code to East Money secid format. Individual stock…

### Community 101 - "Chart Detail Service"
Cohesion: 0.50
Nodes (4): Attach a stable daily-extreme shape to a return-detail period., Attach tooltip and candlestick data to a return-detail period., _with_chart_detail(), _with_daily_extremes()

### Community 104 - "Global Assets Concepts"
Cohesion: 0.67
Nodes (4): Global Asset Class Annual Returns — multi-year performance comparison across asset types including US equities, international equities, bonds, commodities, gold, and cryptocurrencies, sourced from Yahoo Finance and other data providers, Multi-Asset Return Comparison — cross-asset performance analysis allowing users to visually compare annual returns of different asset classes side-by-side in a single heatmap view, highlighting relative winners and losers each year, Yearly Heatmap Visualization — SVG-based color-coded grid displaying annual percentage returns for multiple global asset classes (equities, bonds, commodities, crypto) across multiple years, with color intensity proportional to return magnitude, Yearly Heatmap Screenshot — visual overview of annual returns across global asset classes using a color-coded grid (green=positive, red=negative), demonstrating the heatmap chart feature on the price-change page

### Community 105 - "Yearly Chart Screenshot"
Cohesion: 0.67
Nodes (3): Bar Chart: Green positive years, Red negative years, Yearly Performance Chart Screenshot, S&P 500 Annual Returns Visualization

## Knowledge Gaps
- **122 isolated node(s):** `_btCashflows`, `_btEquityByDate`, `LINE_COLORS`, `_chartHidden`, `hmFilterToggle` (+117 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `PriceSeries` connect `PriceSeries & CSV Tests` to `Yearly Returns Calculation`, `Computation Test Config`, `Detail Quality Service`, `Price Change API Routes`, `SEO Route Tests`, `Stock Compare Service Tests`, `Test Fixtures & Logging`, `Computation Test Fixtures`, `Service Test Rationales C`, `Stock Fundamentals`, `Service Test Fixtures`, `Price Change Service Tests`, `Service Test Rationales D`, `Price Change Service Core`, `Computation Conftest`, `Stock Detail Service`, `Service Test Rationales A`, `Service Test Rationales B`?**
  _High betweenness centrality (0.124) - this node is a cross-community bridge._
- **Why does `track_coverage()` connect `Computation Test Config` to `Test Fixtures & Logging`, `Price Change Config`, `Equity Curve Calculation`, `Crash Statistics Service`, `Computation Test Fixtures`, `Calculation Test Rationales`, `Price Change Service Tests`, `PriceSeries & CSV Tests`, `Computation Conftest`, `Service Test Rationales A`, `Service Test Rationales B`, `Calc Test Rationales B`, `Monthly Returns Calc`, `Price Change Route Tests A`, `Price Change Route Tests B`, `Calc Test Rationales C`, `Calc Test Rationales D`, `Calc Test Rationales E`, `Calc Test Rationales F`, `Config Test Rationales`, `Price Change Route Tests C`, `Service Test Rationales C`, `Service Test Rationales D`, `Date Parsing & Tests`, `Calc Test Rationales G`, `Price Change Route Tests D`, `Price Change Route Tests E`, `Price Change Route Tests F`, `Return Detail Tests`, `Stock Compare Tests`, `Monthly Batch Tests`, `Price Change Route Tests G`?**
  _High betweenness centrality (0.108) - this node is a cross-community bridge._
- **Why does `_fetch_daily_series_cached()` connect `Price Change API Routes` to `Yearly Returns Calculation`, `Detail Quality Service`, `ETF Benchmark Service`, `Equity Curve Calculation`, `App Health & Diagnostics`, `App Entry & Vercel`, `PriceSeries & CSV Tests`, `Price Change Service Core`?**
  _High betweenness centrality (0.096) - this node is a cross-community bridge._
- **Are the 22 inferred relationships involving `PriceSeries` (e.g. with `TestHistoricalCsv` and `TestHtmlMeta`) actually correct?**
  _`PriceSeries` has 22 INFERRED edges - model-reasoned connections that need verification._
- **What connects `_btCashflows`, `_btEquityByDate`, `LINE_COLORS` to the rest of the system?**
  _122 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Yearly Returns Calculation` be split into smaller, more focused modules?**
  _Cohesion score 0.06502816180235535 - nodes in this community are weakly interconnected._
- **Should `Computation Test Config` be split into smaller, more focused modules?**
  _Cohesion score 0.049667178699436765 - nodes in this community are weakly interconnected._