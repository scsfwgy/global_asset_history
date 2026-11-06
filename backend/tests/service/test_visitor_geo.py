from datetime import date, timedelta

from service import visitor_geo


def test_country_header_keeps_only_a_real_code():
    assert visitor_geo.country_from_headers({"X-Vercel-IP-Country": "cn"}) == "CN"
    for raw in ("", "XX", "C1", "CHN", "C N"):
        assert visitor_geo.country_from_headers({"X-Vercel-IP-Country": raw}) == ""


def test_periods_sum_daily_counts_and_drop_older_days(monkeypatch, tmp_path):
    today = date(2026, 11, 6)
    monkeypatch.setattr(visitor_geo, "_PATH", tmp_path / "geo.json")
    monkeypatch.setattr(visitor_geo, "_today", lambda: today)
    monkeypatch.setattr(visitor_geo.cache_store, "is_enabled", lambda: False)

    visitor_geo.record(today.isoformat(), "CN")
    visitor_geo.record(today.isoformat(), "US")
    visitor_geo.record((today - timedelta(days=6)).isoformat(), "CN")
    visitor_geo.record((today - timedelta(days=7)).isoformat(), "JP")
    visitor_geo.record((today - timedelta(days=29)).isoformat(), "JP")
    visitor_geo.record((today - timedelta(days=30)).isoformat(), "DE")

    report = visitor_geo.periods()
    assert report["day"] == [{"code": "CN", "value": 1}, {"code": "US", "value": 1}]
    assert {row["code"]: row["value"] for row in report["week"]} == {"CN": 2, "US": 1}
    assert {row["code"]: row["value"] for row in report["month"]} == {"CN": 2, "JP": 2, "US": 1}
    assert "DE" not in (tmp_path / "geo.json").read_text()


def test_redis_counts_stay_out_of_the_local_file(monkeypatch, tmp_path):
    monkeypatch.setattr(visitor_geo, "_PATH", tmp_path / "geo.json")
    monkeypatch.setattr(visitor_geo, "_today", lambda: date(2026, 11, 6))
    store = {}
    monkeypatch.setattr(visitor_geo.cache_store, "is_enabled", lambda: True)

    def hincrby(key, field, amount=1):
        assert key == visitor_geo._KEY
        store[field] = store.get(field, 0) + amount
        return store[field]

    monkeypatch.setattr(visitor_geo.cache_store, "cache_hincrby", hincrby)
    monkeypatch.setattr(visitor_geo.cache_store, "cache_hgetall", lambda key: {k: str(v) for k, v in store.items()})
    visitor_geo.record("2026-11-06", "CN")
    visitor_geo.record("2026-11-06", "CN")
    visitor_geo.record("not-a-day", "US")
    assert visitor_geo.periods()["day"] == [{"code": "CN", "value": 2}]
    assert store == {"2026-11-06:CN": 2}
    assert not (tmp_path / "geo.json").exists()
