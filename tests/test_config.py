"""config.py 单元测试。"""

from __future__ import annotations

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch

from lumi.config import (
    LumiConfig, HAConfig, MilocoConfig, ServerConfig,
    get_config, _load_config_file,
)


# ─── 默认值 ───────────────────────────────────────────────────────────────────

class TestDefaults:
    def test_default_ha_config(self):
        cfg = HAConfig()
        assert cfg.enabled is False
        assert cfg.base_url == "http://192.168.5.184:8123"
        assert cfg.token_file == "~/.hermes/ha_token"

    def test_default_server_config(self):
        cfg = ServerConfig()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8810
        assert cfg.token == ""

    def test_default_miloco_config(self):
        cfg = MilocoConfig()
        assert cfg.enabled is False
        assert cfg.base_url == "http://127.0.0.1:1810"

    def test_lumi_config_defaults(self):
        cfg = LumiConfig()
        assert isinstance(cfg.ha, HAConfig)
        assert isinstance(cfg.server, ServerConfig)
        assert isinstance(cfg.miloco, MilocoConfig)
        assert cfg.device_aliases == []


# ─── 从文件加载 ───────────────────────────────────────────────────────────────

class TestLoadConfigFile:
    def test_load_nonexistent_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = _load_config_file()
        assert result == {}

    def test_load_valid_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config_dir = tmp_path / ".lumi"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(
            json.dumps({"server": {"port": 9999}}), encoding="utf-8"
        )
        result = _load_config_file()
        assert result["server"]["port"] == 9999

    def test_load_invalid_json_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config_dir = tmp_path / ".lumi"
        config_dir.mkdir()
        (config_dir / "config.json").write_text("not valid json", encoding="utf-8")
        result = _load_config_file()
        assert result == {}


# ─── get_config 环境变量覆盖 ──────────────────────────────────────────────────

class TestGetConfigEnvOverrides:
    def setup_method(self):
        """每个测试前清掉 singleton 缓存。"""
        import lumi.config as cfg_module
        cfg_module._config = None

    def teardown_method(self):
        import lumi.config as cfg_module
        cfg_module._config = None

    def test_env_ha_base_url(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("LUMI_HA_BASE_URL", "http://10.0.0.1:8123")
        cfg = get_config()
        assert cfg.ha.base_url == "http://10.0.0.1:8123"
        monkeypatch.delenv("LUMI_HA_BASE_URL", raising=False)

    def test_env_ha_token_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("LUMI_HA_TOKEN_FILE", "/tmp/my_token")
        cfg = get_config()
        assert cfg.ha.token_file == "/tmp/my_token"
        monkeypatch.delenv("LUMI_HA_TOKEN_FILE", raising=False)

    def test_env_server_token(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("LUMI_SERVER_TOKEN", "secret123")
        cfg = get_config()
        assert cfg.server.token == "secret123"
        monkeypatch.delenv("LUMI_SERVER_TOKEN", raising=False)

    def test_get_config_singleton(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2

    def test_file_overrides_defaults(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config_dir = tmp_path / ".lumi"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(json.dumps({
            "ha": {"enabled": True, "base_url": "http://192.168.1.100:8123"},
            "server": {"port": 9090},
        }), encoding="utf-8")
        cfg = get_config()
        assert cfg.ha.enabled is True
        assert cfg.ha.base_url == "http://192.168.1.100:8123"
        assert cfg.server.port == 9090

    def test_device_aliases_loaded(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config_dir = tmp_path / ".lumi"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(json.dumps({
            "device_aliases": [
                {"entity_id": "fan.purifier", "name": "净化器", "room": "客厅"}
            ]
        }), encoding="utf-8")
        cfg = get_config()
        assert len(cfg.device_aliases) == 1
        assert cfg.device_aliases[0]["name"] == "净化器"

    def test_env_server_port(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("LUMI_SERVER_PORT", "9999")
        cfg = get_config()
        assert cfg.server.port == 9999

    def test_env_server_port_invalid_ignored(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("LUMI_SERVER_PORT", "notanint")
        cfg = get_config()
        assert cfg.server.port == 8810  # 默认值不变

    def test_env_server_host(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("LUMI_SERVER_HOST", "0.0.0.0")
        cfg = get_config()
        assert cfg.server.host == "0.0.0.0"

    def test_env_miloco_base_url(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("LUMI_MILOCO_BASE_URL", "http://10.0.0.2:1810")
        cfg = get_config()
        assert cfg.miloco.base_url == "http://10.0.0.2:1810"

    def test_env_miloco_token(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("LUMI_MILOCO_TOKEN", "mytoken123")
        cfg = get_config()
        assert cfg.miloco.token == "mytoken123"
