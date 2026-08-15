"""Tools24 Android release URL storage and validation."""

import json
import re
import threading
from datetime import datetime, timezone
from urllib.parse import urlsplit

from service.price_change import cache_store


DEFAULT_DOWNLOAD_URL = (
    "https://mateo-oss.oss-cn-shanghai.aliyuncs.com/tools24/release/"
    "toosl24_V1.0.1-e1e8c778_57_20260815164933_official_release.apk"
)
GOOGLE_PLAY_URL = "https://play.google.com/store/apps/details?id=com.maxhall.tools24"
_CACHE_KEY = "tools24:official_release"
_CACHE_TTL_SECONDS = 10 * 365 * 24 * 60 * 60
_VERSION_RE = re.compile(r"(?:^|[_-])[vV](\d+(?:\.\d+){1,3})(?:[_-]|$)")
_lock = threading.Lock()
_memory_release: dict | None = None


def validate_download_url(value: object) -> str:
    """Return a normalized HTTPS APK URL or raise ValueError."""
    if not isinstance(value, str):
        raise ValueError("download_url 必须是字符串")
    url = value.strip()
    if not url or len(url) > 2048:
        raise ValueError("download_url 长度无效")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("download_url 必须是有效的 HTTPS 地址")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("download_url 不能包含账号信息或片段")
    if not parsed.path.lower().endswith(".apk"):
        raise ValueError("download_url 必须指向 APK 文件")
    return url


def _version_from_url(url: str) -> str:
    filename = urlsplit(url).path.rsplit("/", 1)[-1]
    match = _VERSION_RE.search(filename)
    return match.group(1) if match else "最新版本"


def _normalize_release(data: object) -> dict | None:
    if not isinstance(data, dict):
        return None
    try:
        url = validate_download_url(data.get("download_url"))
    except ValueError:
        return None
    updated_at = data.get("updated_at")
    if not isinstance(updated_at, str) or not updated_at:
        updated_at = None
    return {
        "download_url": url,
        "version": _version_from_url(url),
        "updated_at": updated_at,
        "google_play_url": GOOGLE_PLAY_URL,
    }


def get_release() -> dict:
    """Load the current release from shared storage, then local fallback."""
    if cache_store.is_enabled():
        cached = cache_store.cache_get(_CACHE_KEY)
        if cached:
            try:
                release = _normalize_release(json.loads(cached))
            except (TypeError, ValueError, json.JSONDecodeError):
                release = None
            if release:
                return release
    with _lock:
        if _memory_release:
            return dict(_memory_release)
    return {
        "download_url": DEFAULT_DOWNLOAD_URL,
        "version": _version_from_url(DEFAULT_DOWNLOAD_URL),
        "updated_at": None,
        "google_play_url": GOOGLE_PLAY_URL,
    }


def set_release(download_url: object) -> dict:
    """Validate and persist a release URL in Redis when configured."""
    url = validate_download_url(download_url)
    release = {
        "download_url": url,
        "version": _version_from_url(url),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "google_play_url": GOOGLE_PLAY_URL,
    }
    if cache_store.is_enabled():
        payload = json.dumps(release, ensure_ascii=False, separators=(",", ":"))
        if not cache_store.cache_set(_CACHE_KEY, payload, _CACHE_TTL_SECONDS):
            raise RuntimeError("下载地址暂时无法保存，请稍后重试")
    with _lock:
        global _memory_release
        _memory_release = dict(release)
    return release
