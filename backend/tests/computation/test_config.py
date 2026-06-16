"""Tests for backend/service/price_change/config.py"""

import json
import os
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from service.price_change.config import (
    coingecko_ids,
    crypto_config,
    get_color_range,
    get_color_scheme,
    get_presets,
    load_config,
)
from tests.conftest import diagnose, track_coverage

MOD = "config.py"

# Path to real config file for integration-style tests
REAL_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "price_change_config.json"
)


class TestLoadConfig:
    """Configuration loading and caching."""

    def test_loads_real_config(self):
        """The actual config file in the project should load successfully."""
        if not os.path.exists(REAL_CONFIG_PATH):
            pytest.skip("Config file not found at expected path")
        # Reset module-level cache for clean test
        import service.price_change.config as cfg_mod
        cfg_mod._CONFIG_CACHE = None

        config = load_config()
        assert isinstance(config, dict)
        assert "presets" in config
        assert "color_range" in config
        assert "crypto" in config
        diagnose("config keys", sorted(config.keys()))
        diagnose("preset count", len(config["presets"]))
        track_coverage(MOD, 3)

    def test_caches_result(self):
        """Second call returns the same object (cached)."""
        import service.price_change.config as cfg_mod
        cfg_mod._CONFIG_CACHE = None

        c1 = load_config()
        c2 = load_config()
        assert c1 is c2
        track_coverage(MOD, 1)

    def test_missing_file_returns_defaults(self):
        """When config file is missing, defaults are returned."""
        import service.price_change.config as cfg_mod
        cfg_mod._CONFIG_CACHE = None

        fake_path = Path("/nonexistent/path/to/config.json")
        with patch.object(cfg_mod, "CONFIG_PATH", fake_path):
            config = load_config()
            assert isinstance(config, dict)
            assert "presets" in config
            assert "crypto" in config
            # Default presets should be empty dict
            assert config["presets"] == {}
            diagnose("default config keys", sorted(config.keys()))
        track_coverage(MOD, 2)

    def test_malformed_json_returns_defaults(self):
        """Corrupt JSON file returns defaults."""
        import service.price_change.config as cfg_mod
        cfg_mod._CONFIG_CACHE = None

        fake_path = Path("/fake/exists.json")
        m = mock_open(read_data="{this is not valid json")
        # Patch Path.exists to return True, but Path.open to return bad data
        with patch.object(Path, "exists", return_value=True):
            with patch("builtins.open", m):
                config = load_config()
                assert isinstance(config, dict)
                assert "presets" in config
        track_coverage(MOD, 2)

    def test_missing_crypto_key_merged(self):
        """Config missing 'crypto' key should get defaults merged in."""
        import service.price_change.config as cfg_mod
        cfg_mod._CONFIG_CACHE = None

        minimal = json.dumps({"presets": {"test": []}})
        m = mock_open(read_data=minimal)
        with patch.object(Path, "exists", return_value=True):
            with patch("builtins.open", m):
                config = load_config()
                assert "crypto" in config
                assert "binance_base_url" in config["crypto"]
        track_coverage(MOD, 1)


class TestConfigAccessors:
    """Accessor functions for config values."""

    def setup_method(self):
        """Reset config cache before each test."""
        import service.price_change.config as cfg_mod
        cfg_mod._CONFIG_CACHE = None

    def test_get_presets(self):
        presets = get_presets()
        assert isinstance(presets, dict)
        diagnose("preset names", sorted(presets.keys())[:5])
        track_coverage(MOD, 1)

    def test_get_color_range(self):
        cr = get_color_range()
        assert isinstance(cr, dict)
        assert "min" in cr
        assert "max" in cr
        assert cr["min"] < cr["max"]
        diagnose("color range", cr)
        track_coverage(MOD, 1)

    def test_get_color_scheme(self):
        scheme = get_color_scheme()
        assert scheme in ("green_up", "red_up")
        diagnose("color scheme", scheme)
        track_coverage(MOD, 1)

    def test_crypto_config(self):
        cfg = crypto_config()
        assert isinstance(cfg, dict)
        assert "binance_base_url" in cfg
        assert "okx_base_url" in cfg
        assert "coingecko_base_url" in cfg
        diagnose("crypto config URLs", {
            "binance": cfg["binance_base_url"],
            "okx": cfg["okx_base_url"],
            "coingecko": cfg["coingecko_base_url"],
        })
        track_coverage(MOD, 1)

    def test_coingecko_ids(self):
        ids_map = coingecko_ids()
        assert isinstance(ids_map, dict)
        diagnose("coingecko id count", len(ids_map))
        # Should contain common symbols
        if ids_map:
            diagnose("sample ids", dict(list(ids_map.items())[:3]))
        track_coverage(MOD, 1)
