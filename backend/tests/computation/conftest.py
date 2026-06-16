"""Fixtures for pure-computation tests."""

from datetime import date
from typing import List, Optional, Tuple

import pytest

from tests.conftest import (
    _to_timestamp,
    _trading_dates,
    make_crash_data,
    make_daily_data,
    make_series,
    make_series_with_nulls,
    make_zero_price_series,
)


@pytest.fixture
def daily_3year() -> Tuple[List[int], List[float], List[float], List[float], List[float]]:
    """3 years of daily OHLC data: timestamps, closes, opens, highs, lows."""
    return make_daily_data(years=3, start_price=100.0, trend=0.0002)


@pytest.fixture
def daily_3year_ts(daily_3year) -> List[int]:
    return daily_3year[0]


@pytest.fixture
def daily_3year_closes(daily_3year) -> List[float]:
    return daily_3year[1]


@pytest.fixture
def sample_series():
    """PriceSeries with 3 years of trending data."""
    return make_series(years=3, start_price=100.0, trend=0.0002)


@pytest.fixture
def series_with_nulls():
    """PriceSeries with periodic None closes."""
    return make_series_with_nulls(years=2, null_every=5)


@pytest.fixture
def zero_price_series():
    """PriceSeries containing a zero close."""
    return make_zero_price_series()


@pytest.fixture
def crash_data() -> Tuple[List[int], List[float]]:
    """Price data with known crash events."""
    return make_crash_data()


@pytest.fixture
def crash_ts(crash_data) -> List[int]:
    return crash_data[0]


@pytest.fixture
def crash_closes(crash_data) -> List[float]:
    return crash_data[1]


@pytest.fixture
def sample_price_points() -> List[Tuple[date, float]]:
    """A deterministic list of (date, close) pairs for execution resolution."""
    dates = _trading_dates(date(2024, 1, 1), 30)
    price = 100.0
    points: List[Tuple[date, float]] = []
    for d in dates:
        price *= (1.0 + 0.001)  # mild uptrend
        points.append((d, round(price, 6)))
    return points
