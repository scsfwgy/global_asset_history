"""Country-only offline lookup. Never persist or send visitor IPs elsewhere."""

import gzip
import logging
import os
import re
from functools import lru_cache
from ipaddress import ip_address, ip_network
from pathlib import Path

import maxminddb

logger = logging.getLogger(__name__)
_DATABASE = Path(__file__).resolve().parent.parent / "resources" / "dbip-country-lite.mmdb.gz"
_CODE = re.compile(r"^[A-Z]{2}$")


def _country(value):
    code = str(value or "").strip().upper()
    return code if _CODE.fullmatch(code) and code not in {"XX", "ZZ"} else ""


def _address(value):
    address = ip_address(value)
    return getattr(address, "ipv4_mapped", None) or address


def _trusted_proxies():
    # Trust only local reverse proxies unless the operator names other networks.
    value = os.getenv("GEOIP_TRUSTED_PROXIES", "127.0.0.0/8,::1/128")
    return tuple(ip_network(part.strip()) for part in value.split(",") if part.strip())


def _client_address(headers, remote_addr):
    peer = _address(remote_addr)
    networks = _trusted_proxies()
    if not any(peer in network for network in networks):
        return peer
    forwarded = str(headers.get("X-Forwarded-For") or "")
    if not forwarded:
        return peer
    if len(forwarded) > 4096:
        raise ValueError("Forwarded chain too long")
    # Walk from the known peer; ignore forged entries before the first untrusted hop.
    for raw in reversed(forwarded.split(",")):
        peer = _address(raw.strip())
        if not any(peer in network for network in networks):
            return peer
    return peer


@lru_cache(maxsize=1)
def _reader(path):
    if path.endswith(".gz"):
        with gzip.open(path, "rb") as database:
            return maxminddb.open_database(database, mode=maxminddb.MODE_FD)
    return maxminddb.open_database(path)


def _database_path():
    return os.getenv("GEOIP_DATABASE") or str(_DATABASE)


def country_from_headers(headers, remote_addr=None):
    if os.getenv("VERCEL"):
        return _country(headers.get("X-Vercel-IP-Country"))
    if not remote_addr:
        return ""
    try:
        address = _client_address(headers, remote_addr)
        if not address.is_global:
            return ""
        record = _reader(_database_path()).get(str(address)) or {}
        return _country(record.get("country", {}).get("iso_code"))
    except (OSError, ValueError, RuntimeError):
        logger.warning("GeoIP lookup unavailable; check database and trusted proxies")
        return ""


def report_metadata():
    """Admin-only collection health, separate from count storage health."""
    if os.getenv("VERCEL"):
        return {"lookupStatus": "ok", "countrySource": "vercel"}
    try:
        _trusted_proxies()
        _reader(_database_path())
    except FileNotFoundError:
        return {"lookupStatus": "unconfigured", "lookupMessage": "国家数据库未配置，地区访问暂不能采集。"}
    except (OSError, ValueError, RuntimeError):
        return {"lookupStatus": "unavailable", "lookupMessage": "国家解析不可用，请检查数据库与可信代理配置。"}
    return {"lookupStatus": "ok", "countrySource": "local-db"}
