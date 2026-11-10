"""Short-lived quotes for the homepage, independent of historical series."""

import hashlib
import json
import logging
import math
import threading
import time
from datetime import datetime, timezone
from typing import Callable

from . import cache_store

logger = logging.getLogger(__name__)

QUOTE_TTL = 60
_FORCE_COOLDOWN = 10
_STALE_TTL = 6 * 60 * 60
_locks = {source: threading.Lock() for source in ("yahoo-quote", "tencent-quote", "binance-quote")}
_cache: dict[str, dict] = {source: {} for source in _locks}


def quote_number(value) -> float | None:
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) else None


def iso_time(timestamp) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _is_fresh(snapshot: dict, source: str, now: float, ttl: int) -> bool:
    stamp = snapshot["ts"]
    return now - stamp < ttl and (
        source != "binance-quote" or int(now // 86400) == int(stamp // 86400)
    )


def cached_quotes(
    source: str,
    symbols: list[str],
    fetch: Callable,
    force: bool = False,
) -> dict[str, dict]:
    """Coalesce refreshes per source and retain the last usable quote per symbol."""
    if not symbols:
        return {}
    digest = hashlib.sha256(json.dumps(sorted(symbols)).encode()).hexdigest()[:24]
    key = f"homepage-quotes:v1:{source}:{digest}"
    ttl = _FORCE_COOLDOWN if force else QUOTE_TTL

    with _locks[source]:
        now = time.time()
        local = _cache[source]
        for expired in [k for k, entry in local.items() if now - entry["ts"] >= _STALE_TTL]:
            local.pop(expired, None)
        snapshot = local.get(key, {"ts": 0, "quotes": {}})
        if _is_fresh(snapshot, source, now, ttl):
            logger.info("event=homepage_quote_cache layer=l1 source=%s count=%s", source, len(snapshot["quotes"]))
            return snapshot["quotes"]

        raw = cache_store.cache_get(key)
        if raw:
            try:
                shared = json.loads(raw)
                if isinstance(shared["quotes"], dict) and shared["ts"] > snapshot["ts"]:
                    snapshot = shared
            except (KeyError, TypeError, ValueError):
                logger.warning("Invalid homepage quote snapshot for %s", source)
            if _is_fresh(snapshot, source, now, ttl):
                local[key] = snapshot
                logger.info("event=homepage_quote_cache layer=l2 source=%s count=%s", source, len(snapshot["quotes"]))
                return snapshot["quotes"]

        started = time.perf_counter()
        previous = {
            symbol: quote for symbol, quote in snapshot["quotes"].items()
            if now - quote["fetched_ts"] < _STALE_TTL
        }
        try:
            quotes = fetch(symbols, previous)
        except Exception as exc:
            logger.warning("Homepage quote request failed for %s: %s", source, exc)
            quotes = []

        fetched = time.time()
        results = {symbol: {**quote, "stale": True} for symbol, quote in previous.items()}
        for quote in quotes:
            symbol = quote["symbol"]
            old = results.get(symbol)
            # An upstream replica can return an older trade after a successful refresh.
            if old and quote.get("trade_time") and old.get("trade_time") and quote["trade_time"] < old["trade_time"]:
                continue
            results[symbol] = {
                **quote, "source": source, "fetched_ts": quote.get("fetched_ts", fetched), "stale": False,
            }

        snapshot = {"ts": fetched, "quotes": results}
        local[key] = snapshot
        cache_store.cache_set(key, json.dumps(snapshot, separators=(",", ":")), _STALE_TTL)
        logger.info(
            "event=homepage_quote_refresh source=%s requested=%s received=%s stale=%s duration_ms=%.1f",
            source, len(symbols), len(quotes), sum(quote["stale"] for quote in results.values()),
            (time.perf_counter() - started) * 1000,
        )
        return results
