"""Tests for cumulative website-language and device-language users."""

from unittest.mock import call, patch

from service import visitor_stats
from service.price_change import cache_store


def test_normalizes_only_supported_site_languages():
    assert visitor_stats.normalize_site_language("zh-CN") == "zh-CN"
    assert visitor_stats.normalize_site_language("ZH-cn") == "zh-CN"
    assert visitor_stats.normalize_site_language("en") == "en"
    assert visitor_stats.normalize_site_language("fr") == ""
    assert visitor_stats.normalize_site_language("") == ""


def test_normalizes_complete_device_language():
    assert visitor_stats.normalize_device_language("zh-hant-tw") == "zh-Hant-TW"
    assert visitor_stats.normalize_device_language("en-us") == "en-US"
    assert visitor_stats.normalize_device_language("es-419") == "es-419"
    assert visitor_stats.normalize_device_language("bad language!") == "unknown"
    assert visitor_stats.normalize_device_language("") == "unknown"


def test_local_fallback_deduplicates_and_keeps_dimensions_independent(tmp_path, monkeypatch):
    storage_path = tmp_path / "languages.json"
    monkeypatch.setattr(visitor_stats, "_LANGUAGE_VISITS_PATH", storage_path)
    monkeypatch.setattr(visitor_stats.cache_store, "is_enabled", lambda: False)
    digest = "a" * 64

    visitor_stats.record_language_visit(digest, "zh-CN", "en-US")
    visitor_stats.record_language_visit(digest, "zh-CN", "en-US")
    visitor_stats.record_language_visit(digest, "en", "en-US")

    assert visitor_stats.get_language_stats() == {
        "site_language": {"zh-CN": 1, "en": 1},
        "device_language": {"en-US": 1},
    }
    contents = storage_path.read_text()
    assert contents.count(digest) == 3


def test_invalid_digest_is_not_persisted(tmp_path, monkeypatch):
    storage_path = tmp_path / "languages.json"
    monkeypatch.setattr(visitor_stats, "_LANGUAGE_VISITS_PATH", storage_path)
    monkeypatch.setattr(visitor_stats.cache_store, "is_enabled", lambda: False)

    visitor_stats.record_language_visit("raw-user-id", "zh-CN", "en-US")

    assert visitor_stats.get_language_stats() == {
        "site_language": {"zh-CN": 0, "en": 0},
        "device_language": {},
    }
    assert not storage_path.exists()


def test_redis_uses_independent_sets_and_reads_exact_cardinality(monkeypatch):
    digest = "b" * 64
    monkeypatch.setattr(visitor_stats.cache_store, "is_enabled", lambda: True)

    with (
        patch.object(visitor_stats.cache_store, "cache_sadd", return_value=1) as sadd,
        patch.object(visitor_stats.cache_store, "cache_smembers", return_value=["en-US", "zh-TW"]),
        patch.object(
            visitor_stats.cache_store,
            "cache_scard",
            side_effect=lambda key: {
                "site_language_users:zh-CN": 4,
                "site_language_users:en": 2,
                "device_language_users:en-US": 3,
                "device_language_users:zh-TW": 1,
            }[key],
        ),
    ):
        visitor_stats.record_language_visit(digest, "zh-CN", "en-us")
        stats = visitor_stats.get_language_stats()

    assert sadd.call_args_list == [
        call("site_language_users:zh-CN", digest),
        call("device_language_locales", "en-US"),
        call("device_language_users:en-US", digest),
    ]
    assert stats == {
        "site_language": {"zh-CN": 4, "en": 2},
        "device_language": {"en-US": 3, "zh-TW": 1},
    }


def test_redis_failures_do_not_escape(monkeypatch):
    monkeypatch.setattr(visitor_stats.cache_store, "is_enabled", lambda: True)
    monkeypatch.setattr(
        visitor_stats.cache_store,
        "cache_sadd",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("redis unavailable")),
    )

    visitor_stats.record_language_visit("c" * 64, "zh-CN", "en-US")


def test_cache_smembers_filters_non_string_values(monkeypatch):
    monkeypatch.setattr(cache_store, "_command", lambda _args: ["en-US", 3, "zh-TW"])

    assert cache_store.cache_smembers("device_language_locales") == ["en-US", "zh-TW"]
