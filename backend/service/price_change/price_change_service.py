"""Public API and orchestration for the price change feature."""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from .calculations import (
    _build_equity_curve,
    _compute_daily_returns_for_month,
    _compute_monthly_returns,
    _compute_money_weighted_annualized_return,
    _compute_yearly_returns,
    _generate_schedule_dates,
    _normalize_frequency,
    _parse_iso_date,
    _resolve_execution_points,
    _safe_int,
    _series_points_in_range,
)
from .crash_stats import compute_crash_statistics
from .common import (
    DAILY_SERIES_TTL_SECONDS,
    ERROR_CACHE_TTL_SECONDS,
    MAX_YEARLY_WORKERS,
    REQUEST_TIMEOUT,
    PriceSeries,
    empty_series,
)
from .config import get_color_range, get_color_scheme, get_presets, get_site_config
from .fetchers import DAILY_SERIES_FETCHERS, FETCHERS
from . import cache_store

logger = logging.getLogger(__name__)

# L1: in-process cache (fast, but per-instance — wiped on serverless cold start).
# L2: shared Upstash Redis (cross-instance, survives cold starts). Falls back to
# L1-only when Redis is not configured (local dev).
_DAILY_SERIES_CACHE: Dict[Tuple[str, str], PriceSeries] = {}
_CACHE_LOCK = threading.RLock()

_FETCHERS: Dict[str, Callable[[str], Dict[str, float]]] = dict(FETCHERS)
_DAILY_SERIES_FETCHERS: Dict[str, Callable[[str], PriceSeries]] = dict(DAILY_SERIES_FETCHERS)


def _cache_ttl(series: PriceSeries) -> int:
    return ERROR_CACHE_TTL_SECONDS if series.error else DAILY_SERIES_TTL_SECONDS


# Bump this whenever the cached PriceSeries shape changes, so old entries (which
# lack new fields) are abandoned instead of served stale. v3 added volumes.
_CACHE_SCHEMA_VERSION = "v3"


def _redis_key(symbol: str, asset_type: str) -> str:
    return f"{_CACHE_SCHEMA_VERSION}:daily:{asset_type}:{symbol}"


def _serialize_series(series: PriceSeries) -> str:
    return json.dumps(asdict(series), separators=(",", ":"))


def _deserialize_series(raw: str) -> Optional[PriceSeries]:
    try:
        return PriceSeries(**json.loads(raw))
    except (ValueError, TypeError) as e:
        logger.warning("Failed to deserialize cached series: %s", e)
        return None


def _get_cached_daily_series(symbol: str, asset_type: str) -> PriceSeries | None:
    key = (asset_type, symbol)
    now = time.time()
    # L1 — in-process
    with _CACHE_LOCK:
        series = _DAILY_SERIES_CACHE.get(key)
        if series:
            if now - series.fetched_at < _cache_ttl(series):
                return series
            # Expired — delete it to free memory
            del _DAILY_SERIES_CACHE[key]
    # L2 — shared Redis. Redis EX handles expiry, but re-check fetched_at to
    # guard against clock skew between the writer and this reader.
    raw = cache_store.cache_get(_redis_key(symbol, asset_type))
    if raw:
        series = _deserialize_series(raw)
        if series and now - series.fetched_at < _cache_ttl(series):
            with _CACHE_LOCK:
                _DAILY_SERIES_CACHE[key] = series  # warm L1
            return series
    return None


def _set_cached_daily_series(symbol: str, asset_type: str, series: PriceSeries) -> PriceSeries:
    key = (asset_type, symbol)
    with _CACHE_LOCK:
        _DAILY_SERIES_CACHE[key] = series
    cache_store.cache_set(_redis_key(symbol, asset_type), _serialize_series(series), _cache_ttl(series))
    return series


def clear_price_change_cache() -> None:
    """Clear in-memory market-data cache. Mainly useful for tests."""
    with _CACHE_LOCK:
        _DAILY_SERIES_CACHE.clear()


def _series_meta(symbol: str, asset_type: str, series: PriceSeries) -> Dict:
    return {
        "symbol": symbol,
        "type": asset_type,
        "source": series.source,
        "updated_at": datetime.fromtimestamp(series.fetched_at, tz=timezone.utc).isoformat(),
        "error": series.error,
        "points": len(series.timestamps),
    }


def register_fetcher(asset_type: str, fetcher: Callable[[str], Dict[str, float]]) -> None:
    """Register a custom yearly fetcher for a new asset type."""
    _FETCHERS[asset_type] = fetcher


def register_daily_series_fetcher(asset_type: str, fetcher: Callable[[str], PriceSeries]) -> None:
    """Register a daily-series fetcher for a new asset type."""
    _DAILY_SERIES_FETCHERS[asset_type] = fetcher


def _normalize_symbol_entry(entry: Dict[str, str]) -> Tuple[str, str]:
    symbol = entry["symbol"].strip().upper()
    asset_type = entry.get("type", "stock").strip().lower()
    return symbol, asset_type


def _fetch_daily_series_cached(symbol: str, asset_type: str) -> PriceSeries:
    cached = _get_cached_daily_series(symbol, asset_type)
    if cached is not None:
        return cached

    fetcher = _DAILY_SERIES_FETCHERS.get(asset_type)
    if fetcher is None:
        return empty_series(None, f"unknown asset type: {asset_type}")

    logger.info("Fetching daily series for %s (%s)", symbol, asset_type)
    try:
        series = fetcher(symbol)
    except Exception as e:
        logger.exception("Failed to fetch daily series for %s (%s): %s", symbol, asset_type, e)
        series = empty_series(None, str(e))

    return _set_cached_daily_series(symbol, asset_type, series)


def _fetch_one_yearly(entry: Dict[str, str]) -> Tuple[str, Dict[str, float], Dict]:
    symbol, asset_type = _normalize_symbol_entry(entry)

    if not symbol:
        return symbol, {}, {
            "symbol": symbol,
            "type": asset_type,
            "source": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "error": "empty symbol",
            "points": 0,
        }

    if asset_type in _DAILY_SERIES_FETCHERS:
        series = _fetch_daily_series_cached(symbol, asset_type)
        yearly = {} if series.error else _compute_yearly_returns(series.timestamps, series.closes)
        meta = _series_meta(symbol, asset_type, series)
        if not yearly and not meta["error"]:
            meta["error"] = "insufficient data"
        return symbol, yearly, meta

    fetcher = _FETCHERS.get(asset_type)
    if fetcher is None:
        now = datetime.now(timezone.utc).isoformat()
        return symbol, {}, {
            "symbol": symbol,
            "type": asset_type,
            "source": None,
            "updated_at": now,
            "error": f"unknown asset type: {asset_type}",
            "points": 0,
        }

    try:
        yearly = fetcher(symbol)
        now = datetime.now(timezone.utc).isoformat()
        return symbol, yearly, {
            "symbol": symbol,
            "type": asset_type,
            "source": "custom",
            "updated_at": now,
            "error": None if yearly else "insufficient data",
            "points": None,
        }
    except Exception as e:
        logger.exception("Custom fetcher failed for %s (%s): %s", symbol, asset_type, e)
        now = datetime.now(timezone.utc).isoformat()
        return symbol, {}, {
            "symbol": symbol,
            "type": asset_type,
            "source": "custom",
            "updated_at": now,
            "error": str(e),
            "points": 0,
        }


def fetch_yearly_returns(symbols: List[Dict[str, str]]) -> dict:
    """Fetch yearly returns for a list of symbols."""
    data: Dict[str, Dict[str, float]] = {}
    meta: Dict[str, Dict] = {}
    all_years: set = set()
    normalized_entries = []
    seen_keys = set()

    for entry in symbols:
        try:
            symbol, asset_type = _normalize_symbol_entry(entry)
        except KeyError:
            logger.warning("Skipping symbol entry without symbol: %s", entry)
            continue
        key = (symbol, asset_type)
        if not symbol or key in seen_keys:
            continue
        seen_keys.add(key)
        normalized_entries.append({"symbol": symbol, "type": asset_type})

    worker_count = min(MAX_YEARLY_WORKERS, max(1, len(normalized_entries)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(_fetch_one_yearly, entry) for entry in normalized_entries]
        for future in as_completed(futures):
            symbol, yearly, symbol_meta = future.result()
            data[symbol] = yearly
            meta[symbol] = symbol_meta
            all_years.update(yearly.keys())

    ordered_data = {}
    ordered_meta = {}
    for entry in normalized_entries:
        symbol = entry["symbol"]
        yearly = data.get(symbol, {})
        ordered_data[symbol] = yearly
        ordered_meta[symbol] = meta.get(symbol, {
            "symbol": symbol,
            "type": entry["type"],
            "source": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "error": "not fetched",
            "points": 0,
        })

    return {
        "years": sorted(all_years, reverse=True),
        "data": ordered_data,
        "meta": ordered_meta,
    }


def fetch_monthly_returns(symbol: str, asset_type: str, year: int) -> list:
    """Fetch monthly returns for a symbol in a given year."""
    logger.info("Fetching monthly returns for %s (%s) year %d", symbol, asset_type, year)
    clean_sym = symbol.strip().upper()
    clean_type = asset_type.strip().lower()

    if clean_type not in _DAILY_SERIES_FETCHERS:
        return _compute_monthly_returns([], [], year)

    series = _fetch_daily_series_cached(clean_sym, clean_type)
    if series.error:
        return _compute_monthly_returns([], [], year)
    return _compute_monthly_returns(series.timestamps, series.closes, year)


def fetch_daily_returns(symbol: str, asset_type: str, year: int, month: int) -> list:
    """Fetch daily returns for a symbol in a given month."""
    logger.info("Fetching daily returns for %s (%s) %d-%02d", symbol, asset_type, year, month)
    clean_sym = symbol.strip().upper()
    clean_type = asset_type.strip().lower()

    if clean_type not in _DAILY_SERIES_FETCHERS:
        return []

    series = _fetch_daily_series_cached(clean_sym, clean_type)
    if series.error:
        return []
    return _compute_daily_returns_for_month(series.timestamps, series.closes, year, month)


def fetch_monthly_returns_batch(symbols: List[Dict[str, str]], year: int) -> Dict[str, list]:
    """Fetch monthly returns for multiple symbols in a given year."""
    data: Dict[str, list] = {}
    for entry in symbols:
        try:
            symbol = entry["symbol"].strip().upper()
            asset_type = entry.get("type", "stock").strip().lower()
        except (KeyError, AttributeError):
            continue
        if symbol:
            data[symbol] = fetch_monthly_returns(symbol, asset_type, year)
    return data


def _avg(values: List[float]) -> Optional[float]:
    return round(sum(values) / len(values), 2) if values else None


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    if n % 2 == 1:
        return round(ordered[n // 2], 2)
    return round((ordered[n // 2 - 1] + ordered[n // 2]) / 2, 2)


def _win_rate(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(1 for v in values if v > 0) / len(values) * 100, 1)


def _build_monthly_stats(month_values: Dict[int, List[float]]) -> List[Dict]:
    stats = []
    for month in range(1, 13):
        values = month_values.get(month, [])
        stats.append({
            "month": month,
            "avg": _avg(values),
            "median": _median(values),
            "total": round(sum(values), 2) if values else None,
            "count": len(values),
        })
    return stats


def _row_stats(month_values: List[Optional[float]]) -> Dict:
    """Compute avg, median, total across 12 month cells for one row."""
    clean = [v for v in month_values if v is not None]
    if not clean:
        return {"avg": None, "median": None, "total": None}
    return {
        "avg": _avg(clean),
        "median": _median(clean),
        "total": round(sum(clean), 2),
    }


def _compute_daily_grid(series: PriceSeries, year: int) -> List[Dict]:
    """Compute daily returns grouped by (day, month) for a single year.

    Returns rows for days 1-31, each with 12 month cells.
    """
    daily_grid: Dict[Tuple[int, int], float] = {}
    prev_close: Optional[float] = None

    for ts, close in zip(series.timestamps, series.closes):
        if close is None:
            continue
        dt_date = datetime.fromtimestamp(ts, tz=timezone.utc)
        daily_ret = None
        if prev_close is not None and prev_close != 0:
            daily_ret = round((close / prev_close - 1) * 100, 2)
        if dt_date.year == year:
            daily_grid[(dt_date.day, dt_date.month)] = daily_ret
        prev_close = close

    daily_rows = []
    for day in range(1, 32):
        month_data = []
        for month in range(1, 13):
            month_data.append({"month": month, "return": daily_grid.get((day, month))})
        daily_rows.append({"day": day, "months": month_data})
    return daily_rows


def fetch_return_detail(symbol: str, asset_type: str, year: Optional[int] = None) -> Dict:
    """Fetch single-symbol yearly/monthly return detail, or daily grid for a specific year."""
    clean_sym = symbol.strip().upper()
    clean_type = asset_type.strip().lower()
    if not clean_sym:
        raise ValueError("symbol is required")
    if clean_type not in _DAILY_SERIES_FETCHERS:
        raise ValueError(f"unknown asset type: {clean_type}")

    series = _fetch_daily_series_cached(clean_sym, clean_type)
    if series.error:
        raise ValueError(series.error)

    yearly = _compute_yearly_returns(series.timestamps, series.closes)
    years = sorted((int(y) for y in yearly.keys()), reverse=True)
    if not years:
        raise ValueError("insufficient data")

    # -- yearly mode ---------------------------------------------------------
    if year is None:
        month_values: Dict[int, List[float]] = {m: [] for m in range(1, 13)}
        year_values: List[float] = []
        best_month = None
        worst_month = None
        monthly_rows = []

        for y in years:
            months = _compute_monthly_returns(series.timestamps, series.closes, y)
            clean_months = []
            for item in months:
                month = int(item["month"])
                value = item["return"]
                if value is not None:
                    month_values[month].append(float(value))
                    point = {"year": y, "month": month, "return": float(value)}
                    if best_month is None or point["return"] > best_month["return"]:
                        best_month = point
                    if worst_month is None or point["return"] < worst_month["return"]:
                        worst_month = point
                clean_months.append({"month": month, "return": value})
            y_ret = yearly.get(str(y))
            if y_ret is not None:
                year_values.append(float(y_ret))
            month_vals = [m["return"] for m in clean_months]
            monthly_rows.append({
                "year": y,
                "annual_return": y_ret,
                "months": clean_months,
                "row_stats": _row_stats(month_vals),
            })

        return {
            "symbol": clean_sym,
            "type": clean_type,
            "mode": "yearly",
            "source": series.source,
            "meta": _series_meta(clean_sym, clean_type, series),
            "years": years,
            "rows": monthly_rows,
            "stats": _build_monthly_stats(month_values),
            "summary": {
                "year_count": len(years),
                "avg_yearly_return": _avg(year_values),
                "median_yearly_return": _median(year_values),
                "yearly_win_rate": _win_rate(year_values),
                "best_month": best_month,
                "worst_month": worst_month,
            },
        }

    # -- daily mode ----------------------------------------------------------
    if year not in years:
        raise ValueError(f"year {year} not in available data")

    daily_rows = _compute_daily_grid(series, year)
    month_values: Dict[int, List[float]] = {m: [] for m in range(1, 13)}
    for row in daily_rows:
        month_vals = [m["return"] for m in row["months"]]
        row["row_stats"] = _row_stats(month_vals)
        for m in row["months"]:
            if m["return"] is not None:
                month_values[m["month"]].append(m["return"])

    return {
        "symbol": clean_sym,
        "type": clean_type,
        "mode": "daily",
        "year": year,
        "source": series.source,
        "meta": _series_meta(clean_sym, clean_type, series),
        "years": years,
        "daily_rows": daily_rows,
        "stats": _build_monthly_stats(month_values),
        "summary": {
            "year_count": len(years),
            "selected_year": year,
        },
    }


def run_dca_backtest(payload: Dict) -> Dict:
    """Run a single-symbol DCA backtest using daily price data."""
    symbol = str(payload.get("symbol", "")).strip().upper()
    asset_type = str(payload.get("type", "stock")).strip().lower()
    start_date = _parse_iso_date(payload.get("start_date"), "start_date")
    end_date = _parse_iso_date(payload.get("end_date"), "end_date")
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    frequency = _normalize_frequency(payload.get("frequency", "monthly"))
    interval = max(1, _safe_int(payload.get("interval"), 1))
    amount = float(payload.get("amount", 0) or 0)
    initial_amount = float(payload.get("initial_amount", 0) or 0)
    day_of_month = _safe_int(payload.get("day_of_month"), start_date.day)
    weekday = payload.get("weekday")
    weekday = None if weekday in (None, "") else max(0, min(6, _safe_int(weekday, 0)))

    if not symbol:
        raise ValueError("symbol is required")
    if amount <= 0 and initial_amount <= 0:
        raise ValueError("amount or initial_amount must be greater than 0")

    series = _fetch_daily_series_cached(symbol, asset_type)
    if series.error:
        raise ValueError(series.error)

    price_points = _series_points_in_range(series.timestamps, series.closes, start_date, end_date)
    if not price_points:
        raise ValueError("no price data in selected date range")

    schedule_dates = _generate_schedule_dates(
        start_date=start_date,
        end_date=end_date,
        frequency=frequency,
        interval=interval,
        anchor_day=day_of_month,
        weekday=weekday,
    )
    execution_dates = _resolve_execution_points(price_points, schedule_dates)

    cashflows: List[dict] = []
    irr_cashflows: List[Tuple] = []
    executed_points: List[Tuple] = []
    cumulative_units = 0.0

    first_trade_date, first_trade_price = price_points[0]
    if initial_amount > 0:
        initial_units = initial_amount / first_trade_price
        cumulative_units += initial_units
        irr_cashflows.append((first_trade_date, -initial_amount))
        cashflows.append({
            "date": first_trade_date.isoformat(),
            "planned_date": start_date.isoformat(),
            "amount": round(initial_amount, 2),
            "price": round(first_trade_price, 6),
            "units": round(initial_units, 8),
            "cum_units": round(cumulative_units, 8),
            "kind": "initial",
        })

    for exec_date, price in execution_dates:
        if amount <= 0:
            break
        units = amount / price
        cumulative_units += units
        irr_cashflows.append((exec_date, -amount))
        executed_points.append((exec_date, price, amount, units, cumulative_units))
        cashflows.append({
            "date": exec_date.isoformat(),
            "planned_date": exec_date.isoformat(),
            "amount": round(amount, 2),
            "price": round(price, 6),
            "units": round(units, 8),
            "cum_units": round(cumulative_units, 8),
            "kind": "recurring",
        })

    equity_curve = _build_equity_curve(
        price_points=price_points,
        executed_points=executed_points,
        initial_amount=initial_amount,
        initial_date=first_trade_date if initial_amount > 0 else None,
        initial_price=first_trade_price if initial_amount > 0 else None,
    )

    invested = initial_amount + amount * len(executed_points)
    last_date, last_price = price_points[-1]
    final_value = cumulative_units * last_price
    profit = final_value - invested
    return_pct = 0.0 if invested == 0 else (profit / invested) * 100
    money_weighted_return = _compute_money_weighted_annualized_return(
        cashflows=irr_cashflows,
        final_date=last_date,
        final_value=final_value,
    )
    annualized_return_pct = (money_weighted_return or 0.0) * 100

    return {
        "symbol": symbol,
        "type": asset_type,
        "source": series.source,
        "frequency": frequency,
        "interval": interval,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "summary": {
            "invested": round(invested, 2),
            "final_value": round(final_value, 2),
            "profit": round(profit, 2),
            "return_pct": round(return_pct, 2),
            "annualized_return_pct": round(annualized_return_pct, 2),
            "trade_count": len(cashflows),
            "last_price": round(last_price, 6),
        },
        "cashflows": cashflows,
        "equity_curve": equity_curve,
    }


def run_crash_stats(payload: Dict) -> Dict:
    """Analyze single-day crash events and recovery for a symbol.

    Request payload:
        symbol: str (e.g. "QQQ")
        type: str (asset type, default "stock")
        start_date: str (YYYY-MM-DD)
        end_date: str (YYYY-MM-DD)
        threshold_pct: float (e.g. 4.77 = drop >= 4.77%)

    Returns:
        dict with crashes list and summary statistics.
    """
    symbol = str(payload.get("symbol", "")).strip().upper()
    asset_type = str(payload.get("type", "stock")).strip().lower()
    start_date = _parse_iso_date(payload.get("start_date"), "start_date")
    end_date = _parse_iso_date(payload.get("end_date"), "end_date")
    threshold_pct = float(payload.get("threshold_pct", 4.77))

    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    if not symbol:
        raise ValueError("symbol is required")
    if threshold_pct <= 0:
        raise ValueError("threshold_pct must be positive")

    series = _fetch_daily_series_cached(symbol, asset_type)
    if series.error:
        raise ValueError(series.error)

    crashes = compute_crash_statistics(
        timestamps=series.timestamps,
        closes=series.closes,
        start_date=start_date,
        end_date=end_date,
        threshold_pct=threshold_pct,
    )

    # Summary stats
    total = len(crashes)
    recovered_count = sum(1 for c in crashes if c["recovered"])
    recovery_days_list = [c["recovery_days"] for c in crashes if c["recovery_days"] is not None]
    avg_recovery = round(sum(recovery_days_list) / len(recovery_days_list), 1) if recovery_days_list else None
    median_recovery = None
    if recovery_days_list:
        sorted_days = sorted(recovery_days_list)
        n = len(sorted_days)
        if n % 2 == 0:
            median_recovery = round((sorted_days[n // 2 - 1] + sorted_days[n // 2]) / 2, 1)
        else:
            median_recovery = round(float(sorted_days[n // 2]), 1)
    max_drop = min((c["drop_pct"] for c in crashes), default=None)
    avg_drop = round(sum(c["drop_pct"] for c in crashes) / len(crashes), 2) if crashes else None

    return {
        "symbol": symbol,
        "type": asset_type,
        "source": series.source,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "threshold_pct": threshold_pct,
        "summary": {
            "total_crashes": total,
            "recovered": recovered_count,
            "not_recovered": total - recovered_count,
            "avg_recovery_days": avg_recovery,
            "median_recovery_days": median_recovery,
            "max_drop_pct": max_drop,
            "avg_drop_pct": avg_drop,
        },
        "crashes": crashes,
    }


def get_crash_chart_data(payload: Dict) -> Dict:
    """Return a window of daily close prices around a crash for charting.

    Request payload:
        symbol: str
        type: str (asset type)
        pre_crash_date: str (YYYY-MM-DD) — the trading day before the crash
        trading_days: int (default 30) — how many trading days after crash to include

    Returns:
        dict with prices list [{date, close}] for the window.
    """
    symbol = str(payload.get("symbol", "")).strip().upper()
    asset_type = str(payload.get("type", "stock")).strip().lower()
    pre_crash_date = _parse_iso_date(payload.get("pre_crash_date"), "pre_crash_date")
    trading_days = _safe_int(payload.get("trading_days"), 30)

    if not symbol:
        raise ValueError("symbol is required")
    if trading_days < 1 or trading_days > 250:
        raise ValueError("trading_days must be between 1 and 250")

    series = _fetch_daily_series_cached(symbol, asset_type)
    if series.error:
        raise ValueError(series.error)

    # Build (date, close, open, high, low) list. OHLC arrays are optional and
    # aligned with timestamps; index into them only when present and valid.
    has_ohlc = bool(series.opens and series.highs and series.lows)
    n = len(series.timestamps)

    def _ohlc_at(arr, i):
        if arr is None or i >= len(arr) or arr[i] is None:
            return None
        return float(arr[i])

    points: list = []
    for i in range(n):
        close = series.closes[i] if i < len(series.closes) else None
        if close is None:
            continue
        dt = datetime.fromtimestamp(series.timestamps[i], tz=timezone.utc).date()
        points.append((
            dt, float(close),
            _ohlc_at(series.opens, i),
            _ohlc_at(series.highs, i),
            _ohlc_at(series.lows, i),
        ))

    # Find the index of pre_crash_date
    start_idx = None
    for idx, point in enumerate(points):
        if point[0] == pre_crash_date:
            start_idx = idx
            break

    if start_idx is None:
        raise ValueError(f"pre_crash_date {pre_crash_date.isoformat()} not found in price data")

    # Extract window: from pre_crash_date through the next trading_days trading days
    # That's start_idx (pre-crash day) + trading_days+1 data points
    end_idx = min(start_idx + trading_days + 1, len(points))
    window = points[start_idx:end_idx]

    def _price_point(d, c, o, h, low):
        p = {"date": d.isoformat(), "close": round(c, 6)}
        if o is not None and h is not None and low is not None:
            p["open"] = round(o, 6)
            p["high"] = round(h, 6)
            p["low"] = round(low, 6)
        return p

    prices = [_price_point(*pt) for pt in window]
    # Only advertise candlestick data when every point in the window has OHLC.
    window_has_ohlc = has_ohlc and all("open" in p for p in prices)

    pre_crash_close = prices[0]["close"] if prices else None

    return {
        "symbol": symbol,
        "type": asset_type,
        "pre_crash_date": pre_crash_date.isoformat(),
        "pre_crash_close": pre_crash_close,
        "trading_days": trading_days,
        "has_ohlc": window_has_ohlc,
        "prices": prices,
    }


_TURNOVER_CURRENCY = {
    "stock": "USD",
    "crypto": "USDT",
    "cn_stock": "CNY",
}

# Comprehensive watchlist of high-volume US stocks & ETFs.
# The ranking is computed dynamically from actual turnover in the selected
# period — the list below just ensures we have broad coverage of candidates.
_HEATMAP_US_WATCHLIST = [
    # Major ETFs
    "SPY", "QQQ", "IWM", "DIA", "TLT", "HYG", "LQD", "EEM", "EFA", "GLD",
    "VOO", "VTI", "VEA", "VWO", "BND", "ARKK", "XLE", "XLF", "XLV", "SMH",
    # Mega-cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
    # Large-cap tech / semis
    "AVGO", "ADBE", "CRM", "INTC", "AMD", "QCOM", "CSCO", "ORCL", "IBM",
    "NFLX", "UBER", "PYPL", "NOW", "PANW", "SNOW", "PLTR", "ARM",
    # Finance
    "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "C", "BLK", "SCHW",
    # Healthcare
    "LLY", "UNH", "JNJ", "ABBV", "MRK", "PFE", "TMO", "AMGN", "ISRG", "GILD",
    # Consumer / retail
    "WMT", "HD", "PG", "KO", "PEP", "COST", "NKE", "MCD", "SBUX", "LOW", "TGT",
    # Energy / industrial
    "XOM", "CVX", "CAT", "BA", "GE", "RTX", "LMT",
    # Other large cap
    "DIS", "VZ", "T", "CMCSA", "NEE", "SPGI",
]


def _fetch_heatmap_watchlist() -> List[str]:
    """Return the watchlist symbols. Kept as a function for future extensibility
    (e.g. adding a secondary live source when available)."""
    return list(_HEATMAP_US_WATCHLIST)

_PERIOD_LABELS = {
    "today": "1d",
    "week": "1w",
    "month": "1m",
    "quarter": "3m",
    "year": "1y",
}


def _period_start_ts(period: str) -> int:
    """Return the UTC timestamp for the start of the given period."""
    now = datetime.now(timezone.utc)
    if period == "today":
        dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        # Monday of current week
        weekday = now.weekday()  # 0=Monday
        dt = (now - __import__("datetime").timedelta(days=weekday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif period == "month":
        dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "quarter":
        q_month = ((now.month - 1) // 3) * 3 + 1
        dt = now.replace(month=q_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "year":
        dt = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        # Default to month
        dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(dt.timestamp())


def _period_label(period: str) -> str:
    """Return a human-readable label for the period."""
    now = datetime.now(timezone.utc)
    if period == "today":
        return now.strftime("%Y-%m-%d")
    elif period == "week":
        return f"{now.strftime('%Y')}-W{now.isocalendar()[1]:02d}"
    elif period == "month":
        return now.strftime("%Y-%m")
    elif period == "quarter":
        q = (now.month - 1) // 3 + 1
        return f"{now.year}-Q{q}"
    elif period == "year":
        return str(now.year)
    return now.strftime("%Y-%m")


# ── Market-cap fetch (best-effort, for heatmap "size by" dimension) ──
# Primary: Yahoo v7/quote, batched (one request for all symbols), authenticated
# with a cached crumb and browser impersonation — this is the reliable path from
# an overseas (US) server. Fallback: East Money f116 (per-symbol, China-domestic
# — reachable when Yahoo is blocked). Results cached 24h.
#
# Why not yfinance.fast_info.market_cap: it fires a *second*, separately
# rate-limited Yahoo request (get_shares_full) per symbol and routinely raises
# YFRateLimitError, so it silently fell through to the slow China fallback.
_market_cap_cache: Dict[str, Tuple[float, float]] = {}  # symbol -> (cap, ts)
_market_cap_lock = threading.Lock()
_MARKET_CAP_TTL = 24 * 60 * 60  # 24 hours

import requests as _requests

# East Money is a direct domestic API — bypass any ambient proxy (trust_env),
# which on some dev machines routes through a flaky proxy and fails.
_EM_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
_em_session = _requests.Session()
_em_session.trust_env = False
_em_session.headers.update({"User-Agent": "Mozilla/5.0"})

# Yahoo quote endpoint. Prefer curl_cffi (browser TLS impersonation dodges the
# bot throttling that plain requests hits); fall back to requests if absent.
_YH_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
_YH_CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
_YH_COOKIE_URL = "https://fc.yahoo.com"
_YH_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
_YH_BATCH = 50              # symbols per quote request
_YH_CRUMB_TTL = 60 * 60     # re-prime crumb/cookies hourly

try:
    from curl_cffi import requests as _creq
    _yh_session = _creq.Session(impersonate="chrome", trust_env=False)
except Exception:  # pragma: no cover - curl_cffi optional
    _yh_session = _requests.Session()
    _yh_session.trust_env = False
    _yh_session.headers.update({"User-Agent": _YH_UA})

_yh_crumb: Optional[str] = None
_yh_crumb_ts: float = 0.0
_yh_crumb_lock = threading.Lock()


def _yahoo_crumb() -> Optional[str]:
    """Return a cached Yahoo crumb, priming cookies + crumb hourly."""
    global _yh_crumb, _yh_crumb_ts
    with _yh_crumb_lock:
        if _yh_crumb and time.time() - _yh_crumb_ts < _YH_CRUMB_TTL:
            return _yh_crumb
        try:
            _yh_session.get(_YH_COOKIE_URL, timeout=8)
            r = _yh_session.get(_YH_CRUMB_URL, timeout=8)
            crumb = (r.text or "").strip()
            # A valid crumb is a short token, never an HTML error page.
            if crumb and "<" not in crumb and len(crumb) < 64:
                _yh_crumb = crumb
                _yh_crumb_ts = time.time()
                return _yh_crumb
            logger.debug("Yahoo crumb fetch returned non-token (status %s)", r.status_code)
        except Exception as e:
            logger.debug("Yahoo crumb fetch failed: %s", e)
    return None


def _yahoo_market_caps(symbols: List[str]) -> Dict[str, float]:
    """Batched Yahoo v7/quote market-cap lookup. Returns {symbol: cap}."""
    out: Dict[str, float] = {}
    crumb = _yahoo_crumb()
    if not crumb:
        return out
    for i in range(0, len(symbols), _YH_BATCH):
        chunk = symbols[i:i + _YH_BATCH]
        try:
            r = _yh_session.get(
                _YH_QUOTE_URL,
                params={"symbols": ",".join(chunk), "crumb": crumb},
                timeout=10,
            )
            if r.status_code != 200:
                logger.debug("Yahoo quote batch %s returned %s", i // _YH_BATCH, r.status_code)
                continue
            results = (r.json().get("quoteResponse") or {}).get("result") or []
            for q in results:
                sym = q.get("symbol")
                mc = q.get("marketCap")
                if sym and mc and float(mc) > 0:
                    out[sym.upper()] = float(mc)
        except Exception as e:
            logger.debug("Yahoo quote batch failed: %s", e)
            continue
    return out


def _yahoo_quote_batch(symbols: List[str]) -> List[dict]:
    """Fetch quote data for multiple US stocks in a single batch request.

    Uses Yahoo v7/quote endpoint. Returns list of dicts with keys:
    symbol, name, price, change_pct, volume, market_cap.
    Returns empty list on failure (crumb unavailable, network error, etc.).
    """
    crumb = _yahoo_crumb()
    if not crumb:
        return []

    results: List[dict] = []
    for i in range(0, len(symbols), _YH_BATCH):
        chunk = symbols[i:i + _YH_BATCH]
        try:
            r = _yh_session.get(
                _YH_QUOTE_URL,
                params={"symbols": ",".join(chunk), "crumb": crumb},
                timeout=10,
            )
            if r.status_code != 200:
                logger.debug("Yahoo quote batch returned %s", r.status_code)
                continue
            quotes = (r.json().get("quoteResponse") or {}).get("result") or []
            for q in quotes:
                sym = q.get("symbol", "").upper()
                price = q.get("regularMarketPrice")
                if not sym or price is None:
                    continue
                results.append({
                    "symbol": sym,
                    "name": q.get("shortName") or q.get("longName"),
                    "price": price,
                    "change_pct": q.get("regularMarketChangePercent"),
                    "volume": q.get("regularMarketVolume"),
                    "market_cap": q.get("marketCap"),
                })
        except Exception as e:
            logger.debug("Yahoo quote batch failed: %s", e)
            continue
    return results


def _build_heatmap_today(
    unique_entries: List[Tuple[str, str]],
    user_symbols_set: set,
    auto_syms: set,
    auto_top_n: int,
    include_market_cap: bool,
    compute_fn: Callable,
) -> Optional[dict]:
    """Build heatmap data for period='today' using batch v7/quote.

    Stocks are fetched in a single batch request (1-2 HTTP calls for
    up to 92 symbols). Non-stock symbols go through *compute_fn*
    (per-symbol OHLCV). Returns None when the batch fails and the
    caller should fall back to the per-symbol path for everything.
    """
    # Split entries
    stock_syms: List[str] = []
    non_stock_entries: List[Tuple[str, str]] = []
    for sym, atype in unique_entries:
        if atype == "stock":
            stock_syms.append(sym)
        else:
            non_stock_entries.append((sym, atype))

    # Batch v7/quote — 1 request for all stocks
    quotes = _yahoo_quote_batch(stock_syms) if stock_syms else []

    # Had stocks but batch returned nothing → fail, let caller fall back
    if stock_syms and not quotes:
        return None

    quote_map = {q["symbol"]: q for q in quotes}
    results: List[dict] = []

    # --- stock results from batch quote data ---
    for sym in stock_syms:
        q = quote_map.get(sym)
        if q:
            turnover = None
            if q["volume"] and q["price"]:
                turnover = round(q["volume"] * q["price"], 2)
            results.append({
                "symbol": sym,
                "name": q.get("name"),
                "type": "stock",
                "return_pct": round(q["change_pct"], 2) if q["change_pct"] is not None else None,
                "turnover": turnover,
                "turnover_currency": "USD",
                "market_cap": q.get("market_cap") if include_market_cap else None,
            })
        else:
            results.append({
                "symbol": sym, "name": None, "type": "stock",
                "return_pct": None, "turnover": None,
                "turnover_currency": "USD",
                "market_cap": None,
            })

    # --- non-stock: per-symbol OHLCV (usually 0 entries) ---
    if non_stock_entries:
        worker_count = min(MAX_YEARLY_WORKERS, max(1, len(non_stock_entries)))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(compute_fn, sym, atype): sym
                for sym, atype in non_stock_entries
            }
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception:
                    logger.exception(
                        "Heatmap compute failed for %s", futures[future]
                    )

    # --- sort & filter (same logic as the generic path) ---
    auto_results = [r for r in results if r["symbol"] in auto_syms]
    user_results = [r for r in results if r["symbol"] in user_symbols_set]

    auto_results.sort(
        key=lambda r: r["turnover"] if r["turnover"] is not None else 0,
        reverse=True,
    )
    top_auto = auto_results[:auto_top_n] if auto_top_n > 0 else []

    ordered = list(top_auto)
    for sym, _ in unique_entries:
        if sym in user_symbols_set:
            match = next((r for r in user_results if r["symbol"] == sym), None)
            if match and match not in ordered:
                ordered.append(match)

    return {
        "period": "today",
        "period_label": _period_label("today"),
        "data": ordered,
    }


def _em_market_cap(symbol: str) -> Optional[float]:
    """Fetch total market cap from East Money (f116). Resolves the US exchange
    prefix (105=NASDAQ, 106=NYSE) by trying both."""
    for prefix in ("105", "106"):
        try:
            r = _em_session.get(
                _EM_QUOTE_URL,
                params={"secid": f"{prefix}.{symbol}", "fields": "f57,f116",
                        "_": int(time.time())},
                timeout=8,
            )
            r.raise_for_status()
            data = r.json().get("data") or {}
            mc = data.get("f116")
            if mc and float(mc) > 0:
                return float(mc)
        except Exception as e:
            logger.debug("East Money market_cap failed for %s (prefix %s): %s", symbol, prefix, e)
            continue
    return None


def _get_market_caps(symbols: List[str]) -> Dict[str, float]:
    """Return {symbol: market_cap} for US stocks, using a 24h cache.

    Yahoo (batched, one request) is primary; East Money fills any misses.
    """
    if not symbols:
        return {}
    now = time.time()
    result: Dict[str, float] = {}
    to_fetch: List[str] = []
    with _market_cap_lock:
        # Clean expired entries while we're here (amortized cleanup)
        expired_keys = [k for k, (_, ts) in _market_cap_cache.items() if now - ts >= _MARKET_CAP_TTL]
        for k in expired_keys:
            del _market_cap_cache[k]

        for s in symbols:
            entry = _market_cap_cache.get(s)
            if entry and now - entry[1] < _MARKET_CAP_TTL:
                result[s] = entry[0]
            else:
                to_fetch.append(s)

    if not to_fetch:
        return result

    # 1) Yahoo batch — fast, reliable from a US server.
    fetched = _yahoo_market_caps(to_fetch)

    # 2) East Money fallback for whatever Yahoo didn't return (per-symbol).
    misses = [s for s in to_fetch if s not in fetched]
    if misses:
        worker_count = min(MAX_YEARLY_WORKERS, max(1, len(misses)))
        with ThreadPoolExecutor(max_workers=worker_count) as ex:
            for sym, mc in zip(misses, ex.map(_em_market_cap, misses)):
                if mc and mc > 0:
                    fetched[sym] = mc

    if fetched:
        with _market_cap_lock:
            for sym, mc in fetched.items():
                _market_cap_cache[sym] = (mc, now)
        result.update(fetched)
    return result


def fetch_heatmap_data(
    symbols: List[Dict[str, str]], period: str, auto_top_n: int = 0,
    include_market_cap: bool = False,
) -> dict:
    """Compute per-symbol return + turnover for a treemap heatmap.

    Args:
        symbols: list of {"symbol": str, "type": str}
        period: one of "today", "week", "month", "quarter", "year"
        auto_top_n: if > 0, auto-include _TOP_US_STOCKS, fetch all, return
                    top N by turnover from the auto-list, plus all user symbols.
        include_market_cap: if True, attach market_cap (best-effort) to each item.

    Returns:
        {"period": str, "period_label": str,
         "data": [{"symbol": str, "name": str or None, "type": str,
                    "return_pct": float or None, "turnover": float or None,
                    "turnover_currency": str}]}
    """
    start_ts = _period_start_ts(period)
    end_ts = int(time.time())

    # Build the full fetch list: user symbols + optional auto top-N watchlist
    seen = set()
    unique_entries = []
    user_symbols_set = set()

    for entry in symbols:
        try:
            sym = entry["symbol"].strip().upper()
            atype = entry.get("type", "stock").strip().lower()
        except (KeyError, AttributeError):
            continue
        key = (sym, atype)
        if not sym or key in seen:
            continue
        seen.add(key)
        user_symbols_set.add(sym)
        unique_entries.append((sym, atype))

    auto_syms = set()
    if auto_top_n > 0:
        top_symbols = _fetch_heatmap_watchlist()
        for sym in top_symbols:
            key = (sym, "stock")
            if key not in seen:
                seen.add(key)
                auto_syms.add(sym)
                unique_entries.append((sym, "stock"))

    def _compute_one(sym: str, atype: str) -> dict:
        series = _fetch_daily_series_cached(sym, atype)

        result = {
            "symbol": sym,
            "name": None,
            "type": atype,
            "return_pct": None,
            "turnover": None,
            "turnover_currency": _TURNOVER_CURRENCY.get(atype, "USD"),
        }

        if series.error or not series.timestamps:
            return result

        # Build all valid (ts, close, vol) points, then filter to the period.
        n = len(series.timestamps)
        all_pts = []
        for i in range(n):
            close = series.closes[i] if i < len(series.closes) else None
            if close is None:
                continue
            ts = series.timestamps[i]
            vol = series.volumes[i] if (series.volumes and i < len(series.volumes)) else None
            all_pts.append((ts, close, vol))

        if not all_pts:
            return result

        in_range = [p for p in all_pts if start_ts <= p[0] <= end_ts]

        # Return needs 2 points. For "today" the range usually holds only the
        # current day's candle (1 point) → fall back to the last 2 trading days
        # so we still show today's move vs the previous close.
        return_pts = in_range if len(in_range) >= 2 else all_pts[-2:]
        if len(return_pts) >= 2:
            first_close = return_pts[0][1]
            last_close = return_pts[-1][1]
            if first_close and first_close != 0:
                result["return_pct"] = round((last_close / first_close - 1) * 100, 2)

        # Turnover: prefer the in-range window; if empty (no point in period),
        # use the most recent point so the cell still has a size.
        turnover_pts = in_range if in_range else all_pts[-1:]
        total_turnover = 0.0
        has_volume = False
        for _, close, vol in turnover_pts:
            if vol is not None and vol > 0:
                total_turnover += vol * close
                has_volume = True
        if has_volume:
            result["turnover"] = round(total_turnover, 2)

        return result

    # ---- Today fast path: batch v7/quote for stocks (1 request vs 92) ----
    if period == "today":
        result = _build_heatmap_today(
            unique_entries, user_symbols_set, auto_syms,
            auto_top_n, include_market_cap, _compute_one,
        )
        if result is not None:
            logger.info("Heatmap today: batch v7/quote used (%d symbols, 1 request)",
                        len(result["data"]))
            return result
        logger.warning("Heatmap today: batch v7/quote failed, falling back to per-symbol OHLCV")

    # Fetch concurrently
    worker_count = min(MAX_YEARLY_WORKERS, max(1, len(unique_entries)))
    results = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(_compute_one, sym, atype): sym
            for sym, atype in unique_entries
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                logger.exception("Heatmap compute failed for %s: %s", futures[future], e)

    # Separate auto-list results from user results
    auto_results = [r for r in results if r["symbol"] in auto_syms]
    user_results = [r for r in results if r["symbol"] in user_symbols_set]

    # Sort auto results by turnover descending, take top N
    auto_results.sort(
        key=lambda r: r["turnover"] if r["turnover"] is not None else 0,
        reverse=True,
    )
    top_auto = auto_results[:auto_top_n] if auto_top_n > 0 else []

    # Merge: top auto first, then user symbols (preserving user order)
    ordered = list(top_auto)
    for sym, atype in unique_entries:
        if sym in user_symbols_set:
            match = next((r for r in user_results if r["symbol"] == sym), None)
            if match and match not in ordered:
                ordered.append(match)

    # Attach display names for every period, not only the "today" fast path.
    # Reuse the same quote response for market caps to avoid another Yahoo call.
    if ordered:
        stock_syms = [r["symbol"] for r in ordered if r["type"] == "stock"]
        quote_map = {
            q["symbol"]: q for q in _yahoo_quote_batch(stock_syms)
        } if stock_syms else {}

        for r in ordered:
            if r["type"] == "stock":
                quote = quote_map.get(r["symbol"])
                if quote and quote.get("name"):
                    r["name"] = quote["name"]

        if include_market_cap:
            caps = {
                sym: float(quote["market_cap"])
                for sym, quote in quote_map.items()
                if quote.get("market_cap") and float(quote["market_cap"]) > 0
            }
            missing_caps = [sym for sym in stock_syms if sym not in caps]
            if missing_caps:
                caps.update(_get_market_caps(missing_caps))
            for r in ordered:
                r["market_cap"] = caps.get(r["symbol"]) if r["type"] == "stock" else None

    return {
        "period": period,
        "period_label": _period_label(period),
        "data": ordered,
    }
