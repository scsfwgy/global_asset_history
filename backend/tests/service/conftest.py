"""Fixtures for service-layer tests."""

from unittest.mock import MagicMock, patch

import pytest

from service.price_change.common import PriceSeries, empty_series
from tests.conftest import make_series


@pytest.fixture
def mock_fetch_daily_series():
    """Returns a MagicMock that can be configured per-test.

    Usage:
        def test_foo(mock_fetch_daily_series):
            mock_fetch_daily_series.return_value = make_series(years=3)
            # call service function...
    """
    with patch(
        "service.price_change.price_change_service._fetch_daily_series_cached"
    ) as mock:
        yield mock


@pytest.fixture
def three_year_series():
    """A 3-year PriceSeries with trending data."""
    return make_series(years=3, start_price=100.0, trend=0.0002)


@pytest.fixture
def flat_series():
    """A 1-year PriceSeries with flat prices (all = 100.0)."""
    from datetime import date

    from tests.conftest import _to_timestamp, _trading_dates

    dates = _trading_dates(date(2024, 1, 1), 252)
    ts = [_to_timestamp(d) for d in dates]
    closes = [100.0] * len(dates)
    return PriceSeries(
        timestamps=ts,
        closes=closes,
        source="test-flat",
        fetched_at=0.0,
    )


@pytest.fixture
def error_series():
    """A PriceSeries that represents a fetch error."""
    return empty_series("test", "network timeout")


@pytest.fixture
def two_point_series():
    """Minimal series: just 2 trading days."""
    from datetime import date

    from tests.conftest import _to_timestamp

    ts = [
        _to_timestamp(date(2024, 1, 3)),
        _to_timestamp(date(2024, 1, 4)),
    ]
    closes = [100.0, 105.0]
    return PriceSeries(
        timestamps=ts,
        closes=closes,
        source="test-minimal",
        fetched_at=0.0,
    )
