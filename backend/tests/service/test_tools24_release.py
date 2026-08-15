"""Tests for Tools24 release URL validation and persistence."""

import json

import pytest

from service import tools24_release


@pytest.fixture(autouse=True)
def isolate_release_state(monkeypatch):
    monkeypatch.setattr(tools24_release, "_memory_release", None)


def test_default_release_contains_current_official_apk(monkeypatch):
    monkeypatch.setattr(tools24_release.cache_store, "is_enabled", lambda: False)

    release = tools24_release.get_release()

    assert release["download_url"] == tools24_release.DEFAULT_DOWNLOAD_URL
    assert release["version"] == "1.0.1"
    assert release["google_play_url"] == tools24_release.GOOGLE_PLAY_URL


def test_set_release_persists_to_shared_cache(monkeypatch):
    stored = {}
    monkeypatch.setattr(tools24_release.cache_store, "is_enabled", lambda: True)
    monkeypatch.setattr(tools24_release.cache_store, "cache_get", lambda key: stored.get(key))

    def fake_cache_set(key, value, ttl):
        stored[key] = value
        stored["ttl"] = ttl
        return True

    monkeypatch.setattr(tools24_release.cache_store, "cache_set", fake_cache_set)
    url = "https://downloads.example.com/tools24_V2.3.4_official.apk"

    updated = tools24_release.set_release(url)
    tools24_release._memory_release = None
    loaded = tools24_release.get_release()

    assert updated["version"] == "2.3.4"
    assert loaded["download_url"] == url
    assert json.loads(stored[tools24_release._CACHE_KEY])["download_url"] == url
    assert stored["ttl"] == tools24_release._CACHE_TTL_SECONDS


@pytest.mark.parametrize(
    "value",
    [None, "", "http://example.com/app.apk", "https://example.com/app.zip", "https:///app.apk"],
)
def test_validate_download_url_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        tools24_release.validate_download_url(value)
