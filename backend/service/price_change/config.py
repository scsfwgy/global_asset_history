"""Configuration loader for price change feature."""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parents[3] / "backend" / "config" / "price_change_config.json"
DEFAULT_SITE_BASE_URL = "https://qqq.tools24.uk"

_CONFIG_CACHE: Optional[Dict] = None


def load_config() -> Dict:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    default = {
        "site": {"base_url": DEFAULT_SITE_BASE_URL},
        "presets": {},
        "color_range": {"min": -100, "max": 100},
        "crypto": {
            "binance_base_url": "https://api.binance.com",
            "okx_base_url": "https://www.okx.com",
            "coingecko_base_url": "https://api.coingecko.com/api/v3",
            "coin_ids": {},
        },
    }

    if not CONFIG_PATH.exists():
        logger.warning("Config not found at %s, using defaults", CONFIG_PATH)
        _CONFIG_CACHE = default
        return default

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error("Failed to load config %s: %s, using defaults", CONFIG_PATH, e)
        _CONFIG_CACHE = default
        return default

    crypto = dict(default["crypto"])
    crypto.update(cfg.get("crypto", {}))
    cfg["crypto"] = crypto
    site = dict(default["site"])
    site.update(cfg.get("site", {}))
    cfg["site"] = site
    cfg.setdefault("presets", {})

    _CONFIG_CACHE = cfg
    return cfg


def get_presets() -> Dict:
    return load_config().get("presets", {})


def get_color_range() -> Dict:
    return load_config().get("color_range", {"min": -100, "max": 100})


def get_color_scheme() -> str:
    """Return the color scheme: 'green_up' (default, international) or 'red_up' (A-share convention)."""
    return load_config().get("color_scheme", "green_up")


def get_site_config() -> Dict:
    return load_config().get("site", {"base_url": DEFAULT_SITE_BASE_URL})


def get_site_base_url() -> str:
    return get_site_config().get("base_url", DEFAULT_SITE_BASE_URL).rstrip("/")


def crypto_config() -> Dict:
    return load_config().get("crypto", {})


def coingecko_ids() -> Dict[str, str]:
    return crypto_config().get("coin_ids", {})


def binance_base_url() -> str:
    return crypto_config().get("binance_base_url", "https://api.binance.com")


def okx_base_url() -> str:
    return crypto_config().get("okx_base_url", "https://www.okx.com")


def coingecko_base_url() -> str:
    return crypto_config().get("coingecko_base_url", "https://api.coingecko.com/api/v3")
