"""miloco/client.py 单元测试——mock urllib，不依赖真实 Miloco 服务。"""

from __future__ import annotations

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from lumi.miloco.client import MilocoClient


# ─── 辅助工具 ─────────────────────────────────────────────────────────────────

class FakeHTTPResponse:
    def __init__(self, data: dict | list, status: int = 200):
        self._data = json.dumps(data).encode()
        self.status = status

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def _make_client(token: str = "test_token") -> MilocoClient:
    return MilocoClient(base_url="http://127.0.0.1:1810", token=token)


def _make_client_from_config(tmp_path: Path, token: str = "test_token") -> MilocoClient:
    config_dir = tmp_path / ".miloco"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({"token": token, "base_url": "http://127.0.0.1:1810"}),
        encoding="utf-8"
    )
    return MilocoClient.from_config(str(config_dir / "config.json"))


# ─── from_config ──────────────────────────────────────────────────────────────

class TestFromConfig:
    def test_loads_token_from_file(self, tmp_path):
        client = _make_client_from_config(tmp_path, "my_miloco_token")
        assert client._token == "my_miloco_token"

    def test_loads_base_url_from_file(self, tmp_path):
        config_dir = tmp_path / ".miloco"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(
            json.dumps({"token": "t", "base_url": "http://192.168.1.5:1810"}),
            encoding="utf-8"
        )
        client = MilocoClient.from_config(str(config_dir / "config.json"))
        assert client.base_url == "http://192.168.1.5:1810"

    def test_missing_config_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            MilocoClient.from_config("/nonexistent/path/config.json")


# ─── get_device_list ──────────────────────────────────────────────────────────

class TestGetDeviceList:
    def test_success(self):
        client = _make_client()
        fake_devices = [
            {"did": "12345", "name": "灯", "category": "light", "online": True},
        ]
        fake_resp = FakeHTTPResponse({"code": 0, "data": fake_devices})

        with patch("urllib.request.urlopen", return_value=fake_resp):
            devices = client.get_device_list()

        assert len(devices) == 1
        assert devices[0]["did"] == "12345"

    def test_failure_returns_empty(self):
        client = _make_client()
        with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
            devices = client.get_device_list()
        assert devices == []

    def test_sends_auth_header(self):
        client = _make_client("miloco_token")
        requests_made = []

        def fake_urlopen(req, timeout=None):
            requests_made.append(req)
            return FakeHTTPResponse({"code": 0, "data": []})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.get_device_list()

        assert requests_made[0].get_header("Authorization") == "Bearer miloco_token"


# ─── set_property ─────────────────────────────────────────────────────────────

class TestSetProperty:
    def test_set_property_success(self):
        client = _make_client()
        fake_resp = FakeHTTPResponse({"code": 0, "data": {}})

        with patch("urllib.request.urlopen", return_value=fake_resp):
            result = client.set_property("123456", 2, 1, True)

        assert result is True

    def test_set_property_failure(self):
        client = _make_client()
        fake_resp = FakeHTTPResponse({"code": -1, "message": "failed"})

        with patch("urllib.request.urlopen", return_value=fake_resp):
            result = client.set_property("123456", 2, 1, True)

        assert result is False

    def test_set_property_exception_returns_false(self):
        client = _make_client()
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = client.set_property("123456", 2, 1, False)
        assert result is False

    def test_set_property_sends_correct_iid(self):
        client = _make_client()
        requests_made = []

        def fake_urlopen(req, timeout=None):
            requests_made.append(req)
            return FakeHTTPResponse({"code": 0})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.set_property("abc", 3, 5, 80)

        body = json.loads(requests_made[0].data)
        assert body["iid"] == "prop.3.5"
        assert body["value"] == 80
        assert body["type"] == "set_property"


# ─── call_action ─────────────────────────────────────────────────────────────

class TestCallAction:
    def test_call_action_success(self):
        client = _make_client()
        fake_resp = FakeHTTPResponse({"code": 0})

        with patch("urllib.request.urlopen", return_value=fake_resp):
            result = client.call_action("abc", 2, 1, [])

        assert result is True

    def test_call_action_failure(self):
        client = _make_client()
        fake_resp = FakeHTTPResponse({"code": -1})

        with patch("urllib.request.urlopen", return_value=fake_resp):
            result = client.call_action("abc", 2, 3, [])

        assert result is False

    def test_call_action_sends_correct_body(self):
        client = _make_client()
        requests_made = []

        def fake_urlopen(req, timeout=None):
            requests_made.append(req)
            return FakeHTTPResponse({"code": 0})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.call_action("did123", 2, 4, ["param1"])

        body = json.loads(requests_made[0].data)
        assert body["type"] == "call_action"
        assert body["iid"] == "action.2.4"
        assert body["params"] == ["param1"]


# ─── is_available ─────────────────────────────────────────────────────────────

class TestIsAvailable:
    def test_available_when_health_ok(self):
        client = _make_client()
        with patch("urllib.request.urlopen", return_value=FakeHTTPResponse({"status": "ok"})):
            assert client.is_available() is True

    def test_unavailable_when_connection_fails(self):
        client = _make_client()
        with patch("urllib.request.urlopen", side_effect=Exception("refused")):
            assert client.is_available() is False
