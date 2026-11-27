"""Admin-only mihomo (Clash) VPN monitor, probe, and anti-abuse subscription service."""

import ipaddress
import logging
import os
import socket
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, urlparse

import requests
import yaml

logger = logging.getLogger(__name__)

_YAHOO_PROBE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1d&interval=1d"
_CONTROLLER_TIMEOUT = 5
_DELAY_TEST_TIMEOUT_MS = 5000
_PROBE_TIMEOUT = 12
_SUBSCRIPTION_TIMEOUT = 15
_MAX_SUBSCRIPTION_BYTES = 5 * 1024 * 1024
_ANTI_ABUSE_INTERVAL_SECONDS = 1800
_DEFAULT_ANTI_ABUSE_NODES = 5

_INFO_PROXY_KEYWORDS = ("到期", "重置", "获取", "流量", "官网", "剩余", "套餐", "公告", "过滤")
_REGION_BUCKETS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("US", ("美国", "🇺🇸", " US")),
    ("SG", ("狮城", "新加坡", "🇸🇬", " SG")),
    ("JP", ("日本", "🇯🇵", " JP")),
    ("TW", ("台湾", "台灣", "🇹🇼", " TW")),
    ("HK", ("香港", "🇭🇰", " HK")),
)

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


def _config_path() -> str:
    return (os.environ.get("MIHOMO_CONFIG_PATH") or "").strip()


def _host_config_path() -> str:
    return (os.environ.get("MIHOMO_HOST_CONFIG_PATH") or _config_path()).strip()


def _controller_bind() -> str:
    parsed = urlparse(_controller_url())
    if parsed.netloc:
        return parsed.netloc
    return "172.17.0.1:9090"


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


def _controller_put(path: str, payload: Dict[str, Any], timeout: float = 10) -> None:
    base = _controller_url()
    resp = _ctrl_session.put(
        f"{base}{path}",
        headers=_controller_headers(),
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()


def _is_disallowed_ip(ip_obj: ipaddress._BaseAddress) -> bool:
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def _validate_subscription_url(raw_url: str) -> str:
    url = str(raw_url or "").strip()
    if not url:
        raise ValueError("订阅地址不能为空")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("请输入有效的 http/https 订阅地址")

    host = parsed.hostname.lower().strip(".")
    if host in {"localhost"} or host.endswith(".local") or host.endswith(".internal"):
        raise ValueError("不允许使用内网或本地订阅地址")

    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if _is_disallowed_ip(literal_ip):
            raise ValueError("不允许使用内网或保留 IP 订阅地址")
        return url

    try:
        addr_infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError:
        # Allow HTTP client to report upstream resolution error if unreachable.
        return url

    for info in addr_infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip_str = str(sockaddr[0]).split("%", 1)[0]
        try:
            resolved_ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if _is_disallowed_ip(resolved_ip):
            raise ValueError("不允许解析到内网或保留 IP 的订阅地址")
    return url


def _is_info_proxy(proxy: Any) -> bool:
    if not isinstance(proxy, dict):
        return True
    name = str(proxy.get("name") or "").strip()
    server = str(proxy.get("server") or "").strip().lower()
    port = proxy.get("port")
    if not name or not server or not port:
        return True
    if server in {"127.0.0.1", "localhost", "0.0.0.0", "::1"}:
        return True
    return any(keyword in name for keyword in _INFO_PROXY_KEYWORDS)


def _is_preferred_daily_node(name: str) -> bool:
    return "日用" in name or "[0." in name


def _select_anti_abuse_proxies(proxies: List[Dict[str, Any]], max_nodes: int = _DEFAULT_ANTI_ABUSE_NODES) -> List[Dict[str, Any]]:
    limit = max(1, min(10, int(max_nodes or _DEFAULT_ANTI_ABUSE_NODES)))
    valid = [p for p in proxies if not _is_info_proxy(p)]
    if len(valid) <= limit:
        return valid

    selected: List[Dict[str, Any]] = []
    selected_names = set()

    for _, keywords in _REGION_BUCKETS:
        if len(selected) >= limit:
            break
        candidates = [
            p for p in valid
            if p["name"] not in selected_names
            and any(kw in p["name"].upper() or kw in p["name"] for kw in keywords)
        ]
        if not candidates:
            continue
        preferred = [p for p in candidates if _is_preferred_daily_node(p["name"])]
        pick = preferred[0] if preferred else candidates[0]
        selected.append(pick)
        selected_names.add(pick["name"])

    for p in valid:
        if len(selected) >= limit:
            break
        if p["name"] not in selected_names:
            selected.append(p)
            selected_names.add(p["name"])

    return selected


def build_anti_abuse_mihomo_config(
    sub_yaml: str, *, max_nodes: int = _DEFAULT_ANTI_ABUSE_NODES
) -> Tuple[str, List[str], int]:
    """Build a minimal anti-abuse mihomo config from a raw Clash subscription."""
    try:
        parsed = yaml.safe_load(sub_yaml)
    except yaml.YAMLError as exc:
        raise ValueError("订阅内容不是有效的 Clash YAML 配置") from exc

    if not isinstance(parsed, dict) or not isinstance(parsed.get("proxies"), list):
        raise ValueError("订阅中未找到有效的 proxies 节点列表")

    valid_proxies = [p for p in parsed["proxies"] if not _is_info_proxy(p)]
    if not valid_proxies:
        raise ValueError("订阅中没有可用的代理节点")

    selected = _select_anti_abuse_proxies(valid_proxies, max_nodes=max_nodes)
    selected_names = [str(p["name"]) for p in selected]
    group_name = _proxy_group()

    config: Dict[str, Any] = {
        "port": 7890,
        "socks-port": 7891,
        "mixed-port": 7893,
        "allow-lan": True,
        "bind-address": "*",
        "lan-allowed-ips": ["127.0.0.1/8", "172.17.0.0/16"],
        "mode": "rule",
        "log-level": "warning",
        "external-controller": _controller_bind(),
        "unified-delay": True,
        "ipv6": False,
        "proxies": selected,
        "proxy-groups": [
            {
                "name": group_name,
                "type": "fallback",
                "proxies": selected_names,
                "url": _YAHOO_PROBE_URL,
                "expected-status": 200,
                "interval": _ANTI_ABUSE_INTERVAL_SECONDS,
                "lazy": True,
            }
        ],
        "rules": [
            f"DOMAIN-SUFFIX,yahoo.com,{group_name}",
            f"DOMAIN-SUFFIX,yimg.com,{group_name}",
            f"MATCH,{group_name}",
        ],
    }
    secret = _controller_secret()
    if secret:
        config["secret"] = secret

    yaml_text = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    return yaml_text, selected_names, len(valid_proxies)


def _atomic_write_config(path: str, content: str) -> None:
    target_dir = os.path.dirname(os.path.abspath(path))
    os.makedirs(target_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".mihomo-cfg-", suffix=".yaml", dir=target_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


def _latest_delay(proxy_info: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
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


def update_vpn_subscription(subscription_url: str, *, max_nodes: int = _DEFAULT_ANTI_ABUSE_NODES) -> Dict[str, Any]:
    """Fetch a Clash subscription, build an anti-abuse config, and hot-reload mihomo."""
    global _last_hit
    base = _controller_url()
    if not base:
        return {
            "configured": False,
            "error": "MIHOMO_CONTROLLER_URL not configured",
        }

    validated_url = _validate_subscription_url(subscription_url)

    chunks: List[bytes] = []
    total_read = 0
    resp = _ctrl_session.get(
        validated_url,
        headers={"User-Agent": "clash-verge/v2.0.0"},
        timeout=_SUBSCRIPTION_TIMEOUT,
        stream=True,
    )
    try:
        resp.raise_for_status()
        for chunk in resp.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total_read += len(chunk)
            if total_read > _MAX_SUBSCRIPTION_BYTES:
                raise ValueError("订阅响应体积超过 5 MB 限制")
            chunks.append(chunk)
    finally:
        resp.close()

    raw_text = b"".join(chunks).decode("utf-8", errors="replace")
    yaml_text, selected_names, total_count = build_anti_abuse_mihomo_config(
        raw_text, max_nodes=max_nodes
    )

    cfg_path = _config_path()
    if cfg_path:
        _atomic_write_config(cfg_path, yaml_text)
        _controller_put("/configs?force=true", {"path": _host_config_path()})
    else:
        _controller_put("/configs?force=true", {"payload": yaml_text})

    with _last_hit_lock:
        _last_hit = None

    logger.info(
        "event=vpn_subscription_updated total_nodes=%d selected_nodes=%d mode=anti_abuse",
        total_count,
        len(selected_names),
    )

    status = get_vpn_status()
    status["subscription_update"] = {
        "mode": "anti_abuse",
        "selected_nodes": selected_names,
        "selected_count": len(selected_names),
        "total_in_subscription": total_count,
        "updated_at": int(time.time()),
    }
    return status
