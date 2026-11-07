"""Daily unique visitors by network country, for the admin map.

Counts only. The anonymous id stays in the existing daily-unique set and is
not stored again here. Week and month totals add those daily counts up.
"""

import json
import logging
import os
import re
import threading
from datetime import date, timedelta
from pathlib import Path

from service import geoip
from service.price_change import cache_store

logger = logging.getLogger(__name__)

_CODE_RE = re.compile(r"^[A-Z]{2}$")
_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_KEY = "geo_visit_daily_counts"
_WINDOW = {"day": 1, "week": 7, "month": 30}
LABELS = {
    "day": "今日去重访客",
    "week": "近 7 日用户天次",
    "month": "近 30 日用户天次",
}
NOTE = ("日是今天的去重访客，国家取当天第一次计入时的网络位置。"
        "周、月把近 7 日和近 30 日的每日人数相加，同一个人跨天会再计一次，不是周活或月活。"
        "没有国家码的访问不计入，上线前的访问也不会补进来。")
_PATH = Path("/tmp/geo_visits.json") if os.path.exists("/tmp") else (
    Path(__file__).resolve().parent.parent / "config" / "geo_visits.json"
)
_lock = threading.Lock()


def _today() -> date:
    return date.today()


country_from_headers = geoip.country_from_headers


def _keep_days(today: date | None = None) -> list[str]:
    today = today or _today()
    return [(today - timedelta(days=offset)).isoformat() for offset in range(_WINDOW["month"] - 1, -1, -1)]


def _read_local() -> dict:
    try:
        payload = json.loads(_PATH.read_text())
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("Invalid geo counters")
    counts = {}
    for day, bucket in payload.items():
        if not _DAY_RE.fullmatch(str(day)) or not isinstance(bucket, dict):
            continue
        parsed = {}
        for code, value in bucket.items():
            if _CODE_RE.fullmatch(str(code)) and isinstance(value, int) and value > 0:
                parsed[str(code)] = value
        if parsed:
            counts[str(day)] = parsed
    return counts


def _write_local(counts: dict) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(counts, ensure_ascii=False, sort_keys=True))


def _load() -> dict:
    if cache_store.is_enabled():
        counts = {}
        for field, value in cache_store.cache_hgetall(_KEY, strict=True).items():
            day, separator, code = str(field).partition(":")
            if not separator or not _DAY_RE.fullmatch(day) or not _CODE_RE.fullmatch(code):
                continue
            try:
                count = int(value)
            except (TypeError, ValueError):
                continue
            if count > 0:
                counts.setdefault(day, {})[code] = count
        return counts
    with _lock:
        return _read_local()


def record(day: str, code: str) -> None:
    """Add one daily visitor. Callers decide whether this person is new today."""
    if not code or not _DAY_RE.fullmatch(str(day)) or str(day) not in set(_keep_days()):
        return
    try:
        if cache_store.is_enabled():
            # ponytail: old hash fields are left in place; drop them if this key grows.
            cache_store.cache_hincrby(_KEY, f"{day}:{code}")
            return
        with _lock:
            counts = _read_local()
            keep = set(_keep_days())
            counts = {kept: counts[kept] for kept in keep if kept in counts}
            bucket = counts.setdefault(str(day), {})
            bucket[code] = bucket.get(code, 0) + 1
            _write_local(counts)
    except Exception:  # noqa: BLE001 - analytics must never break a visit
        logger.warning("Geo analytics write failed")


def periods() -> dict:
    """Today, trailing 7 days, and trailing 30 days, each summed from daily counts."""
    try:
        counts = _load()
    except Exception:  # noqa: BLE001 - a geo read must not take down the rest of the export
        logger.warning("Geo analytics read failed")
        return {**{name: [] for name in _WINDOW}, "status": "unavailable",
                "message": "地区统计读取失败，请检查存储连接后重试。",
                "labels": dict(LABELS), "note": NOTE, **geoip.report_metadata()}
    today = _today()
    report = {}
    for name, days in _WINDOW.items():
        merged = {}
        for offset in range(days - 1, -1, -1):
            bucket = counts.get((today - timedelta(days=offset)).isoformat(), {})
            for code, value in bucket.items():
                merged[code] = merged.get(code, 0) + value
        report[name] = [
            {"code": code, "value": value}
            for code, value in sorted(merged.items(), key=lambda item: (-item[1], item[0]))
        ]
    report["labels"] = dict(LABELS)
    report["note"] = NOTE
    report["status"] = "ok"
    report.update(geoip.report_metadata())
    return report
