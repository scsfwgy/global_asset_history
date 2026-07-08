"""Guard tests for the A-share ETF preset groups.

These tests lock down two things that have drifted before:

1. Every ETF code listed in the cn_etf_* presets must have a matching entry in
   data/etf_fees.json, and vice versa (no orphan fees, no missing fees). This
   is the exact failure mode that left the "其它" group without fee data.
2. The high-profile move/add operations are asserted explicitly so a careless
   future edit cannot silently regress the benchmark-grouping rule.

The benchmark rule: only true Nasdaq-100 broad-index funds belong in
cn_etf_nasdaq100 (→ benchmarked against QQQ/^NDX), only true S&P 500 broad-index
funds belong in cn_etf_sp500 (→ SPY/^GSPC). Everything else (sector themes,
other US broad indices) belongs in cn_etf_others where it is intentionally left
without a benchmark — see backend/routes/etf_market.py _load_benchmark_map.
"""

import json
import os
from pathlib import Path

import pytest

from service.price_change.config import get_presets

# Resolve data paths relative to this test file (backend root is two levels up).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _BACKEND_ROOT / "config" / "price_change_config.json"
_FEES_PATH = _BACKEND_ROOT / "data" / "etf_fees.json"

_ETF_GROUP_KEYS = ("cn_etf_nasdaq100", "cn_etf_sp500", "cn_etf_others")


def _etf_symbols_by_group() -> dict[str, list[str]]:
    """Return {group_key: [symbol, ...]} from the config presets."""
    presets = get_presets()
    return {
        key: [str(entry.get("symbol", "")).strip() for entry in presets.get(key, {}).get("symbols", [])]
        for key in _ETF_GROUP_KEYS
    }


def _load_fee_codes() -> set[str]:
    with open(_FEES_PATH, "r", encoding="utf-8") as f:
        return set(json.load(f).get("funds", {}).keys())


class TestEtfGroupFeeCoverage:
    """Every configured ETF code must have fee data, and no orphan fees."""

    def test_config_groups_exist(self):
        """All three ETF group keys must be present in the config."""
        presets = get_presets()
        for key in _ETF_GROUP_KEYS:
            assert key in presets, f"Missing ETF group preset: {key}"

    def test_every_config_code_has_fee(self):
        """Each symbol in any cn_etf_* group must have an etf_fees.json entry."""
        fee_codes = _load_fee_codes()
        configured = {
            sym for syms in _etf_symbols_by_group().values() for sym in syms if sym
        }
        missing = sorted(configured - fee_codes)
        assert not missing, f"Config ETF codes without fee data: {missing}"

    def test_no_orphan_fee_entries(self):
        """etf_fees.json must not contain codes absent from the config groups."""
        fee_codes = _load_fee_codes()
        configured = {
            sym for syms in _etf_symbols_by_group().values() for sym in syms if sym
        }
        orphans = sorted(fee_codes - configured)
        assert not orphans, f"Fee entries not in any config group: {orphans}"

    def test_no_duplicate_codes_across_groups(self):
        """A code must not appear in more than one group (drives benchmark)."""
        groups = _etf_symbols_by_group()
        seen: dict[str, list[str]] = {}
        for key, syms in groups.items():
            for sym in syms:
                seen.setdefault(sym, []).append(key)
        dupes = {sym: keys for sym, keys in seen.items() if len(keys) > 1}
        assert not dupes, f"Codes present in multiple groups: {dupes}"


class TestEtfGroupAssignments:
    """Explicit assertions for the benchmark-grouping rule.

    These guard the specific corrections made when fixing the mis-grouped and
    missing ETFs. If someone moves a sector-theme fund back into a broad-index
    group, these tests will fail.
    """

    def test_known_nasdaq100_codes(self):
        """159529 (S&P consumer theme) must NOT be in nasdaq100."""
        syms = set(_etf_symbols_by_group()["cn_etf_nasdaq100"])
        assert "159529" not in syms

    def test_known_sp500_codes(self):
        """159652 (commodities theme) must NOT be in sp500."""
        syms = set(_etf_symbols_by_group()["cn_etf_sp500"])
        assert "159652" not in syms

    @pytest.mark.parametrize(
        "code",
        ["159509", "159529", "159577", "159652", "513850"],
    )
    def test_misfit_and_new_codes_in_others(self, code):
        """Sector themes and non-NDX/SPX broad indices belong in 'others'."""
        syms = set(_etf_symbols_by_group()["cn_etf_others"])
        assert code in syms, f"{code} should be in cn_etf_others"
