"""
Yearly price change API blueprint.
"""
import hashlib
import json
import logging
import re
import threading as _threading
import time

from flask import Blueprint, jsonify, request
from service.price_change import cache_store
from service.price_change.common import normalize_asset_symbol
from service.price_change.fundamentals_history import (
    fetch_fundamentals_history,
)

from service.price_change.price_change_service import (
    _fetch_daily_series_cached,
    fetch_daily_returns,
    fetch_heatmap_data,
    fetch_return_detail,
    fetch_yearly_returns,
    fetch_monthly_returns,
    fetch_monthly_returns_batch,
    fetch_market_pulse,
    fetch_price_history,
    fetch_stock_comparison,
    get_presets,
    get_color_range,
    get_color_scheme,
    get_site_config,
    run_dca_backtest,
    run_crash_stats,
    run_fear_threshold_stats,
    get_crash_chart_data,
    search_asset_symbols,
)

logger = logging.getLogger(__name__)

price_change_bp = Blueprint("price_change", __name__, url_prefix="/api/price-change")

_MARKET_PULSE_SHARED_CACHE_KEY = "market-pulse:v1"
_MARKET_PULSE_CACHE_TTL = 5 * 60
_US_COMPANY_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9._-]{0,19}$")


def _get_cached_market_pulse() -> dict | None:
    raw = cache_store.cache_get(_MARKET_PULSE_SHARED_CACHE_KEY)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        if time.time() - float(payload["ts"]) >= _MARKET_PULSE_CACHE_TTL:
            return None
        data = payload["data"]
        return dict(data) if isinstance(data, dict) else None
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _set_cached_market_pulse(result: dict) -> None:
    cache_store.cache_set(
        _MARKET_PULSE_SHARED_CACHE_KEY,
        json.dumps({"ts": time.time(), "data": result}, separators=(",", ":")),
        _MARKET_PULSE_CACHE_TTL,
    )


@price_change_bp.route("/config", methods=["GET"])
def config():
    """Return presets and other config for the frontend."""
    presets_dict = get_presets()
    # Return as list to preserve insertion order (Flask's jsonify sorts keys by default)
    presets_list = [
        {"key": k, "label": v["label"], "symbols": v["symbols"]}
        for k, v in presets_dict.items()
    ]
    color_range = get_color_range()
    color_scheme = get_color_scheme()
    site = get_site_config()
    return jsonify({
        "presets": presets_list,
        "color_range": color_range,
        "color_scheme": color_scheme,
        "site": site,
    })


@price_change_bp.route("/symbol-search", methods=["GET"])
def symbol_search():
    """Search supported assets by symbol or company name."""
    query = str(request.args.get("q", "")).strip()
    asset_type = str(request.args.get("type", "stock")).strip().lower()
    if not query:
        return jsonify({"query": "", "type": asset_type, "results": []})
    if len(query) > 80:
        return jsonify({"error": "q must be at most 80 characters"}), 400
    if asset_type not in {"stock", "hk_stock", "global_stock", "crypto", "cn_stock"}:
        return jsonify({"error": "unsupported asset type"}), 400
    try:
        results = search_asset_symbols(query, asset_type, limit=8)
        return jsonify({"query": query, "type": asset_type, "results": results})
    except Exception as exc:
        logger.exception("Failed to search symbols: %s", exc)
        return jsonify({"error": str(exc)}), 500


@price_change_bp.route("/market-pulse", methods=["GET"])
def market_pulse():
    """Return the latest daily move for the global benchmark strip."""
    cached_result = _get_cached_market_pulse()
    if cached_result is not None:
        cached_result["cached"] = True
        return jsonify(cached_result)
    try:
        result = fetch_market_pulse()
        _set_cached_market_pulse(result)
        return jsonify(result)
    except Exception as e:
        logger.exception("Failed to fetch market pulse: %s", e)
        return jsonify({"error": str(e)}), 500


@price_change_bp.route("/yearly", methods=["POST"])
def get_yearly_returns():
    """Return yearly returns for given symbols.

    Request body:
        {"symbols": [{"symbol": "AAPL", "type": "stock"}, ...]}

    Returns:
        {
            "years": [...],
            "data": {"SYMBOL": {"year": pct, ...}, ...},
            "drawdowns": {"SYMBOL": {"year": {"max_drawdown": pct, ...}}},
        }
    """
    body = request.get_json(silent=True) or {}
    symbols = body.get("symbols", [])

    if not symbols:
        return jsonify({"error": "symbols list is required"}), 400

    try:
        result = fetch_yearly_returns(symbols)
        return jsonify(result)
    except Exception as e:
        logger.exception("Failed to fetch yearly returns: %s", e)
        return jsonify({"error": str(e)}), 500


@price_change_bp.route("/monthly", methods=["POST"])
def get_monthly_returns():
    """Return monthly returns for a symbol in a given year.

    Request body:
        {"symbol": "AAPL", "type": "stock", "year": 2024}

    Returns:
        {
            "symbol": "AAPL",
            "year": 2024,
            "months": [{"month": 1, "return": 5.2, "max_drawdown": -3.1}, ...],
        }
    """
    body = request.get_json(silent=True) or {}
    asset_type = body.get("type", "stock").strip().lower()
    symbol = normalize_asset_symbol(body.get("symbol", ""), asset_type)
    year = body.get("year")

    if not symbol or not year:
        return jsonify({"error": "symbol and year are required"}), 400

    try:
        year = int(year)
    except (ValueError, TypeError):
        return jsonify({"error": "year must be an integer"}), 400

    try:
        months = fetch_monthly_returns(symbol, asset_type, year)
        return jsonify({"symbol": symbol, "type": asset_type, "year": year, "months": months})
    except Exception as e:
        logger.exception("Failed to fetch monthly returns: %s", e)
        return jsonify({"error": str(e)}), 500


@price_change_bp.route("/monthly-batch", methods=["POST"])
def get_monthly_returns_batch():
    """Return monthly returns for multiple symbols in a given year.

    Request body:
        {"symbols": [{"symbol": "AAPL", "type": "stock"}, ...], "year": 2025}

    Returns:
        {
            "year": 2025,
            "data": {"AAPL": [{"month": 1, "return": 5.2, "max_drawdown": -3.1}, ...]},
            "drawdowns": {"AAPL": {"2025": {"max_drawdown": -12.3, ...}}},
        }
    """
    body = request.get_json(silent=True) or {}
    symbols = body.get("symbols", [])
    year = body.get("year")

    if not symbols or not year:
        return jsonify({"error": "symbols and year are required"}), 400

    try:
        year = int(year)
    except (ValueError, TypeError):
        return jsonify({"error": "year must be an integer"}), 400

    try:
        result = fetch_monthly_returns_batch(symbols, year)
        return jsonify({"year": year, **result})
    except Exception as e:
        logger.exception("Failed to fetch monthly returns batch: %s", e)
        return jsonify({"error": str(e)}), 500


@price_change_bp.route("/daily", methods=["POST"])
def get_daily_returns():
    """Return daily returns for a symbol in a given year and month."""
    body = request.get_json(silent=True) or {}
    asset_type = body.get("type", "stock").strip().lower()
    symbol = normalize_asset_symbol(body.get("symbol", ""), asset_type)
    year = body.get("year")
    month = body.get("month")

    if not symbol or not year or not month:
        return jsonify({"error": "symbol, year and month are required"}), 400

    try:
        year = int(year)
        month = int(month)
    except (ValueError, TypeError):
        return jsonify({"error": "year and month must be integers"}), 400

    if month < 1 or month > 12:
        return jsonify({"error": "month must be between 1 and 12"}), 400

    try:
        days = fetch_daily_returns(symbol, asset_type, year, month)
        return jsonify({"symbol": symbol, "type": asset_type, "year": year, "month": month, "days": days})
    except Exception as e:
        logger.exception("Failed to fetch daily returns: %s", e)
        return jsonify({"error": str(e)}), 500


@price_change_bp.route("/detail", methods=["POST"])
def get_return_detail():
    """Return single-symbol yearly/monthly return detail, or daily grid for a specific year."""
    body = request.get_json(silent=True) or {}
    asset_type = body.get("type", "stock").strip().lower()
    symbol = normalize_asset_symbol(body.get("symbol", ""), asset_type)
    year = body.get("year")
    include_stock_history = body.get("include_stock_history", True)

    if not symbol:
        return jsonify({"error": "symbol is required"}), 400
    if year is not None:
        try:
            year = int(year)
        except (TypeError, ValueError):
            return jsonify({"error": "year must be an integer"}), 400
    if not isinstance(include_stock_history, bool):
        return jsonify({"error": "include_stock_history must be a boolean"}), 400

    try:
        result = fetch_return_detail(
            symbol,
            asset_type,
            year,
            include_stock_history,
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to fetch return detail: %s", e)
        return jsonify({"error": str(e)}), 500


@price_change_bp.route("/fundamentals-history", methods=["POST"])
def get_fundamentals_history():
    """Return historical PE, PB and annual ROE for a US company stock."""
    body = request.get_json(silent=True)
    raw_symbol = body.get("symbol") if isinstance(body, dict) else None
    symbol = raw_symbol.strip().upper() if isinstance(raw_symbol, str) else ""
    if not _US_COMPANY_SYMBOL_RE.fullmatch(symbol):
        return jsonify({
            "error": "valid US stock symbol is required",
        }), 400

    try:
        return jsonify(fetch_fundamentals_history(symbol))
    except Exception as e:
        logger.exception(
            "Failed to fetch fundamentals history for %s: %s",
            symbol,
            e,
        )
        return jsonify({
            "error": "failed to fetch fundamentals history",
        }), 500


@price_change_bp.route("/stock-compare", methods=["POST"])
def stock_compare():
    """Return a compact annual comparison cube for multiple US stocks."""
    body = request.get_json(silent=True) or {}
    symbols = body.get("symbols", [])
    tax_rate = body.get("tax_rate", 30)
    include_dividend_reinvestment = body.get("include_dividend_reinvestment", True)
    backtest_enabled = body.get("backtest_enabled", False)
    start_date = body.get("start_date")
    if not isinstance(symbols, list) or not symbols:
        return jsonify({"error": "symbols list is required"}), 400
    try:
        return jsonify(fetch_stock_comparison(
            symbols,
            tax_rate,
            include_dividend_reinvestment=include_dividend_reinvestment,
            backtest_enabled=backtest_enabled,
            start_date=start_date,
        ))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to build stock comparison: %s", e)
        return jsonify({"error": str(e)}), 500


@price_change_bp.route("/history-download", methods=["POST"])
def history_download():
    """Return date-bounded price history as a JSON collection."""
    body = request.get_json(silent=True) or {}
    asset_type = str(body.get("type", "crypto")).strip().lower()
    symbol = normalize_asset_symbol(body.get("symbol", ""), asset_type)
    period = str(body.get("period", "daily")).strip().lower()
    start_date = str(body.get("start_date", "")).strip()
    end_date = str(body.get("end_date", "")).strip()
    if not symbol or not start_date or not end_date:
        return jsonify({"error": "symbol, start_date and end_date are required"}), 400

    try:
        return jsonify(fetch_price_history(symbol, asset_type, period, start_date, end_date))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to build history download: %s", e)
        return jsonify({"error": str(e)}), 500


@price_change_bp.route("/backtest", methods=["POST"])
def backtest():
    """Run DCA backtest using daily prices."""
    body = request.get_json(silent=True) or {}
    try:
        result = run_dca_backtest(body)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to run backtest: %s", e)
        return jsonify({"error": str(e)}), 500


@price_change_bp.route("/crash-stats", methods=["POST"])
def crash_stats():
    """Detect crash events over a selected period and compute recovery metrics.

    Request body:
        {"symbol": "QQQ", "type": "stock", "start_date": "2020-01-01",
         "end_date": "2025-12-31", "threshold_pct": 4.77,
         "period_type": "day", "period_days": 5}
    """
    body = request.get_json(silent=True) or {}
    try:
        result = run_crash_stats(body)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to run crash stats: %s", e)
        return jsonify({"error": str(e)}), 500


@price_change_bp.route("/crash-chart", methods=["POST"])
def crash_chart():
    """Return daily close prices around a crash event for charting.

    Request body:
        {"symbol": "QQQ", "type": "stock", "pre_crash_date": "2022-05-04",
         "trading_days": 30}
    """
    body = request.get_json(silent=True) or {}
    try:
        result = get_crash_chart_data(body)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to get crash chart data: %s", e)
        return jsonify({"error": str(e)}), 500


# Heatmap result cache: keyed by (period, auto_top_n, sorted_symbol_keys).
# TTL = 4 hours.  Bypassed when force=true.
_heatmap_cache: dict = {}
_heatmap_cache_lock = _threading.Lock()
_HEATMAP_CACHE_TTL = 4 * 60 * 60  # 4 hours
_HEATMAP_SHARED_CACHE_PREFIX = "heatmap:v1:"


def _heatmap_cache_key(
    symbols: list,
    period: str,
    auto_top_n: int,
    include_market_cap: bool,
    market_type: str | None = None,
) -> str:
    """Stable cache key for heatmap results."""
    sym_keys = sorted(
        f"{s.get('symbol','').strip().upper()}|{s.get('type','stock').strip().lower()}"
        for s in symbols
    )
    raw = (
        f"hm:{market_type or 'legacy'}:{period}:{auto_top_n}:"
        f"{int(include_market_cap)}:{','.join(sym_keys)}"
    )
    return hashlib.md5(raw.encode()).hexdigest()


def _get_cached_heatmap(cache_key: str) -> dict | None:
    """Read heatmap data from process memory, then the shared Redis cache."""
    now = time.time()
    with _heatmap_cache_lock:
        entry = _heatmap_cache.get(cache_key)
        if entry:
            if now - entry["ts"] < _HEATMAP_CACHE_TTL:
                return dict(entry["data"])
            del _heatmap_cache[cache_key]

    raw = cache_store.cache_get(_HEATMAP_SHARED_CACHE_PREFIX + cache_key)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        fetched_at = float(payload["ts"])
        data = payload["data"]
        if now - fetched_at >= _HEATMAP_CACHE_TTL or not isinstance(data, dict):
            return None
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    with _heatmap_cache_lock:
        _heatmap_cache[cache_key] = {"ts": fetched_at, "data": dict(data)}
    return dict(data)


def _set_cached_heatmap(cache_key: str, result: dict) -> None:
    """Store the computed heatmap in both local and cross-instance caches."""
    fetched_at = time.time()
    cached_result = dict(result)
    with _heatmap_cache_lock:
        _heatmap_cache[cache_key] = {"ts": fetched_at, "data": cached_result}
    cache_store.cache_set(
        _HEATMAP_SHARED_CACHE_PREFIX + cache_key,
        json.dumps({"ts": fetched_at, "data": cached_result}, separators=(",", ":")),
        _HEATMAP_CACHE_TTL,
    )


@price_change_bp.route("/heatmap", methods=["POST"])
def heatmap():
    """Return treemap heatmap data: per-symbol return + turnover over a period.

    Request body:
        {"symbols": [{"symbol": "AAPL", "type": "stock"}, ...],
         "market_type": "stock|hk_stock|global_stock|crypto|cn_stock",
         "period": "today|week|month|quarter|year",
         "auto_top_n": 20,              # legacy: limit automatic US selection
         "include_market_cap": true,    # optional: attach best-effort market cap
         "force": true}                  # optional: bypass cache

    Returns:
        {"period": "month", "period_label": "2026-06",
         "data": [{"symbol": "AAPL", "name": "Apple Inc", "type": "stock",
                    "return_pct": 5.23, "turnover": 123456789,
                    "turnover_currency": "USD", "market_cap": 3.0e12}, ...]}
    """
    body = request.get_json(silent=True) or {}
    symbols = body.get("symbols", [])
    raw_market_type = body.get("market_type")
    market_type = (
        str(raw_market_type).strip().lower()
        if raw_market_type is not None
        else None
    )
    period = str(body.get("period", "week")).strip().lower()
    auto_top_n = int(body.get("auto_top_n", 0) or 0)
    include_market_cap = bool(body.get("include_market_cap", False))
    force = bool(body.get("force", False))

    # A market type displays its complete configured pool. auto_top_n remains
    # accepted for backwards compatibility with older clients.
    if not symbols and not market_type and auto_top_n <= 0:
        return jsonify({
            "error": "symbols list is required (or set market_type/auto_top_n)"
        }), 400

    valid_periods = {"today", "week", "month", "quarter", "year"}
    if period not in valid_periods:
        return jsonify({"error": f"period must be one of: {', '.join(sorted(valid_periods))}"}), 400

    valid_market_types = {
        "stock", "hk_stock", "global_stock", "crypto", "cn_stock"
    }
    if market_type is not None and market_type not in valid_market_types:
        return jsonify({
            "error": f"market_type must be one of: {', '.join(sorted(valid_market_types))}"
        }), 400

    # Check cache (skip when force=true)
    cache_key = _heatmap_cache_key(
        symbols, period, auto_top_n, include_market_cap, market_type
    )
    if not force:
        cached_result = _get_cached_heatmap(cache_key)
        if cached_result is not None:
            logger.info("Heatmap cache hit for %s", cache_key[:12])
            cached_result["cached"] = True
            return jsonify(cached_result)

    try:
        result = fetch_heatmap_data(
            symbols,
            period,
            auto_top_n=auto_top_n,
            include_market_cap=include_market_cap,
            market_type=market_type,
        )
    except Exception as e:
        logger.exception("Failed to fetch heatmap data: %s", e)
        return jsonify({"error": str(e)}), 500

    _set_cached_heatmap(cache_key, result)

    return jsonify(result)


@price_change_bp.route("/vix-comparison", methods=["POST"])
def vix_comparison():
    """Return SPY, QQQ, VIX, and VXN data aggregated by period.

    Request body:
        {"period": "1hour|daily|weekly|monthly", "count": 30}

    Returns:
        {"spy": [...], "qqq": [...], "spy_candles": [...],
         "qqq_candles": [...], "vix": [...], "vxn": [...],
         "latest_vix": float, "meta": {...}}
    """
    import concurrent.futures
    import time as _time
    from datetime import datetime, timezone

    from service.price_change.common import YAHOO_BASE, REQUEST_TIMEOUT, ThreadLocalSession

    body = request.get_json(silent=True) or {}
    period = body.get("period", "daily").strip().lower()
    if period not in ("1hour", "daily", "weekly", "monthly"):
        return jsonify({"error": "period must be 1hour, daily, weekly, or monthly"}), 400

    try:
        count = int(body.get("count", body.get("days", 30)))
    except (ValueError, TypeError):
        count = 30

    # Number of returned chart bars. Keep a bounded range for UI performance.
    if period == "1hour":
        count = max(5, min(count, 240))
    else:
        count = max(5, min(count, 2000))

    # Map period to Yahoo interval
    interval_map = {
        "1hour": "1h",
        "daily": "1d",
        "weekly": "1d",
        "monthly": "1d",
    }
    yahoo_interval = interval_map[period]

    # For intraday periods, fetch directly from Yahoo (bypass daily cache —
    # intraday data changes too fast to cache meaningfully).
    # For daily/weekly/monthly, use the cached daily fetcher.
    symbols = ["SPY", "QQQ", "^VIX", "^VXN"]
    series_map = {}

    def _fetch_intraday(symbol: str) -> dict:
        """Fetch intraday bars from Yahoo Finance. Returns raw bar list."""
        session = ThreadLocalSession()
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        now = int(_time.time())
        # Yahoo requires a recent period1 for intraday intervals (not epoch 0).
        lookback = 60 * 24 * 3600
        period1 = now - lookback
        try:
            resp = session.get(
                f"{YAHOO_BASE}/{symbol}",
                params={
                    "period1": period1,
                    "period2": now,
                    "interval": yahoo_interval,
                },
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("Yahoo intraday fetch failed for %s: %s", symbol, e)
            return {"error": str(e)}

        try:
            result = data["chart"]["result"][0]
            timestamps = result["timestamp"]
            quote = result["indicators"]["quote"][0]
            closes = quote.get("close")
            if not closes:
                # Try adjclose
                adjclose = result.get("indicators", {}).get("adjclose")
                if adjclose and adjclose[0].get("adjclose"):
                    closes = adjclose[0]["adjclose"]
            if not closes:
                return {"error": "no close data"}
            return {
                "timestamps": timestamps,
                "opens": quote.get("open"),
                "highs": quote.get("high"),
                "lows": quote.get("low"),
                "closes": closes,
                "raw_closes": quote.get("close") or closes,
            }
        except (KeyError, IndexError, TypeError) as e:
            return {"error": f"parse error: {e}"}

    if period == "1hour":
        # Intraday: fetch directly
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(symbols)) as executor:
            futures = {executor.submit(_fetch_intraday, sym): sym for sym in symbols}
            for fut in concurrent.futures.as_completed(futures):
                sym = futures[fut]
                try:
                    series_map[sym] = fut.result()
                except Exception as e:
                    logger.exception("Failed to fetch %s: %s", sym, e)
                    series_map[sym] = {"error": str(e)}
    else:
        # Daily/weekly/monthly: use cached fetcher
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(symbols)) as executor:
            futures = {
                executor.submit(_fetch_daily_series_cached, sym, "stock"): sym
                for sym in symbols
            }
            for fut in concurrent.futures.as_completed(futures):
                sym = futures[fut]
                try:
                    s = fut.result()
                    if s and not s.error:
                        series_map[sym] = {
                            "timestamps": s.timestamps,
                            "closes": s.closes,
                            "opens": getattr(s, "opens", None),
                            "highs": getattr(s, "highs", None),
                            "lows": getattr(s, "lows", None),
                            "raw_closes": getattr(s, "raw_closes", None),
                            "source": s.source,
                        }
                    else:
                        series_map[sym] = {"error": s.error if s else "no data"}
                except Exception as e:
                    logger.exception("Failed to fetch %s: %s", sym, e)
                    series_map[sym] = {"error": str(e)}

    def _aggregate(raw, period_type):
        """Aggregate raw data to requested period, returning [{date, close}, ...]."""
        if raw is None or raw.get("error"):
            return []

        timestamps = raw.get("timestamps", [])
        closes = raw.get("closes", [])

        from collections import defaultdict

        # Build (datetime, close) pairs
        pairs = []
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            pairs.append((dt, close))

        if not pairs:
            return []

        # Limit to requested data points
        if period_type in ("1hour", "daily"):
            pairs = pairs[-count:]

        if period_type == "1hour":
            # Return raw hourly bars with precise timestamps
            result = []
            for dt, close in pairs:
                result.append({
                    "date": dt.strftime("%Y-%m-%dT%H:%M:%S"),
                    "close": round(close, 2),
                })
            return result

        if period_type == "daily":
            result = []
            for dt, close in pairs:
                result.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "close": round(close, 2),
                })
            return result

        if period_type == "weekly":
            groups = defaultdict(list)
            for dt, close in pairs:
                iso = dt.isocalendar()
                groups[(iso[0], iso[1])].append((dt, close))
            result = []
            for key in sorted(groups.keys())[-count:]:
                last_dt, last_close = groups[key][-1]
                result.append({
                    "date": last_dt.strftime("%Y-%m-%d"),
                    "close": round(last_close, 2),
                })
            return result

        if period_type == "monthly":
            groups = defaultdict(list)
            for dt, close in pairs:
                groups[(dt.year, dt.month)].append((dt, close))
            result = []
            for key in sorted(groups.keys())[-count:]:
                last_dt, last_close = groups[key][-1]
                result.append({
                    "date": last_dt.strftime("%Y-%m-%d"),
                    "close": round(last_close, 2),
                })
            return result

        return []

    def _aggregate_candles(raw, period_type):
        """Return adjusted OHLC candles for SPY/QQQ in the requested period.

        Yahoo's daily stock closes are adjusted for distributions and splits,
        while its OHLC values are raw. Apply the close adjustment factor to
        every OHLC field so candle returns and the existing return series use
        the same price basis.
        """
        if raw is None or raw.get("error"):
            return []

        timestamps = raw.get("timestamps", [])
        closes = raw.get("closes", [])
        opens = raw.get("opens") or []
        highs = raw.get("highs") or []
        lows = raw.get("lows") or []
        raw_closes = raw.get("raw_closes") or []

        def _number(values, index, fallback):
            try:
                value = values[index]
                return float(value) if value is not None else fallback
            except (IndexError, TypeError, ValueError):
                return fallback

        bars = []
        for index, (ts, adjusted_close) in enumerate(zip(timestamps, closes)):
            if adjusted_close is None:
                continue
            try:
                close = float(adjusted_close)
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            except (TypeError, ValueError, OSError, OverflowError):
                continue

            raw_close = _number(raw_closes, index, close)
            factor = close / raw_close if raw_close else 1.0
            open_price = _number(opens, index, raw_close) * factor
            high_price = _number(highs, index, raw_close) * factor
            low_price = _number(lows, index, raw_close) * factor
            high_price = max(high_price, open_price, close)
            low_price = min(low_price, open_price, close)
            bars.append({
                "dt": dt,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close,
            })

        if not bars:
            return []

        if period_type in ("1hour", "daily"):
            grouped = bars
        else:
            grouped_map = {}
            for bar in bars:
                dt = bar["dt"]
                if period_type == "weekly":
                    iso = dt.isocalendar()
                    key = (iso[0], iso[1])
                else:
                    key = (dt.year, dt.month)
                group = grouped_map.get(key)
                if group is None:
                    grouped_map[key] = {
                        "dt": dt,
                        "open": bar["open"],
                        "high": bar["high"],
                        "low": bar["low"],
                        "close": bar["close"],
                    }
                else:
                    group["dt"] = dt
                    group["high"] = max(group["high"], bar["high"])
                    group["low"] = min(group["low"], bar["low"])
                    group["close"] = bar["close"]
            grouped = [grouped_map[key] for key in sorted(grouped_map)]

        result = []
        previous_close = None
        for bar in grouped:
            dt = bar["dt"]
            result.append({
                "date": dt.strftime("%Y-%m-%dT%H:%M:%S")
                if period_type == "1hour" else dt.strftime("%Y-%m-%d"),
                "open": round(bar["open"], 2),
                "high": round(bar["high"], 2),
                "low": round(bar["low"], 2),
                "close": round(bar["close"], 2),
                "previous_close": round(previous_close, 2)
                if previous_close is not None else None,
            })
            previous_close = bar["close"]

        return result[-count:]

    def _valid_closes(raw):
        if not raw or raw.get("error"):
            return []
        return [c for c in raw.get("closes", []) if c is not None]

    def _vix_percentile(raw, lookback: int = 252):
        closes = _valid_closes(raw)
        if len(closes) < 2:
            return None
        window = closes[-lookback:]
        latest = window[-1]
        below_or_equal = sum(1 for c in window if c <= latest)
        return round(below_or_equal / len(window) * 100, 1)

    def _daily_return_map(raw):
        if not raw or raw.get("error"):
            return {}
        items = []
        for ts, close in zip(raw.get("timestamps", []), raw.get("closes", [])):
            if close is None:
                continue
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            items.append((dt, close))
        result = {}
        for i in range(1, len(items)):
            prev = items[i - 1][1]
            curr = items[i][1]
            if prev:
                result[items[i][0]] = curr / prev - 1
        return result

    def _spy_vix_correlation(window: int = 30):
        spy_returns = _daily_return_map(series_map.get("SPY"))
        vix_returns = _daily_return_map(series_map.get("^VIX"))
        dates = sorted(set(spy_returns) & set(vix_returns))[-window:]
        if len(dates) < 5:
            return None
        xs = [spy_returns[d] for d in dates]
        ys = [vix_returns[d] for d in dates]
        avg_x = sum(xs) / len(xs)
        avg_y = sum(ys) / len(ys)
        cov = sum((x - avg_x) * (y - avg_y) for x, y in zip(xs, ys))
        var_x = sum((x - avg_x) ** 2 for x in xs)
        var_y = sum((y - avg_y) ** 2 for y in ys)
        if not var_x or not var_y:
            return None
        return round(cov / ((var_x * var_y) ** 0.5), 3)

    result = {
        "spy": _aggregate(series_map.get("SPY"), period),
        "qqq": _aggregate(series_map.get("QQQ"), period),
        "spy_candles": _aggregate_candles(series_map.get("SPY"), period),
        "qqq_candles": _aggregate_candles(series_map.get("QQQ"), period),
        "vix": _aggregate(series_map.get("^VIX"), period),
        "vxn": _aggregate(series_map.get("^VXN"), period),
        "period": period,
        "meta": {},
        "stats": {},
    }

    vix_data = series_map.get("^VIX", {})
    valid_vix = _valid_closes(vix_data)
    result["latest_vix"] = round(valid_vix[-1], 2) if valid_vix else None
    result["stats"] = {
        "vix_percentile_1y": _vix_percentile(vix_data, 252),
        "spy_vix_corr_30": _spy_vix_correlation(30) if period != "1hour" else None,
    }

    # Meta: data source and point counts
    for sym in symbols:
        raw = series_map.get(sym, {})
        result["meta"][sym] = {
            "source": raw.get("source", "yahoo"),
            "points": len(raw.get("timestamps", [])),
            "error": raw.get("error"),
        }

    return jsonify(result)


# Supported fiat currencies for the exchange-loss tool. Each maps to a Yahoo
# FX symbol plus an inverse flag: inverse=True means the symbol quotes "units
# of the currency per 1 USD" (e.g. CNY=X is USD/CNY), inverse=False means the
# symbol quotes "USD per 1 unit" (e.g. EURUSD=X is EUR/USD). USD is the hub.
FX_CURRENCIES = {
    "USD": (None, False),
    "CNY": ("CNY=X", True),
    "EUR": ("EURUSD=X", False),
    "GBP": ("GBPUSD=X", False),
    "JPY": ("JPY=X", True),
    "HKD": ("HKD=X", True),
    "KRW": ("KRW=X", True),
    "AUD": ("AUDUSD=X", False),
    "SGD": ("SGD=X", True),
    "CAD": ("CAD=X", True),
    "CHF": ("CHF=X", True),
    "TWD": ("TWD=X", True),
}


@price_change_bp.route("/exchange-loss", methods=["POST"])
def exchange_loss():
    """Return the held->target fiat cross-rate daily OHLC history.

    Every supported currency is priced against USD (the hub) via Yahoo FX
    symbols, so any held->target pair's close is
    usd_per_unit[held] / usd_per_unit[target] on shared dates.

    Only the close is a true cross rate — a real intraday high/low cannot be
    derived by dividing two independent currencies' intraday extremes (the
    extremes almost never coincide), so doing so fabricates volatile wicks that
    never happened. We instead build an honest OHLC from the close series:
    open = previous close, high/low = max/min(open, close). Same-currency
    pairs (e.g. USD/USD) therefore collapse to a flat series of 1.0. Weekly/
    monthly k-lines are aggregated client-side from this daily series.

    Request body:
        {"held": "USD", "target": "CNY"}   # 3-letter codes, default USD / CNY

    Returns:
        {"held": "USD", "target": "CNY",
         "series": [{"date": "YYYY-MM-DD", "open": o, "high": h, "low": l, "close": c}, ...],
         "latest": {"date": ..., "rate": ...},
         "meta": {"held": {"source", "points", "error"}, "target": {...}}}
    """
    import concurrent.futures
    from datetime import datetime, timezone

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    held = str(body.get("held", "USD")).upper().strip()
    target = str(body.get("target", "CNY")).upper().strip()
    for code in (held, target):
        if code not in FX_CURRENCIES:
            return jsonify({"error": f"unsupported currency: {code}"}), 400

    def _usd_per_unit(code: str) -> dict:
        """Return {"points": [{date, open, high, low, close}, ...], "source"} where
        each field is USD per 1 unit (inverse-quoted symbols are flipped)."""
        if code == "USD":
            return {"points": [], "source": "usd-basis", "constant": True}
        symbol, inverse = FX_CURRENCIES[code]
        try:
            s = _fetch_daily_series_cached(symbol, "stock")
            # Trust the unified layer's ~5 min negative cache: a transient upstream
            # blip is already cached short-lived, so we do NOT force-refresh here.
            # Re-hitting Yahoo on every request would amplify 429s and timeouts
            # under a sustained outage (two sources × every page load).
            if s and not s.error and s.closes:
                n = len(s.closes)
                opens = getattr(s, "opens", None) or [None] * n
                highs = getattr(s, "highs", None) or [None] * n
                lows = getattr(s, "lows", None) or [None] * n
                points = []
                for ts, o, h, l, c in zip(s.timestamps, opens, highs, lows, s.closes):
                    if c is None or c <= 0:
                        continue
                    o = o if (o is not None and o > 0) else c
                    h = h if (h is not None and h > 0) else c
                    l = l if (l is not None and l > 0) else c
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    if inverse:
                        o, h, l, c = 1.0 / o, 1.0 / l, 1.0 / h, 1.0 / c
                    # Keep full precision; only the final cross OHLC is rounded.
                    points.append({
                        "date": dt.strftime("%Y-%m-%d"),
                        "open": o, "high": h, "low": l, "close": c,
                    })
                return {"points": points, "source": s.source}
            return {"error": s.error if s else "no data"}
        except Exception as e:
            logger.exception("Failed to fetch FX %s: %s", symbol, e)
            return {"error": str(e)}

    codes = sorted({c for c in (held, target) if c != "USD"})
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(len(codes), 1)) as executor:
        futures = {executor.submit(_usd_per_unit, code): code for code in codes}
        for fut in concurrent.futures.as_completed(futures):
            results[futures[fut]] = fut.result()

    # usd_per_unit OHLC maps; missing currency (or USD) means constant 1.
    held_raw = results.get(held) if held != "USD" else None
    target_raw = results.get(target) if target != "USD" else None
    held_points = (held_raw or {}).get("points", [])
    target_points = (target_raw or {}).get("points", [])
    held_ohlc = {p["date"]: p for p in held_points}
    target_ohlc = {p["date"]: p for p in target_points}
    _ONE = {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}

    if held_points and target_points:
        dates = [p["date"] for p in held_points if p["date"] in target_ohlc]
    elif held_points:
        dates = [p["date"] for p in held_points]
    elif target_points:
        dates = [p["date"] for p in target_points]
    else:
        dates = []

    series = []
    prev_close = None
    for d in dates:
        h = held_ohlc.get(d, _ONE)
        t = target_ohlc.get(d, _ONE)
        close = round(h["close"] / t["close"], 6)
        # Honest OHLC from the close series: open = previous close, high/low are
        # bounded by the open/close pair — no synthetic intraday extremes.
        open_v = prev_close if prev_close is not None else close
        series.append({
            "date": d,
            "open": round(open_v, 6),
            "high": round(max(open_v, close), 6),
            "low": round(min(open_v, close), 6),
            "close": close,
        })
        prev_close = close
    # Bound the payload; the default chart counts (730/105/24) are well within it.
    series = series[-2600:]

    def _meta(code, raw, is_usd):
        return {
            "code": code,
            "source": (raw or {}).get("source", "usd-basis"),
            "points": None if is_usd else len((raw or {}).get("points", [])),
            "error": (raw or {}).get("error"),
        }

    result = {
        "held": held,
        "target": target,
        "series": series,
        "latest": {"date": series[-1]["date"], "rate": series[-1]["close"]} if series else None,
        "meta": {
            "held": _meta(held, held_raw, held == "USD"),
            "target": _meta(target, target_raw, target == "USD"),
        },
    }
    return jsonify(result)


# Reference exchange rates for the FX calculator — Frankfurter (ECB) EUR basis.
# 30+ fiat currencies with names/symbols; one snapshot cached in process for a
# day, degraded to a stale snapshot for a week if the upstream blips. The
# calculator derives any pair as amount * rates[target] / rates[base].
_FX_RATES_STATE = {"payload": None, "fetched_at": 0.0}
_FX_RATES_LOCK = _threading.Lock()
_FX_RATES_TTL = 24 * 3600
_FX_RATES_STALE_TTL = 7 * 24 * 3600
_FX_RATES_REQUIRED = ("EUR", "CNY", "USD", "JPY", "KRW", "HKD")
_FX_RATES_URL = "https://api.frankfurter.dev/v2/rates"
_FX_CURRENCIES_URL = "https://api.frankfurter.dev/v2/currencies"


def _valid_fx_payload(payload):
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("rates"), dict)
        or not isinstance(payload.get("currencies"), list)
    ):
        return False
    rates = payload["rates"]
    codes = {item.get("code") for item in payload["currencies"] if isinstance(item, dict)}
    return (
        len(rates) >= 20
        and len(codes) >= 20
        and all(isinstance(rates.get(code), (int, float)) and rates[code] > 0 for code in _FX_RATES_REQUIRED)
        and all(code in codes for code in _FX_RATES_REQUIRED)
    )


def _fetch_fx_remote():
    import requests

    rates_resp = requests.get(_FX_RATES_URL, params={"base": "EUR"}, timeout=10)
    rates_resp.raise_for_status()
    rows = rates_resp.json()
    if not isinstance(rows, list):
        raise ValueError("Unexpected Frankfurter rates response")

    currency_resp = requests.get(_FX_CURRENCIES_URL, timeout=10)
    currency_resp.raise_for_status()
    currency_rows = currency_resp.json()
    if not isinstance(currency_rows, list):
        raise ValueError("Unexpected Frankfurter currency response")

    rates = {"EUR": 1.0}
    dates = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("base") != "EUR":
            continue
        quote, rate = row.get("quote"), row.get("rate")
        if isinstance(quote, str) and len(quote) == 3 and isinstance(rate, (int, float)) and rate > 0:
            rates[quote] = float(rate)
            if row.get("date"):
                dates.add(row["date"])

    currencies = []
    for item in currency_rows:
        if not isinstance(item, dict):
            continue
        code = item.get("iso_code")
        if code not in rates:
            continue
        currencies.append({
            "code": code,
            "name": str(item.get("name") or code),
            "symbol": str(item.get("symbol") or code),
        })
    currencies.sort(key=lambda item: item["code"])

    payload = {
        "date": max(dates) if dates else "",
        "base": "EUR",
        "rates": rates,
        "currencies": currencies,
        "fetched_at": int(time.time()),
    }
    if not _valid_fx_payload(payload):
        raise ValueError("Frankfurter response is incomplete")
    return payload


def _fx_rates_response(payload, stale=False):
    return jsonify({
        "base": payload["base"],
        "date": payload.get("date", ""),
        "rates": payload["rates"],
        "currencies": payload["currencies"],
        "stale": stale,
    })


@price_change_bp.route("/exchange-rates", methods=["GET"])
def exchange_rates():
    """Return Frankfurter (ECB) reference rates for the FX calculator.

    Base is EUR: rates[code] means "1 EUR = <rate> code". Any held->target pair
    is amount * rates[target] / rates[base]. One snapshot is cached in process
    for 24h; a stale snapshot degrades gracefully for 7 days on upstream failure.
    """
    now = time.time()
    with _FX_RATES_LOCK:
        state = _FX_RATES_STATE
        if state["payload"] and now - state["fetched_at"] <= _FX_RATES_TTL:
            return _fx_rates_response(state["payload"])
        try:
            payload = _fetch_fx_remote()
        except Exception as exc:
            logger.warning("event=exchange_rates_remote_failed error_type=%s", type(exc).__name__)
            if state["payload"] and now - state["fetched_at"] <= _FX_RATES_STALE_TTL:
                return _fx_rates_response(state["payload"], stale=True)
            return jsonify({"error": "exchange rates unavailable"}), 502
        state["payload"] = payload
        state["fetched_at"] = now
        return _fx_rates_response(payload)


@price_change_bp.route("/fear-threshold-stats", methods=["POST"])
def fear_threshold_stats():
    """Return SPY/QQQ forward returns after VIX/VXN threshold days."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(run_fear_threshold_stats(body))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to build fear threshold stats: %s", e)
        return jsonify({"error": str(e)}), 500


@price_change_bp.route("/header-trend", methods=["GET"])
def header_trend():
    """Return a downsampled full-history daily close series for the header
    background sparkline. Decoration-only.

    Query params:
        symbol (default "QQQ") -- a US stock/ETF ticker handled by the daily
                                   series fetcher (Yahoo primary, yfinance fallback).
        points (default 240)   -- target sample size, clamped to [60, 400].

    Returns:
        {"symbol": "QQQ",
         "points": [{"date": "YYYY-MM-DD", "close": float}, ...],
         "meta": {"source": str, "points": int, "error": str | None}}

    The series is downsampled server-side so a full listing history (e.g. QQQ
    since 1999, ~6500 daily bars) ships as a few hundred points — light payload
    and a smooth SVG path. Failures degrade gracefully (empty points, HTTP 200)
    so the header simply renders without the decoration.
    """
    from datetime import datetime, timezone

    symbol = (request.args.get("symbol") or "QQQ").strip().upper() or "QQQ"

    try:
        target = int(request.args.get("points", 240))
    except (ValueError, TypeError):
        target = 240
    target = max(60, min(target, 400))

    try:
        series = _fetch_daily_series_cached(symbol, "stock")
    except Exception as e:
        logger.exception("header-trend fetch failed for %s: %s", symbol, e)
        return jsonify({
            "symbol": symbol,
            "points": [],
            "meta": {"source": None, "points": 0, "error": str(e)},
        })

    if not series or series.error or not series.timestamps:
        return jsonify({
            "symbol": symbol,
            "points": [],
            "meta": {
                "source": getattr(series, "source", None) if series else None,
                "points": 0,
                "error": (series.error if series else "no data"),
            },
        })

    # Build (date_str, close) pairs, skipping missing closes, keep order.
    pairs = []
    for ts, close in zip(series.timestamps, series.closes):
        if close is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        pairs.append((dt, round(close, 2)))

    if len(pairs) > target:
        # Even stride downsample; always include first and last samples.
        stride = (len(pairs) - 1) / (target - 1) if target > 1 else len(pairs)
        indices = sorted({0, len(pairs) - 1} | {
            min(len(pairs) - 1, int(round(i * stride))) for i in range(target)
        })
        pairs = [pairs[i] for i in indices]

    return jsonify({
        "symbol": symbol,
        "points": [{"date": d, "close": c} for d, c in pairs],
        "meta": {
            "source": series.source,
            "points": len(pairs),
            "error": None,
        },
    })
