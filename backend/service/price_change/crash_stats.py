"""Crash detection and recovery analysis using period close returns."""

from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple


CRASH_PERIOD_TYPES = {"day", "n_days", "week", "month"}


def _build_period_windows(
    points: List[Tuple[date, float]],
    period_type: str,
    period_days: int,
    start_date: date,
    end_date: date,
) -> List[Tuple[int, int]]:
    """Return non-overlapping (candle-start, candle-end) point indices."""
    if period_type not in CRASH_PERIOD_TYPES:
        raise ValueError("period_type must be one of day, n_days, week, month")

    if period_type == "day":
        return [
            (index, index)
            for index, (point_date, _) in enumerate(points)
            if start_date <= point_date <= end_date
        ]

    if period_type == "n_days":
        if period_days < 2 or period_days > 250:
            raise ValueError("period_days must be between 2 and 250")
        selected = [
            index
            for index, (point_date, _) in enumerate(points)
            if start_date <= point_date <= end_date
        ]
        windows = []
        for offset in range(0, len(selected), period_days):
            candle = selected[offset:offset + period_days]
            if len(candle) < period_days:
                break
            windows.append((candle[0], candle[-1]))
        return windows

    periods: List[Tuple[int, int]] = []
    previous_key = None
    for index, (point_date, _) in enumerate(points):
        if point_date > end_date:
            break
        if period_type == "week":
            iso_year, iso_week, _ = point_date.isocalendar()
            key = (iso_year, iso_week)
        else:
            key = (point_date.year, point_date.month)
        if key != previous_key:
            periods.append((index, index))
            previous_key = key
        else:
            periods[-1] = (periods[-1][0], index)

    return [
        (start_index, end_index)
        for start_index, end_index in periods
        if points[end_index][0] >= start_date
    ]


def compute_crash_statistics(
    timestamps: List[int],
    closes: List[Optional[float]],
    start_date: date,
    end_date: date,
    threshold_pct: float,
    period_type: str = "day",
    period_days: int = 1,
) -> List[Dict]:
    """Find crash events and their recovery metrics.

    Daily, N-trading-day, weekly, and monthly periods are evaluated from the
    previous period close to the current period close. This includes overnight
    and weekend gaps. N-day periods are non-overlapping and anchored to the first
    trading day in the requested range. Recovery is measured against the close
    immediately before the triggering period.

    Args:
        timestamps: Unix epoch seconds for each trading day.
        closes: Close prices aligned with timestamps.
        start_date: Only consider crashes on or after this date.
        end_date: Only consider crashes on or before this date.
        threshold_pct: Positive number (e.g. 4.77 means drop >= -4.77%).
        period_type: One of day, n_days, week, month.
        period_days: Non-overlapping candle size when period_type is n_days.

    Returns:
        List of crash event dicts, each with:
        - crash_date: ISO date string of the crash day
        - pre_crash_date: ISO date string of the previous trading day
        - pre_crash_close: close price before the drop
        - crash_close: close price on the crash day
        - drop_pct: percentage drop (negative number)
        - bottom_date: ISO date string of the lowest close during drawdown
        - bottom_close: the lowest close price during drawdown
        - bottom_pct: percentage drop from pre-crash close to bottom close
        - days_to_bottom: trading days from crash to bottom (0 = crash itself is bottom)
        - recovery_date: ISO date string of recovery day, or None if not recovered
        - recovery_close: close price on the recovery day, or None
        - recovery_days: number of trading days from crash to recovery, or None
        - recovered: bool indicating whether price recovered by end_date
    """
    # Build aligned (date, adjusted close) points for the full series.
    points: List[Tuple[date, float]] = []
    for ts, close_value in zip(timestamps, closes):
        if close_value is None:
            continue
        try:
            close = float(close_value)
        except (TypeError, ValueError):
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        points.append((dt, close))

    if not points:
        return []

    results: List[Dict] = []
    windows = _build_period_windows(
        points,
        period_type,
        period_days,
        start_date,
        end_date,
    )

    for start_idx, end_idx in windows:
        # The immediately preceding trading-day close is also the previous
        # period close for daily, N-day, weekly, and monthly periods.
        if start_idx == 0:
            continue
        pre_period_date, pre_period_close = points[start_idx - 1]
        period_start_date, _ = points[start_idx]
        period_end_date, period_close = points[end_idx]

        period_return_pct = (period_close / pre_period_close - 1) * 100
        if period_return_pct > -threshold_pct:
            continue  # not a crash

        # A period-level crash is confirmed at the period close, so bottom and
        # recovery measurements start there rather than inside the period.
        bottom_idx = end_idx
        bottom_date: date = period_end_date
        bottom_close: float = period_close
        recovery_date: Optional[date] = None
        recovery_close: Optional[float] = None
        recovery_days: Optional[int] = None
        recovered = False

        for j in range(end_idx + 1, len(points)):
            check_date, check_close = points[j]
            if check_date > end_date:
                break

            # Track the lowest point
            if check_close < bottom_close:
                bottom_close = float(check_close)
                bottom_date = check_date
                bottom_idx = j

            # Check for recovery
            if check_close >= pre_period_close:
                recovery_date = check_date
                recovery_close = float(check_close)
                recovered = True
                break

        # Count trading days from the triggering period close to the bottom.
        days_to_bottom = bottom_idx - end_idx

        # Count trading days: crash → recovery
        if recovered and recovery_date is not None:
            recovery_days = next(
                index - end_idx
                for index in range(end_idx + 1, len(points))
                if points[index][0] >= recovery_date
            )

        bottom_pct = round((bottom_close / pre_period_close - 1) * 100, 2)

        results.append({
            "crash_date": period_end_date.isoformat(),
            "pre_crash_date": pre_period_date.isoformat(),
            "period_start_date": period_start_date.isoformat(),
            "period_end_date": period_end_date.isoformat(),
            "period_type": period_type,
            "period_days": period_days if period_type == "n_days" else None,
            "pre_crash_close": round(pre_period_close, 6),
            "crash_close": round(period_close, 6),
            "drop_pct": round(period_return_pct, 2),
            "bottom_date": bottom_date.isoformat(),
            "bottom_close": round(bottom_close, 6),
            "bottom_pct": bottom_pct,
            "days_to_bottom": days_to_bottom,
            "recovery_date": recovery_date.isoformat() if recovery_date else None,
            "recovery_close": round(recovery_close, 6) if recovery_close is not None else None,
            "recovery_days": recovery_days,
            "recovered": recovered,
        })

    return results
