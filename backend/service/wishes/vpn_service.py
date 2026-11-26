"""Admin-only mihomo (Clash) VPN monitor and Yahoo probe service."""

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

_YAHOO_PROBE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1d&interval=1d"
_CONTROLLER_TIMEOUT = 5
_DELAY_TEST_TIMEOUT_MS = 5000
_PROBE_TIMEOUT = 12

_ctrl_session = requests.Session()
_ctrl_session.trust_env = False

_last_hit_lock = threading.Lock()
_last_hit: Optional[Dict[str, Any]] = None


def _controller_url() -> str:
    return (os.environ.get("MIHOMO_CONTROLLER_URL") or "").strip().rstrip("/")


def _controller_secret() -> str:
    return (os.environ.get("MIHOMO_CONTROLLER_SECRET") or "").strip()


def _proxy_group() -> str:
    return (os.environ.get("MIHOMO_PROXY_GROUP") or "YahooAuto").strip() or "YahooAuto"


def _yahoo_proxy_url() -> str:
    return (
        os.environ.get("YAHOO_PROXY_URL")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
        or ""
    ).strip()


def _controller_headers() -> Dict[str, str]:
    secret = _controller_secret()
    if secret:
        return {"Authorization": f"Bearer {secret}"}
    return {}


def _controller_get(path: str, timeout: float = _CONTROLLER_TIMEOUT) -> Dict[str, Any]:
    base = _controller_url()
    resp = _ctrl_session.get(
        f"{base}{path}",
        headers=_controller_headers(),
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json() or {}


def _latest_delay(proxy_info: Dict[str, Any]) -> tuple[Optional[int], Optional[str]]:
    history = proxy_info.get("history") or []
    if not isinstance(history, list) or not history:
        return None, None
    last = history[-1]
    if not isinstance(last, dict):
        return None, None
    raw_delay = last.get("delay")
    delay_ms = int(raw_delay) if isinstance(raw_delay, (int, float)) and raw_delay > 0 else None
    return delay_ms, last.get("time")


def _extract_hit_node(conns_payload: Dict[str, Any], target_host: str = "query1.finance.yahoo.com") -> Optional[str]:
    connections = conns_payload.get("connections") or []
    for conn in connections:
        meta = conn.get("metadata") or {}
        host = str(meta.get("host") or "").lower()
        if target_host not in host:
            continue
        chains = conn.get("chains") or []
        if chains:
            # mihomo returns chains as [leaf_node, ..., group_name]
            return str(chains[0])
    return None


def get_vpn_status() -> Dict[str, Any]:
    """Return mihomo proxy group nodes, latency, active connections, and traffic."""
    base = _controller_url()
    if not base:
        return {
            "configured": False,
            "error": "MIHOMO_CONTROLLER_URL not configured",
        }

    group_name = _proxy_group()
    proxies_data = _controller_get("/proxies")
    conns_data = _controller_get("/connections")

    all_proxies = proxies_data.get("proxies") or {}
    group_info = all_proxies.get(group_name) or {}
    member_names: List[str] = list(group_info.get("all") or [])

    nodes: List[Dict[str, Any]] = []
    for name in member_names:
        info = all_proxies.get(name) or {}
        delay_ms, tested_at = _latest_delay(info)
        alive = bool(info.get("alive", False)) and (delay_ms is not None)
        nodes.append({
            "name": name,
            "type": info.get("type") or "",
            "alive": alive,
            "delay_ms": delay_ms,
            "tested_at": tested_at,
        })

    # Sort healthy nodes by latency ascending, then offline/untested nodes.
    nodes.sort(key=lambda n: (0 if n["delay_ms"] is not None else 1, n["delay_ms"] or 10**9, n["name"]))

    upload_bytes = int(conns_data.get("uploadTotal") or 0)
    download_bytes = int(conns_data.get("downloadTotal") or 0)
    active_conns = conns_data.get("connections") or []

    with _last_hit_lock:
        last_hit = dict(_last_hit) if _last_hit else None

    return {
        "configured": True,
        "group": {
            "name": group_name,
            "type": group_info.get("type") or "",
            "now": group_info.get("now") or None,
            "total_nodes": len(nodes),
            "alive_nodes": sum(1 for n in nodes if n["delay_ms"] is not None),
        },
        "traffic": {
            "upload_bytes": upload_bytes,
            "download_bytes": download_bytes,
            "total_bytes": upload_bytes + download_bytes,
            "active_connections": len(active_conns),
        },
        "last_hit": last_hit,
        "nodes": nodes,
    }


def probe_yahoo_vpn(refresh_delays: bool = False) -> Dict[str, Any]:
    """Probe Yahoo via the configured proxy and record the hit node + latency."""
    global _last_hit
    base = _controller_url()
    if not base:
        return {
            "configured": False,
            "error": "MIHOMO_CONTROLLER_URL not configured",
        }

    group_name = _proxy_group()
    if refresh_delays:
        query = urlencode({"timeout": _DELAY_TEST_TIMEOUT_MS, "url": _YAHOO_PROBE_URL})
        try:
            _controller_get(f"/group/{group_name}/delay?{query}", timeout=15)
        except Exception as exc:
            logger.warning("mihomo group delay refresh failed: %s", exc)

    proxy_url = _yahoo_proxy_url()
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

    hit_node: Optional[str] = None
    status_code: Optional[int] = None
    error_msg: Optional[str] = None
    start = time.time()
    resp = None
    try:
        resp = requests.get(
            _YAHOO_PROBE_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            proxies=proxies,
            stream=True,
            timeout=_PROBE_TIMEOUT,
        )
        status_code = resp.status_code
        # Inspect active mihomo connections while the stream is still open.
        try:
            conns_data = _controller_get("/connections", timeout=2)
            hit_node = _extract_hit_node(conns_data)
        except Exception as exc:
            logger.debug("Failed to read active mihomo connections during probe: %s", exc)
        # Drain/close cleanly.
        resp.raw.read(64)
    except Exception as exc:
        error_msg = str(exc)
    finally:
        if resp is not None:
            resp.close()

    latency_ms = int((time.time() - start) * 1000)

    status = get_vpn_status()
    node_delay_ms = None
    if hit_node:
        for n in status.get("nodes", []):
            if n["name"] == hit_node:
                node_delay_ms = n.get("delay_ms")
                break

    hit_record = {
        "node": hit_node,
        "node_delay_ms": node_delay_ms,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "tested_at": int(time.time()),
        "error": error_msg,
    }
    with _last_hit_lock:
        _last_hit = hit_record
    status["last_hit"] = dict(hit_record)
    return status
