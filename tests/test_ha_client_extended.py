"""tests/test_ha_client_extended.py — HAClient 新增方法单元测试。"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from lumi.ha.client import HAClient


# ─── 辅助 ─────────────────────────────────────────────────────────────────────

class FakeResp:
    def __init__(self, data: bytes | str, status: int = 200):
        self._data = data.encode() if isinstance(data, str) else data
        self.status = status

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def _client(tmp_path: Path, token: str = "tok",
            retries: int = 1, retry_delay: float = 0.0) -> HAClient:
    tf = tmp_path / "ha_token"
    tf.write_text(token)
    return HAClient(
        base_url="http://ha.local:8123",
        token_file=str(tf),
        retries=retries,
        retry_delay=retry_delay,
    )


# ─── get_services ─────────────────────────────────────────────────────────────

class TestGetServices:
    def test_returns_domain_dict(self, tmp_path):
        client = _client(tmp_path)
        payload = [
            {"domain": "light", "services": {"turn_on": {}, "turn_off": {}}},
            {"domain": "switch", "services": {"turn_on": {}}},
        ]
        with patch("urllib.request.urlopen",
                   return_value=FakeResp(json.dumps(payload).encode())):
            result = client.get_services()
        assert "light" in result
        assert "switch" in result
        assert "turn_on" in result["light"]

    def test_returns_empty_on_failure(self, tmp_path):
        client = _client(tmp_path)
        with patch("urllib.request.urlopen", side_effect=Exception("err")):
            assert client.get_services() == {}

    def test_handles_empty_list(self, tmp_path):
        client = _client(tmp_path)
        with patch("urllib.request.urlopen",
                   return_value=FakeResp(json.dumps([]).encode())):
            assert client.get_services() == {}

    def test_url_is_api_services(self, tmp_path):
        client = _client(tmp_path)
        urls = []
        def fake_open(req, timeout=None):
            urls.append(req.full_url)
            return FakeResp(json.dumps([]).encode())
        with patch("urllib.request.urlopen", side_effect=fake_open):
            client.get_services()
        assert "/api/services" in urls[0]


# ─── get_automations ──────────────────────────────────────────────────────────

class TestGetAutomations:
    def test_filters_automation_domain(self, tmp_path):
        client = _client(tmp_path)
        states = [
            {"entity_id": "automation.morning", "state": "on", "attributes": {}},
            {"entity_id": "light.kitchen", "state": "on", "attributes": {}},
            {"entity_id": "automation.night", "state": "off", "attributes": {}},
        ]
        with patch("urllib.request.urlopen",
                   return_value=FakeResp(json.dumps(states).encode())):
            result = client.get_automations()
        assert len(result) == 2
        assert all(a["entity_id"].startswith("automation.") for a in result)

    def test_returns_empty_on_failure(self, tmp_path):
        client = _client(tmp_path)
        with patch("urllib.request.urlopen", side_effect=Exception("net")):
            assert client.get_automations() == []

    def test_empty_states(self, tmp_path):
        client = _client(tmp_path)
        with patch("urllib.request.urlopen",
                   return_value=FakeResp(json.dumps([]).encode())):
            assert client.get_automations() == []


# ─── trigger_automation ───────────────────────────────────────────────────────

class TestTriggerAutomation:
    def test_calls_automation_trigger(self, tmp_path):
        client = _client(tmp_path)
        urls = []
        def fake_open(req, timeout=None):
            urls.append(req.full_url)
            return FakeResp(b"[]", status=200)
        with patch("urllib.request.urlopen", side_effect=fake_open):
            ok = client.trigger_automation("automation.morning")
        assert ok is True
        assert "/api/services/automation/trigger" in urls[0]

    def test_sends_entity_id(self, tmp_path):
        client = _client(tmp_path)
        bodies = []
        def fake_open(req, timeout=None):
            bodies.append(json.loads(req.data))
            return FakeResp(b"[]", status=200)
        with patch("urllib.request.urlopen", side_effect=fake_open):
            client.trigger_automation("automation.morning")
        assert bodies[0]["entity_id"] == "automation.morning"


# ─── toggle_automation ────────────────────────────────────────────────────────

class TestToggleAutomation:
    def test_enable_calls_turn_on(self, tmp_path):
        client = _client(tmp_path)
        urls = []
        def fake_open(req, timeout=None):
            urls.append(req.full_url)
            return FakeResp(b"[]", status=200)
        with patch("urllib.request.urlopen", side_effect=fake_open):
            ok = client.toggle_automation("automation.x", enable=True)
        assert ok is True
        assert "/api/services/automation/turn_on" in urls[0]

    def test_disable_calls_turn_off(self, tmp_path):
        client = _client(tmp_path)
        urls = []
        def fake_open(req, timeout=None):
            urls.append(req.full_url)
            return FakeResp(b"[]", status=200)
        with patch("urllib.request.urlopen", side_effect=fake_open):
            ok = client.toggle_automation("automation.x", enable=False)
        assert ok is True
        assert "/api/services/automation/turn_off" in urls[0]

    def test_failure_returns_false(self, tmp_path):
        client = _client(tmp_path)
        with patch("urllib.request.urlopen", side_effect=Exception("err")):
            assert client.toggle_automation("automation.x", enable=True) is False


# ─── get_scripts ──────────────────────────────────────────────────────────────

class TestGetScripts:
    def test_filters_script_domain(self, tmp_path):
        client = _client(tmp_path)
        states = [
            {"entity_id": "script.welcome", "state": "off", "attributes": {}},
            {"entity_id": "light.hall", "state": "on", "attributes": {}},
        ]
        with patch("urllib.request.urlopen",
                   return_value=FakeResp(json.dumps(states).encode())):
            result = client.get_scripts()
        assert len(result) == 1
        assert result[0]["entity_id"] == "script.welcome"

    def test_returns_empty_on_failure(self, tmp_path):
        client = _client(tmp_path)
        with patch("urllib.request.urlopen", side_effect=Exception("net")):
            assert client.get_scripts() == []


# ─── run_script ───────────────────────────────────────────────────────────────

class TestRunScript:
    def test_calls_script_turn_on(self, tmp_path):
        client = _client(tmp_path)
        urls = []
        def fake_open(req, timeout=None):
            urls.append(req.full_url)
            return FakeResp(b"[]", status=200)
        with patch("urllib.request.urlopen", side_effect=fake_open):
            ok = client.run_script("script.welcome")
        assert ok is True
        assert "/api/services/script/turn_on" in urls[0]

    def test_sends_entity_id(self, tmp_path):
        client = _client(tmp_path)
        bodies = []
        def fake_open(req, timeout=None):
            bodies.append(json.loads(req.data))
            return FakeResp(b"[]", status=200)
        with patch("urllib.request.urlopen", side_effect=fake_open):
            client.run_script("script.clean")
        assert bodies[0]["entity_id"] == "script.clean"

    def test_failure_returns_false(self, tmp_path):
        client = _client(tmp_path)
        with patch("urllib.request.urlopen", side_effect=Exception("err")):
            assert client.run_script("script.x") is False


# ─── get_history ──────────────────────────────────────────────────────────────

class TestGetHistory:
    def test_returns_list(self, tmp_path):
        client = _client(tmp_path)
        fake_data = [[{"entity_id": "light.x", "state": "on", "last_changed": "2026-06-26T01:00:00"}]]
        with patch("urllib.request.urlopen",
                   return_value=FakeResp(json.dumps(fake_data).encode())):
            result = client.get_history("light.x", hours=24)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_url_contains_entity_id(self, tmp_path):
        client = _client(tmp_path)
        urls = []
        def fake_open(req, timeout=None):
            urls.append(req.full_url)
            return FakeResp(json.dumps([]).encode())
        with patch("urllib.request.urlopen", side_effect=fake_open):
            client.get_history("sensor.temp", hours=6)
        assert "sensor.temp" in urls[0]
        assert "/api/history/period/" in urls[0]

    def test_returns_empty_on_failure(self, tmp_path):
        client = _client(tmp_path)
        with patch("urllib.request.urlopen", side_effect=Exception("net")):
            assert client.get_history("light.x") == []

    def test_default_hours_24(self, tmp_path):
        client = _client(tmp_path)
        urls = []
        def fake_open(req, timeout=None):
            urls.append(req.full_url)
            return FakeResp(json.dumps([]).encode())
        with patch("urllib.request.urlopen", side_effect=fake_open):
            client.get_history("light.x")
        # URL 包含 filter_entity_id
        assert "filter_entity_id=light.x" in urls[0]


# ─── fire_event ───────────────────────────────────────────────────────────────

class TestFireEvent:
    def test_returns_true_on_success(self, tmp_path):
        client = _client(tmp_path)
        with patch("urllib.request.urlopen",
                   return_value=FakeResp(json.dumps({"message": "Event fired."}).encode())):
            ok = client.fire_event("my_event", {"key": "val"})
        assert ok is True

    def test_url_contains_event_type(self, tmp_path):
        client = _client(tmp_path)
        urls = []
        def fake_open(req, timeout=None):
            urls.append(req.full_url)
            return FakeResp(json.dumps({}).encode())
        with patch("urllib.request.urlopen", side_effect=fake_open):
            client.fire_event("custom_event")
        assert "/api/events/custom_event" in urls[0]

    def test_sends_event_data(self, tmp_path):
        client = _client(tmp_path)
        bodies = []
        def fake_open(req, timeout=None):
            bodies.append(json.loads(req.data))
            return FakeResp(json.dumps({}).encode())
        with patch("urllib.request.urlopen", side_effect=fake_open):
            client.fire_event("evt", {"foo": "bar"})
        assert bodies[0]["foo"] == "bar"

    def test_returns_false_on_failure(self, tmp_path):
        client = _client(tmp_path)
        with patch("urllib.request.urlopen", side_effect=Exception("err")):
            assert client.fire_event("evt") is False

    def test_none_event_data_sends_empty_dict(self, tmp_path):
        client = _client(tmp_path)
        bodies = []
        def fake_open(req, timeout=None):
            bodies.append(json.loads(req.data))
            return FakeResp(json.dumps({}).encode())
        with patch("urllib.request.urlopen", side_effect=fake_open):
            client.fire_event("evt", None)
        assert bodies[0] == {}


# ─── render_template ──────────────────────────────────────────────────────────

class TestRenderTemplate:
    def test_returns_string_result(self, tmp_path):
        client = _client(tmp_path)
        # HA 返回纯文本（字节）
        with patch("urllib.request.urlopen",
                   return_value=FakeResp(json.dumps("Hello World").encode())):
            result = client.render_template("Hello World")
        assert result == "Hello World"

    def test_url_is_api_template(self, tmp_path):
        client = _client(tmp_path)
        urls = []
        def fake_open(req, timeout=None):
            urls.append(req.full_url)
            return FakeResp(json.dumps("ok").encode())
        with patch("urllib.request.urlopen", side_effect=fake_open):
            client.render_template("{{ states('light.x') }}")
        assert "/api/template" in urls[0]

    def test_sends_template_in_body(self, tmp_path):
        client = _client(tmp_path)
        bodies = []
        def fake_open(req, timeout=None):
            bodies.append(json.loads(req.data))
            return FakeResp(json.dumps("on").encode())
        with patch("urllib.request.urlopen", side_effect=fake_open):
            client.render_template("{{ states('light.x') }}")
        assert "template" in bodies[0]
        assert "light.x" in bodies[0]["template"]

    def test_returns_empty_string_on_failure(self, tmp_path):
        client = _client(tmp_path)
        with patch("urllib.request.urlopen", side_effect=Exception("err")):
            assert client.render_template("{{ 1+1 }}") == ""


# ─── get_config ───────────────────────────────────────────────────────────────

class TestGetConfig:
    def test_returns_dict(self, tmp_path):
        client = _client(tmp_path)
        cfg = {"location_name": "Home", "version": "2024.1.0"}
        with patch("urllib.request.urlopen",
                   return_value=FakeResp(json.dumps(cfg).encode())):
            result = client.get_config()
        assert result["location_name"] == "Home"
        assert result["version"] == "2024.1.0"

    def test_url_is_api_config(self, tmp_path):
        client = _client(tmp_path)
        urls = []
        def fake_open(req, timeout=None):
            urls.append(req.full_url)
            return FakeResp(json.dumps({}).encode())
        with patch("urllib.request.urlopen", side_effect=fake_open):
            client.get_config()
        assert "/api/config" in urls[0]

    def test_returns_empty_dict_on_failure(self, tmp_path):
        client = _client(tmp_path)
        with patch("urllib.request.urlopen", side_effect=Exception("err")):
            assert client.get_config() == {}


# ─── _post 内部方法 ────────────────────────────────────────────────────────────

class TestPostMethod:
    def test_post_uses_post_method(self, tmp_path):
        client = _client(tmp_path)
        methods = []
        def fake_open(req, timeout=None):
            methods.append(req.get_method())
            return FakeResp(json.dumps({}).encode())
        with patch("urllib.request.urlopen", side_effect=fake_open):
            client._post("/api/template", {"template": "x"})
        assert methods[0] == "POST"

    def test_post_retries_on_failure(self, tmp_path):
        client = _client(tmp_path, retries=3, retry_delay=0.0)
        count = [0]
        def fake_open(req, timeout=None):
            count[0] += 1
            raise ConnectionError("net")
        with patch("urllib.request.urlopen", side_effect=fake_open):
            with pytest.raises(ConnectionError):
                client._post("/api/events/x", {})
        assert count[0] == 3

    def test_post_sends_auth_header(self, tmp_path):
        client = _client(tmp_path, token="secret_tok")
        headers = []
        def fake_open(req, timeout=None):
            headers.append(req.get_header("Authorization"))
            return FakeResp(json.dumps({}).encode())
        with patch("urllib.request.urlopen", side_effect=fake_open):
            client._post("/api/template", {})
        assert headers[0] == "Bearer secret_tok"
