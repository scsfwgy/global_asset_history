"""Historical valuation and profitability data for US company stocks."""

from __future__ import annotations

import math
import json
import logging
import statistics
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import quote

import requests as _requests

from . import cache_store

logger = logging.getLogger(__name__)

_SUCCESS_TTL_SECONDS = 24 * 60 * 60
_ERROR_TTL_SECONDS = 10 * 60
_CACHE_SCHEMA_VERSION = "v2"
_CACHE_LOCK = threading.RLock()
_MAX_MEMORY_CACHE_ENTRIES = 256
_HISTORY_CACHE: OrderedDict[str, tuple] = OrderedDict()
_FETCH_LOCKS: Dict[str, tuple] = {}
_YAHOO_TIMESERIES_URL = (
    "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/"
    "v1/finance/timeseries/{symbol}"
)
_YAHOO_TYPES = (
    "quarterlyPeRatio,quarterlyPbRatio,"
    "trailingPeRatio,trailingPbRatio"
)
_YAHOO_COOKIE_URL = "https://fc.yahoo.com"
_YAHOO_CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
_YAHOO_CRUMB_TTL_SECONDS = 60 * 60
_YAHOO_CRUMB_FAILURE_TTL_SECONDS = 5 * 60
_EASTMONEY_DATA_URL = (
    "https://datacenter.eastmoney.com/securities/api/data/v1/get"
)
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

try:
    from curl_cffi import requests as _curl_requests

    _yahoo_session = _curl_requests.Session(
        impersonate="chrome",
        trust_env=False,
    )
except Exception:  # pragma: no cover - curl_cffi is optional
    _yahoo_session = _requests.Session()
    _yahoo_session.trust_env = False
    _yahoo_session.headers.update({"User-Agent": _USER_AGENT})

_eastmoney_session = _requests.Session()
_eastmoney_session.trust_env = False
_eastmoney_session.headers.update(
    {
        "User-Agent": _USER_AGENT,
        "Referer": "https://emweb.securities.eastmoney.com/",
    }
)

_yahoo_crumb: Optional[str] = None
_yahoo_crumb_at = 0.0
_yahoo_crumb_failure_at = 0.0
_YAHOO_CRUMB_LOCK = threading.Lock()


def _clear_yahoo_crumb() -> None:
    """Discard Yahoo's cached authentication token."""
    global _yahoo_crumb, _yahoo_crumb_at, _yahoo_crumb_failure_at
    with _YAHOO_CRUMB_LOCK:
        _yahoo_crumb = None
        _yahoo_crumb_at = 0.0
        _yahoo_crumb_failure_at = 0.0


def _get_yahoo_crumb(force_refresh: bool = False) -> Optional[str]:
    """Return a cookie-bound Yahoo crumb, refreshing it at most hourly."""
    global _yahoo_crumb, _yahoo_crumb_at, _yahoo_crumb_failure_at
    with _YAHOO_CRUMB_LOCK:
        now = time.time()
        if force_refresh:
            _yahoo_crumb = None
            _yahoo_crumb_at = 0.0
            _yahoo_crumb_failure_at = 0.0
        if (
            _yahoo_crumb
            and now - _yahoo_crumb_at < _YAHOO_CRUMB_TTL_SECONDS
        ):
            return _yahoo_crumb
        if (
            _yahoo_crumb_failure_at
            and now - _yahoo_crumb_failure_at
            < _YAHOO_CRUMB_FAILURE_TTL_SECONDS
        ):
            return None

        try:
            # fc.yahoo.com commonly returns 404 while still setting the cookie
            # required by the crumb endpoint, so its status is intentionally
            # not treated as a failure.
            _yahoo_session.get(_YAHOO_COOKIE_URL, timeout=8)
            response = _yahoo_session.get(_YAHOO_CRUMB_URL, timeout=8)
            response.raise_for_status()
            crumb = str(response.text or "").strip()
            if crumb and "<" not in crumb and len(crumb) < 64:
                _yahoo_crumb = crumb
                _yahoo_crumb_at = now
                _yahoo_crumb_failure_at = 0.0
                return crumb
            _yahoo_crumb_failure_at = now
            logger.warning(
                "event=fundamentals_history_source_error "
                "source=yahoo stage=crumb reason=invalid_token status=%s",
                getattr(response, "status_code", None),
            )
        except Exception as exc:  # noqa: BLE001 - source degrades cleanly
            _yahoo_crumb_failure_at = now
            logger.warning(
                "event=fundamentals_history_source_error "
                "source=yahoo stage=crumb error=%s status=%s",
                type(exc).__name__,
                getattr(getattr(exc, "response", None), "status_code", None),
            )
        return None


def _finite_number(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _iso_date(value) -> Optional[str]:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _yahoo_points(items) -> List[Dict]:
    by_date: Dict[str, float] = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        as_of = _iso_date(item.get("asOfDate"))
        reported = item.get("reportedValue")
        value = _finite_number(
            reported.get("raw") if isinstance(reported, dict) else None
        )
        if as_of and value is not None and value > 0 and as_of not in by_date:
            by_date[as_of] = round(value, 6)
    return [
        {"date": as_of, "value": by_date[as_of]}
        for as_of in sorted(by_date)
    ]


def _latest_yahoo_value(items) -> Optional[float]:
    points = _yahoo_points(items)
    return points[-1]["value"] if points else None


def _parse_yahoo_valuation_payload(payload: dict) -> Dict:
    parsed = {
        "pe": [],
        "pb": [],
        "latest_pe": None,
        "latest_pb": None,
    }
    timeseries = payload.get("timeseries") if isinstance(payload, dict) else None
    results = timeseries.get("result") if isinstance(timeseries, dict) else None
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict):
            continue
        if "quarterlyPeRatio" in item:
            parsed["pe"] = _yahoo_points(item.get("quarterlyPeRatio"))
        if "quarterlyPbRatio" in item:
            parsed["pb"] = _yahoo_points(item.get("quarterlyPbRatio"))
        if "trailingPeRatio" in item:
            parsed["latest_pe"] = _latest_yahoo_value(
                item.get("trailingPeRatio")
            )
        if "trailingPbRatio" in item:
            parsed["latest_pb"] = _latest_yahoo_value(
                item.get("trailingPbRatio")
            )
    return parsed


def _parse_eastmoney_roe_payload(payload: dict) -> List[Dict]:
    result = payload.get("result") if isinstance(payload, dict) else None
    rows = result.get("data") if isinstance(result, dict) else None
    by_date: Dict[str, float] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or str(row.get("DATE_TYPE_CODE")) != "001":
            continue
        report_date = _iso_date(row.get("REPORT_DATE"))
        value = _finite_number(
            row.get("ROE_AVG")
            if row.get("ROE_AVG") is not None
            else row.get("ROE")
        )
        if report_date and value is not None and report_date not in by_date:
            by_date[report_date] = round(value, 6)
    return [
        {"date": report_date, "value": by_date[report_date]}
        for report_date in sorted(by_date)
    ]


def _metric_stats(points: List[Dict], current, years: int = 5) -> Dict:
    """Calculate a recent median and the current value's empirical percentile."""
    current_value = _finite_number(current)
    dated_values = []
    for point in points if isinstance(points, list) else []:
        if not isinstance(point, dict):
            continue
        point_date = _iso_date(point.get("date"))
        point_value = _finite_number(point.get("value"))
        if point_date and point_value is not None:
            dated_values.append((date.fromisoformat(point_date), point_value))

    if not dated_values:
        return {"median_5y": None, "percentile_5y": None}

    latest_date = max(point_date for point_date, _ in dated_values)
    try:
        cutoff = latest_date.replace(year=latest_date.year - years)
    except ValueError:
        cutoff = latest_date.replace(
            year=latest_date.year - years,
            day=28,
        )
    values = [
        value
        for point_date, value in dated_values
        if point_date >= cutoff
    ]
    if len(values) < 4:
        return {"median_5y": None, "percentile_5y": None}

    median = round(float(statistics.median(values)), 6)
    if current_value is None:
        return {"median_5y": median, "percentile_5y": None}
    percentile = round(
        sum(value <= current_value for value in values) * 100.0 / len(values),
        2,
    )
    return {"median_5y": median, "percentile_5y": percentile}


def _fetch_yahoo_valuation_history(symbol: str) -> Dict:
    """Fetch quarterly PE/PB series plus the latest trailing ratios."""
    empty = {
        "pe": [],
        "pb": [],
        "latest_pe": None,
        "latest_pb": None,
    }
    try:
        crumb = _get_yahoo_crumb()
        if not crumb:
            return empty

        url = _YAHOO_TIMESERIES_URL.format(symbol=quote(symbol, safe=""))

        def request(active_crumb: str):
            return _yahoo_session.get(
                url,
                params={
                "symbol": symbol,
                "type": _YAHOO_TYPES,
                "period1": 1483142400,
                "period2": int(time.time()),
                    "crumb": active_crumb,
                },
                timeout=10,
            )

        response = request(crumb)
        if getattr(response, "status_code", None) in (401, 403):
            refreshed_crumb = _get_yahoo_crumb(force_refresh=True)
            if not refreshed_crumb:
                return empty
            response = request(refreshed_crumb)
        response.raise_for_status()
        parsed = _parse_yahoo_valuation_payload(response.json())
        logger.info(
            "Yahoo fundamentals history symbol=%s pe_points=%d pb_points=%d",
            symbol,
            len(parsed["pe"]),
            len(parsed["pb"]),
        )
        return parsed
    except Exception as exc:  # noqa: BLE001 - one source must degrade cleanly
        logger.warning(
            "event=fundamentals_history_source_error "
            "source=yahoo stage=timeseries symbol=%s error=%s status=%s",
            symbol,
            type(exc).__name__,
            getattr(getattr(exc, "response", None), "status_code", None),
        )
        return empty


def _fetch_eastmoney_roe_history(symbol: str) -> List[Dict]:
    """Resolve a US security and fetch Eastmoney's annual average ROE rows."""
    try:
        profile_response = _eastmoney_session.get(
            _EASTMONEY_DATA_URL,
            params={
                "reportName": "RPT_USF10_INFO_ORGPROFILE",
                "columns": "SECUCODE,SECURITY_CODE",
                "filter": f'(SECURITY_CODE="{symbol}")',
                "pageNumber": 1,
                "pageSize": 10,
                "source": "HSF10",
                "client": "PC",
            },
            timeout=10,
        )
        profile_response.raise_for_status()
        profile_result = profile_response.json().get("result") or {}
        profile_rows = profile_result.get("data") or []
        security_code = next(
            (
                str(row.get("SECUCODE"))
                for row in profile_rows
                if isinstance(row, dict) and row.get("SECUCODE")
            ),
            None,
        )
        if not security_code:
            logger.info(
                "Eastmoney ROE security unresolved symbol=%s",
                symbol,
            )
            return []

        indicator_response = _eastmoney_session.get(
            _EASTMONEY_DATA_URL,
            params={
                "reportName": "RPT_USF10_FN_GMAININDICATOR",
                "columns": "USF10_FN_GMAININDICATOR",
                "filter": (
                    f'(SECUCODE="{security_code}")'
                    '(DATE_TYPE_CODE="001")'
                ),
                "sortColumns": "REPORT_DATE",
                "sortTypes": -1,
                "pageNumber": 1,
                "pageSize": 100,
                "source": "HSF10",
                "client": "PC",
            },
            timeout=10,
        )
        indicator_response.raise_for_status()
        points = _parse_eastmoney_roe_payload(indicator_response.json())
        logger.info(
            "Eastmoney ROE history symbol=%s points=%d",
            symbol,
            len(points),
        )
        return points
    except Exception as exc:  # noqa: BLE001 - one source must degrade cleanly
        logger.warning(
            "event=fundamentals_history_source_error "
            "source=eastmoney stage=annual_roe symbol=%s error=%s status=%s",
            symbol,
            type(exc).__name__,
            getattr(getattr(exc, "response", None), "status_code", None),
        )
        return []


def _cache_key(symbol: str) -> str:
    return f"fundamentals-history:{_CACHE_SCHEMA_VERSION}:{symbol}"


def clear_fundamentals_history_cache() -> None:
    """Clear the process-local cache, primarily for tests and diagnostics."""
    with _CACHE_LOCK:
        _HISTORY_CACHE.clear()
        _FETCH_LOCKS.clear()


def _retain_fetch_lock(cache_key: str) -> threading.Lock:
    with _CACHE_LOCK:
        entry = _FETCH_LOCKS.get(cache_key)
        if entry:
            lock, users = entry
            _FETCH_LOCKS[cache_key] = (lock, users + 1)
            return lock
        lock = threading.Lock()
        _FETCH_LOCKS[cache_key] = (lock, 1)
        return lock


def _release_fetch_lock(cache_key: str, lock: threading.Lock) -> None:
    with _CACHE_LOCK:
        entry = _FETCH_LOCKS.get(cache_key)
        if not entry or entry[0] is not lock:
            return
        users = entry[1] - 1
        if users <= 0:
            del _FETCH_LOCKS[cache_key]
        else:
            _FETCH_LOCKS[cache_key] = (lock, users)


def _remember_payload(
    cache_key: str,
    payload: Dict,
    expires_at: float,
) -> None:
    """Store one L1 entry while sweeping expiry and enforcing a hard bound."""
    now = time.monotonic()
    with _CACHE_LOCK:
        expired_keys = [
            key
            for key, (entry_expires_at, _) in _HISTORY_CACHE.items()
            if entry_expires_at <= now
        ]
        for key in expired_keys:
            del _HISTORY_CACHE[key]
        _HISTORY_CACHE[cache_key] = (expires_at, payload)
        _HISTORY_CACHE.move_to_end(cache_key)
        while len(_HISTORY_CACHE) > _MAX_MEMORY_CACHE_ENTRIES:
            _HISTORY_CACHE.popitem(last=False)


def _cached_payload(cache_key: str) -> Optional[Dict]:
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _HISTORY_CACHE.get(cache_key)
        if cached:
            expires_at, payload = cached
            if now < expires_at:
                _HISTORY_CACHE.move_to_end(cache_key)
                logger.info(
                    "event=fundamentals_history_cache_hit layer=l1 key=%s",
                    cache_key,
                )
                return payload
            del _HISTORY_CACHE[cache_key]

    raw = cache_store.cache_get(cache_key)
    if not raw:
        return None
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(decoded, dict):
        return None

    if (
        isinstance(decoded.get("payload"), dict)
        and _finite_number(decoded.get("cached_at")) is not None
        and _finite_number(decoded.get("ttl")) is not None
    ):
        payload = decoded["payload"]
        remaining = (
            float(decoded["cached_at"])
            + float(decoded["ttl"])
            - time.time()
        )
        if remaining <= 0:
            return None
        ttl = remaining
    else:
        # Backward-compatible read of the original payload-only cache format.
        payload = decoded
        ttl = (
            _SUCCESS_TTL_SECONDS
            if payload.get("available")
            else _ERROR_TTL_SECONDS
        )
    _remember_payload(cache_key, payload, now + ttl)
    logger.info(
        "event=fundamentals_history_cache_hit layer=l2 key=%s "
        "remaining_ttl_seconds=%d",
        cache_key,
        max(0, round(ttl)),
    )
    return payload


def _store_payload(cache_key: str, payload: Dict, ttl: int) -> None:
    _remember_payload(cache_key, payload, time.monotonic() + ttl)
    cache_store.cache_set(
        cache_key,
        json.dumps(
            {
                "cached_at": time.time(),
                "ttl": ttl,
                "payload": payload,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        ttl,
    )


def fetch_fundamentals_history(symbol: str) -> Dict:
    """Return historical PE, PB and annual ROE data for a US company stock."""
    normalized_symbol = str(symbol or "").strip().upper()
    cache_key = _cache_key(normalized_symbol)
    cached = _cached_payload(cache_key)
    if cached is not None:
        return cached

    fetch_lock = _retain_fetch_lock(cache_key)
    try:
        with fetch_lock:
            cached = _cached_payload(cache_key)
            if cached is not None:
                return cached
            return _fetch_and_store_fundamentals_history(
                normalized_symbol,
                cache_key,
            )
    finally:
        _release_fetch_lock(cache_key, fetch_lock)


def _fetch_and_store_fundamentals_history(
    normalized_symbol: str,
    cache_key: str,
) -> Dict:
    """Fetch both independent sources and persist their merged response."""
    started_at = time.monotonic()
    logger.info(
        "event=fundamentals_history_fetch_start symbol=%s",
        normalized_symbol,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        yahoo_future = executor.submit(
            _fetch_yahoo_valuation_history,
            normalized_symbol,
        )
        roe_future = executor.submit(
            _fetch_eastmoney_roe_history,
            normalized_symbol,
        )
        yahoo = yahoo_future.result()
        roe = roe_future.result()
    pe = yahoo.get("pe") if isinstance(yahoo.get("pe"), list) else []
    pb = yahoo.get("pb") if isinstance(yahoo.get("pb"), list) else []
    latest_pe = _finite_number(yahoo.get("latest_pe"))
    latest_pb = _finite_number(yahoo.get("latest_pb"))
    latest_roe = _finite_number(roe[-1].get("value")) if roe else None
    latest_roe_date = _iso_date(roe[-1].get("date")) if roe else None

    available_metrics = sum(bool(series) for series in (pe, pb, roe))
    available = available_metrics > 0
    payload = {
        "symbol": normalized_symbol,
        "available": available,
        "partial": available and available_metrics < 3,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "latest": {
            "pe": latest_pe,
            "pb": latest_pb,
            "roe": latest_roe,
            "roe_report_date": latest_roe_date,
        },
        "series": {
            "pe": pe,
            "pb": pb,
            "roe": roe,
        },
        "stats": {
            "pe": _metric_stats(pe, latest_pe),
            "pb": _metric_stats(pb, latest_pb),
            "roe": _metric_stats(roe, latest_roe),
        },
        "sources": {
            "pe": "yahoo_fundamentals_timeseries",
            "pb": "yahoo_fundamentals_timeseries",
            "roe": "eastmoney_us_financials",
        },
    }
    ttl = _SUCCESS_TTL_SECONDS if available else _ERROR_TTL_SECONDS
    _store_payload(cache_key, payload, ttl)
    logger.info(
        "event=fundamentals_history_fetch_complete symbol=%s "
        "status=%s pe_points=%d pb_points=%d roe_points=%d "
        "duration_ms=%d",
        normalized_symbol,
        "full" if available_metrics == 3 else "partial" if available else "empty",
        len(pe),
        len(pb),
        len(roe),
        round((time.monotonic() - started_at) * 1000),
    )
    return payload
