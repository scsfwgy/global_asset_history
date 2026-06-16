"""Shared test fixtures and diagnostic tools for the GlobalAssetHistory test suite.

Provides deterministic test data factories (no random!) and a diagnostic
helper so tests can output meaningful information, not just pass/fail.
"""

import inspect
import time
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import pytest

# ——— test configuration ————————————————————————————————————————————————
# Override config path to use the real config file
import os

os.environ.setdefault("PYTHONPATH", "backend")


# ——— diagnostic helper ——————————————————————————————————————————————————

_DIAG_ENABLED = True  # set False to silence all diagnose() calls


def diagnose(label: str, value, expected=None) -> None:
    """Emit diagnostic info visible with pytest -s or on failure.

    Call this at key checkpoints inside test functions. Output includes the
    calling test name so you can trace which case produced what.
    """
    if not _DIAG_ENABLED:
        return
    frame = inspect.currentframe()
    if frame is not None and frame.f_back is not None:
        test_name = frame.f_back.f_code.co_name
    else:
        test_name = "<?>"
    print(f"\n  [DIAG {test_name}] {label}: {value!r}")
    if expected is not None:
        print(f"  [DIAG {test_name}] expected: {expected!r}")


# ——— date utilities ——————————————————————————————————————————————————————

_EPOCH_START = date(2022, 1, 3)  # first trading day anchor (Monday)


def _is_weekday(d: date) -> bool:
    return d.weekday() < 5  # Mon=0 .. Fri=4


def _trading_dates(start: date, count: int) -> List[date]:
    """Return `count` consecutive trading days starting on or after `start`."""
    result: List[date] = []
    d = start
    while len(result) < count:
        if _is_weekday(d):
            result.append(d)
        d += timedelta(days=1)
    return result


def _to_timestamp(d: date) -> int:
    """Convert a date to a noon UTC Unix timestamp (avoids DST edge cases)."""
    dt_utc = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc)
    return int(dt_utc.timestamp())


# ——— data factories ——————————————————————————————————————————————————————


def make_daily_data(
    years: int = 3,
    start_price: float = 100.0,
    trend: float = 0.0002,  # ~5% / year
    volatility: float = 0.01,
) -> Tuple[List[int], List[float], List[float], List[float], List[float]]:
    """Generate deterministic daily OHLC data for `years` years.

    Returns (timestamps, closes, opens, highs, lows) aligned lists.
    Every run with the same parameters produces identical data.
    """
    trading_days_per_year = 252
    total_days = years * trading_days_per_year
    dates = _trading_dates(_EPOCH_START, total_days)

    timestamps: List[int] = []
    closes: List[float] = []
    opens: List[float] = []
    highs: List[float] = []
    lows: List[float] = []

    prev_close = start_price
    for i, d in enumerate(dates):
        ts = _to_timestamp(d)
        timestamps.append(ts)

        # Deterministic "randomness" from index — sine wave with period 21
        phase = i / 21.0 * 3.14159265 * 2
        daily_factor = 1.0 + trend + volatility * (0.5 * __import__("math").sin(phase * 1.3)
                                                     + 0.3 * __import__("math").cos(phase * 2.7)
                                                     + 0.2 * __import__("math").sin(phase * 5.1))

        open_price = round(prev_close * (1.0 + 0.001 * __import__("math").sin(phase * 0.7)), 6)
        close_price = round(prev_close * daily_factor, 6)
        high_price = round(max(open_price, close_price) * (1.0 + abs(0.005 * __import__("math").sin(phase * 3.3))), 6)
        low_price = round(min(open_price, close_price) * (1.0 - abs(0.005 * __import__("math").cos(phase * 4.1))), 6)

        opens.append(open_price)
        closes.append(close_price)
        highs.append(high_price)
        lows.append(low_price)
        prev_close = close_price

    return timestamps, closes, opens, highs, lows


def make_series(
    years: int = 3,
    start_price: float = 100.0,
    trend: float = 0.0002,
    source: str = "test",
    with_ohlc: bool = True,
) -> "PriceSeries":
    """Build a PriceSeries from generated daily data.

    Imported lazily to avoid circular dependency during test collection.
    """
    from service.price_change.common import PriceSeries

    ts, closes, opens, highs, lows = make_daily_data(years, start_price, trend)
    return PriceSeries(
        timestamps=ts,
        closes=closes,
        source=source,
        fetched_at=time.time(),
        opens=opens if with_ohlc else None,
        highs=highs if with_ohlc else None,
        lows=lows if with_ohlc else None,
    )


def make_crash_data() -> Tuple[List[int], List[float]]:
    """Generate price data with known crash events for testing crash_stats.

    Timeline (252 trading days, ~1 year):
      Day   0– 49: normal growth, price ~100 → ~102
      Day  50    : -6.0% crash (102 → 95.88)
      Day  51– 99: slow recovery, reaches 102 by day 80
      Day 100    : -3.5% crash (small, near threshold)
      Day 101–149: recovery
      Day 150    : -10.0% crash (150 → 135), never recovers in window
      Day 151–251: partial recovery to 145 but not to 150
    """
    dates = _trading_dates(_EPOCH_START, 252)
    closes: List[float] = []
    timestamps: List[int] = []

    price = 100.0
    for i, d in enumerate(dates):
        timestamps.append(_to_timestamp(d))

        if i < 50:
            price *= 1.0004  # mild uptrend
        elif i == 50:
            price *= 0.94  # -6.0% crash
        elif 51 <= i < 100:
            price *= 1.0012  # steady recovery
            if i == 85:
                price = 102.5  # speed recovery
        elif i == 100:
            price *= 0.965  # -3.5% crash
        elif 101 <= i < 150:
            price *= 1.0008  # slow recovery
        elif i == 150:
            price *= 0.90  # -10.0% crash
        elif 151 <= i:
            price *= 1.0003  # partial recovery, never reaches pre-crash 150

        closes.append(round(price, 6))

    return timestamps, closes


def make_series_with_nulls(
    years: int = 2,
    start_price: float = 100.0,
    null_every: int = 5,  # every Nth trading day has close=None
) -> "PriceSeries":
    """Generate a PriceSeries where some closes are None (simulating gaps)."""
    from service.price_change.common import PriceSeries

    ts, closes, opens, highs, lows = make_daily_data(years, start_price)
    nulled_closes: List[Optional[float]] = []
    for i, c in enumerate(closes):
        if (i + 1) % null_every == 0:
            nulled_closes.append(None)
        else:
            nulled_closes.append(c)
    return PriceSeries(
        timestamps=ts,
        closes=nulled_closes,
        source="test-with-gaps",
        fetched_at=time.time(),
    )


def make_zero_price_series() -> "PriceSeries":
    """Generate a series where one close is exactly 0.0 (tests div-by-zero guards)."""
    from service.price_change.common import PriceSeries

    ts, closes, opens, highs, lows = make_daily_data(years=1, start_price=100.0)
    closes[10] = 0.0
    return PriceSeries(
        timestamps=ts,
        closes=closes,
        source="test-zero",
        fetched_at=time.time(),
    )


# ——— module-level coverage tracking ——————————————————————————————————————

_COVERAGE: Dict[str, int] = {}


def track_coverage(module: str, count: int) -> None:
    """Record test case count per module for terminal summary."""
    _COVERAGE[module] = _COVERAGE.get(module, 0) + count


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    """Print a coverage summary after all tests run."""
    terminalreporter.write_sep("=", "Test Coverage Summary")
    terminalreporter.write_line("")
    total = 0
    for module, count in sorted(_COVERAGE.items()):
        terminalreporter.write_line(f"  {module:50s} {count:>5d} test cases")
        total += count
    terminalreporter.write_line(f"  {'─'*50}  ─────")
    terminalreporter.write_line(f"  {'TOTAL':50s} {total:>5d} test cases")
    terminalreporter.write_line("")
