"""Cumulative anonymous language distributions for the admin dashboard."""

import json
import logging
import os
import re
import threading
from pathlib import Path

from service.price_change import cache_store

logger = logging.getLogger(__name__)

_SITE_LANGUAGE_ALIASES = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-hans": "zh-CN",
    "zh-sg": "zh-CN",
    "en": "en",
    "zh-tw": "zh-TW",
    "zh-hk": "zh-TW",
    "zh-mo": "zh-TW",
    "zh-hant": "zh-TW",
}
_SITE_LANGUAGES = ("zh-CN", "zh-TW", "en")
_DEVICE_LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

_SITE_LANGUAGE_KEY_PREFIX = "site_language_users:"
_DEVICE_LANGUAGE_LOCALES_KEY = "device_language_locales"
_DEVICE_LANGUAGE_KEY_PREFIX = "device_language_users:"

_LANGUAGE_VISITS_PATH = Path("/tmp/language_visits.json") if os.path.exists("/tmp") else (
    Path(__file__).resolve().parent.parent / "config" / "language_visits.json"
)
_language_visits_lock = threading.Lock()


def normalize_site_language(value: object) -> str:
    """Return the canonical supported website language or an empty string."""
    return _SITE_LANGUAGE_ALIASES.get(str(value or "").strip().lower(), "")


def normalize_device_language(value: object) -> str:
    """Normalize a complete browser language tag while retaining its subtags."""
    raw = str(value or "").strip()
    if len(raw) > 35 or not _DEVICE_LANGUAGE_RE.fullmatch(raw):
        return "unknown"

    parts = raw.split("-")
    normalized = [parts[0].lower()]
    for part in parts[1:]:
        if len(part) == 4 and part.isalpha():
            normalized.append(part.title())
        elif len(part) == 2 and part.isalpha():
            normalized.append(part.upper())
        else:
            normalized.append(part.lower())
    return "-".join(normalized)


def _empty_data() -> dict:
    return {
        "site_language": {"zh-CN": [], "zh-TW": [], "en": []},
        "device_language": {},
    }


def _read_local_data() -> dict:
    try:
        payload = json.loads(_LANGUAGE_VISITS_PATH.read_text())
    except (OSError, ValueError, TypeError):
        return _empty_data()
    if not isinstance(payload, dict):
        return _empty_data()

    data = _empty_data()
    for language in _SITE_LANGUAGES:
        values = payload.get("site_language", {}).get(language, [])
        if isinstance(values, list):
            data["site_language"][language] = sorted(
                {value for value in values if isinstance(value, str) and _DIGEST_RE.fullmatch(value)}
            )

    device_payload = payload.get("device_language", {})
    if isinstance(device_payload, dict):
        for language, values in device_payload.items():
            normalized = normalize_device_language(language)
            if not isinstance(values, list):
                continue
            digests = sorted(
                {value for value in values if isinstance(value, str) and _DIGEST_RE.fullmatch(value)}
            )
            if digests:
                data["device_language"][normalized] = digests
    return data


def _write_local_data(data: dict) -> None:
    _LANGUAGE_VISITS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LANGUAGE_VISITS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, sort_keys=True)
    )


def record_language_visit(
    anonymous_digest: str,
    site_language: object,
    device_language: object,
) -> None:
    """Record both independent language dimensions without failing a visit."""
    digest = str(anonymous_digest or "").strip()
    if not _DIGEST_RE.fullmatch(digest):
        return

    site = normalize_site_language(site_language)
    device = normalize_device_language(device_language)

    if cache_store.is_enabled():
        try:
            if site:
                cache_store.cache_sadd(_SITE_LANGUAGE_KEY_PREFIX + site, digest)
            cache_store.cache_sadd(_DEVICE_LANGUAGE_LOCALES_KEY, device)
            cache_store.cache_sadd(_DEVICE_LANGUAGE_KEY_PREFIX + device, digest)
        except Exception:  # noqa: BLE001 - analytics must never break visits
            logger.warning("Language analytics Redis write failed")
        return

    try:
        with _language_visits_lock:
            data = _read_local_data()
            if site:
                data["site_language"][site] = sorted(
                    set(data["site_language"][site]) | {digest}
                )
            data["device_language"][device] = sorted(
                set(data["device_language"].get(device, [])) | {digest}
            )
            _write_local_data(data)
    except Exception:  # noqa: BLE001 - local analytics is best effort
        logger.warning("Language analytics local write failed")


def get_language_stats() -> dict[str, dict[str, int]]:
    """Return exact cumulative unique-user counts for both dimensions."""
    if cache_store.is_enabled():
        site_stats = {
            language: cache_store.cache_scard(_SITE_LANGUAGE_KEY_PREFIX + language) or 0
            for language in _SITE_LANGUAGES
        }
        device_stats = {}
        for language in sorted(set(cache_store.cache_smembers(_DEVICE_LANGUAGE_LOCALES_KEY))):
            normalized = normalize_device_language(language)
            device_stats[normalized] = (
                cache_store.cache_scard(_DEVICE_LANGUAGE_KEY_PREFIX + normalized) or 0
            )
        return {
            "site_language": site_stats,
            "device_language": device_stats,
        }

    with _language_visits_lock:
        data = _read_local_data()
    return {
        "site_language": {
            language: len(data["site_language"][language])
            for language in _SITE_LANGUAGES
        },
        "device_language": {
            language: len(digests)
            for language, digests in data["device_language"].items()
        },
    }
