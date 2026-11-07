import pytest

from service import geoip


@pytest.fixture(autouse=True)
def local_geoip(monkeypatch):
    for key in ("VERCEL", "GEOIP_DATABASE", "GEOIP_TRUSTED_PROXIES"):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize("address,country", [
    ("8.8.8.8", "US"), ("114.114.114.114", "CN"),
    ("2001:4860:4860::8888", "CA"), ("::ffff:8.8.8.8", "US"),
])
def test_bundled_database_resolves_public_addresses(address, country):
    assert geoip.country_from_headers({}, address) == country
    assert geoip.report_metadata()["lookupStatus"] == "ok"


def test_self_hosted_ignores_spoofed_headers_from_untrusted_peer():
    headers = {"X-Forwarded-For": "8.8.8.8", "X-Vercel-IP-Country": "US"}
    assert geoip.country_from_headers(headers, "114.114.114.114") == "CN"
    assert geoip.country_from_headers(headers) == ""


def test_trusted_proxy_walks_chain_from_the_right(monkeypatch):
    monkeypatch.setenv("GEOIP_TRUSTED_PROXIES", "127.0.0.0/8,172.18.0.0/16")
    headers = {"X-Forwarded-For": "114.114.114.114, 8.8.8.8, 172.18.0.2"}
    assert geoip.country_from_headers(headers, "172.18.0.3") == "US"


@pytest.mark.parametrize("headers,peer", [
    ({}, "127.0.0.1"), ({}, "10.0.0.1"), ({}, "invalid-ip"),
    ({"X-Forwarded-For": "8.8.8.8, invalid-ip"}, "127.0.0.1"),
])
def test_private_or_invalid_addresses_are_not_located(headers, peer, caplog):
    assert geoip.country_from_headers(headers, peer) == ""
    assert peer not in caplog.text
    assert "8.8.8.8" not in caplog.text


def test_missing_or_corrupt_database_is_reported(monkeypatch, tmp_path):
    database = tmp_path / "country.mmdb"
    monkeypatch.setenv("GEOIP_DATABASE", str(database))
    assert geoip.report_metadata()["lookupStatus"] == "unconfigured"
    assert geoip.country_from_headers({}, "8.8.8.8") == ""
    database.write_bytes(b"corrupt")
    assert geoip.report_metadata()["lookupStatus"] == "unavailable"


def test_invalid_proxy_configuration_is_reported(monkeypatch):
    monkeypatch.setenv("GEOIP_TRUSTED_PROXIES", "not-a-network")
    assert geoip.report_metadata()["lookupStatus"] == "unavailable"
    assert geoip.country_from_headers({}, "8.8.8.8") == ""


def test_vercel_only_trusts_country_header_in_vercel_runtime(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    assert geoip.country_from_headers({"X-Vercel-IP-Country": "jp"}) == "JP"
    assert geoip.country_from_headers({"X-Vercel-IP-Country": "XX"}) == ""
    assert geoip.country_from_headers({"X-Vercel-IP-Country": "ZZ"}) == ""
    assert geoip.report_metadata()["countrySource"] == "vercel"
