"""Public API and orchestration for the price change feature."""

import hashlib
import json
import logging
import math
import threading
import time
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
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
    normalize_asset_symbol,
)
from .config import get_color_range, get_color_scheme, get_presets, get_site_config
from .fetchers import DAILY_SERIES_FETCHERS, FETCHERS, fetch_intraday_series
from . import cache_store

logger = logging.getLogger(__name__)

# L1: in-process cache (fast, but per-instance — wiped on serverless cold start).
# L2: shared Upstash Redis (cross-instance, survives cold starts). Falls back to
# L1-only when Redis is not configured (local dev).
_DAILY_SERIES_CACHE: Dict[Tuple[str, str], PriceSeries] = {}
_STOCK_COMPARE_CACHE: Dict[str, Tuple[float, int, Dict]] = {}
_DETAIL_FUNDAMENTALS_CACHE: Dict[str, Tuple[float, int, Dict]] = {}
_CACHE_LOCK = threading.RLock()

_FETCHERS: Dict[str, Callable[[str], Dict[str, float]]] = dict(FETCHERS)
_DAILY_SERIES_FETCHERS: Dict[str, Callable[[str], PriceSeries]] = dict(DAILY_SERIES_FETCHERS)

_STOCK_ASSET_TYPES = {"stock", "hk_stock"}
_ASSET_CURRENCIES = {
    "stock": "USD",
    "hk_stock": "HKD",
    "cn_stock": "CNY",
    "crypto": "USDT",
}

MARKET_PULSE_TARGETS = (
    {"market": "CN", "symbol": "000001", "type": "cn_stock", "name": "上证指数", "name_en": "SSE Composite"},
    {"market": "KR", "symbol": "^KS11", "type": "stock", "name": "韩国KOSPI", "name_en": "KOSPI"},
    {"market": "US", "symbol": "^GSPC", "type": "stock", "name": "标普500", "name_en": "S&P 500"},
    {"market": "US", "symbol": "^NDX", "type": "stock", "name": "纳指100", "name_en": "Nasdaq-100"},
    {"market": "24/7", "symbol": "BTC", "type": "crypto", "name": "比特币", "name_en": "Bitcoin"},
)

FEAR_THRESHOLD_CONFIG = {
    "VIX": {"fear_symbol": "^VIX", "asset_symbol": "SPY"},
    "VXN": {"fear_symbol": "^VXN", "asset_symbol": "QQQ"},
}
FEAR_FORWARD_HORIZONS = (
    ("day_1", 1),
    ("week_1", 5),
    ("month_1", 21),
    ("half_year", 126),
    ("year_1", 252),
)


def _cache_ttl(series: PriceSeries) -> int:
    return ERROR_CACHE_TTL_SECONDS if series.error else DAILY_SERIES_TTL_SECONDS


# Bump this whenever the cached PriceSeries shape changes, so old entries (which
# lack new fields) are abandoned instead of served stale. v5 adds dividend
# events used by the stock-only history tables in Stock Detail.
_CACHE_SCHEMA_VERSION = "v5"
_STOCK_COMPARE_CACHE_SCHEMA_VERSION = "v1"


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
                logger.info(
                    "event=daily_series_cache_hit layer=l1 symbol=%s asset_type=%s source=%s points=%s error=%s",
                    symbol,
                    asset_type,
                    series.source,
                    len(series.timestamps),
                    bool(series.error),
                )
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
            logger.info(
                "event=daily_series_cache_hit layer=l2 symbol=%s asset_type=%s source=%s points=%s error=%s",
                symbol,
                asset_type,
                series.source,
                len(series.timestamps),
                bool(series.error),
            )
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
    global _market_pulse_quote_cache, _market_pulse_quote_ts
    with _CACHE_LOCK:
        _DAILY_SERIES_CACHE.clear()
        _STOCK_COMPARE_CACHE.clear()
        _DETAIL_FUNDAMENTALS_CACHE.clear()
    with _market_pulse_quote_lock:
        _market_pulse_quote_cache = []
        _market_pulse_quote_ts = 0.0


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
    asset_type = entry.get("type", "stock").strip().lower()
    symbol = normalize_asset_symbol(entry["symbol"], asset_type)
    return symbol, asset_type


def _fetch_daily_series_cached(symbol: str, asset_type: str) -> PriceSeries:
    symbol = normalize_asset_symbol(symbol, asset_type)
    cached = _get_cached_daily_series(symbol, asset_type)
    if cached is not None:
        return cached

    fetcher = _DAILY_SERIES_FETCHERS.get(asset_type)
    if fetcher is None:
        logger.warning(
            "event=daily_series_fetch_rejected symbol=%s asset_type=%s reason=unknown_asset_type",
            symbol,
            asset_type,
        )
        return empty_series(None, f"unknown asset type: {asset_type}")

    started_at = time.perf_counter()
    logger.info("event=daily_series_fetch_start symbol=%s asset_type=%s", symbol, asset_type)
    try:
        series = fetcher(symbol)
    except Exception as e:
        logger.exception("Failed to fetch daily series for %s (%s): %s", symbol, asset_type, e)
        series = empty_series(None, str(e))
    logger.info(
        "event=daily_series_fetch_complete symbol=%s asset_type=%s source=%s points=%s success=%s duration_ms=%.1f",
        symbol,
        asset_type,
        series.source,
        len(series.timestamps),
        not bool(series.error),
        (time.perf_counter() - started_at) * 1000,
    )

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
    clean_type = asset_type.strip().lower()
    clean_sym = normalize_asset_symbol(symbol, clean_type)

    if clean_type not in _DAILY_SERIES_FETCHERS:
        return _compute_monthly_returns([], [], year)

    series = _fetch_daily_series_cached(clean_sym, clean_type)
    if series.error:
        return _compute_monthly_returns([], [], year)
    return _compute_monthly_returns(series.timestamps, series.closes, year)


def fetch_daily_returns(symbol: str, asset_type: str, year: int, month: int) -> list:
    """Fetch daily returns for a symbol in a given month."""
    logger.info("Fetching daily returns for %s (%s) %d-%02d", symbol, asset_type, year, month)
    clean_type = asset_type.strip().lower()
    clean_sym = normalize_asset_symbol(symbol, clean_type)

    if clean_type not in _DAILY_SERIES_FETCHERS:
        return []

    series = _fetch_daily_series_cached(clean_sym, clean_type)
    if series.error:
        return []
    return _compute_daily_returns_for_month(series.timestamps, series.closes, year, month)


def fetch_price_history(
    symbol: str,
    asset_type: str,
    period: str,
    start_date: str,
    end_date: str,
) -> Dict:
    """Return a date-bounded OHLCV collection aggregated to the requested period."""
    clean_type = asset_type.strip().lower()
    # ``global_stock`` is a download-only product type.  International Yahoo
    # symbols use the same chart endpoints as US stocks, so share the stock
    # fetcher and cache while preserving the requested type in the response.
    fetch_type = "stock" if clean_type == "global_stock" else clean_type
    clean_symbol = normalize_asset_symbol(symbol, fetch_type)
    clean_period = period.strip().lower()
    if not clean_symbol:
        raise ValueError("symbol is required")
    intraday_periods = {"1m", "5m", "1h", "4h"}
    if clean_period not in {*intraday_periods, "daily", "weekly", "monthly", "yearly"}:
        raise ValueError("period must be 1m, 5m, 1h, 4h, daily, weekly, monthly, or yearly")
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except (TypeError, ValueError):
        raise ValueError("start_date and end_date must use YYYY-MM-DD") from None
    if start > end:
        raise ValueError("start_date must be on or before end_date")

    if clean_period in intraday_periods:
        max_days = {"1m": 7, "5m": 60, "1h": 730, "4h": 730}[clean_period]
        if (end - start).days + 1 > max_days:
            raise ValueError(f"{clean_period} period supports a maximum date range of {max_days} days")
        series = fetch_intraday_series(clean_symbol, fetch_type, clean_period, start, end)
        if series.error:
            raise ValueError(series.error)
        data = []
        optional = (series.opens, series.highs, series.lows, series.volumes)
        for index, (timestamp, close) in enumerate(zip(series.timestamps, series.closes)):
            instant = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            if instant.date() < start or instant.date() > end or close is None:
                continue
            values = [items[index] if items is not None and index < len(items) else None for items in optional]
            data.append({
                "date": instant.isoformat().replace("+00:00", "Z"),
                "open": values[0],
                "high": values[1],
                "low": values[2],
                "close": close,
                "volume": values[3],
            })
        currency, market = _heatmap_stock_meta(clean_symbol, fetch_type)
        return {
            "symbol": clean_symbol,
            "type": clean_type,
            "currency": currency,
            "market": market,
            "period": clean_period,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "source": series.source,
            "updated_at": datetime.fromtimestamp(series.fetched_at, tz=timezone.utc).isoformat(),
            "count": len(data),
            "data": data,
        }

    series = _fetch_daily_series_cached(clean_symbol, fetch_type)
    if series.error:
        raise ValueError(series.error)
    if not series.timestamps:
        raise ValueError("price history is unavailable")

    optional_series = {
        "open": series.opens,
        "high": series.highs,
        "low": series.lows,
        "volume": series.volumes,
    }
    daily_points = []
    for index, (timestamp, close) in enumerate(zip(series.timestamps, series.closes)):
        day = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
        if day < start or day > end or close is None:
            continue

        def optional_value(field: str):
            values = optional_series[field]
            return values[index] if values is not None and index < len(values) else None

        daily_points.append({
            "date": day.isoformat(),
            "open": optional_value("open"),
            "high": optional_value("high"),
            "low": optional_value("low"),
            "close": close,
            "volume": optional_value("volume"),
        })

    def group_key(point: Dict):
        point_date = date.fromisoformat(point["date"])
        if clean_period == "weekly":
            iso_year, iso_week, _ = point_date.isocalendar()
            return iso_year, iso_week
        if clean_period == "monthly":
            return point_date.year, point_date.month
        if clean_period == "yearly":
            return (point_date.year,)
        return (point["date"],)

    if clean_period == "daily":
        data = daily_points
    else:
        grouped: Dict[Tuple, List[Dict]] = {}
        for point in daily_points:
            grouped.setdefault(group_key(point), []).append(point)

        data = []
        for points in grouped.values():
            closes = [point["close"] for point in points if point["close"] is not None]
            highs = [point["high"] for point in points if point["high"] is not None]
            lows = [point["low"] for point in points if point["low"] is not None]
            volumes = [point["volume"] for point in points if point["volume"] is not None]
            first = points[0]
            last = points[-1]
            data.append({
                "date": first["date"],
                "period_end": last["date"],
                "open": first["open"] if first["open"] is not None else first["close"],
                "high": max(highs) if highs else (max(closes) if closes else None),
                "low": min(lows) if lows else (min(closes) if closes else None),
                "close": last["close"],
                "volume": sum(volumes) if volumes else None,
            })

    currency, market = _heatmap_stock_meta(clean_symbol, fetch_type)
    return {
        "symbol": clean_symbol,
        "type": clean_type,
        "currency": currency,
        "market": market,
        "period": clean_period,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "source": series.source,
        "updated_at": datetime.fromtimestamp(series.fetched_at, tz=timezone.utc).isoformat(),
        "count": len(data),
        "data": data,
    }


def fetch_market_pulse() -> Dict:
    """Return latest daily closes and moves for five global benchmarks.

    Each market is independent: an upstream failure is represented on that
    item and never prevents the remaining benchmarks from rendering.
    """

    def fetch_one(target: Dict[str, str]) -> Dict:
        item = dict(target)
        try:
            series = _fetch_daily_series_cached(target["symbol"], target["type"])
        except Exception as exc:
            logger.warning("Market pulse fetch failed for %s: %s", target["symbol"], exc)
            return {**item, "price": None, "change_pct": None, "trade_date": None,
                    "source": None, "error": str(exc)}

        points = [
            (ts, float(close))
            for ts, close in zip(series.timestamps, series.closes)
            if close is not None
        ]
        if series.error or len(points) < 2:
            return {**item, "price": None, "change_pct": None, "trade_date": None,
                    "source": series.source, "error": series.error or "insufficient data"}

        (_, previous_close), (latest_ts, latest_close) = points[-2:]
        change_pct = round((latest_close / previous_close - 1) * 100, 2) if previous_close else None
        return {
            **item,
            "price": round(latest_close, 4),
            "change_pct": change_pct,
            "trade_date": datetime.fromtimestamp(latest_ts, tz=timezone.utc).date().isoformat(),
            "source": series.source,
            "error": None,
        }

    yahoo_targets = [target for target in MARKET_PULSE_TARGETS if target["symbol"] in {"^GSPC", "^NDX", "^KS11"}]
    other_targets = [target for target in MARKET_PULSE_TARGETS if target not in yahoo_targets]
    results: Dict[str, Dict] = {}

    # Fetch the three Yahoo indices in one batch while CN/BTC load in parallel.
    with ThreadPoolExecutor(max_workers=1 + len(other_targets)) as executor:
        yahoo_future = executor.submit(
            _market_pulse_yahoo_quotes,
            [target["symbol"] for target in yahoo_targets],
        )
        futures = {executor.submit(fetch_one, target): target for target in other_targets}
        for future in as_completed(futures):
            target = futures[future]
            try:
                results[target["symbol"]] = future.result()
            except Exception as exc:
                results[target["symbol"]] = {
                    **target, "price": None, "change_pct": None, "trade_date": None,
                    "source": None, "error": str(exc),
                }

        try:
            quote_map = {quote["symbol"]: quote for quote in yahoo_future.result()}
        except Exception as exc:
            logger.warning("Market pulse Yahoo batch failed: %s", exc)
            quote_map = {}

    missing_yahoo_targets = []
    for target in yahoo_targets:
        quote = quote_map.get(target["symbol"])
        if not quote or quote.get("price") is None or quote.get("change_pct") is None:
            missing_yahoo_targets.append(target)
            continue
        trade_time = quote.get("trade_time")
        results[target["symbol"]] = {
            **target,
            "price": round(float(quote["price"]), 4),
            "change_pct": round(float(quote["change_pct"]), 2),
            "trade_date": (
                datetime.fromtimestamp(trade_time, tz=timezone.utc).date().isoformat()
                if trade_time else None
            ),
            "source": "yahoo-quote",
            "error": None,
        }

    # A partial/failed batch falls back only for the missing symbols.
    if missing_yahoo_targets:
        with ThreadPoolExecutor(max_workers=len(missing_yahoo_targets)) as executor:
            futures = {executor.submit(fetch_one, target): target for target in missing_yahoo_targets}
            for future in as_completed(futures):
                target = futures[future]
                try:
                    results[target["symbol"]] = future.result()
                except Exception as exc:
                    results[target["symbol"]] = {
                        **target, "price": None, "change_pct": None, "trade_date": None,
                        "source": None, "error": str(exc),
                    }

    markets = [results[target["symbol"]] for target in MARKET_PULSE_TARGETS]
    valid_changes = [item["change_pct"] for item in markets if item["change_pct"] is not None]
    up = sum(1 for value in valid_changes if value > 0)
    down = sum(1 for value in valid_changes if value < 0)
    flat = len(valid_changes) - up - down
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "summary": {"up": up, "down": down, "flat": flat, "available": len(valid_changes)},
        "markets": markets,
    }


def fetch_monthly_returns_batch(symbols: List[Dict[str, str]], year: int) -> Dict[str, list]:
    """Fetch monthly returns for multiple symbols in a given year."""
    data: Dict[str, list] = {}
    for entry in symbols:
        try:
            asset_type = entry.get("type", "stock").strip().lower()
            symbol = normalize_asset_symbol(entry["symbol"], asset_type)
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
            "win_rate": _win_rate(values),
            "count": len(values),
        })
    return stats


def _row_stats(month_values: List[Optional[float]]) -> Dict:
    """Compute descriptive statistics across the visible period cells."""
    clean = [v for v in month_values if v is not None]
    if not clean:
        return {
            "avg": None,
            "median": None,
            "win_rate": None,
            "count": 0,
        }
    return {
        "avg": _avg(clean),
        "median": _median(clean),
        "win_rate": _win_rate(clean),
        "count": len(clean),
    }


def _detail_price_points(series: PriceSeries) -> List[Tuple[date, float]]:
    """Return sorted, finite adjusted-close points for detail analytics."""
    points = []
    for timestamp, close in zip(series.timestamps, series.closes):
        try:
            numeric_close = float(close)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric_close) or numeric_close <= 0:
            continue
        points.append((
            datetime.fromtimestamp(timestamp, tz=timezone.utc).date(),
            numeric_close,
        ))
    return sorted(points, key=lambda point: point[0])


def _date_years_before(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _detail_window_start(
    points: List[Tuple[date, float]],
    target: date,
) -> Optional[Tuple[date, float]]:
    """Find the first observed close near or after a requested window start."""
    for point in points:
        if point[0] >= target:
            return point if point[0] <= target + timedelta(days=10) else None
    return None


def _detail_period_return(
    points: List[Tuple[date, float]],
    years: int,
    annualized: bool = False,
) -> Optional[float]:
    if len(points) < 2:
        return None
    end_date, end_close = points[-1]
    start = _detail_window_start(points, _date_years_before(end_date, years))
    if start is None or start[1] <= 0:
        return None
    elapsed_years = (end_date - start[0]).days / 365.2425
    if elapsed_years <= 0:
        return None
    total_factor = end_close / start[1]
    if total_factor <= 0:
        return None
    value = (
        (total_factor ** (1 / elapsed_years) - 1) * 100
        if annualized
        else (total_factor - 1) * 100
    )
    return round(value, 2)


def _detail_ytd_return(points: List[Tuple[date, float]]) -> Optional[float]:
    if len(points) < 2:
        return None
    end_date, end_close = points[-1]
    prior = next(
        (point for point in reversed(points) if point[0].year < end_date.year),
        None,
    )
    if prior is None or prior[1] <= 0:
        return None
    return round((end_close / prior[1] - 1) * 100, 2)


def _detail_annualized_volatility(
    points: List[Tuple[date, float]],
    asset_type: str,
) -> Optional[float]:
    if len(points) < 2:
        return None
    cutoff = points[-1][0] - timedelta(days=365)
    window = [point for point in points if point[0] >= cutoff]
    returns = [
        math.log(window[index][1] / window[index - 1][1])
        for index in range(1, len(window))
        if window[index - 1][1] > 0 and window[index][1] > 0
    ]
    if len(returns) < 20:
        return None
    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
    annual_periods = 365 if asset_type == "crypto" else 252
    return round(math.sqrt(variance) * math.sqrt(annual_periods) * 100, 2)


def _build_detail_quality(
    series: PriceSeries,
    asset_type: str,
) -> Dict:
    """Build daily and rolling one-year return-quality statistics."""
    points = _detail_price_points(series)
    if len(points) < 2:
        return {}

    daily_returns = []
    for index in range(1, len(points)):
        previous_close = points[index - 1][1]
        close = points[index][1]
        if previous_close <= 0 or close <= 0:
            continue
        daily_returns.append({
            "date": points[index][0],
            "return": close / previous_close - 1,
        })

    cutoff = points[-1][0] - timedelta(days=365)
    one_year_daily = [item for item in daily_returns if item["date"] >= cutoff]
    annual_periods = 365 if asset_type == "crypto" else 252
    downside_volatility = None
    sortino_ratio = None
    if len(one_year_daily) >= 20:
        values = [item["return"] for item in one_year_daily]
        downside_deviation = math.sqrt(
            sum(min(value, 0.0) ** 2 for value in values) / len(values)
        )
        if downside_deviation > 0:
            downside_volatility = (
                downside_deviation * math.sqrt(annual_periods) * 100
            )
            sortino_ratio = (
                (sum(values) / len(values)) * annual_periods
                / (downside_deviation * math.sqrt(annual_periods))
            )

    best_day = (
        max(one_year_daily, key=lambda item: item["return"])
        if one_year_daily
        else None
    )
    worst_day = (
        min(one_year_daily, key=lambda item: item["return"])
        if one_year_daily
        else None
    )

    dates = [point[0] for point in points]
    rolling_returns = []
    for end_index, (end_date, end_close) in enumerate(points):
        target = _date_years_before(end_date, 1)
        start_index = bisect_left(dates, target, 0, end_index)
        if start_index >= end_index:
            continue
        start_date, start_close = points[start_index]
        if start_date > target + timedelta(days=10) or start_close <= 0:
            continue
        rolling_returns.append({
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "return": (end_close / start_close - 1) * 100,
        })

    rolling_values = [item["return"] for item in rolling_returns]
    best_rolling = (
        max(rolling_returns, key=lambda item: item["return"])
        if rolling_returns
        else None
    )
    worst_rolling = (
        min(rolling_returns, key=lambda item: item["return"])
        if rolling_returns
        else None
    )

    def format_daily(item: Optional[Dict]) -> Optional[Dict]:
        if item is None:
            return None
        return {
            "date": item["date"].isoformat(),
            "return": round(item["return"] * 100, 2),
        }

    def format_rolling(item: Optional[Dict]) -> Optional[Dict]:
        if item is None:
            return None
        return {
            "start_date": item["start_date"],
            "end_date": item["end_date"],
            "return": round(item["return"], 2),
        }

    return {
        "daily_win_rate": _win_rate([
            item["return"] for item in daily_returns
        ]),
        "daily_observations": len(daily_returns),
        "downside_volatility_1y": (
            round(downside_volatility, 2)
            if downside_volatility is not None
            else None
        ),
        "sortino_ratio_1y": (
            round(sortino_ratio, 2)
            if sortino_ratio is not None
            else None
        ),
        "best_day_1y": format_daily(best_day),
        "worst_day_1y": format_daily(worst_day),
        "rolling_1y_win_rate": _win_rate(rolling_values),
        "rolling_1y_median": _median(rolling_values),
        "rolling_1y_best": format_rolling(best_rolling),
        "rolling_1y_worst": format_rolling(worst_rolling),
        "rolling_1y_observations": len(rolling_returns),
        "return_basis": "adjusted_close",
        "sortino_target_return": 0,
    }


def _detail_drawdown_summary(points: List[Tuple[date, float]]) -> Dict:
    if not points:
        return {
            "current_drawdown": None,
            "all_time_high_date": None,
            "max_drawdown": None,
            "max_drawdown_peak_date": None,
            "max_drawdown_trough_date": None,
            "max_drawdown_recovery_date": None,
            "max_drawdown_recovery_trading_days": None,
        }

    peak_index = 0
    peak_close = points[0][1]
    max_drawdown = 0.0
    max_peak_index = 0
    max_trough_index = 0
    for index, (_, close) in enumerate(points[1:], start=1):
        if close > peak_close:
            peak_index = index
            peak_close = close
            continue
        drawdown = close / peak_close - 1
        if drawdown < max_drawdown:
            max_drawdown = drawdown
            max_peak_index = peak_index
            max_trough_index = index

    recovery_index = (
        next(
            (
                index
                for index in range(max_trough_index + 1, len(points))
                if points[index][1] >= points[max_peak_index][1]
            ),
            None,
        )
        if max_drawdown < 0
        else max_trough_index
    )
    all_time_high_index = max(
        range(len(points)),
        key=lambda index: (points[index][1], index),
    )
    current_drawdown = (points[-1][1] / points[all_time_high_index][1] - 1) * 100
    return {
        "current_drawdown": round(current_drawdown, 2),
        "all_time_high_date": points[all_time_high_index][0].isoformat(),
        "max_drawdown": round(max_drawdown * 100, 2),
        "max_drawdown_peak_date": points[max_peak_index][0].isoformat(),
        "max_drawdown_trough_date": points[max_trough_index][0].isoformat(),
        "max_drawdown_recovery_date": (
            points[recovery_index][0].isoformat()
            if recovery_index is not None
            else None
        ),
        "max_drawdown_recovery_trading_days": (
            recovery_index - max_trough_index
            if recovery_index is not None
            else None
        ),
    }


def _build_detail_overview(
    symbol: str,
    asset_type: str,
    series: PriceSeries,
    yearly: Dict[str, float],
) -> Dict:
    """Build the common identity, long-term return, and risk overview."""
    points = _detail_price_points(series)
    if not points:
        return {}
    latest_date, latest_adjusted_close = points[-1]
    latest_price = latest_adjusted_close
    price_basis = "adjusted_close"
    if (
        series.raw_closes
        and len(series.raw_closes) == len(series.timestamps)
    ):
        for timestamp, close in reversed(list(zip(series.timestamps, series.raw_closes))):
            try:
                numeric_close = float(close)
            except (TypeError, ValueError):
                continue
            if math.isfinite(numeric_close) and numeric_close > 0:
                latest_price = numeric_close
                latest_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
                price_basis = "raw_close"
                break

    current_year_is_ytd = latest_date.month < 12 or latest_date.day < 20
    complete_years = [
        (int(year), float(value))
        for year, value in yearly.items()
        if value is not None
        and not (current_year_is_ytd and int(year) == latest_date.year)
    ]
    best_year = max(complete_years, key=lambda item: item[1]) if complete_years else None
    worst_year = min(complete_years, key=lambda item: item[1]) if complete_years else None
    return {
        "symbol": symbol,
        "type": asset_type,
        "latest_price": round(latest_price, 6),
        "latest_adjusted_close": round(latest_adjusted_close, 6),
        "latest_date": latest_date.isoformat(),
        "first_date": points[0][0].isoformat(),
        "price_basis": price_basis,
        "source": series.source,
        "updated_at": datetime.fromtimestamp(series.fetched_at, tz=timezone.utc).isoformat(),
        "current_year_is_ytd": current_year_is_ytd,
        "ytd_return": _detail_ytd_return(points),
        "one_year_return": _detail_period_return(points, 1),
        "cagr_3y": _detail_period_return(points, 3, annualized=True),
        "cagr_5y": _detail_period_return(points, 5, annualized=True),
        "cagr_10y": _detail_period_return(points, 10, annualized=True),
        "annualized_volatility_1y": _detail_annualized_volatility(points, asset_type),
        "best_year": (
            {"year": best_year[0], "return": round(best_year[1], 2)}
            if best_year
            else None
        ),
        "worst_year": (
            {"year": worst_year[0], "return": round(worst_year[1], 2)}
            if worst_year
            else None
        ),
        **_detail_drawdown_summary(points),
    }


def _enrich_detail_fundamentals_from_series(
    series: PriceSeries,
    snapshot: Optional[Dict],
    fallback_currency: str = "USD",
) -> Dict:
    """Fill resilient market-snapshot fields from the existing daily series."""
    result = dict(snapshot or {})
    snapshot_available = bool(result.get("available"))
    price_values = (
        series.raw_closes
        if series.raw_closes and len(series.raw_closes) == len(series.timestamps)
        else series.closes
    )
    price_points = []
    for timestamp, close in zip(series.timestamps, price_values):
        value = _finite_quote_number(close)
        if value is None or value <= 0:
            continue
        price_points.append((
            datetime.fromtimestamp(timestamp, tz=timezone.utc).date(),
            value,
        ))
    price_points.sort(key=lambda point: point[0])
    if not price_points:
        return result

    latest_date, latest_price = price_points[-1]
    one_year_cutoff = latest_date - timedelta(days=365)
    one_year_prices = [
        close for point_date, close in price_points
        if point_date >= one_year_cutoff
    ]
    high = result.get("fifty_two_week_high")
    low = result.get("fifty_two_week_low")
    if one_year_prices:
        if high is None:
            high = max(one_year_prices)
            result["fifty_two_week_high"] = round(high, 6)
        if low is None:
            low = min(one_year_prices)
            result["fifty_two_week_low"] = round(low, 6)

    if high is not None and high > 0:
        result["distance_to_52w_high"] = round(
            (latest_price / high - 1) * 100,
            2,
        )
    if low is not None and low > 0:
        result["distance_to_52w_low"] = round(
            (latest_price / low - 1) * 100,
            2,
        )
    if high is not None and low is not None and high > low:
        result["position_in_52w_range"] = round(
            (latest_price - low) / (high - low) * 100,
            2,
        )

    trailing_dividend = 0.0
    for payment in series.dividends or []:
        try:
            payment_date = datetime.fromtimestamp(
                int(payment["timestamp"]),
                tz=timezone.utc,
            ).date()
            amount = float(payment["amount"])
        except (KeyError, TypeError, ValueError, OSError):
            continue
        if (
            payment_date >= one_year_cutoff
            and math.isfinite(amount)
            and amount > 0
        ):
            trailing_dividend += amount
    if trailing_dividend > 0:
        result["dividend_per_share_ttm"] = round(trailing_dividend, 6)
        if result.get("dividend_yield") is None:
            result["dividend_yield"] = round(
                trailing_dividend / latest_price * 100,
                4,
            )

    if series.volumes and len(series.volumes) == len(series.timestamps):
        volume_cutoff = latest_date - timedelta(days=90)
        volume_values = []
        for timestamp, volume in zip(series.timestamps, series.volumes):
            point_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
            numeric_volume = _finite_quote_number(volume)
            if (
                point_date >= volume_cutoff
                and numeric_volume is not None
                and numeric_volume >= 0
            ):
                volume_values.append(numeric_volume)
        if volume_values and result.get("average_volume_3m") is None:
            result["average_volume_3m"] = round(
                sum(volume_values) / len(volume_values),
                2,
            )

    if not result.get("snapshot_at"):
        result["snapshot_at"] = datetime.fromtimestamp(
            series.fetched_at,
            tz=timezone.utc,
        ).isoformat()
    result["currency"] = result.get("currency") or fallback_currency
    existing_source = result.get("source") if snapshot_available else None
    result["source"] = (
        f"{existing_source},{series.source}"
        if existing_source and series.source not in existing_source.split(",")
        else existing_source or series.source
    )
    numeric_fields = [
        value
        for key, value in result.items()
        if key not in {"available", "field_count"}
        and isinstance(value, (int, float))
        and value is not None
    ]
    result["field_count"] = len(numeric_fields)
    result["available"] = bool(numeric_fields)
    return result


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


def _compute_daily_extremes(series: PriceSeries) -> Tuple[Dict[int, Dict], Dict[Tuple[int, int], Dict]]:
    """Return the largest positive and negative close-to-close daily moves.

    Results are keyed by year and by (year, month). Ties keep the first
    occurrence so the tooltip remains deterministic.
    """
    yearly: Dict[int, Dict] = {}
    monthly: Dict[Tuple[int, int], Dict] = {}
    prev_close: Optional[float] = None

    def update(bucket: Dict, point: Dict) -> None:
        value = point["return"]
        if value > 0:
            current = bucket.get("max_daily_gain")
            if current is None or value > current["return"]:
                bucket["max_daily_gain"] = point
        elif value < 0:
            current = bucket.get("max_daily_loss")
            if current is None or value < current["return"]:
                bucket["max_daily_loss"] = point

    for timestamp, close in zip(series.timestamps, series.closes):
        if close is None:
            continue
        if prev_close not in (None, 0):
            current_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
            point = {
                "date": current_date.isoformat(),
                "return": round((close / prev_close - 1) * 100, 2),
            }
            update(yearly.setdefault(current_date.year, {}), point)
            update(monthly.setdefault((current_date.year, current_date.month), {}), point)
        prev_close = close

    return yearly, monthly


def _with_daily_extremes(item: Dict, extremes: Optional[Dict]) -> Dict:
    """Attach a stable daily-extreme shape to a return-detail period."""
    data = extremes or {}
    return {
        **item,
        "max_daily_gain": data.get("max_daily_gain"),
        "max_daily_loss": data.get("max_daily_loss"),
    }


def _compute_return_candles(
    series: PriceSeries,
) -> Tuple[Dict[int, Dict], Dict[Tuple[int, int], Dict]]:
    """Aggregate adjusted OHLC candles relative to the previous period close.

    Yahoo returns adjusted closes alongside raw OHLC. Applying each day's
    adjusted-close/raw-close factor keeps all four prices on the same basis and
    prevents a candle body from extending beyond its own high/low wick.
    """
    yearly_prices: Dict[int, Dict[str, float]] = {}
    monthly_prices: Dict[Tuple[int, int], Dict[str, float]] = {}

    def number_at(values: Optional[List[Optional[float]]], index: int) -> Optional[float]:
        if values is None or index >= len(values):
            return None
        try:
            value = float(values[index])
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) else None

    def update(bucket: Dict, key, open_price: float, high: float, low: float, close: float) -> None:
        current = bucket.get(key)
        if current is None:
            bucket[key] = {
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
            }
            return
        current["high"] = max(current["high"], high)
        current["low"] = min(current["low"], low)
        current["close"] = close

    for index, (timestamp, adjusted_close_value) in enumerate(zip(series.timestamps, series.closes)):
        try:
            adjusted_close = float(adjusted_close_value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(adjusted_close):
            continue

        raw_close = number_at(series.raw_closes, index)
        adjustment = adjusted_close / raw_close if raw_close not in (None, 0) else 1.0

        raw_open = number_at(series.opens, index)
        raw_high = number_at(series.highs, index)
        raw_low = number_at(series.lows, index)
        adjusted_open = raw_open * adjustment if raw_open is not None else adjusted_close
        adjusted_high = raw_high * adjustment if raw_high is not None else adjusted_close
        adjusted_low = raw_low * adjustment if raw_low is not None else adjusted_close

        # Guard against incomplete or slightly inconsistent upstream candles.
        adjusted_high = max(adjusted_high, adjusted_open, adjusted_close)
        adjusted_low = min(adjusted_low, adjusted_open, adjusted_close)

        current_date = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        update(
            yearly_prices,
            current_date.year,
            adjusted_open,
            adjusted_high,
            adjusted_low,
            adjusted_close,
        )
        update(
            monthly_prices,
            (current_date.year, current_date.month),
            adjusted_open,
            adjusted_high,
            adjusted_low,
            adjusted_close,
        )

    def build(prices: Dict, previous_key) -> Dict:
        candles = {}
        for key, values in prices.items():
            prior = prices.get(previous_key(key))
            baseline = prior["close"] if prior else None
            low = values["low"]
            if baseline in (None, 0) or low == 0:
                continue
            candles[key] = {
                "open": round(values["open"], 6),
                "high": round(values["high"], 6),
                "low": round(low, 6),
                "close": round(values["close"], 6),
                "open_return": round((values["open"] / baseline - 1) * 100, 2),
                "high_return": round((values["high"] / baseline - 1) * 100, 2),
                "low_return": round((low / baseline - 1) * 100, 2),
                "close_return": round((values["close"] / baseline - 1) * 100, 2),
                "amplitude": round(values["high"] - low, 6),
                "amplitude_percent": round((values["high"] - low) / low * 100, 2),
            }
        return candles

    sorted_years = sorted(yearly_prices)
    previous_year = {
        current: sorted_years[index - 1] if index else None
        for index, current in enumerate(sorted_years)
    }
    yearly = build(yearly_prices, lambda key: previous_year.get(key))
    monthly = build(
        monthly_prices,
        lambda key: (key[0] - 1, 12) if key[1] == 1 else (key[0], key[1] - 1),
    )
    return yearly, monthly


def _with_chart_detail(item: Dict, extremes: Optional[Dict], candle: Optional[Dict]) -> Dict:
    """Attach tooltip and candlestick data to a return-detail period."""
    result = _with_daily_extremes(item, extremes)
    result["candle"] = candle
    return result


def _compute_yearly_drawdowns(
    timestamps: List[int],
    closes: List[Optional[float]],
) -> List[Dict]:
    """Compute the deepest peak-to-trough decline within each calendar year."""
    points_by_year: Dict[int, List[Tuple[date, float]]] = {}
    for timestamp, close in zip(timestamps, closes):
        if close is None:
            continue
        try:
            numeric_close = float(close)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric_close) or numeric_close <= 0:
            continue
        point_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
        points_by_year.setdefault(point_date.year, []).append((point_date, numeric_close))

    rows = []
    for year in sorted(points_by_year, reverse=True):
        points = sorted(points_by_year[year], key=lambda point: point[0])
        peak_date, peak_close = points[0]
        max_drawdown = 0.0
        max_peak_date = None
        trough_date = None

        for point_date, close in points[1:]:
            if close > peak_close:
                peak_date, peak_close = point_date, close
                continue
            drawdown = (close / peak_close - 1) * 100
            if drawdown < max_drawdown:
                max_drawdown = drawdown
                max_peak_date = peak_date
                trough_date = point_date

        rows.append({
            "year": year,
            "max_drawdown": round(max_drawdown, 2),
            "peak_date": max_peak_date.isoformat() if max_peak_date else None,
            "trough_date": trough_date.isoformat() if trough_date else None,
        })
    return rows


def _compute_yearly_runups(
    timestamps: List[int],
    closes: List[Optional[float]],
) -> List[Dict]:
    """Compute the largest trough-to-peak gain within each calendar year."""
    points_by_year: Dict[int, List[Tuple[date, float]]] = {}
    for timestamp, close in zip(timestamps, closes):
        if close is None:
            continue
        try:
            numeric_close = float(close)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric_close) or numeric_close <= 0:
            continue
        point_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
        points_by_year.setdefault(point_date.year, []).append((point_date, numeric_close))

    rows = []
    for year in sorted(points_by_year, reverse=True):
        points = sorted(points_by_year[year], key=lambda point: point[0])
        trough_date, trough_close = points[0]
        max_runup = 0.0
        max_trough_date = None
        peak_date = None

        for point_date, close in points[1:]:
            if close < trough_close:
                trough_date, trough_close = point_date, close
                continue
            runup = (close / trough_close - 1) * 100
            if runup > max_runup:
                max_runup = runup
                max_trough_date = trough_date
                peak_date = point_date

        rows.append({
            "year": year,
            "max_runup": round(max_runup, 2),
            "trough_date": max_trough_date.isoformat() if max_trough_date else None,
            "peak_date": peak_date.isoformat() if peak_date else None,
        })
    return rows


def _compute_yearly_dividends(dividends: Optional[List[Dict]]) -> List[Dict]:
    """Group cash distributions by ex-dividend calendar year."""
    grouped: Dict[int, Dict] = {}
    for event in dividends or []:
        try:
            timestamp = int(event["timestamp"])
            amount = float(event["amount"])
        except (KeyError, TypeError, ValueError):
            continue
        if timestamp <= 0 or not math.isfinite(amount) or amount <= 0:
            continue
        event_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
        year = event_date.year
        item = grouped.setdefault(
            year,
            {"dividend_per_share": 0.0, "payment_count": 0, "payments": []},
        )
        item["dividend_per_share"] = float(item["dividend_per_share"]) + amount
        item["payment_count"] = int(item["payment_count"]) + 1
        item["payments"].append({
            "date": event_date.isoformat(),
            "amount": round(amount, 6),
        })

    return [
        {
            "year": year,
            "dividend_per_share": round(float(grouped[year]["dividend_per_share"]), 6),
            "payment_count": int(grouped[year]["payment_count"]),
            "payments": sorted(grouped[year]["payments"], key=lambda payment: payment["date"]),
        }
        for year in sorted(grouped, reverse=True)
    ]


def _build_stock_history_tables(
    series: PriceSeries,
    currency: str = "USD",
) -> Dict:
    """Build the combined stock-only annual table shown below Stock Detail."""
    price_closes = (
        series.raw_closes
        if series.raw_closes and len(series.raw_closes) == len(series.timestamps)
        else series.closes
    )
    returns_by_year = {
        int(year): value
        for year, value in _compute_yearly_returns(series.timestamps, price_closes).items()
    }
    year_end_closes: Dict[int, float] = {}
    for timestamp, close in zip(series.timestamps, price_closes):
        if close is None:
            continue
        try:
            numeric_close = float(close)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric_close) or numeric_close <= 0:
            continue
        year = datetime.fromtimestamp(timestamp, tz=timezone.utc).year
        year_end_closes[year] = numeric_close
    sorted_price_years = sorted(year_end_closes)
    dividend_basis_by_year = {
        year: year_end_closes[sorted_price_years[index - 1]]
        for index, year in enumerate(sorted_price_years)
        if index
    }
    drawdowns_by_year = {
        row["year"]: row
        for row in _compute_yearly_drawdowns(series.timestamps, price_closes)
    }
    runups_by_year = {
        row["year"]: row
        for row in _compute_yearly_runups(series.timestamps, price_closes)
    }
    dividends_by_year = {
        row["year"]: row
        for row in _compute_yearly_dividends(series.dividends)
    }
    all_years = sorted(
        set(returns_by_year) | set(drawdowns_by_year) | set(runups_by_year) | set(dividends_by_year),
        reverse=True,
    )

    rows = []
    for year in all_years:
        drawdown = drawdowns_by_year.get(year, {})
        runup = runups_by_year.get(year, {})
        dividend = dividends_by_year.get(year, {})
        rows.append({
            "year": year,
            "annual_return": returns_by_year.get(year),
            "max_drawdown": drawdown.get("max_drawdown"),
            "max_runup": runup.get("max_runup"),
            "payment_count": dividend.get("payment_count", 0),
            "dividend_payments": dividend.get("payments", []),
            "total_dividend_per_share": dividend.get("dividend_per_share", 0.0),
            "dividend_yield_basis_price": round(dividend_basis_by_year[year], 6)
            if year in dividend_basis_by_year
            else None,
        })

    return {
        "rows": rows,
        "return_basis": "raw_close",
        "dividend_yield_basis": "previous_year_end_close",
        "dividend_unit": f"{currency}/share",
    }


MAX_STOCK_COMPARE_SYMBOLS = 8
STOCK_COMPARE_METRICS = (
    "combined_annualized",
    "annual_return",
    "dividend_yield_after_tax",
    "max_drawdown",
)


def _stock_compare_cache_key(symbols: List[str], tax_rate: float) -> str:
    signature = json.dumps(
        {"symbols": symbols, "tax_rate": tax_rate},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    return (
        f"{_CACHE_SCHEMA_VERSION}:stock_compare:"
        f"{_STOCK_COMPARE_CACHE_SCHEMA_VERSION}:{digest}"
    )


def _get_cached_stock_comparison(cache_key: str) -> Optional[Dict]:
    now = time.time()
    with _CACHE_LOCK:
        cached = _STOCK_COMPARE_CACHE.get(cache_key)
        if cached:
            cached_at, ttl, payload = cached
            if now - cached_at < ttl:
                logger.info("event=stock_comparison_cache_hit layer=l1")
                return payload
            del _STOCK_COMPARE_CACHE[cache_key]

    raw = cache_store.cache_get(cache_key)
    if not raw:
        return None
    try:
        wrapper = json.loads(raw)
        cached_at = float(wrapper["cached_at"])
        ttl = int(wrapper["ttl"])
        payload = wrapper["payload"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or now - cached_at >= ttl:
        return None
    with _CACHE_LOCK:
        _STOCK_COMPARE_CACHE[cache_key] = (cached_at, ttl, payload)
    logger.info("event=stock_comparison_cache_hit layer=l2")
    return payload


def _set_cached_stock_comparison(cache_key: str, payload: Dict) -> None:
    cached_at = time.time()
    has_errors = any(
        item.get("error")
        for item in payload.get("meta", {}).values()
        if isinstance(item, dict)
    )
    ttl = ERROR_CACHE_TTL_SECONDS if has_errors else DAILY_SERIES_TTL_SECONDS
    if not has_errors:
        remaining_ttls = []
        for item in payload.get("meta", {}).values():
            if not isinstance(item, dict) or not item.get("updated_at"):
                continue
            try:
                fetched_at = datetime.fromisoformat(item["updated_at"]).timestamp()
            except (TypeError, ValueError):
                continue
            remaining_ttls.append(
                DAILY_SERIES_TTL_SECONDS - max(0, cached_at - fetched_at)
            )
        if remaining_ttls:
            ttl = max(1, min(ttl, int(min(remaining_ttls))))
    with _CACHE_LOCK:
        _STOCK_COMPARE_CACHE[cache_key] = (cached_at, ttl, payload)
    wrapper = {
        "cached_at": cached_at,
        "ttl": ttl,
        "payload": payload,
    }
    cache_store.cache_set(
        cache_key,
        json.dumps(wrapper, ensure_ascii=True, separators=(",", ":")),
        ttl,
    )


def _normalize_stock_compare_symbols(symbols: List) -> List[str]:
    normalized = []
    seen = set()
    for entry in symbols:
        value = entry.get("symbol", "") if isinstance(entry, dict) else entry
        symbol = str(value or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        if len(symbol) > 20:
            raise ValueError(f"symbol is too long: {symbol}")
        seen.add(symbol)
        normalized.append(symbol)
    if not normalized:
        raise ValueError("symbols list is required")
    if len(normalized) > MAX_STOCK_COMPARE_SYMBOLS:
        raise ValueError(f"at most {MAX_STOCK_COMPARE_SYMBOLS} symbols are allowed")
    return normalized


def _build_stock_comparison_symbol(
    symbol: str,
    tax_rate: float,
) -> Tuple[str, Dict[int, Dict[str, Optional[float]]], Dict]:
    series = _fetch_daily_series_cached(symbol, "stock")
    meta = _series_meta(symbol, "stock", series)
    if series.error:
        return symbol, {}, meta

    tables = _build_stock_history_tables(series)
    rows: Dict[int, Dict[str, Optional[float]]] = {}
    tax_multiplier = 1 - tax_rate / 100
    for row in tables["rows"]:
        annual_return = row.get("annual_return")
        basis = row.get("dividend_yield_basis_price")
        total_dividend = float(row.get("total_dividend_per_share") or 0)
        dividend_yield = None
        if basis is not None and float(basis) > 0:
            dividend_yield = round(
                total_dividend * tax_multiplier / float(basis) * 100,
                4,
            )
        combined = None
        if annual_return is not None and dividend_yield is not None:
            combined = round(float(annual_return) + dividend_yield, 4)
        rows[int(row["year"])] = {
            "combined_annualized": combined,
            "annual_return": annual_return,
            "dividend_yield_after_tax": dividend_yield,
            "max_drawdown": row.get("max_drawdown"),
        }
    if not rows and not meta["error"]:
        meta["error"] = "insufficient data"
    return symbol, rows, meta


def fetch_stock_comparison(symbols: List, tax_rate: float = 30) -> Dict:
    """Build a compact year × US-stock × metric comparison cube."""
    normalized_symbols = _normalize_stock_compare_symbols(symbols)
    try:
        normalized_tax_rate = float(tax_rate)
    except (TypeError, ValueError):
        raise ValueError("tax_rate must be a number")
    if not math.isfinite(normalized_tax_rate) or not 0 <= normalized_tax_rate <= 100:
        raise ValueError("tax_rate must be between 0 and 100")

    cache_key = _stock_compare_cache_key(normalized_symbols, normalized_tax_rate)
    cached = _get_cached_stock_comparison(cache_key)
    if cached is not None:
        return cached

    started_at = time.perf_counter()
    logger.info(
        "event=stock_comparison_start symbols=%s tax_rate=%s",
        ",".join(normalized_symbols),
        normalized_tax_rate,
    )
    fetched: Dict[str, Dict[int, Dict[str, Optional[float]]]] = {}
    meta: Dict[str, Dict] = {}
    worker_count = min(MAX_YEARLY_WORKERS, len(normalized_symbols))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(_build_stock_comparison_symbol, symbol, normalized_tax_rate)
            for symbol in normalized_symbols
        ]
        for future in as_completed(futures):
            symbol, rows, symbol_meta = future.result()
            fetched[symbol] = rows
            meta[symbol] = symbol_meta

    all_years = sorted(
        {year for rows in fetched.values() for year in rows},
        reverse=True,
    )
    data = {
        str(year): {
            symbol: fetched.get(symbol, {}).get(year, {})
            for symbol in normalized_symbols
        }
        for year in all_years
    }
    ordered_meta = {
        symbol: meta.get(symbol, {
            "symbol": symbol,
            "type": "stock",
            "source": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "error": "not fetched",
            "points": 0,
        })
        for symbol in normalized_symbols
    }
    error_count = sum(1 for item in ordered_meta.values() if item.get("error"))
    logger.info(
        "event=stock_comparison_complete symbols=%s years=%s errors=%s duration_ms=%.1f",
        len(normalized_symbols),
        len(all_years),
        error_count,
        (time.perf_counter() - started_at) * 1000,
    )
    result = {
        "symbols": normalized_symbols,
        "years": all_years,
        "currency": "USD",
        "tax_rate": normalized_tax_rate,
        "metrics": list(STOCK_COMPARE_METRICS),
        "data": data,
        "meta": ordered_meta,
    }
    _set_cached_stock_comparison(cache_key, result)
    return result


def fetch_return_detail(
    symbol: str,
    asset_type: str,
    year: Optional[int] = None,
    include_stock_history: bool = True,
) -> Dict:
    """Fetch single-symbol yearly/monthly return detail, or daily grid for a specific year."""
    clean_type = asset_type.strip().lower()
    clean_sym = normalize_asset_symbol(symbol, clean_type)
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

    overview = _build_detail_overview(clean_sym, clean_type, series, yearly)
    quality = _build_detail_quality(series, clean_type)
    external_fundamentals = (
        _fetch_detail_fundamentals(clean_sym)
        if clean_type in _STOCK_ASSET_TYPES and series.source.startswith("yahoo")
        else None
    )
    fundamentals = (
        _enrich_detail_fundamentals_from_series(
            series,
            external_fundamentals,
            fallback_currency=_ASSET_CURRENCIES[clean_type],
        )
        if clean_type in _STOCK_ASSET_TYPES
        else None
    )
    if fundamentals is not None:
        logger.info(
            "event=detail_fundamentals_ready symbol=%s source=%s available=%s fields=%s external_snapshot=%s",
            clean_sym,
            fundamentals.get("source", "unknown"),
            bool(fundamentals.get("available")),
            fundamentals.get("field_count", 0),
            bool(external_fundamentals and external_fundamentals.get("available")),
        )
    yearly_extremes, monthly_extremes = _compute_daily_extremes(series)
    yearly_candles, monthly_candles = _compute_return_candles(series)

    # -- yearly mode ---------------------------------------------------------
    if year is None:
        stock_tables = (
            _build_stock_history_tables(series, _ASSET_CURRENCIES[clean_type])
            if clean_type in _STOCK_ASSET_TYPES
            else None
        )
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
                clean_months.append(_with_chart_detail(
                    {"month": month, "return": value},
                    monthly_extremes.get((y, month)),
                    monthly_candles.get((y, month)),
                ))
            y_ret = yearly.get(str(y))
            is_partial_current_year = (
                overview.get("current_year_is_ytd")
                and y == int(str(overview.get("latest_date", "0"))[:4])
            )
            if y_ret is not None and not is_partial_current_year:
                year_values.append(float(y_ret))
            month_vals = [m["return"] for m in clean_months]
            monthly_rows.append({
                "year": y,
                "annual_return": y_ret,
                "max_daily_gain": yearly_extremes.get(y, {}).get("max_daily_gain"),
                "max_daily_loss": yearly_extremes.get(y, {}).get("max_daily_loss"),
                "candle": yearly_candles.get(y),
                "months": clean_months,
                "row_stats": _row_stats(month_vals),
            })

        return {
            "symbol": clean_sym,
            "type": clean_type,
            "mode": "yearly",
            "source": series.source,
            "meta": _series_meta(clean_sym, clean_type, series),
            "overview": overview,
            "quality": quality,
            "fundamentals": fundamentals,
            "years": years,
            "rows": monthly_rows,
            "stats": _build_monthly_stats(month_values),
            "stock_tables": stock_tables,
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
        "overview": overview,
        "quality": quality,
        "fundamentals": fundamentals,
        "years": years,
        "monthly_returns": [
            _with_chart_detail(
                item,
                monthly_extremes.get((year, int(item["month"]))),
                monthly_candles.get((year, int(item["month"]))),
            )
            for item in _compute_monthly_returns(series.timestamps, series.closes, year)
        ],
        "daily_rows": daily_rows,
        "stats": _build_monthly_stats(month_values),
        "stock_tables": (
            _build_stock_history_tables(series, _ASSET_CURRENCIES[clean_type])
            if clean_type in _STOCK_ASSET_TYPES and include_stock_history
            else None
        ),
        "summary": {
            "year_count": len(years),
            "selected_year": year,
        },
    }


def run_dca_backtest(payload: Dict) -> Dict:
    """Run a single-symbol DCA backtest using daily price data."""
    asset_type = str(payload.get("type", "stock")).strip().lower()
    symbol = normalize_asset_symbol(payload.get("symbol", ""), asset_type)
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
        "currency": _ASSET_CURRENCIES.get(asset_type, "USD"),
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
    """Analyze crash events and recovery for a symbol.

    Request payload:
        symbol: str (e.g. "QQQ")
        type: str (asset type, default "stock")
        start_date: str (YYYY-MM-DD)
        end_date: str (YYYY-MM-DD)
        threshold_pct: float (e.g. 4.77 = drop >= 4.77%)
        period_type: str (day, n_days, week, or month; default day)
        period_days: int (2-250 when period_type is n_days)

    Returns:
        dict with crashes list and summary statistics.
    """
    asset_type = str(payload.get("type", "stock")).strip().lower()
    symbol = normalize_asset_symbol(payload.get("symbol", ""), asset_type)
    start_date = _parse_iso_date(payload.get("start_date"), "start_date")
    end_date = _parse_iso_date(payload.get("end_date"), "end_date")
    threshold_pct = float(payload.get("threshold_pct", 4.77))
    period_aliases = {
        "day": "day",
        "daily": "day",
        "n_days": "n_days",
        "n-days": "n_days",
        "week": "week",
        "weekly": "week",
        "month": "month",
        "monthly": "month",
    }
    period_type = period_aliases.get(
        str(payload.get("period_type", "day")).strip().lower()
    )
    period_days = _safe_int(payload.get("period_days"), 5)

    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    if not symbol:
        raise ValueError("symbol is required")
    if threshold_pct <= 0:
        raise ValueError("threshold_pct must be positive")
    if period_type is None:
        raise ValueError("period_type must be one of day, n_days, week, month")
    if period_type == "n_days" and not 2 <= period_days <= 250:
        raise ValueError("period_days must be between 2 and 250")

    series = _fetch_daily_series_cached(symbol, asset_type)
    if series.error:
        raise ValueError(series.error)

    crashes = compute_crash_statistics(
        timestamps=series.timestamps,
        closes=series.closes,
        start_date=start_date,
        end_date=end_date,
        threshold_pct=threshold_pct,
        period_type=period_type,
        period_days=period_days,
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
        "period_type": period_type,
        "period_days": period_days if period_type == "n_days" else None,
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


def run_fear_threshold_stats(payload: Dict) -> Dict:
    """Measure ETF forward returns after VIX or VXN closes above a threshold.

    Every qualifying fear-index trading day in the requested date range is an
    observation. Forward prices use adjusted ETF closes after 1, 5, 21, 126,
    and 252 subsequent trading sessions. This intentionally does not collapse
    consecutive high-volatility days into a single episode.
    """
    started_at = time.perf_counter()
    index = str(payload.get("index", "VIX")).strip().upper()
    config = FEAR_THRESHOLD_CONFIG.get(index)
    if config is None:
        raise ValueError("index must be VIX or VXN")

    try:
        threshold = float(payload.get("threshold", 30))
    except (TypeError, ValueError):
        raise ValueError("threshold must be a number") from None
    if not math.isfinite(threshold) or threshold <= 0 or threshold > 500:
        raise ValueError("threshold must be greater than 0 and at most 500")

    start_date = _parse_iso_date(payload.get("start_date"), "start_date")
    end_date = _parse_iso_date(payload.get("end_date"), "end_date")
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    symbols = (config["fear_symbol"], config["asset_symbol"])
    series_by_symbol: Dict[str, PriceSeries] = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(_fetch_daily_series_cached, symbol, "stock"): symbol
            for symbol in symbols
        }
        for future in as_completed(futures):
            symbol = futures[future]
            series_by_symbol[symbol] = future.result()

    fear_series = series_by_symbol[config["fear_symbol"]]
    asset_series = series_by_symbol[config["asset_symbol"]]
    for symbol, series in series_by_symbol.items():
        if series.error:
            raise RuntimeError(f"failed to load {symbol}: {series.error}")

    def _daily_points(series: PriceSeries) -> List[Tuple[date, float]]:
        # Keep the last valid close if an upstream provider emits duplicate
        # timestamps for one UTC trading date.
        by_date: Dict[date, float] = {}
        for timestamp, raw_close in zip(series.timestamps, series.closes):
            if raw_close is None:
                continue
            try:
                close = float(raw_close)
                trading_date = datetime.fromtimestamp(
                    timestamp, tz=timezone.utc
                ).date()
            except (TypeError, ValueError, OSError, OverflowError):
                continue
            if math.isfinite(close) and close > 0:
                by_date[trading_date] = close
        return sorted(by_date.items())

    fear_points = _daily_points(fear_series)
    asset_points = _daily_points(asset_series)
    asset_index_by_date = {
        trading_date: position
        for position, (trading_date, _close) in enumerate(asset_points)
    }

    fear_match_count = 0
    events = []
    for event_date, fear_value in fear_points:
        if event_date < start_date or event_date > end_date or fear_value < threshold:
            continue
        fear_match_count += 1
        asset_position = asset_index_by_date.get(event_date)
        if asset_position is None:
            continue
        asset_price = asset_points[asset_position][1]
        forward = {}
        for key, trading_days in FEAR_FORWARD_HORIZONS:
            future_position = asset_position + trading_days
            if future_position >= len(asset_points):
                forward[key] = None
                continue
            future_date, future_price = asset_points[future_position]
            return_pct = (future_price / asset_price - 1) * 100
            forward[key] = {
                "date": future_date.isoformat(),
                "price": round(future_price, 2),
                "return_pct": round(return_pct, 2),
            }
        events.append({
            "date": event_date.isoformat(),
            "fear_value": round(fear_value, 2),
            "asset_price": round(asset_price, 2),
            "forward": forward,
        })

    def _median(values: List[float]) -> Optional[float]:
        if not values:
            return None
        ordered = sorted(values)
        midpoint = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[midpoint]
        return (ordered[midpoint - 1] + ordered[midpoint]) / 2

    horizon_summary = {}
    for key, trading_days in FEAR_FORWARD_HORIZONS:
        returns = [
            event["forward"][key]["return_pct"]
            for event in events
            if event["forward"][key] is not None
        ]
        horizon_summary[key] = {
            "trading_days": trading_days,
            "available": len(returns),
            "average_return_pct": round(sum(returns) / len(returns), 2)
            if returns else None,
            "median_return_pct": round(_median(returns), 2)
            if returns else None,
            "positive_rate_pct": round(
                sum(1 for value in returns if value > 0) / len(returns) * 100,
                1,
            ) if returns else None,
        }

    result = {
        "index": index,
        "index_symbol": config["fear_symbol"],
        "asset": config["asset_symbol"],
        "threshold": threshold,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "summary": {
            "event_count": len(events),
            "fear_match_count": fear_match_count,
            "unmatched_asset_dates": fear_match_count - len(events),
            "horizons": horizon_summary,
        },
        # Newest first is more useful in the UI; horizon calculation above
        # still uses the complete ascending ETF session sequence.
        "events": list(reversed(events)),
        "meta": {
            "fear_source": fear_series.source,
            "asset_source": asset_series.source,
            "fear_points": len(fear_points),
            "asset_points": len(asset_points),
        },
    }
    logger.info(
        "event=fear_threshold_stats index=%s asset=%s threshold=%s start_date=%s "
        "end_date=%s fear_source=%s asset_source=%s fear_points=%s asset_points=%s "
        "events=%s duration_ms=%s",
        index,
        config["asset_symbol"],
        threshold,
        start_date.isoformat(),
        end_date.isoformat(),
        fear_series.source,
        asset_series.source,
        len(fear_points),
        len(asset_points),
        len(events),
        round((time.perf_counter() - started_at) * 1000, 1),
    )
    return result


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
    asset_type = str(payload.get("type", "stock")).strip().lower()
    symbol = normalize_asset_symbol(payload.get("symbol", ""), asset_type)
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
    "hk_stock": "HKD",
    "crypto": "USDT",
    "cn_stock": "CNY",
}

# Yahoo exchange suffixes used by the global-stock heatmap.  Values are the
# quote currency/unit returned by Yahoo and a compact market label for tiles.
# Keep minor units such as GBp intact: converting prices without also converting
# volume/market cap would make the displayed turnover internally inconsistent.
_HEATMAP_STOCK_SUFFIX_META = (
    (".TWO", "TWD", "TW"),
    (".KS", "KRW", "KR"),
    (".KQ", "KRW", "KR"),
    (".TW", "TWD", "TW"),
    (".NS", "INR", "IN"),
    (".BO", "INR", "IN"),
    (".SI", "SGD", "SG"),
    (".AX", "AUD", "AU"),
    (".TO", "CAD", "CA"),
    (".V", "CAD", "CA"),
    (".L", "GBp", "GB"),
    (".DE", "EUR", "DE"),
    (".AS", "EUR", "NL"),
    (".PA", "EUR", "FR"),
    (".SW", "CHF", "CH"),
    (".CO", "DKK", "DK"),
    (".SA", "BRL", "BR"),
    (".SR", "SAR", "SA"),
    (".T", "JPY", "JP"),
)


def _heatmap_stock_meta(symbol: str, asset_type: str) -> Tuple[str, Optional[str]]:
    """Return the best-effort quote currency and market code for a tile."""
    if asset_type == "hk_stock":
        return "HKD", "HK"
    if asset_type == "cn_stock":
        return "CNY", "CN"
    if asset_type == "crypto":
        return "USDT", "24/7"
    if asset_type == "stock":
        upper_symbol = symbol.upper()
        for suffix, currency, market in _HEATMAP_STOCK_SUFFIX_META:
            if upper_symbol.endswith(suffix):
                return currency, market
        return "USD", "US"
    return _TURNOVER_CURRENCY.get(asset_type, "USD"), None


def _heatmap_currency(
    symbol: str, asset_type: str, quote_currency: Optional[str] = None
) -> str:
    """Prefer the upstream currency, with suffix metadata as the fallback."""
    return quote_currency or _heatmap_stock_meta(symbol, asset_type)[0]

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

# Liquid large-cap A-share pool displayed by the A-share heatmap.
_HEATMAP_CN_WATCHLIST = [
    "600519", "601318", "600036", "000858", "000333", "601166", "600030",
    "601398", "601288", "601939", "601988", "601857", "600028", "601088",
    "600900", "601899", "601012", "300750", "002594", "000651", "002475",
    "300059", "600276", "603259", "600309", "000568", "002714", "600887",
    "601888", "601668", "601728", "600941", "601138", "688981", "688041",
    "000725", "002415", "000063", "600050", "601225", "600690", "600438",
    "002352", "300760", "601919", "600031", "601600", "600019", "601006",
    "600660",
]

# Liquid Hong Kong large caps and actively traded ETFs. Yahoo symbols use the
# HKEX code plus the ``.HK`` suffix, matching the shared hk_stock fetcher.
_HEATMAP_HK_WATCHLIST = [
    "0700.HK", "9988.HK", "3690.HK", "1810.HK", "9618.HK", "0941.HK",
    "0388.HK", "2800.HK", "0005.HK", "1299.HK", "0939.HK", "1398.HK",
    "3988.HK", "2318.HK", "0883.HK", "0857.HK", "1088.HK", "1211.HK",
    "1024.HK", "9999.HK", "9888.HK", "9866.HK", "2015.HK", "9868.HK",
    "9992.HK", "1876.HK", "2020.HK", "6690.HK", "2269.HK", "1177.HK",
]

# Cross-region preview pool.  It intentionally uses the shared ``stock``
# fetcher: ``global_stock`` is a heatmap market selector, not a new asset type.
# Since native-currency turnover is not comparable across markets, the frontend
# forces this view to size blocks by absolute return.
_HEATMAP_GLOBAL_WATCHLIST = [
    # Japan
    "7203.T", "6758.T", "9984.T", "8306.T",
    # South Korea
    "005930.KS", "000660.KS", "035420.KS",
    # Taiwan
    "2330.TW", "2317.TW", "2454.TW",
    # India
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS",
    # Singapore
    "D05.SI", "O39.SI",
    # Australia
    "CBA.AX", "BHP.AX", "CSL.AX",
    # Canada
    "SHOP.TO", "RY.TO",
    # United Kingdom
    "HSBA.L", "AZN.L", "SHEL.L",
    # Continental Europe
    "SAP.DE", "ASML.AS", "MC.PA", "NESN.SW", "NOVO-B.CO",
    # Latin America and Middle East
    "PETR4.SA", "2222.SR",
]

# High-liquidity non-stablecoin pool supported by the existing crypto fetchers.
_HEATMAP_CRYPTO_WATCHLIST = [
    "BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "TRX", "AVAX",
    "LINK", "DOT", "BCH", "LTC", "TON", "NEAR", "UNI", "AAVE", "ETC",
    "FIL", "ATOM", "SUI", "HBAR", "XLM", "SHIB", "ICP", "APT", "ARB", "OP",
]

_HEATMAP_WATCHLISTS = {
    "stock": _HEATMAP_US_WATCHLIST,
    "hk_stock": _HEATMAP_HK_WATCHLIST,
    "global_stock": _HEATMAP_GLOBAL_WATCHLIST,
    "crypto": _HEATMAP_CRYPTO_WATCHLIST,
    "cn_stock": _HEATMAP_CN_WATCHLIST,
}

_HEATMAP_MARKET_ASSET_TYPES = {
    "global_stock": "stock",
}


def _fetch_heatmap_watchlist(market_type: str = "stock") -> List[str]:
    """Return candidates for the requested heatmap market."""
    return list(_HEATMAP_WATCHLISTS.get(market_type, _HEATMAP_US_WATCHLIST))

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
_EM_SYMBOL_SEARCH_URL = "https://searchapi.eastmoney.com/api/suggest/get"
_em_session = _requests.Session()
_em_session.trust_env = False
_em_session.headers.update({"User-Agent": "Mozilla/5.0"})

# Yahoo quote endpoint. Prefer curl_cffi (browser TLS impersonation dodges the
# bot throttling that plain requests hits); fall back to requests if absent.
_YH_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
_YH_SYMBOL_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
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
_symbol_search_cache: Dict[Tuple[str, str, int], Tuple[List[Dict], float]] = {}
_symbol_search_lock = threading.Lock()
_SYMBOL_SEARCH_TTL = 60 * 60
_SYMBOL_SEARCH_MAX_CACHE = 512


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


def _east_money_symbol_search(query: str, asset_type: str, limit: int) -> List[Dict]:
    """Search Chinese, Hong Kong, and US listings by code or company name."""
    classifications = {
        "stock": {"UsStock"},
        "hk_stock": {"HK"},
        "cn_stock": {"AStock"},
    }.get(asset_type)
    if not classifications:
        return []

    try:
        response = _em_session.get(
            _EM_SYMBOL_SEARCH_URL,
            params={"input": query, "type": 14, "count": max(limit * 3, 12)},
            timeout=8,
        )
        if response.status_code != 200:
            return []
        rows = ((response.json().get("QuotationCodeTable") or {}).get("Data") or [])
    except Exception as exc:
        logger.debug("East Money symbol search failed: %s", exc)
        return []

    results: List[Dict] = []
    seen = set()
    for row in rows:
        if row.get("Classify") not in classifications:
            continue
        # East Money also returns US notes, warrants, and other similarly named
        # instruments. Keep common shares, ADRs, and ETFs for this stock picker.
        if asset_type in {"stock", "hk_stock"} and str(row.get("TypeUS", "")) not in {
            "1", "2", "3", "5",
        }:
            continue
        symbol = str(row.get("UnifiedCode") or row.get("Code") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        exchange = str(row.get("JYS") or "").strip()
        if not exchange or exchange.isdigit():
            exchange = str(row.get("SecurityTypeName") or "").strip()
        results.append({
            "symbol": symbol,
            "name": str(row.get("Name") or "").strip(),
            "type": asset_type,
            "exchange": exchange,
        })
        if len(results) >= limit:
            break
    return results


def _yahoo_symbol_search(query: str, asset_type: str, limit: int) -> List[Dict]:
    """Best-effort Yahoo search for global listings and crypto assets."""
    try:
        params = {
            "q": query,
            "quotesCount": max(limit * 3, 12),
            "newsCount": 0,
            "enableFuzzyQuery": "true",
        }
        crumb = _yahoo_crumb()
        if crumb:
            params["crumb"] = crumb
        response = _yh_session.get(_YH_SYMBOL_SEARCH_URL, params=params, timeout=8)
        if response.status_code != 200:
            return []
        rows = response.json().get("quotes") or []
    except Exception as exc:
        logger.debug("Yahoo symbol search failed: %s", exc)
        return []

    stock_quote_types = {"EQUITY", "ETF", "MUTUALFUND", "INDEX"}
    results: List[Dict] = []
    seen = set()
    for row in rows:
        quote_type = str(row.get("quoteType") or "").upper()
        symbol = str(row.get("symbol") or "").strip().upper()
        if asset_type == "crypto":
            if quote_type != "CRYPTOCURRENCY":
                continue
            for suffix in ("-USD", "-USDT"):
                if symbol.endswith(suffix):
                    symbol = symbol[:-len(suffix)]
                    break
        else:
            if quote_type not in stock_quote_types:
                continue
            if asset_type == "stock" and (symbol.endswith(".HK") or symbol.endswith(".SS") or symbol.endswith(".SZ")):
                continue
            if asset_type == "hk_stock" and not symbol.endswith(".HK"):
                continue
            if asset_type == "cn_stock":
                if not (symbol.endswith(".SS") or symbol.endswith(".SZ")):
                    continue
                symbol = symbol.rsplit(".", 1)[0]
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        results.append({
            "symbol": symbol,
            "name": str(row.get("longname") or row.get("shortname") or "").strip(),
            "type": asset_type,
            "exchange": str(row.get("exchDisp") or row.get("exchange") or "").strip(),
        })
        if len(results) >= limit:
            break
    return results


def search_asset_symbols(query: str, asset_type: str, limit: int = 8) -> List[Dict]:
    """Return symbol suggestions suitable for the site's asset input controls."""
    clean_query = str(query or "").strip()[:80]
    clean_type = str(asset_type or "stock").strip().lower()
    clean_limit = max(1, min(int(limit), 10))
    if not clean_query or clean_type not in {
        "stock", "hk_stock", "global_stock", "crypto", "cn_stock",
    }:
        return []

    cache_key = (clean_query.casefold(), clean_type, clean_limit)
    with _symbol_search_lock:
        cached = _symbol_search_cache.get(cache_key)
        if cached and time.time() - cached[1] < _SYMBOL_SEARCH_TTL:
            return [dict(item) for item in cached[0]]

    results = _east_money_symbol_search(clean_query, clean_type, clean_limit)
    if not results:
        results = _yahoo_symbol_search(clean_query, clean_type, clean_limit)

    with _symbol_search_lock:
        now = time.time()
        expired_keys = [
            key for key, (_, cached_at) in _symbol_search_cache.items()
            if now - cached_at >= _SYMBOL_SEARCH_TTL
        ]
        for key in expired_keys:
            _symbol_search_cache.pop(key, None)
        while len(_symbol_search_cache) >= _SYMBOL_SEARCH_MAX_CACHE:
            oldest_key = min(_symbol_search_cache, key=lambda key: _symbol_search_cache[key][1])
            _symbol_search_cache.pop(oldest_key, None)
        _symbol_search_cache[cache_key] = ([dict(item) for item in results], now)
    return results


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

    Uses Yahoo v7/quote endpoint. The normalized result includes both the
    market-pulse fields and best-effort valuation/fundamental snapshot fields.
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
                    "trade_time": q.get("regularMarketTime"),
                    "volume": q.get("regularMarketVolume"),
                    "market_cap": q.get("marketCap"),
                    "quote_type": q.get("quoteType"),
                    "currency": q.get("currency"),
                    "exchange": q.get("fullExchangeName") or q.get("exchange"),
                    "total_assets": q.get("totalAssets"),
                    "trailing_pe": q.get("trailingPE"),
                    "forward_pe": q.get("forwardPE"),
                    "price_to_book": q.get("priceToBook"),
                    "eps_ttm": q.get("epsTrailingTwelveMonths"),
                    "eps_forward": q.get("epsForward"),
                    "dividend_yield": q.get("dividendYield"),
                    "trailing_dividend_yield": q.get("trailingAnnualDividendYield"),
                    "beta": q.get("beta"),
                    "fifty_two_week_high": q.get("fiftyTwoWeekHigh"),
                    "fifty_two_week_low": q.get("fiftyTwoWeekLow"),
                    "average_volume_3m": q.get("averageDailyVolume3Month"),
                    "shares_outstanding": q.get("sharesOutstanding"),
                    "expense_ratio": q.get("netExpenseRatio"),
                    "ytd_return": q.get("ytdReturn"),
                    "three_year_return": q.get("threeYearReturn"),
                    "five_year_average_return": q.get("fiveYearAverageReturn"),
                })
        except Exception as e:
            logger.debug("Yahoo quote batch failed: %s", e)
            continue
    return results


_DETAIL_FUNDAMENTALS_SUCCESS_TTL = 6 * 60 * 60
_DETAIL_FUNDAMENTALS_ERROR_TTL = 5 * 60


def _finite_quote_number(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _fetch_detail_fundamentals(symbol: str) -> Dict:
    """Fetch and cache a best-effort valuation snapshot for one US symbol."""
    cache_key = symbol.upper()
    now = time.time()
    with _CACHE_LOCK:
        cached = _DETAIL_FUNDAMENTALS_CACHE.get(cache_key)
        if cached:
            cached_at, ttl, payload = cached
            if now - cached_at < ttl:
                logger.info(
                    "event=detail_fundamentals_cache_hit layer=l1 symbol=%s source=%s available=%s fields=%s",
                    cache_key,
                    payload.get("source", "unknown"),
                    bool(payload.get("available")),
                    payload.get("field_count", 0),
                )
                return dict(payload)
            del _DETAIL_FUNDAMENTALS_CACHE[cache_key]

    started_at = time.perf_counter()
    logger.info(
        "event=detail_fundamentals_fetch_start symbol=%s source=yahoo_quote,eastmoney_quote",
        cache_key,
    )
    quotes = _yahoo_quote_batch([cache_key])
    quote = next(
        (item for item in quotes if item.get("symbol") == cache_key),
        None,
    )
    source = "yahoo_quote"
    if quote is None:
        quote = _eastmoney_detail_quote(cache_key)
        source = "eastmoney_quote"
    if quote is None:
        payload = {
            "available": False,
            "source": "yahoo_quote,eastmoney_quote",
            "field_count": 0,
        }
        ttl = _DETAIL_FUNDAMENTALS_ERROR_TTL
        logger.warning(
            "event=detail_fundamentals_fetch_complete symbol=%s source=yahoo_quote,eastmoney_quote available=false fields=0 duration_ms=%s error=quote_unavailable",
            cache_key,
            round((time.perf_counter() - started_at) * 1000, 1),
        )
    else:
        price = _finite_quote_number(quote.get("price"))
        high = _finite_quote_number(quote.get("fifty_two_week_high"))
        low = _finite_quote_number(quote.get("fifty_two_week_low"))
        trailing_dividend_yield = _finite_quote_number(
            quote.get("trailing_dividend_yield")
        )
        dividend_yield = _finite_quote_number(quote.get("dividend_yield"))
        if dividend_yield is None and trailing_dividend_yield is not None:
            dividend_yield = trailing_dividend_yield * 100

        payload = {
            "available": True,
            "source": source,
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
            "name": quote.get("name"),
            "quote_type": quote.get("quote_type"),
            "currency": quote.get("currency"),
            "exchange": quote.get("exchange"),
            "market_cap": _finite_quote_number(quote.get("market_cap")),
            "total_assets": _finite_quote_number(quote.get("total_assets")),
            "trailing_pe": _finite_quote_number(quote.get("trailing_pe")),
            "forward_pe": _finite_quote_number(quote.get("forward_pe")),
            "price_to_book": _finite_quote_number(quote.get("price_to_book")),
            "eps_ttm": _finite_quote_number(quote.get("eps_ttm")),
            "eps_forward": _finite_quote_number(quote.get("eps_forward")),
            "dividend_yield": dividend_yield,
            "beta": _finite_quote_number(quote.get("beta")),
            "fifty_two_week_high": high,
            "fifty_two_week_low": low,
            "distance_to_52w_high": (
                (price / high - 1) * 100
                if price is not None and high is not None and high > 0
                else None
            ),
            "distance_to_52w_low": (
                (price / low - 1) * 100
                if price is not None and low is not None and low > 0
                else None
            ),
            "position_in_52w_range": (
                (price - low) / (high - low) * 100
                if (
                    price is not None
                    and high is not None
                    and low is not None
                    and high > low
                )
                else None
            ),
            "average_volume_3m": _finite_quote_number(
                quote.get("average_volume_3m")
            ),
            "shares_outstanding": _finite_quote_number(
                quote.get("shares_outstanding")
            ),
            "expense_ratio": _finite_quote_number(quote.get("expense_ratio")),
            "ytd_return": _finite_quote_number(quote.get("ytd_return")),
            "three_year_return": _finite_quote_number(
                quote.get("three_year_return")
            ),
            "five_year_average_return": _finite_quote_number(
                quote.get("five_year_average_return")
            ),
        }
        numeric_fields = [
            key
            for key, value in payload.items()
            if key not in {"available", "field_count"}
            and isinstance(value, (int, float))
            and value is not None
        ]
        payload["field_count"] = len(numeric_fields)
        payload["distance_to_52w_high"] = (
            round(payload["distance_to_52w_high"], 2)
            if payload["distance_to_52w_high"] is not None
            else None
        )
        payload["distance_to_52w_low"] = (
            round(payload["distance_to_52w_low"], 2)
            if payload["distance_to_52w_low"] is not None
            else None
        )
        payload["position_in_52w_range"] = (
            round(payload["position_in_52w_range"], 2)
            if payload["position_in_52w_range"] is not None
            else None
        )
        payload["available"] = payload["field_count"] > 0
        ttl = (
            _DETAIL_FUNDAMENTALS_SUCCESS_TTL
            if payload["available"]
            else _DETAIL_FUNDAMENTALS_ERROR_TTL
        )
        logger.info(
            "event=detail_fundamentals_fetch_complete symbol=%s source=%s available=%s fields=%s duration_ms=%s error=none",
            cache_key,
            source,
            str(payload["available"]).lower(),
            payload["field_count"],
            round((time.perf_counter() - started_at) * 1000, 1),
        )

    with _CACHE_LOCK:
        _DETAIL_FUNDAMENTALS_CACHE[cache_key] = (now, ttl, payload)
    return dict(payload)


_MARKET_PULSE_QUOTE_TTL = 5 * 60
_market_pulse_quote_cache: List[dict] = []
_market_pulse_quote_ts = 0.0
_market_pulse_quote_lock = threading.Lock()


def _market_pulse_yahoo_quotes(symbols: List[str]) -> List[dict]:
    """Return one cached Yahoo batch for the market-pulse stock indices.

    The lock is intentionally held during refresh so concurrent cold requests
    share one upstream call instead of causing a cache stampede.
    """
    global _market_pulse_quote_cache, _market_pulse_quote_ts
    with _market_pulse_quote_lock:
        if time.time() - _market_pulse_quote_ts < _MARKET_PULSE_QUOTE_TTL:
            return list(_market_pulse_quote_cache)
        quotes = _yahoo_quote_batch(symbols)
        _market_pulse_quote_cache = list(quotes)
        _market_pulse_quote_ts = time.time()
        return list(_market_pulse_quote_cache)


def _build_heatmap_today(
    unique_entries: List[Tuple[str, str]],
    user_symbols_set: set,
    auto_syms: set,
    auto_top_n: int,
    include_market_cap: bool,
    compute_fn: Callable,
) -> Optional[dict]:
    """Build heatmap data for period='today' using batch v7/quote.

    Yahoo-backed stocks are fetched in a single batch request (1-2 HTTP calls
    per chunk). Other asset types go through *compute_fn*
    (per-symbol OHLCV). Returns None when the batch fails and the
    caller should fall back to the per-symbol path for everything.
    """
    # Split entries
    stock_entries: List[Tuple[str, str]] = []
    non_stock_entries: List[Tuple[str, str]] = []
    for sym, atype in unique_entries:
        if atype in _STOCK_ASSET_TYPES:
            stock_entries.append((sym, atype))
        else:
            non_stock_entries.append((sym, atype))

    stock_syms = [sym for sym, _ in stock_entries]

    # Batch v7/quote — 1 request for all stocks
    quotes = _yahoo_quote_batch(stock_syms) if stock_syms else []

    # Had stocks but batch returned nothing → fail, let caller fall back
    if stock_syms and not quotes:
        return None

    quote_map = {q["symbol"]: q for q in quotes}
    results: List[dict] = []

    # --- stock results from batch quote data ---
    for sym, atype in stock_entries:
        q = quote_map.get(sym)
        currency = q.get("currency") if q else None
        display_currency = _heatmap_currency(sym, atype, currency)
        market = _heatmap_stock_meta(sym, atype)[1]
        if q:
            turnover = None
            if q["volume"] and q["price"]:
                turnover = round(q["volume"] * q["price"], 2)
            results.append({
                "symbol": sym,
                "name": q.get("name"),
                "type": atype,
                "return_pct": round(q["change_pct"], 2) if q["change_pct"] is not None else None,
                "turnover": turnover,
                "turnover_currency": display_currency,
                "market": market,
                "market_cap": q.get("market_cap") if include_market_cap else None,
                "market_cap_currency": display_currency,
            })
        else:
            results.append({
                "symbol": sym, "name": None, "type": atype,
                "return_pct": None, "turnover": None,
                "turnover_currency": display_currency,
                "market": market,
                "market_cap": None,
                "market_cap_currency": display_currency,
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


def _eastmoney_detail_quote(symbol: str) -> Optional[Dict]:
    """Return a normalized US quote snapshot from East Money as a fallback."""
    fields = ",".join((
        "f43",   # current price
        "f57",   # symbol
        "f58",   # name
        "f59",   # price decimal places
        "f84",   # total shares
        "f116",  # total market cap
        "f152",  # ratio decimal places
        "f163",  # trailing P/E
        "f167",  # price/book
        "f172",  # currency
        "f174",  # 52-week high
        "f175",  # 52-week low
    ))

    def scaled(value, decimal_places) -> Optional[float]:
        number = _finite_quote_number(value)
        places = _finite_quote_number(decimal_places)
        if number is None:
            return None
        divisor = 10 ** int(places if places is not None else 0)
        return number / divisor

    def positive_scaled(value, decimal_places) -> Optional[float]:
        number = scaled(value, decimal_places)
        return number if number is not None and number > 0 else None

    for prefix in ("105", "106", "107"):
        try:
            response = _em_session.get(
                _EM_QUOTE_URL,
                params={
                    "secid": f"{prefix}.{symbol}",
                    "fields": fields,
                    "_": int(time.time()),
                },
                timeout=5,
            )
            response.raise_for_status()
            data = response.json().get("data") or {}
            if str(data.get("f57") or "").upper() != symbol.upper():
                continue
            name = data.get("f58")
            quote_type = (
                "ETF"
                if "ETF" in str(name or "").upper()
                or "TRUST" in str(name or "").upper()
                else "EQUITY"
            )
            return {
                "symbol": symbol.upper(),
                "name": name,
                "price": scaled(data.get("f43"), data.get("f59")),
                "quote_type": quote_type,
                "currency": data.get("f172") or "USD",
                "market_cap": _finite_quote_number(data.get("f116")),
                "trailing_pe": positive_scaled(data.get("f163"), data.get("f152")),
                "price_to_book": positive_scaled(data.get("f167"), data.get("f152")),
                "shares_outstanding": _finite_quote_number(data.get("f84")),
                "fifty_two_week_high": scaled(data.get("f174"), data.get("f59")),
                "fifty_two_week_low": scaled(data.get("f175"), data.get("f59")),
            }
        except Exception as error:
            logger.debug(
                "East Money detail quote failed for %s (prefix %s): %s",
                symbol,
                prefix,
                error,
            )
    return None


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
    include_market_cap: bool = False, market_type: Optional[str] = None,
) -> dict:
    """Compute per-symbol return + turnover for a treemap heatmap.

    Args:
        symbols: list of {"symbol": str, "type": str}
        period: one of "today", "week", "month", "quarter", "year"
        auto_top_n: if > 0, auto-include the selected market's candidate pool,
                    fetch all, and return top N by turnover plus user symbols.
        include_market_cap: if True, attach market_cap (best-effort) to each item.
        market_type: when set, include the complete configured pool for stock,
                     hk_stock, global_stock, crypto, or cn_stock.

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
            atype = entry.get("type", "stock").strip().lower()
            sym = normalize_asset_symbol(entry["symbol"], atype)
        except (KeyError, AttributeError):
            continue
        key = (sym, atype)
        if not sym or key in seen:
            continue
        seen.add(key)
        user_symbols_set.add(sym)
        unique_entries.append((sym, atype))

    auto_syms = set()
    if market_type or auto_top_n > 0:
        selected_market = market_type or "stock"
        auto_asset_type = _HEATMAP_MARKET_ASSET_TYPES.get(
            selected_market, selected_market
        )
        top_symbols = _fetch_heatmap_watchlist(selected_market)
        for sym in top_symbols:
            key = (sym, auto_asset_type)
            if key not in seen:
                seen.add(key)
                auto_syms.add(sym)
                unique_entries.append((sym, auto_asset_type))

    # Selecting a market means showing its entire configured pool. The
    # historical auto_top_n limit is only applied to legacy requests that do
    # not provide market_type.
    result_limit = len(auto_syms) if market_type else auto_top_n

    def _compute_one(sym: str, atype: str) -> dict:
        series = _fetch_daily_series_cached(sym, atype)

        currency, market = _heatmap_stock_meta(sym, atype)
        result = {
            "symbol": sym,
            "name": None,
            "type": atype,
            "return_pct": None,
            "turnover": None,
            "turnover_currency": currency,
            "market": market,
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
            result_limit, include_market_cap, _compute_one,
        )
        if result is not None:
            result["market_type"] = market_type
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

    # Sort the market pool by turnover. Selected markets keep the full pool;
    # legacy auto_top_n callers still receive only their requested limit.
    auto_results.sort(
        key=lambda r: r["turnover"] if r["turnover"] is not None else 0,
        reverse=True,
    )
    top_auto = auto_results[:result_limit] if result_limit > 0 else []

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
        stock_syms = [
            r["symbol"] for r in ordered if r["type"] in _STOCK_ASSET_TYPES
        ]
        quote_map = {
            q["symbol"]: q for q in _yahoo_quote_batch(stock_syms)
        } if stock_syms else {}

        for r in ordered:
            if r["type"] in _STOCK_ASSET_TYPES:
                quote = quote_map.get(r["symbol"])
                if quote and quote.get("name"):
                    r["name"] = quote["name"]
                quote_currency = quote.get("currency") if quote else None
                r["market_cap_currency"] = _heatmap_currency(
                    r["symbol"], r["type"], quote_currency
                )

        if include_market_cap:
            caps = {
                sym: float(quote["market_cap"])
                for sym, quote in quote_map.items()
                if quote.get("market_cap") and float(quote["market_cap"]) > 0
            }
            missing_us_caps = [
                r["symbol"] for r in ordered
                if r["type"] == "stock" and r["symbol"] not in caps
            ]
            if missing_us_caps:
                caps.update(_get_market_caps(missing_us_caps))
            for r in ordered:
                r["market_cap"] = (
                    caps.get(r["symbol"])
                    if r["type"] in _STOCK_ASSET_TYPES
                    else None
                )

    return {
        "market_type": market_type,
        "period": period,
        "period_label": _period_label(period),
        "data": ordered,
    }
