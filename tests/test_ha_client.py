"""ha/client.py 单元测试——用 mock urllib，不依赖真实 HA。"""

from __future__ import annotations

import json
import os
import pytest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock

from lumi.ha.client import HAClient, _clear_proxy, _restore_proxy


# ─── 辅助工具 ─────────────────────────────────────────────────────────────────

class FakeHTTPResponse:
    def __init__(self, data: bytes, status: int = 200):
        self._data = data
        self.status = status

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def _make_client(tmp_path: Path, token: str = "test_token",
                 retries: int = 1, retry_delay: float = 0.0) -> HAClient:
    token_file = tmp_path / "ha_token"
    token_file.write_text(token, encoding="utf-8")
    return HAClient(
        base_url="http://192.168.5.184:8123",
        token_file=str(token_file),
        retries=retries,
        retry_delay=retry_delay,
    )


# ─── token 读取 ───────────────────────────────────────────────────────────────

class TestHAClientToken:
    def test_token_loaded_from_file(self, tmp_path):
        client = _make_client(tmp_path, "my_secret_token")
        assert client.token == "my_secret_token"

    def test_token_stripped_whitespace(self, tmp_path):
        token_file = tmp_path / "ha_token"
        token_file.write_text("  token_with_spaces  \n", encoding="utf-8")
        client = HAClient("http://localhost:8123", str(token_file))
        assert client.token == "token_with_spaces"

    def test_missing_token_file_raises(self, tmp_path):
        client = HAClient("http://localhost:8123", str(tmp_path / "nonexistent"))
        with pytest.raises(FileNotFoundError):
            _ = client.token

    def test_token_cached(self, tmp_path):
        client = _make_client(tmp_path, "cached_token")
        t1 = client.token
        t2 = client.token
        assert t1 is t2  # 同一对象（缓存）


# ─── 代理清除/恢复 ────────────────────────────────────────────────────────────

class TestProxyHandling:
    def test_clear_proxy_removes_env_vars(self):
        os.environ["HTTP_PROXY"] = "http://proxy:7897"
        os.environ["HTTPS_PROXY"] = "http://proxy:7897"
        backup = _clear_proxy()
        assert "HTTP_PROXY" not in os.environ
        assert "HTTPS_PROXY" not in os.environ
        _restore_proxy(backup)

    def test_restore_proxy_restores_env_vars(self):
        os.environ["HTTP_PROXY"] = "http://proxy:7897"
        backup = _clear_proxy()
        assert "HTTP_PROXY" not in os.environ
        _restore_proxy(backup)
        assert os.environ.get("HTTP_PROXY") == "http://proxy:7897"
        del os.environ["HTTP_PROXY"]

    def test_no_proxy_set_after_clear(self):
        backup = _clear_proxy()
        assert os.environ.get("NO_PROXY") == "*"
        _restore_proxy(backup)


# ─── get_states ───────────────────────────────────────────────────────────────

class TestGetStates:
    def test_get_states_success(self, tmp_path):
        client = _make_client(tmp_path)
        fake_states = [
            {"entity_id": "light.x", "state": "on", "attributes": {}},
            {"entity_id": "switch.y", "state": "off", "attributes": {}},
        ]
        fake_resp = FakeHTTPResponse(json.dumps(fake_states).encode())

        with patch("urllib.request.urlopen", return_value=fake_resp):
            states = client.get_states()

        assert len(states) == 2
        assert states[0]["entity_id"] == "light.x"

    def test_get_states_failure_returns_empty(self, tmp_path):
        client = _make_client(tmp_path)
        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            states = client.get_states()
        assert states == []

    def test_get_states_sends_auth_header(self, tmp_path):
        client = _make_client(tmp_path, "my_token")
        requests_made = []

        def fake_urlopen(req, timeout=None):
            requests_made.append(req)
            return FakeHTTPResponse(json.dumps([]).encode())

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.get_states()

        assert len(requests_made) == 1
        assert requests_made[0].get_header("Authorization") == "Bearer my_token"


# ─── get_state ────────────────────────────────────────────────────────────────

class TestGetState:
    def test_get_single_state(self, tmp_path):
        client = _make_client(tmp_path)
        fake_state = {"entity_id": "light.living", "state": "on", "attributes": {}}
        fake_resp = FakeHTTPResponse(json.dumps(fake_state).encode())

        with patch("urllib.request.urlopen", return_value=fake_resp):
            state = client.get_state("light.living")

        assert state["entity_id"] == "light.living"
        assert state["state"] == "on"

    def test_get_state_failure_returns_none(self, tmp_path):
        client = _make_client(tmp_path)
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = client.get_state("light.nonexistent")
        assert result is None


# ─── call_service ─────────────────────────────────────────────────────────────

class TestCallService:
    def test_call_service_success(self, tmp_path):
        client = _make_client(tmp_path)
        fake_resp = FakeHTTPResponse(b"[]", status=200)
        fake_resp.status = 200

        with patch("urllib.request.urlopen", return_value=fake_resp):
            result = client.call_service("light", "turn_on", {"entity_id": "light.x"})

        assert result is True

    def test_call_service_failure_returns_false(self, tmp_path):
        client = _make_client(tmp_path)
        with patch("urllib.request.urlopen", side_effect=Exception("HA error")):
            result = client.call_service("light", "turn_on", {"entity_id": "light.x"})
        assert result is False

    def test_call_service_sends_post(self, tmp_path):
        client = _make_client(tmp_path)
        requests_made = []

        def fake_urlopen(req, timeout=None):
            requests_made.append(req)
            return FakeHTTPResponse(b"[]", status=200)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.call_service("homeassistant", "toggle", {"entity_id": "switch.x"})

        req = requests_made[0]
        assert req.get_method() == "POST"
        body = json.loads(req.data)
        assert body["entity_id"] == "switch.x"

    def test_call_service_url_contains_domain_service(self, tmp_path):
        client = _make_client(tmp_path)
        urls_called = []

        def fake_urlopen(req, timeout=None):
            urls_called.append(req.full_url)
            return FakeHTTPResponse(b"[]", status=200)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.call_service("climate", "set_temperature", {"entity_id": "climate.ac"})

        assert "/api/services/climate/set_temperature" in urls_called[0]


# ─── Retry 逻辑 ───────────────────────────────────────────────────────────────

class TestRetryLogic:
    def test_get_states_retries_on_failure(self, tmp_path):
        """get_states 失败后重试，最终返回空列表。"""
        client = _make_client(tmp_path, retries=3, retry_delay=0.0)
        call_count = 0

        def fake_urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("timeout")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = client.get_states()

        assert result == []
        assert call_count == 3  # 重试了 3 次

    def test_get_states_succeeds_on_second_attempt(self, tmp_path):
        """第一次失败，第二次成功。"""
        client = _make_client(tmp_path, retries=3, retry_delay=0.0)
        attempt = 0

        def fake_urlopen(req, timeout=None):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise ConnectionError("first fail")
            return FakeHTTPResponse(
                json.dumps([{"entity_id": "light.x", "state": "on"}]).encode()
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = client.get_states()

        assert len(result) == 1
        assert attempt == 2

    def test_call_service_retries_on_failure(self, tmp_path):
        """call_service 失败后重试，最终返回 False。"""
        client = _make_client(tmp_path, retries=2, retry_delay=0.0)
        call_count = 0

        def fake_urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("network error")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = client.call_service("light", "turn_on", {"entity_id": "light.x"})

        assert result is False
        assert call_count == 2

    def test_call_service_succeeds_on_retry(self, tmp_path):
        """call_service 第一次失败，第二次成功返回 True。"""
        client = _make_client(tmp_path, retries=3, retry_delay=0.0)
        attempt = 0

        def fake_urlopen(req, timeout=None):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise ConnectionError("blip")
            return FakeHTTPResponse(b"[]", status=200)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = client.call_service("light", "turn_on", {"entity_id": "light.x"})

        assert result is True
        assert attempt == 2
