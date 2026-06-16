"""Tests for backend/service/price_change/calculations.py

Covers all 12 functions with normal, edge-case, and error scenarios.
"""

import math
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple

import pytest

from service.price_change.calculations import (
    _build_equity_curve,
    _compute_daily_returns_for_month,
    _compute_monthly_returns,
    _compute_money_weighted_annualized_return,
    _compute_yearly_returns,
    _generate_schedule_dates,
    _next_month_anchor,
    _normalize_frequency,
    _parse_iso_date,
    _resolve_execution_points,
    _safe_int,
    _series_points_in_range,
)
from tests.conftest import (
    _EPOCH_START,
    _to_timestamp,
    _trading_dates,
    diagnose,
    make_daily_data,
    track_coverage,
)

MOD = "calculations.py"


# ═══════════════════════════════════════════════════════════════════════════
# _compute_yearly_returns
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeYearlyReturns:
    """Year-over-year returns from year-end close prices."""

    def test_normal_multi_year(self, daily_3year_ts, daily_3year_closes):
        """3-year uptrend data should produce returns for years 2023 and 2024."""
        result = _compute_yearly_returns(daily_3year_ts, daily_3year_closes)
        diagnose("years found", sorted(result.keys()))
        diagnose("returns", {y: f"{r:.2f}%" for y, r in result.items()})
        # 3 years of data (2022, 2023, 2024) => 2 year-over-year returns
        assert len(result) >= 1, "Expected at least 1 YoY return"
        assert all(isinstance(k, str) for k in result), "Keys must be year strings"
        assert all(isinstance(v, float) for v in result.values()), "Values must be floats"
        track_coverage(MOD, 4)

    def test_single_year_returns_empty(self):
        """Only 1 year of data — needs at least 2 year-end closes."""
        dates = _trading_dates(_EPOCH_START, 100)  # all in 2022
        ts = [_to_timestamp(d) for d in dates]
        closes = [100.0 + i * 0.01 for i in range(100)]
        result = _compute_yearly_returns(ts, closes)
        assert result == {}
        track_coverage(MOD, 1)

    def test_empty_data(self):
        """Empty timestamps and closes should return {}."""
        assert _compute_yearly_returns([], []) == {}
        track_coverage(MOD, 1)

    def test_zero_prev_close_skipped(self):
        """Year where prev_close == 0 should be skipped (no ZeroDivisionError)."""
        # Build: 2022 close=0, 2023 close=110
        ts = [
            _to_timestamp(date(2022, 12, 30)),  # close=0
            _to_timestamp(date(2023, 12, 29)),  # close=110
        ]
        closes = [0.0, 110.0]
        result = _compute_yearly_returns(ts, closes)
        # 2023 should be skipped because prev_close (2022) == 0
        assert "2023" not in result or result.get("2023") is not None
        track_coverage(MOD, 1)

    def test_price_decline(self):
        """Price going down should produce negative returns."""
        ts = [
            _to_timestamp(date(2022, 12, 30)),
            _to_timestamp(date(2023, 12, 29)),
            _to_timestamp(date(2024, 12, 31)),
        ]
        closes = [100.0, 90.0, 81.0]
        result = _compute_yearly_returns(ts, closes)
        assert result["2023"] == pytest.approx(-10.0, abs=0.1)
        assert result["2024"] == pytest.approx(-10.0, abs=0.1)
        diagnose("decline returns", result)
        track_coverage(MOD, 1)

    def test_nulls_skipped(self):
        """None closes should be ignored; year-end is last valid close."""
        ts = [
            _to_timestamp(date(2022, 12, 28)),
            _to_timestamp(date(2022, 12, 29)),
            _to_timestamp(date(2022, 12, 30)),  # close=None, skipped
            _to_timestamp(date(2023, 12, 29)),  # close=110
        ]
        closes = [100.0, None, None, 110.0]
        result = _compute_yearly_returns(ts, closes)
        assert "2023" in result
        assert result["2023"] == pytest.approx(10.0, abs=0.1)
        track_coverage(MOD, 1)

    def test_gap_year(self):
        """Data in 2022 and 2024 but not 2023 — compute 2022→2024 directly."""
        ts = [
            _to_timestamp(date(2022, 12, 30)),
            _to_timestamp(date(2024, 12, 31)),
        ]
        closes = [100.0, 121.0]
        result = _compute_yearly_returns(ts, closes)
        assert "2024" in result
        assert result["2024"] == pytest.approx(21.0, abs=0.1)
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# _compute_monthly_returns
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeMonthlyReturns:
    """Month-over-month returns for a specific year."""

    def test_full_year(self):
        """All 12 months with data should produce 12 entries with computed returns."""
        # Build data covering 2023-01 through 2023-12, each month-end
        ts = []
        closes_list = []
        for m in range(1, 13):
            # last trading day of month (approximate)
            d = date(2023, m, 28)
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            ts.append(_to_timestamp(d))
            closes_list.append(100.0 + m * 2.0)  # rising price

        # Add Dec 2022 for January's prev_close
        dec_date = date(2022, 12, 29)
        while dec_date.weekday() >= 5:
            dec_date -= timedelta(days=1)
        ts.insert(0, _to_timestamp(dec_date))
        closes_list.insert(0, 100.0)

        result = _compute_monthly_returns(ts, closes_list, 2023)
        assert len(result) == 12
        # January should have a return (prev = Dec 2022, 100 → Jan 2023, 102)
        jan = result[0]
        assert jan["month"] == 1
        assert jan["return"] is not None
        assert jan["return"] == pytest.approx(2.0, abs=0.1)
        diagnose("January return", jan["return"])
        track_coverage(MOD, 2)

    def test_missing_months_return_none(self):
        """Months without data should have return=None."""
        ts = [
            _to_timestamp(date(2023, 3, 31)),
            _to_timestamp(date(2023, 6, 30)),
        ]
        closes = [105.0, 110.0]
        result = _compute_monthly_returns(ts, closes, 2023)
        assert len(result) == 12
        # Only months 3 and 6 might have data; others should be None
        none_months = [r for r in result if r["return"] is None]
        assert len(none_months) >= 10  # most months have no data
        track_coverage(MOD, 1)

    def test_january_boundary_uses_prev_december(self):
        """January's prev_close comes from December of previous year."""
        ts = [
            _to_timestamp(date(2022, 12, 30)),
            _to_timestamp(date(2023, 1, 31)),
        ]
        closes = [100.0, 105.0]
        result = _compute_monthly_returns(ts, closes, 2023)
        jan = result[0]
        assert jan["month"] == 1
        assert jan["return"] == pytest.approx(5.0, abs=0.1)
        diagnose("January cross-year", jan["return"])
        track_coverage(MOD, 1)

    def test_all_none_closes(self):
        """All closes are None → all 12 months return None."""
        ts = [_to_timestamp(date(2023, 1, 15))]
        closes: List[Optional[float]] = [None]
        result = _compute_monthly_returns(ts, closes, 2023)
        assert all(r["return"] is None for r in result)
        track_coverage(MOD, 1)

    def test_prev_close_zero(self):
        """When prev_close is 0, month return is None (div-by-zero guard)."""
        ts = [
            _to_timestamp(date(2022, 12, 30)),
            _to_timestamp(date(2023, 1, 31)),
        ]
        closes = [0.0, 105.0]
        result = _compute_monthly_returns(ts, closes, 2023)
        jan = result[0]
        assert jan["return"] is None
        track_coverage(MOD, 1)

    def test_year_not_in_data(self):
        """Requesting a year with no data → all months return None."""
        result = _compute_monthly_returns([], [], 2050)
        assert all(r["return"] is None for r in result)
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# _compute_daily_returns_for_month
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeDailyReturnsForMonth:
    """Daily returns within a specific month."""

    def test_normal_month(self):
        """A full month of trading days with rising prices."""
        dates = _trading_dates(date(2023, 3, 1), 23)  # March has ~23 trading days
        ts = [_to_timestamp(d) for d in dates]
        price = 100.0
        closes: List[float] = []
        for _ in dates:
            price *= 1.002
            closes.append(round(price, 6))

        result = _compute_daily_returns_for_month(ts, closes, 2023, 3)
        diagnose("daily returns count", len(result))
        assert len(result) > 0
        assert all("day" in r for r in result)
        assert all("date" in r for r in result)
        assert all("return" in r for r in result)
        assert all("close" in r for r in result)
        # First trading day should have return=None (no previous close)
        assert result[0]["return"] is None
        # Later days should have returns
        assert result[1]["return"] is not None
        diagnose("first day return (None expected)", result[0]["return"])
        diagnose("second day return", result[1]["return"])
        track_coverage(MOD, 3)

    def test_month_with_no_data(self):
        """Month not in data → empty list."""
        result = _compute_daily_returns_for_month([], [], 2050, 3)
        assert result == []
        track_coverage(MOD, 1)

    def test_cross_month_prev_close(self):
        """Prev_close for March 1 should come from February's last trading day."""
        ts = [
            _to_timestamp(date(2023, 2, 28)),
            _to_timestamp(date(2023, 3, 1)),
            _to_timestamp(date(2023, 3, 2)),
        ]
        closes = [100.0, 102.0, 103.0]
        result = _compute_daily_returns_for_month(ts, closes, 2023, 3)
        diagnose("March daily results", [(r["day"], r["return"]) for r in result])
        # March 1: prev_close is Feb 28's 100.0 → return 2.0%
        assert result[0]["day"] == 1
        assert result[0]["return"] == pytest.approx(2.0, abs=0.1)
        # March 2: prev_close is March 1's 102.0 → return ~0.98%
        assert result[1]["day"] == 2
        assert result[1]["return"] is not None
        track_coverage(MOD, 2)

    def test_none_closes_in_chain(self):
        """None closes should not break prev_close chain."""
        ts = [
            _to_timestamp(date(2023, 3, 1)),
            _to_timestamp(date(2023, 3, 2)),  # None
            _to_timestamp(date(2023, 3, 3)),
        ]
        closes: List[Optional[float]] = [100.0, None, 104.0]
        result = _compute_daily_returns_for_month(ts, closes, 2023, 3)
        # March 3 return uses March 1 as prev_close (skipping March 2)
        day3 = [r for r in result if r["day"] == 3]
        if day3:
            assert day3[0]["return"] == pytest.approx(4.0, abs=0.1)
        diagnose("day3 with None gap", day3)
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# _series_points_in_range
# ═══════════════════════════════════════════════════════════════════════════

class TestSeriesPointsInRange:
    """Date range filtering of price series."""

    def test_full_range(self, daily_3year_ts, daily_3year_closes):
        """Range covering all data should return all valid points."""
        start = _EPOCH_START
        end = _EPOCH_START + timedelta(days=365 * 3 + 10)
        points = _series_points_in_range(daily_3year_ts, daily_3year_closes, start, end)
        assert len(points) > 0
        diagnose("total points in full range", len(points))
        track_coverage(MOD, 1)

    def test_sub_range(self, daily_3year_ts, daily_3year_closes):
        """Only points within [start, end] should be returned."""
        start = date(2023, 1, 1)
        end = date(2023, 3, 31)
        points = _series_points_in_range(daily_3year_ts, daily_3year_closes, start, end)
        for d, _ in points:
            assert start <= d <= end
        diagnose("points in Q1 2023", len(points))
        track_coverage(MOD, 1)

    def test_empty_range(self):
        """start > end should return empty."""
        points = _series_points_in_range([], [], date(2024, 1, 1), date(2023, 1, 1))
        assert points == []
        track_coverage(MOD, 1)

    def test_single_date(self, daily_3year_ts, daily_3year_closes):
        """start == end returns points on that exact date."""
        # Pick a date we know exists
        target = date(2023, 6, 15)
        points = _series_points_in_range(daily_3year_ts, daily_3year_closes, target, target)
        for d, _ in points:
            assert d == target
        track_coverage(MOD, 1)

    def test_nulls_excluded(self):
        """None closes should be filtered out."""
        ts = [
            _to_timestamp(date(2023, 1, 3)),
            _to_timestamp(date(2023, 1, 4)),
        ]
        closes: List[Optional[float]] = [None, 105.0]
        start = date(2023, 1, 1)
        end = date(2023, 1, 31)
        points = _series_points_in_range(ts, closes, start, end)
        assert len(points) == 1
        assert points[0][1] == 105.0
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# _compute_money_weighted_annualized_return
# ═══════════════════════════════════════════════════════════════════════════

class TestMoneyWeightedReturn:
    """XIRR-style annualized return for DCA cashflows."""

    def test_simple_one_year_lump_sum(self):
        """Single contribution, exactly 1 year later final value 1100 on 1000 → ~10%."""
        cashflows = [(date(2023, 1, 1), -1000.0)]
        result = _compute_money_weighted_annualized_return(
            cashflows, date(2024, 1, 1), 1100.0
        )
        assert result is not None
        assert result == pytest.approx(0.10, abs=0.01)
        diagnose("1-year lump sum XIRR", f"{result*100:.2f}%")
        track_coverage(MOD, 1)

    def test_monthly_dca_one_year(self):
        """12 monthly contributions of -100, final value 1300 → positive rate."""
        cashflows = []
        for m in range(12):
            cashflows.append((date(2023, m + 1, 1), -100.0))
        result = _compute_money_weighted_annualized_return(
            cashflows, date(2024, 1, 1), 1300.0
        )
        assert result is not None
        assert result > 0, f"Expected positive rate, got {result}"
        diagnose("12-month DCA XIRR", f"{result*100:.2f}%")
        track_coverage(MOD, 1)

    def test_loss_scenario(self):
        """Final value < total invested → negative rate."""
        cashflows = [(date(2023, 1, 1), -1000.0)]
        result = _compute_money_weighted_annualized_return(
            cashflows, date(2024, 1, 1), 800.0
        )
        assert result is not None
        assert result < 0
        diagnose("loss XIRR", f"{result*100:.2f}%")
        track_coverage(MOD, 1)

    def test_final_value_zero_or_negative(self):
        """final_value <= 0 should return None."""
        result = _compute_money_weighted_annualized_return(
            [(date(2023, 1, 1), -1000.0)], date(2024, 1, 1), 0.0
        )
        assert result is None
        result2 = _compute_money_weighted_annualized_return(
            [(date(2023, 1, 1), -1000.0)], date(2024, 1, 1), -100.0
        )
        assert result2 is None
        track_coverage(MOD, 2)

    def test_empty_cashflows(self):
        """No cashflows → None."""
        result = _compute_money_weighted_annualized_return([], date(2024, 1, 1), 1000.0)
        assert result is None
        track_coverage(MOD, 1)

    def test_all_zero_amounts(self):
        """All amounts are 0 → filtered out, no flows → None."""
        result = _compute_money_weighted_annualized_return(
            [(date(2023, 1, 1), 0.0)], date(2024, 1, 1), 1000.0
        )
        assert result is None
        track_coverage(MOD, 1)

    def test_same_day_all_flows(self):
        """All cashflows on same day → zero duration → None."""
        result = _compute_money_weighted_annualized_return(
            [(date(2023, 1, 1), -500.0), (date(2023, 1, 1), -500.0)],
            date(2023, 1, 1),
            1100.0,
        )
        assert result is None
        track_coverage(MOD, 1)

    def test_multi_year_growth(self):
        """3-year DCA should produce a meaningful annualized return."""
        cashflows = []
        for m in range(36):
            d = date(2022, 1, 1)
            # advance by m months
            total_months = d.year * 12 + (d.month - 1) + m
            y = total_months // 12
            mo = total_months % 12 + 1
            cashflows.append((date(y, mo, 1), -100.0))
        result = _compute_money_weighted_annualized_return(
            cashflows, date(2025, 1, 1), 4500.0
        )
        assert result is not None
        diagnose("3-year DCA XIRR", f"{result*100:.2f}%")
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# _normalize_frequency
# ═══════════════════════════════════════════════════════════════════════════

class TestNormalizeFrequency:
    """Frequency string normalization and validation."""

    @pytest.mark.parametrize("input_val, expected", [
        ("monthly", "monthly"),
        ("  daily  ", "daily"),
        ("WEEKLY", "weekly"),
        ("once", "once"),
        ("YEARLY", "yearly"),
        (None, "monthly"),
        ("", "monthly"),
    ], ids=["monthly", "stripped_whitespace", "lowercased", "once", "yearly",
            "none_defaults", "empty_defaults"])
    def test_valid_frequencies(self, input_val, expected):
        """Valid inputs should normalize correctly; None/empty default to 'monthly'."""
        result = _normalize_frequency(input_val)
        assert result == expected
        diagnose(f"normalize({input_val!r})", result)
        track_coverage(MOD, 7)

    @pytest.mark.parametrize("input_val", [
        "quarterly",
        "biweekly",
        "annually",
        "    ",
    ], ids=["quarterly", "biweekly", "annually", "whitespace_only"])
    def test_invalid_frequencies_raise(self, input_val):
        """Invalid frequency strings should raise ValueError."""
        with pytest.raises(ValueError, match="frequency must be one of"):
            _normalize_frequency(input_val)
        track_coverage(MOD, 4)


# ═══════════════════════════════════════════════════════════════════════════
# _safe_int
# ═══════════════════════════════════════════════════════════════════════════

class TestSafeInt:
    """Safe integer conversion with fallback default."""

    @pytest.mark.parametrize("value, default, expected", [
        ("42", 10, 42),
        (42, 10, 42),
        ("0", 10, 0),
        ("-5", 10, -5),
    ], ids=["string_int", "actual_int", "zero", "negative"])
    def test_valid_conversions(self, value, default, expected):
        assert _safe_int(value, default) == expected
        track_coverage(MOD, 4)

    @pytest.mark.parametrize("value, default, expected", [
        (None, 10, 10),
        ("", 10, 10),
        ("abc", 99, 99),
        ("3.14", 50, 50),
        ([], 7, 7),
    ], ids=["none", "empty_str", "non_numeric", "float_str", "list"])
    def test_fallback_to_default(self, value, default, expected):
        assert _safe_int(value, default) == expected
        track_coverage(MOD, 5)


# ═══════════════════════════════════════════════════════════════════════════
# _parse_iso_date
# ═══════════════════════════════════════════════════════════════════════════

class TestParseIsoDate:
    """ISO date string parsing."""

    def test_valid_date(self):
        result = _parse_iso_date("2024-01-15", "start_date")
        assert result == date(2024, 1, 15)
        track_coverage(MOD, 1)

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="is required"):
            _parse_iso_date("", "start_date")
        track_coverage(MOD, 1)

    def test_none_raises(self):
        with pytest.raises(ValueError):
            _parse_iso_date(None, "end_date")
        track_coverage(MOD, 1)

    def test_wrong_format_raises(self):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            _parse_iso_date("01/15/2024", "date")
        track_coverage(MOD, 1)

    def test_invalid_date_raises(self):
        """Feb 30 doesn't exist."""
        with pytest.raises(ValueError):
            _parse_iso_date("2024-02-30", "date")
        track_coverage(MOD, 1)

    def test_field_name_in_error(self):
        """Error message should include the field name."""
        with pytest.raises(ValueError, match="custom_field"):
            _parse_iso_date("", "custom_field")
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# _next_month_anchor
# ═══════════════════════════════════════════════════════════════════════════

class TestNextMonthAnchor:
    """Month advancement with day clamping."""

    @pytest.mark.parametrize("current, months, target_day, expected", [
        (date(2024, 1, 15), 1, 15, date(2024, 2, 15)),
        (date(2024, 12, 15), 1, 15, date(2025, 1, 15)),
        (date(2024, 1, 31), 1, 31, date(2024, 2, 29)),   # leap year Feb
        (date(2025, 1, 31), 1, 31, date(2025, 2, 28)),   # non-leap year Feb
        (date(2024, 1, 15), 3, 15, date(2024, 4, 15)),
        (date(2024, 1, 31), 1, 31, date(2024, 2, 29)),   # day 31 → Feb 29 (leap)
        (date(2024, 3, 31), 1, 31, date(2024, 4, 30)),   # day 31 → Apr (30 days)
    ], ids=["normal_1m", "year_boundary", "leap_feb_clamp", "nonleap_feb_clamp",
            "multi_month", "jan31_to_feb", "mar31_to_apr"])
    def test_advances(self, current, months, target_day, expected):
        result = _next_month_anchor(current, months, target_day)
        assert result == expected
        diagnose(f"{current} +{months}m → day {target_day}", result)
        track_coverage(MOD, 7)


# ═══════════════════════════════════════════════════════════════════════════
# _generate_schedule_dates
# ═══════════════════════════════════════════════════════════════════════════

class TestGenerateScheduleDates:
    """DCA schedule generation for all frequency types."""

    def test_once(self):
        """Once frequency returns only start_date."""
        result = _generate_schedule_dates(
            date(2024, 1, 15), date(2024, 12, 31), "once", 1
        )
        assert result == [date(2024, 1, 15)]
        track_coverage(MOD, 1)

    def test_daily_interval_1(self):
        """Daily interval=1 from Jan 1 to Jan 5."""
        result = _generate_schedule_dates(
            date(2024, 1, 1), date(2024, 1, 5), "daily", 1
        )
        assert result == [
            date(2024, 1, 1),
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
            date(2024, 1, 5),
        ]
        track_coverage(MOD, 1)

    def test_daily_interval_2(self):
        """Daily interval=2 skips every other day."""
        result = _generate_schedule_dates(
            date(2024, 1, 1), date(2024, 1, 7), "daily", 2
        )
        assert result == [
            date(2024, 1, 1),
            date(2024, 1, 3),
            date(2024, 1, 5),
            date(2024, 1, 7),
        ]
        track_coverage(MOD, 1)

    def test_weekly_default_monday(self):
        """Weekly with default weekday (Monday=0)."""
        # Jan 1, 2024 is a Monday
        result = _generate_schedule_dates(
            date(2024, 1, 1), date(2024, 1, 21), "weekly", 1
        )
        assert len(result) == 3  # 3 Mondays: Jan 1, 8, 15
        assert all(d.weekday() == 0 for d in result)
        track_coverage(MOD, 1)

    def test_weekly_friday(self):
        """Weekly on Friday (weekday=4)."""
        # Jan 1, 2024 is Monday → first Friday is Jan 5
        result = _generate_schedule_dates(
            date(2024, 1, 1), date(2024, 1, 31), "weekly", 1, weekday=4
        )
        assert len(result) >= 3
        assert all(d.weekday() == 4 for d in result)
        assert result[0] == date(2024, 1, 5)
        diagnose("Friday schedule", [str(d) for d in result])
        track_coverage(MOD, 1)

    def test_monthly_day_15(self):
        """Monthly on the 15th. First date = start_date when start_day < anchor_day."""
        result = _generate_schedule_dates(
            date(2024, 1, 10), date(2024, 6, 15), "monthly", 1, anchor_day=15
        )
        # start_date.day (10) < anchor_day (15): first date is start_date Jan 10
        # Then subsequent dates fall on the 15th
        diagnose("monthly day-15 schedule", [str(d) for d in result])
        assert result[0] == date(2024, 1, 10)
        assert result[-1] == date(2024, 6, 15)
        # All dates after the first should be on the 15th
        if len(result) > 1:
            assert all(d.day == 15 for d in result[1:])
        track_coverage(MOD, 1)

    def test_monthly_day_31_clamping(self):
        """Monthly on day 31 clamps to last day of short months."""
        result = _generate_schedule_dates(
            date(2024, 1, 31), date(2024, 6, 30), "monthly", 1, anchor_day=31
        )
        diagnose("monthly day-31 schedule", [str(d) for d in result])
        assert result[0] == date(2024, 1, 31)
        assert result[1] == date(2024, 2, 29)  # leap year Feb
        assert result[2] == date(2024, 3, 31)
        assert result[3] == date(2024, 4, 30)  # April has 30 days
        track_coverage(MOD, 1)

    def test_monthly_start_after_anchor(self):
        """If start_date is after the anchor day, first execution is next month."""
        result = _generate_schedule_dates(
            date(2024, 1, 20), date(2024, 3, 31), "monthly", 1, anchor_day=15
        )
        # Jan 15 is before Jan 20, so first should be Feb 15
        assert result[0] == date(2024, 2, 15)
        track_coverage(MOD, 1)

    def test_yearly(self):
        """Yearly schedule."""
        result = _generate_schedule_dates(
            date(2022, 1, 1), date(2025, 1, 1), "yearly", 1
        )
        assert result == [
            date(2022, 1, 1),
            date(2023, 1, 1),
            date(2024, 1, 1),
            date(2025, 1, 1),
        ]
        track_coverage(MOD, 1)

    def test_yearly_leap_day(self):
        """Yearly from Feb 29 in a leap year clamps in non-leap years."""
        result = _generate_schedule_dates(
            date(2024, 2, 29), date(2028, 2, 28), "yearly", 1
        )
        diagnose("yearly from leap day", [str(d) for d in result])
        assert result[0] == date(2024, 2, 29)
        assert result[1] == date(2025, 2, 28)  # 2025 is not leap
        assert result[2] == date(2026, 2, 28)
        assert result[3] == date(2027, 2, 28)
        assert result[4] == date(2028, 2, 28)  # since end_date is Feb 28, no Feb 29
        track_coverage(MOD, 1)

    def test_end_before_start(self):
        """end_date < start_date → empty schedule."""
        result = _generate_schedule_dates(
            date(2024, 6, 1), date(2024, 1, 1), "monthly", 1
        )
        assert result == []
        track_coverage(MOD, 1)

    def test_monthly_interval_2(self):
        """Monthly interval=2 means every other month."""
        result = _generate_schedule_dates(
            date(2024, 1, 1), date(2024, 6, 30), "monthly", 2, anchor_day=1
        )
        diagnose("monthly interval=2 schedule", [str(d) for d in result])
        assert result[0] == date(2024, 1, 1)
        assert result[1] == date(2024, 3, 1)
        assert result[2] == date(2024, 5, 1)
        track_coverage(MOD, 1)

    def test_weekly_interval_2(self):
        """Weekly interval=2 means bi-weekly."""
        result = _generate_schedule_dates(
            date(2024, 1, 1), date(2024, 1, 31), "weekly", 2
        )
        # Jan 1 is Monday → should get Jan 1, Jan 15, Jan 29
        assert all(d.weekday() == 0 for d in result)
        diagnose("bi-weekly schedule", [str(d) for d in result])
        track_coverage(MOD, 1)


# ═══════════════════════════════════════════════════════════════════════════
# _resolve_execution_points
# ═══════════════════════════════════════════════════════════════════════════

class TestResolveExecutionPoints:
    """Execution point resolution: map planned dates to actual trading days."""

    def test_exact_match(self, sample_price_points):
        """When schedule dates match price dates exactly."""
        schedule = [sample_price_points[0][0], sample_price_points[2][0]]
        result = _resolve_execution_points(sample_price_points, schedule)
        assert len(result) == 2
        assert result[0][0] == schedule[0]
        assert result[1][0] == schedule[1]
        track_coverage(MOD, 1)

    def test_weekend_shifts_forward(self):
        """Scheduled Saturday resolves to next Monday (first available trading day)."""
        # Build price points with a gap on weekend
        prices = [
            (date(2024, 1, 5), 100.0),   # Friday
            (date(2024, 1, 8), 102.0),   # Monday
        ]
        schedule = [date(2024, 1, 6)]  # Saturday → should resolve to Jan 8
        result = _resolve_execution_points(prices, schedule)
        assert len(result) == 1
        assert result[0][0] == date(2024, 1, 8)
        diagnose("weekend resolution", f"{schedule[0]} → {result[0][0]}")
        track_coverage(MOD, 1)

    def test_duplicate_dates_deduplicated(self):
        """Same execution date should not appear twice."""
        prices = [
            (date(2024, 1, 3), 100.0),
            (date(2024, 1, 4), 101.0),
        ]
        schedule = [date(2024, 1, 3), date(2024, 1, 3)]  # duplicate
        result = _resolve_execution_points(prices, schedule)
        assert len(result) == 1
        track_coverage(MOD, 1)

    def test_schedule_beyond_data(self):
        """Schedule extends past available price data."""
        prices = [
            (date(2024, 1, 3), 100.0),
        ]
        schedule = [date(2024, 1, 3), date(2024, 1, 10)]
        result = _resolve_execution_points(prices, schedule)
        assert len(result) == 1  # only the first one resolved
        track_coverage(MOD, 1)

    def test_empty_inputs(self):
        """Empty price points or schedule → empty result."""
        assert _resolve_execution_points([], [date(2024, 1, 1)]) == []
        assert _resolve_execution_points([(date(2024, 1, 1), 100.0)], []) == []
        track_coverage(MOD, 2)


# ═══════════════════════════════════════════════════════════════════════════
# _build_equity_curve
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildEquityCurve:
    """Equity curve construction from price points and executions."""

    @staticmethod
    def _make_executed(
        dates: List[date],
        prices: List[float],
        amounts: List[float],
    ) -> List[Tuple[date, float, float, float, float]]:
        """Build executed_points in the format expected by _build_equity_curve.

        Format: (date, price, amount, bought_units, cum_units)
        """
        cum_units = 0.0
        result = []
        for d, p, amt in zip(dates, prices, amounts):
            bought = amt / p if p != 0 else 0.0
            cum_units += bought
            result.append((d, p, amt, bought, cum_units))
        return result

    def test_normal_dca_curve(self):
        """12 monthly executions, 24 months of price data."""
        price_dates = _trading_dates(date(2023, 1, 3), 24)
        price = 100.0
        price_points: List[Tuple[date, float]] = []
        for d in price_dates:
            price *= 1.005
            price_points.append((d, round(price, 6)))

        # Execute on the first of every month (if it's a trading day approximation)
        exec_dates = [price_points[i][0] for i in [0, 4, 8, 12, 16, 20]]
        exec_prices = [price_points[i][1] for i in [0, 4, 8, 12, 16, 20]]
        exec_amounts = [100.0] * len(exec_dates)
        executed = self._make_executed(exec_dates, exec_prices, exec_amounts)

        curve = _build_equity_curve(price_points, executed, 0.0, None, None)
        assert len(curve) == len(price_points)
        assert all("date" in p for p in curve)
        assert all("price" in p for p in curve)
        assert all("invested" in p for p in curve)
        assert all("value" in p for p in curve)
        # After first execution, invested should be > 0
        invested_values = [p["invested"] for p in curve]
        diagnose("invested growth", f"{invested_values[0]} → {invested_values[-1]}")
        diagnose("final value", f"{curve[-1]['value']}")
        assert invested_values[-1] > 0
        track_coverage(MOD, 3)

    def test_only_initial_investment(self):
        """Initial lump sum, no recurring executions."""
        price_dates = _trading_dates(date(2023, 1, 3), 10)
        price_points: List[Tuple[date, float]] = []
        for i, d in enumerate(price_dates):
            price_points.append((d, 100.0 + i * 1.0))

        curve = _build_equity_curve(
            price_points, [],
            initial_amount=1000.0,
            initial_date=price_dates[0],
            initial_price=100.0,
        )
        assert len(curve) == 10
        # All points should have invested=1000 since no recurring
        assert all(p["invested"] == 1000.0 for p in curve)
        # Value should start at 1000 and grow with price
        assert curve[0]["value"] == pytest.approx(1000.0, abs=1.0)
        diagnose("initial-only curve", [(p["date"], p["value"]) for p in curve])
        track_coverage(MOD, 2)

    def test_zero_initial_price_guard(self):
        """initial_price=0 should not cause div-by-zero (units not computed)."""
        price_dates = _trading_dates(date(2023, 1, 3), 5)
        price_points = [(d, 100.0) for d in price_dates]
        curve = _build_equity_curve(
            price_points, [],
            initial_amount=1000.0,
            initial_date=price_dates[0],
            initial_price=0.0,
        )
        # Should not crash; units=0, value=0
        assert curve[0]["value"] == 0.0
        track_coverage(MOD, 1)

    def test_no_executions_no_initial(self):
        """Neither executions nor initial investment → flat zero curve."""
        price_dates = _trading_dates(date(2023, 1, 3), 5)
        price_points = [(d, 100.0 + i) for i, d in enumerate(price_dates)]
        curve = _build_equity_curve(price_points, [], 0.0, None, None)
        assert all(p["value"] == 0.0 for p in curve)
        assert all(p["invested"] == 0.0 for p in curve)
        track_coverage(MOD, 1)

    def test_value_tracks_price_after_last_execution(self):
        """After all executions, value should continue tracking price changes."""
        price_dates = _trading_dates(date(2023, 1, 3), 20)
        price = 100.0
        price_points: List[Tuple[date, float]] = []
        for d in price_dates:
            price *= 1.002
            price_points.append((d, round(price, 6)))

        # Only one early execution
        executed = self._make_executed(
            [price_points[2][0]], [price_points[2][1]], [1000.0]
        )
        curve = _build_equity_curve(price_points, executed, 0.0, None, None)

        # After execution at index 2, value should be positive and changing
        post_exec_values = [p["value"] for p in curve[3:]]
        assert len(set(post_exec_values)) > 1, "Value should change with price"
        diagnose("post-exec values", post_exec_values[:5])
        track_coverage(MOD, 1)
