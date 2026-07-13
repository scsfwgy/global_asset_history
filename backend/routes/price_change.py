"""
Yearly price change API blueprint.
"""
import hashlib
import logging
import threading as _threading
import time

from flask import Blueprint, jsonify, request

from service.price_change.price_change_service import (
    _fetch_daily_series_cached,
    fetch_daily_returns,
    fetch_heatmap_data,
    fetch_return_detail,
    fetch_yearly_returns,
    fetch_monthly_returns,
    fetch_monthly_returns_batch,
    fetch_market_pulse,
    get_presets,
    get_color_range,
    get_color_scheme,
    get_site_config,
    run_dca_backtest,
    run_crash_stats,
    get_crash_chart_data,
)

logger = logging.getLogger(__name__)

price_change_bp = Blueprint("price_change", __name__, url_prefix="/api/price-change")


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


@price_change_bp.route("/market-pulse", methods=["GET"])
def market_pulse():
    """Return the latest daily move for the global benchmark strip."""
    try:
        return jsonify(fetch_market_pulse())
    except Exception as e:
        logger.exception("Failed to fetch market pulse: %s", e)
        return jsonify({"error": str(e)}), 500


@price_change_bp.route("/yearly", methods=["POST"])
def get_yearly_returns():
    """Return yearly returns for given symbols.

    Request body:
        {"symbols": [{"symbol": "AAPL", "type": "stock"}, ...]}

    Returns:
        {"years": [...], "data": {"SYMBOL": {"year": pct, ...}, ...}}
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
        {"symbol": "AAPL", "year": 2024, "months": [{"month": 1, "return": 5.2}, ...]}
    """
    body = request.get_json(silent=True) or {}
    symbol = body.get("symbol", "").strip().upper()
    asset_type = body.get("type", "stock").strip().lower()
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
        {"year": 2025, "data": {"AAPL": [{"month": 1, "return": 5.2}, ...], ...}}
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
        return jsonify({"year": year, "data": result})
    except Exception as e:
        logger.exception("Failed to fetch monthly returns batch: %s", e)
        return jsonify({"error": str(e)}), 500


@price_change_bp.route("/daily", methods=["POST"])
def get_daily_returns():
    """Return daily returns for a symbol in a given year and month."""
    body = request.get_json(silent=True) or {}
    symbol = body.get("symbol", "").strip().upper()
    asset_type = body.get("type", "stock").strip().lower()
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
    symbol = body.get("symbol", "").strip().upper()
    asset_type = body.get("type", "stock").strip().lower()
    year = body.get("year")

    if not symbol:
        return jsonify({"error": "symbol is required"}), 400
    if year is not None:
        try:
            year = int(year)
        except (TypeError, ValueError):
            return jsonify({"error": "year must be an integer"}), 400

    try:
        result = fetch_return_detail(symbol, asset_type, year)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to fetch return detail: %s", e)
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
    """Detect single-day crash events and compute recovery metrics.

    Request body:
        {"symbol": "QQQ", "type": "stock", "start_date": "2020-01-01",
         "end_date": "2025-12-31", "threshold_pct": 4.77}
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


def _heatmap_cache_key(symbols: list, period: str, auto_top_n: int, include_market_cap: bool) -> str:
    """Stable cache key for heatmap results."""
    sym_keys = sorted(
        f"{s.get('symbol','').strip().upper()}|{s.get('type','stock').strip().lower()}"
        for s in symbols
    )
    raw = f"hm:{period}:{auto_top_n}:{int(include_market_cap)}:{','.join(sym_keys)}"
    return hashlib.md5(raw.encode()).hexdigest()


@price_change_bp.route("/heatmap", methods=["POST"])
def heatmap():
    """Return treemap heatmap data: per-symbol return + turnover over a period.

    Request body:
        {"symbols": [{"symbol": "AAPL", "type": "stock"}, ...],
         "period": "today|week|month|quarter|year",
         "auto_top_n": 20,              # optional: auto-include top US stocks
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
    period = str(body.get("period", "week")).strip().lower()
    auto_top_n = int(body.get("auto_top_n", 0) or 0)
    include_market_cap = bool(body.get("include_market_cap", False))
    force = bool(body.get("force", False))

    # auto_top_n allows calling without explicit symbols
    if not symbols and auto_top_n <= 0:
        return jsonify({"error": "symbols list is required (or set auto_top_n > 0)"}), 400

    valid_periods = {"today", "week", "month", "quarter", "year"}
    if period not in valid_periods:
        return jsonify({"error": f"period must be one of: {', '.join(sorted(valid_periods))}"}), 400

    # Check cache (skip when force=true)
    cache_key = _heatmap_cache_key(symbols, period, auto_top_n, include_market_cap)
    if not force:
        now = time.time()
        with _heatmap_cache_lock:
            entry = _heatmap_cache.get(cache_key)
            if entry:
                if now - entry["ts"] < _HEATMAP_CACHE_TTL:
                    logger.info("Heatmap cache hit for %s", cache_key[:12])
                    result = dict(entry["data"])
                    result["cached"] = True
                    return jsonify(result)
                # Expired — delete it to free memory
                del _heatmap_cache[cache_key]

    try:
        result = fetch_heatmap_data(symbols, period, auto_top_n=auto_top_n,
                                    include_market_cap=include_market_cap)
    except Exception as e:
        logger.exception("Failed to fetch heatmap data: %s", e)
        return jsonify({"error": str(e)}), 500

    # Store in cache
    with _heatmap_cache_lock:
        _heatmap_cache[cache_key] = {"ts": time.time(), "data": dict(result)}

    return jsonify(result)


@price_change_bp.route("/vix-comparison", methods=["POST"])
def vix_comparison():
    """Return SPY, QQQ, VIX data aggregated by period.

    Request body:
        {"period": "1hour|daily|weekly|monthly", "count": 30}

    Returns:
        {"spy": [...], "qqq": [...], "vix": [...],
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
    symbols = ["SPY", "QQQ", "^VIX"]
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
            return {"timestamps": timestamps, "closes": closes}
        except (KeyError, IndexError, TypeError) as e:
            return {"error": f"parse error: {e}"}

    if period == "1hour":
        # Intraday: fetch directly
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
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
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
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
        "vix": _aggregate(series_map.get("^VIX"), period),
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
    for sym in ("SPY", "QQQ", "^VIX"):
        raw = series_map.get(sym, {})
        result["meta"][sym] = {
            "source": raw.get("source", "yahoo"),
            "points": len(raw.get("timestamps", [])),
            "error": raw.get("error"),
        }

    return jsonify(result)


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
