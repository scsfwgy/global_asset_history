"""Return calculations and backtest helpers."""

from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

def _compute_yearly_returns(
    timestamps: List[int],
    closes: List[Optional[float]],
) -> Dict[str, float]:
    """Compute yearly returns using YoY change on year-end close prices.

    For each year, return (last_close_of_year / last_close_of_prev_year - 1) * 100.
    This is the standard financial convention used by published total return data.
    """
    # Build year → last_close mapping
    year_closes: Dict[int, float] = {}
    for ts, c in zip(timestamps, closes):
        if c is not None:
            year = datetime.fromtimestamp(ts, tz=timezone.utc).year
            year_closes[year] = c  # last in chrono order wins = year-end close

    if len(year_closes) < 2:
        return {}

    result = {}
    sorted_years = sorted(year_closes.keys())
    for i in range(1, len(sorted_years)):
        prev, cur = sorted_years[i - 1], sorted_years[i]
        prev_close = year_closes[prev]
        cur_close = year_closes[cur]
        if prev_close == 0:
            continue
        result[str(cur)] = round((cur_close / prev_close - 1) * 100, 2)

    return result



def _compute_monthly_returns(
    timestamps: List[int],
    closes: List[Optional[float]],
    year: int,
) -> List[dict]:
    """Compute monthly returns for a specific year.

    Month returns use end-of-month closes:
    current month-end close / previous month-end close - 1.

    Returns [{"month": 1, "return": 5.2}, ...] (month is 1-12, return is % or None).
    """
    month_end_closes: Dict[Tuple[int, int], float] = {}
    for ts, c in zip(timestamps, closes):
        if c is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        month_end_closes[(dt.year, dt.month)] = c

    result = []
    for m in range(1, 13):
        cur_close = month_end_closes.get((year, m))
        prev_key = (year - 1, 12) if m == 1 else (year, m - 1)
        prev_close = month_end_closes.get(prev_key)
        if cur_close is not None and prev_close not in (None, 0):
            ret = round((cur_close / prev_close - 1) * 100, 2)
            result.append({"month": m, "return": ret})
        else:
            result.append({"month": m, "return": None})
    return result


def _compute_daily_returns_for_month(
    timestamps: List[int],
    closes: List[Optional[float]],
    year: int,
    month: int,
) -> List[dict]:
    """Compute daily returns for a specific month from daily closes.

    Daily return uses the previous available close:
    current close / previous close - 1.
    """
    result: List[dict] = []
    prev_close: Optional[float] = None

    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        daily_return = None
        if prev_close not in (None, 0):
            daily_return = round((close / prev_close - 1) * 100, 2)

        if dt.year == year and dt.month == month:
            result.append({
                "day": dt.day,
                "date": dt.date().isoformat(),
                "return": daily_return,
                "close": round(close, 6),
            })

        prev_close = close

    return result


def _series_points_in_range(
    timestamps: List[int],
    closes: List[Optional[float]],
    start_date: date,
    end_date: date,
) -> List[Tuple[date, float]]:
    points: List[Tuple[date, float]] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        current_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        if start_date <= current_date <= end_date:
            points.append((current_date, float(close)))
    return points


def _compute_money_weighted_annualized_return(
    cashflows: List[Tuple[date, float]],
    final_date: date,
    final_value: float,
) -> Optional[float]:
    """Compute XIRR-style annualized return for dated investment cash flows.

    Cash flows use the investor perspective: contributions are negative, and
    withdrawals or the final market value are positive cash flows. This is the
    right annualized metric for DCA and VCA because each contribution or sale
    is weighted by the exact time capital is invested.
    """
    if final_value < 0:
        return None
    if final_value == 0 and not any(amount > 0 for _, amount in cashflows):
        return None

    dated_flows = [(flow_date, amount) for flow_date, amount in cashflows if amount]
    if not dated_flows:
        return None
    if final_value > 0:
        dated_flows.append((final_date, final_value))

    first_date = min(flow_date for flow_date, _ in dated_flows)
    if max((flow_date - first_date).days for flow_date, _ in dated_flows) <= 0:
        return None

    has_positive = any(amount > 0 for _, amount in dated_flows)
    has_negative = any(amount < 0 for _, amount in dated_flows)
    if not has_positive or not has_negative:
        return None

    def xnpv(rate: float) -> float:
        base = 1 + rate
        return sum(
            amount / (base ** ((flow_date - first_date).days / 365.0))
            for flow_date, amount in dated_flows
        )

    low = -0.999999
    high = 1.0
    low_val = xnpv(low)
    high_val = xnpv(high)

    # Expand the upper bound until it brackets the root. Conventional DCA cash
    # flows are monotonic, so bisection is stable once signs differ.
    bracketed = False
    for _ in range(64):
        if low_val == 0:
            return low
        if high_val == 0:
            return high
        if low_val * high_val < 0:
            bracketed = True
            break
        high *= 2
        try:
            high_val = xnpv(high)
        except OverflowError:
            break

    if not bracketed:
        # Fallback grid scan for alternating buy/sell cashflows (e.g. VCA).
        scan_points = [
            -0.99, -0.95, -0.9, -0.8, -0.6, -0.4, -0.2, -0.1,
            0.0, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 50.0,
        ]
        prev_r = scan_points[0]
        prev_v = xnpv(prev_r)
        for cur_r in scan_points[1:]:
            cur_v = xnpv(cur_r)
            if prev_v == 0:
                return prev_r
            if cur_v == 0:
                return cur_r
            if prev_v * cur_v < 0:
                low, high = prev_r, cur_r
                low_val, high_val = prev_v, cur_v
                bracketed = True
                break
            prev_r, prev_v = cur_r, cur_v
        if not bracketed:
            return None

    for _ in range(100):
        mid = (low + high) / 2
        mid_val = xnpv(mid)
        if abs(mid_val) < 1e-7:
            return mid
        if low_val * mid_val <= 0:
            high = mid
            high_val = mid_val
        else:
            low = mid
            low_val = mid_val

    return (low + high) / 2



def _normalize_frequency(frequency: str) -> str:
    clean = (frequency or "monthly").strip().lower()
    if clean not in {"once", "daily", "weekly", "monthly", "yearly"}:
        raise ValueError("frequency must be one of once, daily, weekly, monthly, yearly")
    return clean


def _normalize_strategy(strategy: Optional[str]) -> str:
    clean = (strategy or "dca").strip().lower()
    if clean not in {"dca", "vca"}:
        raise ValueError("strategy must be one of dca, vca")
    return clean


def _normalize_rebalance(rebalance: Optional[str]) -> str:
    clean = (rebalance or "none").strip().lower()
    if clean not in {"none", "monthly", "quarterly", "yearly"}:
        raise ValueError("rebalance must be one of none, monthly, quarterly, yearly")
    return clean


def _compute_vca_step(
    prev_target: float,
    increment: float,
    growth_rate_pct: float,
    apply_growth: bool,
    current_value: float,
    allow_sell: bool = True,
    max_contribution: Optional[float] = None,
) -> Tuple[float, float, str]:
    """Compute one Value Averaging (VCA) step.

    Returns:
        (new_target_value, trade_amount, kind)
        where trade_amount > 0 is a buy ('vca_buy'), trade_amount < 0 is a sell
        ('vca_sell'), and trade_amount == 0 is a hold ('vca_hold').
    """
    growth_factor = 1.0 + (float(growth_rate_pct or 0.0) / 100.0)
    if apply_growth and prev_target > 0:
        new_target = prev_target * growth_factor + increment
    else:
        new_target = prev_target + increment
    new_target = max(0.0, new_target)

    gap = new_target - current_value
    if gap > 1e-8:
        amount = gap
        if max_contribution is not None and max_contribution > 0:
            amount = min(amount, float(max_contribution))
        return new_target, amount, "vca_buy"

    if gap < -1e-8 and allow_sell and current_value > 1e-8:
        sell_amount = min(-gap, current_value)
        if sell_amount > 1e-8:
            return new_target, -sell_amount, "vca_sell"

    return new_target, 0.0, "vca_hold"


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_iso_date(value: str, field_name: str) -> date:
    if not value:
        raise ValueError(f"{field_name} is required")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as e:
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format") from e


def _next_month_anchor(current: date, months: int, target_day: int) -> date:
    total_months = (current.year * 12 + (current.month - 1)) + months
    year = total_months // 12
    month = total_months % 12 + 1
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(year, month, min(target_day, last_day))


def _generate_schedule_dates(
    start_date: date,
    end_date: date,
    frequency: str,
    interval: int,
    anchor_day: Optional[int] = None,
    weekday: Optional[int] = None,
) -> List[date]:
    schedule: List[date] = []
    current = start_date

    if frequency == "once":
        return [start_date]

    if frequency == "daily":
        step = timedelta(days=interval)
        while current <= end_date:
            schedule.append(current)
            current += step
        return schedule

    if frequency == "weekly":
        target_weekday = 0 if weekday is None else max(0, min(6, weekday))
        delta = (target_weekday - start_date.weekday()) % 7
        current = start_date + timedelta(days=delta)
        step = timedelta(days=7 * interval)
        while current <= end_date:
            schedule.append(current)
            current += step
        return schedule

    if frequency == "yearly":
        current = start_date
        while current <= end_date:
            schedule.append(current)
            target_year = current.year + interval
            try:
                current = date(target_year, current.month, current.day)
            except ValueError:
                # Leap day → clamp to last day of month in non-leap year
                import calendar as _cal
                last_day = _cal.monthrange(target_year, current.month)[1]
                current = date(target_year, current.month, last_day)
        return schedule

    target_day = anchor_day or start_date.day
    current = date(start_date.year, start_date.month, min(target_day, start_date.day))
    if current < start_date:
        current = _next_month_anchor(current, 1, target_day)

    while current <= end_date:
        if current >= start_date:
            schedule.append(current)
        current = _next_month_anchor(current, interval, target_day)

    return schedule


def _resolve_execution_points(
    price_points: List[Tuple[date, float]],
    schedule_dates: List[date],
) -> List[Tuple[date, float]]:
    executed: List[Tuple[date, float]] = []
    pointer = 0
    last_used_date: Optional[date] = None

    for planned_date in schedule_dates:
        while pointer < len(price_points) and price_points[pointer][0] < planned_date:
            pointer += 1
        if pointer >= len(price_points):
            break
        exec_date, price = price_points[pointer]
        if last_used_date == exec_date:
            continue
        executed.append((exec_date, price))
        last_used_date = exec_date

    return executed


def _build_equity_curve(
    price_points: List[Tuple[date, float]],
    executed_points: List[Tuple[date, float, float, float, float]],
    initial_amount: float,
    initial_date: Optional[date],
    initial_price: Optional[float],
) -> List[dict]:
    curve: List[dict] = []
    invested = initial_amount
    units = 0.0
    exec_idx = 0

    if initial_amount > 0 and initial_date is not None and initial_price not in (None, 0):
        units = initial_amount / float(initial_price)

    for point_date, price in price_points:
        while exec_idx < len(executed_points) and executed_points[exec_idx][0] == point_date:
            _, _, amount, bought_units, cum_units = executed_points[exec_idx]
            invested += amount
            units = cum_units
            exec_idx += 1

        value = units * price
        curve.append({
            "date": point_date.isoformat(),
            "price": round(price, 6),
            "invested": round(invested, 2),
            "value": round(value, 2),
        })

    return curve


def _format_leg_summary(legs: List[dict]) -> str:
    """Format a compact human-readable leg allocation summary for portfolio cashflows."""
    parts = []
    for leg in legs:
        amt = float(leg.get("amount", 0.0) or 0.0)
        sym = leg.get("symbol", "")
        if abs(amt) >= 0.01:
            sign = "+" if amt > 0 else ""
            parts.append(f"{sym} {sign}{amt:.2f}")
        else:
            parts.append(f"{sym} 0.00")
    return " · ".join(parts)


def _simulate_single_backtest(
    price_points: List[Tuple[date, float]],
    execution_dates: List[Tuple[date, float]],
    start_date: date,
    initial_amount: float,
    amount: float,
    strategy: str = "dca",
    vca_growth_rate: float = 0.0,
    vca_allow_sell: bool = True,
    vca_max_contribution: Optional[float] = None,
) -> Dict:
    """Simulate a single-asset DCA or VCA backtest over resolved price points."""
    clean_strategy = _normalize_strategy(strategy)
    cashflows: List[dict] = []
    irr_cashflows: List[Tuple[date, float]] = []
    executed_points: List[Tuple[date, float, float, float, float]] = []
    cumulative_units = 0.0

    net_invested = 0.0
    gross_invested = 0.0
    total_withdrawn = 0.0
    peak_invested = 0.0
    buy_count = 0
    sell_count = 0
    hold_count = 0

    target_value = 0.0
    last_target_date: Optional[date] = None
    target_by_date: Dict[date, float] = {}

    first_trade_date, first_trade_price = price_points[0]
    if initial_amount > 0:
        initial_units = initial_amount / first_trade_price
        cumulative_units += initial_units
        net_invested += initial_amount
        gross_invested += initial_amount
        peak_invested = max(peak_invested, net_invested)
        buy_count += 1
        irr_cashflows.append((first_trade_date, -initial_amount))
        row = {
            "date": first_trade_date.isoformat(),
            "planned_date": start_date.isoformat(),
            "amount": round(initial_amount, 2),
            "price": round(first_trade_price, 6),
            "units": round(initial_units, 8),
            "cum_units": round(cumulative_units, 8),
            "kind": "initial",
            "net_invested": round(net_invested, 2),
            "portfolio_value": round(cumulative_units * first_trade_price, 2),
        }
        if clean_strategy == "vca":
            target_value = initial_amount
            last_target_date = first_trade_date
            target_by_date[first_trade_date] = target_value
            row["target_value"] = round(target_value, 2)
        cashflows.append(row)

    for exec_date, price in execution_dates:
        if amount <= 0:
            break
        if clean_strategy == "dca":
            trade_amount = amount
            kind = "recurring"
        else:
            current_val = cumulative_units * price
            apply_growth = last_target_date is not None and exec_date > last_target_date
            target_value, trade_amount, kind = _compute_vca_step(
                prev_target=target_value,
                increment=amount,
                growth_rate_pct=vca_growth_rate,
                apply_growth=apply_growth,
                current_value=current_val,
                allow_sell=vca_allow_sell,
                max_contribution=vca_max_contribution,
            )
            last_target_date = exec_date
            target_by_date[exec_date] = target_value

        units = (trade_amount / price) if price > 0 else 0.0
        cumulative_units = max(0.0, cumulative_units + units)
        net_invested += trade_amount
        if trade_amount > 1e-8:
            gross_invested += trade_amount
            buy_count += 1
            irr_cashflows.append((exec_date, -trade_amount))
        elif trade_amount < -1e-8:
            total_withdrawn += -trade_amount
            sell_count += 1
            irr_cashflows.append((exec_date, -trade_amount))
        else:
            hold_count += 1
        peak_invested = max(peak_invested, net_invested)

        executed_points.append((exec_date, price, trade_amount, units, cumulative_units))
        row = {
            "date": exec_date.isoformat(),
            "planned_date": exec_date.isoformat(),
            "amount": round(trade_amount, 2),
            "price": round(price, 6),
            "units": round(units, 8),
            "cum_units": round(cumulative_units, 8),
            "kind": kind,
            "net_invested": round(net_invested, 2),
            "portfolio_value": round(cumulative_units * price, 2),
        }
        if clean_strategy == "vca":
            row["target_value"] = round(target_value, 2)
        cashflows.append(row)

    equity_curve = _build_equity_curve(
        price_points=price_points,
        executed_points=executed_points,
        initial_amount=initial_amount,
        initial_date=first_trade_date if initial_amount > 0 else None,
        initial_price=first_trade_price if initial_amount > 0 else None,
    )

    if clean_strategy == "vca":
        active_target = 0.0
        for point, (pt_date, _) in zip(equity_curve, price_points):
            if pt_date in target_by_date:
                active_target = target_by_date[pt_date]
            point["target"] = round(active_target, 2)

    last_date, last_price = price_points[-1]
    final_value = cumulative_units * last_price
    profit = final_value - net_invested
    roi_base = peak_invested if total_withdrawn > 0 else net_invested
    return_pct = 0.0 if roi_base <= 0 else (profit / roi_base) * 100
    money_weighted_return = _compute_money_weighted_annualized_return(
        cashflows=irr_cashflows,
        final_date=last_date,
        final_value=final_value,
    )
    annualized_return_pct = (money_weighted_return or 0.0) * 100

    return {
        "summary": {
            "invested": round(net_invested, 2),
            "gross_invested": round(gross_invested, 2),
            "total_withdrawn": round(total_withdrawn, 2),
            "peak_invested": round(peak_invested, 2),
            "final_value": round(final_value, 2),
            "profit": round(profit, 2),
            "return_pct": round(return_pct, 2),
            "annualized_return_pct": round(annualized_return_pct, 2),
            "trade_count": buy_count + sell_count if clean_strategy == "vca" else len(cashflows),
            "buy_count": buy_count,
            "sell_count": sell_count,
            "hold_count": hold_count,
            "rebalance_count": 0,
            "last_price": round(last_price, 6),
        },
        "cashflows": cashflows,
        "equity_curve": equity_curve,
    }


def _simulate_portfolio_backtest(
    asset_inputs: List[Dict],
    start_date: date,
    end_date: date,
    frequency: str,
    interval: int,
    day_of_month: int,
    weekday: Optional[int],
    initial_amount: float,
    amount: float,
    strategy: str = "dca",
    rebalance: str = "none",
    vca_growth_rate: float = 0.0,
    vca_allow_sell: bool = True,
    vca_max_contribution: Optional[float] = None,
) -> Dict:
    """Simulate a multi-asset portfolio backtest with DCA/VCA and scheduled rebalancing."""
    clean_strategy = _normalize_strategy(strategy)
    clean_rebalance = _normalize_rebalance(rebalance)

    if not asset_inputs:
        raise ValueError("portfolio requires at least 2 assets")

    for item in asset_inputs:
        if not item.get("base_points"):
            raise ValueError(f"no price data in selected date range for {item.get('symbol')}")

    effective_start_date = max(
        start_date,
        max(item["base_points"][0][0] for item in asset_inputs),
    )
    if effective_start_date > end_date:
        raise ValueError("no overlapping price data across portfolio assets in selected date range")

    union_dates = sorted({
        pt_date
        for item in asset_inputs
        for pt_date, _ in item["base_points"]
        if effective_start_date <= pt_date <= end_date
    })
    if not union_dates:
        raise ValueError("no overlapping price data across portfolio assets in selected date range")

    n_assets = len(asset_inputs)
    n_days = len(union_dates)
    base_prices: List[List[float]] = [[0.0] * n_days for _ in range(n_assets)]
    native_prices: List[List[float]] = [[0.0] * n_days for _ in range(n_assets)]

    for asset_idx, item in enumerate(asset_inputs):
        b_pts = item["base_points"]
        n_pts = item.get("native_points") or b_pts
        b_ptr = 0
        n_ptr = 0
        last_b = b_pts[0][1]
        last_n = n_pts[0][1]
        for day_idx, current_date in enumerate(union_dates):
            while b_ptr < len(b_pts) and b_pts[b_ptr][0] <= current_date:
                last_b = b_pts[b_ptr][1]
                b_ptr += 1
            while n_ptr < len(n_pts) and n_pts[n_ptr][0] <= current_date:
                last_n = n_pts[n_ptr][1]
                n_ptr += 1
            base_prices[asset_idx][day_idx] = float(last_b)
            native_prices[asset_idx][day_idx] = float(last_n)

    union_price_points = [(d, 100.0) for d in union_dates]
    schedule_dates = _generate_schedule_dates(
        start_date=effective_start_date,
        end_date=end_date,
        frequency=frequency,
        interval=interval,
        anchor_day=day_of_month,
        weekday=weekday,
    )
    exec_dates_set = {
        d for d, _ in _resolve_execution_points(union_price_points, schedule_dates)
    }

    rebalance_dates_set = set()
    if clean_rebalance != "none":
        reb_freq = "yearly" if clean_rebalance == "yearly" else "monthly"
        reb_interval = 3 if clean_rebalance == "quarterly" else 1
        reb_schedule = _generate_schedule_dates(
            start_date=effective_start_date,
            end_date=end_date,
            frequency=reb_freq,
            interval=reb_interval,
            anchor_day=day_of_month,
        )
        first_union_date = union_dates[0]
        rebalance_dates_set = {
            d
            for d, _ in _resolve_execution_points(union_price_points, reb_schedule)
            if d > first_union_date
        }

    weights = [float(item["weight"]) for item in asset_inputs]
    units = [0.0] * n_assets
    net_invested = 0.0
    gross_invested = 0.0
    total_withdrawn = 0.0
    peak_invested = 0.0
    buy_count = 0
    sell_count = 0
    hold_count = 0
    rebalance_count = 0

    target_value = 0.0
    last_target_date: Optional[date] = None
    cashflows: List[dict] = []
    irr_cashflows: List[Tuple[date, float]] = []
    equity_curve: List[dict] = []

    unit_index = 100.0
    prev_close_value = 0.0

    for day_idx, current_date in enumerate(union_dates):
        prices_today = [base_prices[i][day_idx] for i in range(n_assets)]
        pre_value = sum(units[i] * prices_today[i] for i in range(n_assets))
        if day_idx > 0 and prev_close_value > 1e-8:
            unit_index *= pre_value / prev_close_value

        # 1. Initial lump-sum investment on first trading day
        if day_idx == 0 and initial_amount > 0:
            legs = []
            for i in range(n_assets):
                leg_amt = initial_amount * weights[i]
                leg_units = (leg_amt / prices_today[i]) if prices_today[i] > 0 else 0.0
                units[i] += leg_units
                legs.append({
                    "symbol": asset_inputs[i]["symbol"],
                    "amount": round(leg_amt, 2),
                    "weight": round(weights[i] * 100, 2),
                })
            net_invested += initial_amount
            gross_invested += initial_amount
            peak_invested = max(peak_invested, net_invested)
            buy_count += 1
            irr_cashflows.append((current_date, -initial_amount))
            post_init_val = sum(units[i] * prices_today[i] for i in range(n_assets))
            row = {
                "date": current_date.isoformat(),
                "planned_date": effective_start_date.isoformat(),
                "amount": round(initial_amount, 2),
                "kind": "initial",
                "net_invested": round(net_invested, 2),
                "portfolio_value": round(post_init_val, 2),
                "legs": legs,
                "allocation_summary": _format_leg_summary(legs),
            }
            if clean_strategy == "vca":
                target_value = initial_amount
                last_target_date = current_date
                row["target_value"] = round(target_value, 2)
            cashflows.append(row)

        # 2. Scheduled DCA or VCA cashflow
        if current_date in exec_dates_set and amount > 0:
            cur_val = sum(units[i] * prices_today[i] for i in range(n_assets))
            if clean_strategy == "dca":
                trade_amount = amount
                kind = "recurring"
            else:
                apply_growth = last_target_date is not None and current_date > last_target_date
                target_value, trade_amount, kind = _compute_vca_step(
                    prev_target=target_value,
                    increment=amount,
                    growth_rate_pct=vca_growth_rate,
                    apply_growth=apply_growth,
                    current_value=cur_val,
                    allow_sell=vca_allow_sell,
                    max_contribution=vca_max_contribution,
                )
                last_target_date = current_date

            legs = []
            if trade_amount > 1e-8:
                for i in range(n_assets):
                    leg_amt = trade_amount * weights[i]
                    leg_units = (leg_amt / prices_today[i]) if prices_today[i] > 0 else 0.0
                    units[i] += leg_units
                    legs.append({
                        "symbol": asset_inputs[i]["symbol"],
                        "amount": round(leg_amt, 2),
                        "weight": round(weights[i] * 100, 2),
                    })
                gross_invested += trade_amount
                buy_count += 1
                irr_cashflows.append((current_date, -trade_amount))
            elif trade_amount < -1e-8 and cur_val > 1e-8:
                for i in range(n_assets):
                    asset_val = units[i] * prices_today[i]
                    cur_share = asset_val / cur_val
                    leg_amt = trade_amount * cur_share
                    leg_units = (leg_amt / prices_today[i]) if prices_today[i] > 0 else 0.0
                    units[i] = max(0.0, units[i] + leg_units)
                    legs.append({
                        "symbol": asset_inputs[i]["symbol"],
                        "amount": round(leg_amt, 2),
                        "weight": round(cur_share * 100, 2),
                    })
                total_withdrawn += -trade_amount
                sell_count += 1
                irr_cashflows.append((current_date, -trade_amount))
            else:
                for i in range(n_assets):
                    asset_val = units[i] * prices_today[i]
                    cur_share = (asset_val / cur_val) if cur_val > 1e-8 else weights[i]
                    legs.append({
                        "symbol": asset_inputs[i]["symbol"],
                        "amount": 0.0,
                        "weight": round(cur_share * 100, 2),
                    })
                hold_count += 1

            net_invested += trade_amount
            peak_invested = max(peak_invested, net_invested)
            post_trade_val = sum(units[i] * prices_today[i] for i in range(n_assets))
            row = {
                "date": current_date.isoformat(),
                "planned_date": current_date.isoformat(),
                "amount": round(trade_amount, 2),
                "kind": kind,
                "net_invested": round(net_invested, 2),
                "portfolio_value": round(post_trade_val, 2),
                "legs": legs,
                "allocation_summary": _format_leg_summary(legs),
            }
            if clean_strategy == "vca":
                row["target_value"] = round(target_value, 2)
            cashflows.append(row)

        # 3. Scheduled Rebalance
        if current_date in rebalance_dates_set:
            cur_val = sum(units[i] * prices_today[i] for i in range(n_assets))
            if cur_val > 1e-8:
                max_drift = max(
                    abs((units[i] * prices_today[i]) / cur_val - weights[i])
                    for i in range(n_assets)
                )
                if max_drift > 1e-4:
                    reb_legs = []
                    for i in range(n_assets):
                        current_leg_val = units[i] * prices_today[i]
                        target_leg_val = cur_val * weights[i]
                        delta_val = target_leg_val - current_leg_val
                        units[i] = (target_leg_val / prices_today[i]) if prices_today[i] > 0 else 0.0
                        reb_legs.append({
                            "symbol": asset_inputs[i]["symbol"],
                            "amount": round(delta_val, 2),
                            "weight": round(weights[i] * 100, 2),
                        })
                    rebalance_count += 1
                    reb_row = {
                        "date": current_date.isoformat(),
                        "planned_date": current_date.isoformat(),
                        "amount": 0.0,
                        "kind": "rebalance",
                        "net_invested": round(net_invested, 2),
                        "portfolio_value": round(cur_val, 2),
                        "legs": reb_legs,
                        "allocation_summary": _format_leg_summary(reb_legs),
                    }
                    if clean_strategy == "vca":
                        reb_row["target_value"] = round(target_value, 2)
                    cashflows.append(reb_row)

        close_val = sum(units[i] * prices_today[i] for i in range(n_assets))
        prev_close_value = close_val
        pt = {
            "date": current_date.isoformat(),
            "price": round(unit_index, 4),
            "invested": round(net_invested, 2),
            "value": round(close_val, 2),
        }
        if clean_strategy == "vca":
            pt["target"] = round(target_value, 2)
        equity_curve.append(pt)

    last_date = union_dates[-1]
    final_value = sum(units[i] * base_prices[i][-1] for i in range(n_assets))
    profit = final_value - net_invested
    roi_base = peak_invested if total_withdrawn > 0 else net_invested
    return_pct = 0.0 if roi_base <= 0 else (profit / roi_base) * 100
    money_weighted_return = _compute_money_weighted_annualized_return(
        cashflows=irr_cashflows,
        final_date=last_date,
        final_value=final_value,
    )
    annualized_return_pct = (money_weighted_return or 0.0) * 100

    holdings = []
    for i, item in enumerate(asset_inputs):
        leg_final_val = units[i] * base_prices[i][-1]
        final_weight_pct = ((leg_final_val / final_value) * 100.0) if final_value > 1e-8 else (weights[i] * 100.0)
        holdings.append({
            "symbol": item["symbol"],
            "type": item["type"],
            "native_currency": item["native_currency"],
            "target_weight": round(weights[i] * 100.0, 2),
            "final_weight": round(final_weight_pct, 2),
            "units": round(units[i], 8),
            "last_price_native": round(native_prices[i][-1], 6),
            "last_price_base": round(base_prices[i][-1], 6),
            "final_value": round(leg_final_val, 2),
            "source": item.get("source"),
        })

    return {
        "effective_start_date": effective_start_date.isoformat(),
        "end_date": last_date.isoformat(),
        "holdings": holdings,
        "summary": {
            "invested": round(net_invested, 2),
            "gross_invested": round(gross_invested, 2),
            "total_withdrawn": round(total_withdrawn, 2),
            "peak_invested": round(peak_invested, 2),
            "final_value": round(final_value, 2),
            "profit": round(profit, 2),
            "return_pct": round(return_pct, 2),
            "annualized_return_pct": round(annualized_return_pct, 2),
            "trade_count": buy_count + sell_count,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "hold_count": hold_count,
            "rebalance_count": rebalance_count,
            "last_price": round(unit_index, 4),
        },
        "cashflows": cashflows,
        "equity_curve": equity_curve,
    }


