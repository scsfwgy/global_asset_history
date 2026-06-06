"""Crash detection and recovery analysis.

Finds single-day drops exceeding a threshold and calculates how many
trading days it took to recover to the pre-crash closing price.
"""

from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple


def compute_crash_statistics(
    timestamps: List[int],
    closes: List[Optional[float]],
    start_date: date,
    end_date: date,
    threshold_pct: float,
) -> List[Dict]:
    """Find crash events and their recovery metrics.

    A "crash" is defined as a single-day drop >= threshold_pct (in absolute terms).
    Recovery is measured by the number of trading days until the close price
    reaches or exceeds the pre-crash close price.

    Args:
        timestamps: Unix epoch seconds for each trading day.
        closes: Close prices aligned with timestamps.
        start_date: Only consider crashes on or after this date.
        end_date: Only consider crashes on or before this date.
        threshold_pct: Positive number (e.g. 4.77 means drop >= -4.77%).

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
    # Build a list of (date, close) for the full series
    points: List[Tuple[date, float]] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        points.append((dt, float(close)))

    if len(points) < 2:
        return []

    # Pre-compute daily returns: return[i] = points[i].close / points[i-1].close - 1
    results: List[Dict] = []

    for i in range(1, len(points)):
        prev_date, prev_close = points[i - 1]
        cur_date, cur_close = points[i]

        if cur_date < start_date or cur_date > end_date:
            continue

        daily_return_pct = (cur_close / prev_close - 1) * 100
        if daily_return_pct > -threshold_pct:
            continue  # not a crash

        # This is a crash.  Scan forward to find:
        #   1) the lowest close (bottom) during the drawdown
        #   2) the first close that recovers to >= pre-crash close
        bottom_date: date = cur_date
        bottom_close: float = float(cur_close)
        bottom_idx: int = i
        recovery_date: Optional[date] = None
        recovery_close: Optional[float] = None
        recovery_days: Optional[int] = None
        recovered = False

        for j in range(i + 1, len(points)):
            check_date, check_close = points[j]

            # Track the lowest point
            if check_close < bottom_close:
                bottom_close = float(check_close)
                bottom_date = check_date
                bottom_idx = j

            # Check for recovery
            if check_close >= prev_close:
                recovery_date = check_date
                recovery_close = float(check_close)
                recovered = True
                break
            if check_date > end_date:
                break

        # Count trading days: crash → bottom
        days_to_bottom = bottom_idx - i

        # Count trading days: crash → recovery
        if recovered and recovery_date is not None:
            trading_days = 0
            for j in range(i + 1, len(points)):
                trading_days += 1
                if points[j][0] >= recovery_date:
                    break
            recovery_days = trading_days

        bottom_pct = round((bottom_close / prev_close - 1) * 100, 2)

        results.append({
            "crash_date": cur_date.isoformat(),
            "pre_crash_date": prev_date.isoformat(),
            "pre_crash_close": round(prev_close, 6),
            "crash_close": round(cur_close, 6),
            "drop_pct": round(daily_return_pct, 2),
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
