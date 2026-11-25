"""Foreign exchange lookup and daily cross-rate conversion helpers."""

from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
import logging
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .common import PriceSeries

logger = logging.getLogger(__name__)

# Supported fiat currencies for the exchange-loss tool. Each maps to a Yahoo
# FX symbol plus an inverse flag: inverse=True means the symbol quotes "units
# of the currency per 1 USD" (e.g. CNY=X is USD/CNY), inverse=False means the
# symbol quotes "USD per 1 unit" (e.g. EURUSD=X is EUR/USD). USD is the hub.
FX_CURRENCIES: Dict[str, Tuple[Optional[str], bool]] = {
    "USD": (None, False),
    "CNY": ("CNY=X", True),
    "EUR": ("EURUSD=X", False),
    "GBP": ("GBPUSD=X", False),
    "JPY": ("JPY=X", True),
    "HKD": ("HKD=X", True),
    "KRW": ("KRW=X", True),
    "AUD": ("AUDUSD=X", False),
    "SGD": ("SGD=X", True),
    "CAD": ("CAD=X", True),
    "CHF": ("CHF=X", True),
    "TWD": ("TWD=X", True),
}

# Extended Yahoo FX lookup used by multi-market portfolio backtesting so global
# stock suffixes (.NS, .CO, .SA, .SR) can also be converted to the base currency.
PORTFOLIO_FX_CURRENCIES: Dict[str, Tuple[Optional[str], bool]] = {
    **FX_CURRENCIES,
    "INR": ("INR=X", True),
    "DKK": ("DKK=X", True),
    "BRL": ("BRL=X", True),
    "SAR": ("SAR=X", True),
}

SUPPORTED_PORTFOLIO_BASE_CURRENCIES = {"USD", "CNY", "HKD"}

# Minor units or stablecoin pegs mapped to their underlying fiat currency and scale.
_CURRENCY_UNIT_ALIASES: Dict[str, Tuple[str, float]] = {
    "USDT": ("USD", 1.0),
    "USDC": ("USD", 1.0),
    "GBP": ("GBP", 1.0),
    "GBp": ("GBP", 0.01),
}


def normalize_currency_unit(currency: str) -> Tuple[str, float]:
    """Return (canonical_fiat_code, scale_to_canonical) for a quote currency."""
    raw = str(currency or "USD").strip()
    if raw in _CURRENCY_UNIT_ALIASES:
        return _CURRENCY_UNIT_ALIASES[raw]
    upper = raw.upper()
    if upper in _CURRENCY_UNIT_ALIASES:
        return _CURRENCY_UNIT_ALIASES[upper]
    return upper or "USD", 1.0


class FxRateLookup:
    """Date-indexed cross-rate converter into a single portfolio base currency."""

    def __init__(
        self,
        base_currency: str,
        usd_series_map: Dict[str, Tuple[List[date], List[float]]],
    ) -> None:
        self.base_currency = str(base_currency or "USD").strip().upper()
        self.base_canonical, self.base_scale = normalize_currency_unit(self.base_currency)
        self._usd_series_map = usd_series_map

    def _usd_per_canonical_unit(self, canonical_code: str, target_date: date) -> float:
        if canonical_code == "USD":
            return 1.0
        entry = self._usd_series_map.get(canonical_code)
        if not entry or not entry[0]:
            raise ValueError(f"FX rate history unavailable for {canonical_code}")
        dates, values = entry
        idx = bisect_right(dates, target_date) - 1
        if idx < 0:
            idx = 0
        return values[idx]

    def rate_to_base(self, from_currency: str, target_date: date) -> float:
        """Return how many units of base_currency equal 1 unit of from_currency on target_date."""
        from_canonical, from_scale = normalize_currency_unit(from_currency)
        if from_canonical == self.base_canonical:
            return from_scale / self.base_scale
        usd_from = self._usd_per_canonical_unit(from_canonical, target_date) * from_scale
        usd_base = self._usd_per_canonical_unit(self.base_canonical, target_date) * self.base_scale
        if usd_base <= 0:
            raise ValueError(f"invalid base FX rate for {self.base_currency}")
        return usd_from / usd_base


def _extract_usd_per_unit_points(
    series: Optional[PriceSeries],
    inverse: bool,
) -> Tuple[List[date], List[float]]:
    if series is None or series.error or not series.timestamps or not series.closes:
        return [], []
    by_date: Dict[date, float] = {}
    for ts, close in zip(series.timestamps, series.closes):
        if close is None:
            continue
        try:
            numeric = float(close)
        except (TypeError, ValueError):
            continue
        if numeric <= 0:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        by_date[dt] = (1.0 / numeric) if inverse else numeric
    if not by_date:
        return [], []
    ordered_dates = sorted(by_date.keys())
    return ordered_dates, [by_date[d] for d in ordered_dates]


def build_fx_rate_lookup(
    currencies: Iterable[str],
    base_currency: str,
    fetch_series_fn: Callable[[str, str], PriceSeries],
) -> FxRateLookup:
    """Fetch only the required Yahoo FX series and return an FxRateLookup."""
    clean_base = str(base_currency or "USD").strip().upper()
    if clean_base not in SUPPORTED_PORTFOLIO_BASE_CURRENCIES:
        raise ValueError(
            f"base_currency must be one of {', '.join(sorted(SUPPORTED_PORTFOLIO_BASE_CURRENCIES))}"
        )

    base_canonical, _ = normalize_currency_unit(clean_base)
    canonical_set = {normalize_currency_unit(c)[0] for c in currencies if c}

    # If all component assets share the same canonical fiat currency as the base,
    # no FX series fetches are required at all.
    if canonical_set <= {base_canonical}:
        return FxRateLookup(clean_base, {})

    needed_codes = sorted(
        code
        for code in (canonical_set | {base_canonical})
        if code != "USD"
    )
    for code in needed_codes:
        if code not in PORTFOLIO_FX_CURRENCIES:
            raise ValueError(f"unsupported currency for FX conversion: {code}")

    usd_series_map: Dict[str, Tuple[List[date], List[float]]] = {}

    def _fetch_one(code: str) -> Tuple[str, Tuple[List[date], List[float]], Optional[str]]:
        symbol, inverse = PORTFOLIO_FX_CURRENCIES[code]
        if not symbol:
            return code, ([], []), None
        series = fetch_series_fn(symbol, "stock")
        if series is None or series.error:
            return code, ([], []), (series.error if series else "no FX data")
        points = _extract_usd_per_unit_points(series, inverse)
        if not points[0]:
            return code, ([], []), f"empty FX history for {symbol}"
        return code, points, None

    if len(needed_codes) == 1:
        code, points, err = _fetch_one(needed_codes[0])
        if err:
            raise ValueError(f"failed to fetch FX rate for {code}: {err}")
        usd_series_map[code] = points
    elif needed_codes:
        with ThreadPoolExecutor(max_workers=min(4, len(needed_codes))) as executor:
            futures = [executor.submit(_fetch_one, code) for code in needed_codes]
            for fut in as_completed(futures):
                code, points, err = fut.result()
                if err:
                    raise ValueError(f"failed to fetch FX rate for {code}: {err}")
                usd_series_map[code] = points

    return FxRateLookup(clean_base, usd_series_map)
