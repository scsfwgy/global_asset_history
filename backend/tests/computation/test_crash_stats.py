"""Tests for backend/service/price_change/crash_stats.py"""

from datetime import date, datetime, timezone
from typing import List, Optional

import pytest

from service.price_change.crash_stats import compute_crash_statistics
from tests.conftest import (
    _to_timestamp,
    _trading_dates,
    diagnose,
    make_crash_data,
    track_coverage,
)

MOD = "crash_stats.py"


class TestComputeCrashStatistics:
    """Crash detection and recovery analysis."""

    def test_single_crash_recovered(self):
        """A -5% drop that recovers within the data window."""
        # Build simple data: 100 → 95 (crash) → 100 (recovered)
        dates = _trading_dates(date(2024, 1, 1), 10)
        ts = [_to_timestamp(d) for d in dates]
        closes = [100.0, 100.5, 95.0, 96.0, 98.0, 100.0, 101.0, 102.0, 103.0, 104.0]

        result = compute_crash_statistics(
            ts, closes,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            threshold_pct=4.0,
        )
        assert len(result) == 1
        crash = result[0]
        assert crash["drop_pct"] == pytest.approx(-5.47, abs=0.1)  # (95/100.5 - 1)*100
        assert crash["recovered"] is True
        assert crash["recovery_date"] is not None
        assert crash["recovery_days"] is not None
        diagnose("single crash recovered", {
            "drop": crash["drop_pct"],
            "bottom": crash["bottom_pct"],
            "days_to_recovery": crash["recovery_days"],
        })
        track_coverage(MOD, 5)

    def test_single_crash_not_recovered(self):
        """A -10% crash that never recovers within the data."""
        ts = [_to_timestamp(d) for d in _trading_dates(date(2024, 1, 1), 5)]
        closes = [100.0, 90.0, 91.0, 92.0, 93.0]  # never back to 100

        result = compute_crash_statistics(
            ts, closes,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            threshold_pct=5.0,
        )
        assert len(result) == 1
        crash = result[0]
        assert crash["drop_pct"] == pytest.approx(-10.0, abs=0.1)
        assert crash["recovered"] is False
        assert crash["recovery_date"] is None
        assert crash["recovery_days"] is None
        diagnose("unrecovered crash", crash["drop_pct"])
        track_coverage(MOD, 3)

    def test_multiple_crashes(self, crash_ts, crash_closes):
        """Data with multiple known crash events."""
        result = compute_crash_statistics(
            crash_ts, crash_closes,
            start_date=date(2022, 1, 1),
            end_date=date(2025, 12, 31),
            threshold_pct=3.0,
        )
        diagnose("crashes found", len(result))
        for i, c in enumerate(result):
            diagnose(f"crash[{i}]", {
                "date": c["crash_date"],
                "drop": c["drop_pct"],
                "recovered": c["recovered"],
            })
        # Should detect at least 2 crashes (-6% and -10%, maybe also -3.5%)
        assert len(result) >= 2
        track_coverage(MOD, 1)

    def test_threshold_boundary_below(self):
        """Drop just below threshold should NOT be a crash."""
        ts = [_to_timestamp(d) for d in _trading_dates(date(2024, 1, 1), 3)]
        closes = [100.0, 95.1, 96.0]  # -4.9% with threshold 5%
        result = compute_crash_statistics(
            ts, closes,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            threshold_pct=5.0,
        )
        assert len(result) == 0
        track_coverage(MOD, 1)

    def test_threshold_boundary_exact(self):
        """Drop exactly at threshold should be a crash."""
        ts = [_to_timestamp(d) for d in _trading_dates(date(2024, 1, 1), 3)]
        closes = [100.0, 95.0, 100.0]  # exactly -5% with threshold 5%
        result = compute_crash_statistics(
            ts, closes,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            threshold_pct=5.0,
        )
        # -5.0 > -5.0 is False, so daily_return_pct (-5.0) > -threshold (-5.0) is False
        # → crash detected
        assert len(result) == 1
        track_coverage(MOD, 1)

    def test_date_range_filter(self):
        """Crashes outside [start_date, end_date] should be excluded."""
        ts = [
            _to_timestamp(date(2024, 1, 3)),
            _to_timestamp(date(2024, 1, 4)),  # crash here
            _to_timestamp(date(2024, 3, 3)),
            _to_timestamp(date(2024, 3, 4)),  # crash here
        ]
        closes = [100.0, 90.0, 100.0, 90.0]
        # Only include March
        result = compute_crash_statistics(
            ts, closes,
            start_date=date(2024, 2, 1),
            end_date=date(2024, 4, 30),
            threshold_pct=5.0,
        )
        assert len(result) == 1
        assert result[0]["crash_date"] == "2024-03-04"
        track_coverage(MOD, 1)

    def test_less_than_two_points(self):
        """Fewer than 2 data points → empty list."""
        result = compute_crash_statistics(
            [_to_timestamp(date(2024, 1, 1))],
            [100.0],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            threshold_pct=5.0,
        )
        assert result == []
        track_coverage(MOD, 1)

    def test_no_crashes(self):
        """All daily returns within threshold → empty list."""
        ts = [_to_timestamp(d) for d in _trading_dates(date(2024, 1, 1), 30)]
        closes = [100.0 + i * 0.01 for i in range(30)]  # tiny up moves
        result = compute_crash_statistics(
            ts, closes,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            threshold_pct=5.0,
        )
        assert result == []
        track_coverage(MOD, 1)

    def test_bottom_after_crash(self):
        """Crash that continues lower before recovering."""
        ts = [_to_timestamp(d) for d in _trading_dates(date(2024, 1, 1), 10)]
        # 100 → 92 (crash -8%) → 88 (bottom) → 95 → 100 (recovered)
        closes = [100.0, 92.0, 88.0, 90.0, 95.0, 100.0, 101.0, 102.0, 103.0, 104.0]
        result = compute_crash_statistics(
            ts, closes,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            threshold_pct=5.0,
        )
        assert len(result) == 1
        crash = result[0]
        assert crash["bottom_close"] == 88.0
        assert crash["bottom_pct"] == pytest.approx(-12.0, abs=0.1)  # (88/100-1)*100
        assert crash["days_to_bottom"] > 0  # crash was not the bottom
        assert crash["recovered"] is True
        diagnose("crash with deeper bottom", {
            "drop": crash["drop_pct"],
            "bottom": crash["bottom_pct"],
            "days_to_bottom": crash["days_to_bottom"],
            "recovery_days": crash["recovery_days"],
        })
        track_coverage(MOD, 4)

    def test_crash_is_itself_bottom(self):
        """Crash day is the lowest point (immediate bounce)."""
        ts = [_to_timestamp(d) for d in _trading_dates(date(2024, 1, 1), 5)]
        closes = [100.0, 90.0, 95.0, 100.0, 105.0]  # crash, then only goes up
        result = compute_crash_statistics(
            ts, closes,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            threshold_pct=5.0,
        )
        assert len(result) == 1
        assert result[0]["days_to_bottom"] == 0
        assert result[0]["bottom_close"] == 90.0
        track_coverage(MOD, 2)

    def test_nulls_are_skipped(self):
        """None closes should not interfere with crash detection."""
        ts = [_to_timestamp(d) for d in _trading_dates(date(2024, 1, 1), 5)]
        closes: List[Optional[float]] = [100.0, None, 90.0, None, 100.0]
        result = compute_crash_statistics(
            ts, closes,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            threshold_pct=5.0,
        )
        # prev_close for index 2 is index 0's 100.0 (None skipped)
        assert len(result) == 1
        assert result[0]["drop_pct"] == pytest.approx(-10.0, abs=0.1)
        track_coverage(MOD, 1)
