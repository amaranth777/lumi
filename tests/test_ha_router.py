"""lumi/ha/router.py 单元测试（TestClient + mock HA client）。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ─── 辅助：构建带 mock HA client 的 TestClient ────────────────────────────────


def _make_client(ha_mock: MagicMock | None = None) -> TestClient:
    """创建测试用 FastAPI TestClient，注入 mock HA client。"""
    # 重置 deps 单例，确保每个测试隔离
    import lumi.deps as _deps
    import lumi.ha.router as _router

    _deps._ha_client = ha_mock  # type: ignore[assignment]

    from lumi.main import app
    return TestClient(app, raise_server_exceptions=True)


def _make_ha_mock(**kwargs: Any) -> MagicMock:
    mock = MagicMock()
    for k, v in kwargs.items():
        setattr(mock, k, MagicMock(return_value=v))
    return mock


@pytest.fixture(autouse=True)
def reset_deps():
    """每个测试后重置 deps 单例。"""
    yield
    import lumi.deps as _deps
    _deps._ha_client = None
    _deps._device_graph_service = None


# ─── 503 when ha_client is None ───────────────────────────────────────────────


class TestNoHAClient:
    def test_get_services_503(self):
        client = _make_client(ha_mock=None)
        resp = client.get("/api/ha/services")
        assert resp.status_code == 503

    def test_get_automations_503(self):
        client = _make_client(ha_mock=None)
        resp = client.get("/api/ha/automations")
        assert resp.status_code == 503

    def test_get_scripts_503(self):
        client = _make_client(ha_mock=None)
        resp = client.get("/api/ha/scripts")
        assert resp.status_code == 503

    def test_get_history_503(self):
        client = _make_client(ha_mock=None)
        resp = client.get("/api/ha/history/light.test")
        assert resp.status_code == 503

    def test_get_config_503(self):
        client = _make_client(ha_mock=None)
        resp = client.get("/api/ha/config")
        assert resp.status_code == 503

    def test_trigger_automation_503(self):
        client = _make_client(ha_mock=None)
        resp = client.post("/api/ha/automations/automation.test/trigger")
        assert resp.status_code == 503

    def test_toggle_automation_503(self):
        client = _make_client(ha_mock=None)
        resp = client.post("/api/ha/automations/automation.test/toggle", json={"enable": True})
        assert resp.status_code == 503

    def test_run_script_503(self):
        client = _make_client(ha_mock=None)
        resp = client.post("/api/ha/scripts/script.test/run")
        assert resp.status_code == 503

    def test_fire_event_503(self):
        client = _make_client(ha_mock=None)
        resp = client.post("/api/ha/events/my_event", json={"event_data": {}})
        assert resp.status_code == 503

    def test_render_template_503(self):
        client = _make_client(ha_mock=None)
        resp = client.post("/api/ha/template", json={"template": "{{ states('light.x') }}"})
        assert resp.status_code == 503


# ─── GET /api/ha/services ─────────────────────────────────────────────────────


class TestGetServices:
    def test_returns_services_dict(self):
        ha = _make_ha_mock(get_services={"light": {"turn_on": {}, "turn_off": {}}})
        client = _make_client(ha_mock=ha)
        resp = client.get("/api/ha/services")
        assert resp.status_code == 200
        data = resp.json()
        assert "light" in data

    def test_empty_services(self):
        ha = _make_ha_mock(get_services={})
        client = _make_client(ha_mock=ha)
        resp = client.get("/api/ha/services")
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_calls_ha_get_services(self):
        ha = _make_ha_mock(get_services={})
        client = _make_client(ha_mock=ha)
        client.get("/api/ha/services")
        ha.get_services.assert_called_once()


# ─── GET /api/ha/automations ──────────────────────────────────────────────────


class TestGetAutomations:
    def test_returns_list(self):
        automations = [
            {"entity_id": "automation.wake_up", "state": "on", "attributes": {}},
        ]
        ha = _make_ha_mock(get_automations=automations)
        client = _make_client(ha_mock=ha)
        resp = client.get("/api/ha/automations")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["entity_id"] == "automation.wake_up"

    def test_empty_automations(self):
        ha = _make_ha_mock(get_automations=[])
        client = _make_client(ha_mock=ha)
        resp = client.get("/api/ha/automations")
        assert resp.status_code == 200
        assert resp.json() == []


# ─── POST /api/ha/automations/{entity_id}/trigger ─────────────────────────────


class TestTriggerAutomation:
    def test_trigger_success(self):
        ha = _make_ha_mock(trigger_automation=True)
        client = _make_client(ha_mock=ha)
        resp = client.post("/api/ha/automations/automation.wake_up/trigger")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["entity_id"] == "automation.wake_up"

    def test_trigger_failure(self):
        ha = _make_ha_mock(trigger_automation=False)
        client = _make_client(ha_mock=ha)
        resp = client.post("/api/ha/automations/automation.wake_up/trigger")
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_trigger_calls_client(self):
        ha = _make_ha_mock(trigger_automation=True)
        client = _make_client(ha_mock=ha)
        client.post("/api/ha/automations/automation.test/trigger")
        ha.trigger_automation.assert_called_once_with("automation.test")


# ─── POST /api/ha/automations/{entity_id}/toggle ──────────────────────────────


class TestToggleAutomation:
    def test_enable_true(self):
        ha = _make_ha_mock(toggle_automation=True)
        client = _make_client(ha_mock=ha)
        resp = client.post(
            "/api/ha/automations/automation.test/toggle",
            json={"enable": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["enable"] is True

    def test_enable_false(self):
        ha = _make_ha_mock(toggle_automation=True)
        client = _make_client(ha_mock=ha)
        resp = client.post(
            "/api/ha/automations/automation.test/toggle",
            json={"enable": False},
        )
        assert resp.status_code == 200
        assert resp.json()["enable"] is False

    def test_toggle_calls_client(self):
        ha = _make_ha_mock(toggle_automation=True)
        client = _make_client(ha_mock=ha)
        client.post("/api/ha/automations/automation.abc/toggle", json={"enable": True})
        ha.toggle_automation.assert_called_once_with("automation.abc", True)

    def test_missing_enable_field_422(self):
        ha = _make_ha_mock(toggle_automation=True)
        client = _make_client(ha_mock=ha)
        resp = client.post("/api/ha/automations/automation.test/toggle", json={})
        assert resp.status_code == 422


# ─── GET /api/ha/scripts ──────────────────────────────────────────────────────


class TestGetScripts:
    def test_returns_list(self):
        scripts = [{"entity_id": "script.morning_lights", "state": "off", "attributes": {}}]
        ha = _make_ha_mock(get_scripts=scripts)
        client = _make_client(ha_mock=ha)
        resp = client.get("/api/ha/scripts")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["entity_id"] == "script.morning_lights"

    def test_empty_scripts(self):
        ha = _make_ha_mock(get_scripts=[])
        client = _make_client(ha_mock=ha)
        assert client.get("/api/ha/scripts").json() == []


# ─── POST /api/ha/scripts/{entity_id}/run ─────────────────────────────────────


class TestRunScript:
    def test_run_success(self):
        ha = _make_ha_mock(run_script=True)
        client = _make_client(ha_mock=ha)
        resp = client.post("/api/ha/scripts/script.morning_lights/run")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_run_calls_client(self):
        ha = _make_ha_mock(run_script=True)
        client = _make_client(ha_mock=ha)
        client.post("/api/ha/scripts/script.test_script/run")
        ha.run_script.assert_called_once_with("script.test_script")


# ─── GET /api/ha/history/{entity_id} ─────────────────────────────────────────


class TestGetHistory:
    def test_default_hours(self):
        history_data = [[{"entity_id": "light.x", "state": "on"}]]
        ha = _make_ha_mock(get_history=history_data)
        client = _make_client(ha_mock=ha)
        resp = client.get("/api/ha/history/light.x")
        assert resp.status_code == 200
        ha.get_history.assert_called_once_with("light.x", hours=24)

    def test_custom_hours(self):
        ha = _make_ha_mock(get_history=[])
        client = _make_client(ha_mock=ha)
        client.get("/api/ha/history/light.x?hours=48")
        ha.get_history.assert_called_once_with("light.x", hours=48)

    def test_invalid_hours_422(self):
        ha = _make_ha_mock(get_history=[])
        client = _make_client(ha_mock=ha)
        resp = client.get("/api/ha/history/light.x?hours=0")
        assert resp.status_code == 422

    def test_returns_list(self):
        ha = _make_ha_mock(get_history=[[{"entity_id": "light.x", "state": "on"}]])
        client = _make_client(ha_mock=ha)
        resp = client.get("/api/ha/history/light.x")
        assert isinstance(resp.json(), list)


# ─── POST /api/ha/events/{event_type} ────────────────────────────────────────


class TestFireEvent:
    def test_fire_event_success(self):
        ha = _make_ha_mock(fire_event=True)
        client = _make_client(ha_mock=ha)
        resp = client.post("/api/ha/events/lumi_test_event", json={"event_data": {"key": "val"}})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["event_type"] == "lumi_test_event"

    def test_fire_event_calls_client(self):
        ha = _make_ha_mock(fire_event=True)
        client = _make_client(ha_mock=ha)
        client.post("/api/ha/events/my_event", json={"event_data": {"foo": "bar"}})
        ha.fire_event.assert_called_once_with("my_event", {"foo": "bar"})

    def test_fire_event_empty_data(self):
        ha = _make_ha_mock(fire_event=True)
        client = _make_client(ha_mock=ha)
        resp = client.post("/api/ha/events/my_event", json={"event_data": {}})
        assert resp.status_code == 200


# ─── POST /api/ha/template ────────────────────────────────────────────────────


class TestRenderTemplate:
    def test_render_success(self):
        ha = _make_ha_mock(render_template="on")
        client = _make_client(ha_mock=ha)
        resp = client.post("/api/ha/template", json={"template": "{{ states('light.x') }}"})
        assert resp.status_code == 200
        assert resp.json()["result"] == "on"

    def test_render_calls_client(self):
        ha = _make_ha_mock(render_template="42")
        client = _make_client(ha_mock=ha)
        client.post("/api/ha/template", json={"template": "{{ 6 * 7 }}"})
        ha.render_template.assert_called_once_with("{{ 6 * 7 }}")

    def test_missing_template_422(self):
        ha = _make_ha_mock(render_template="")
        client = _make_client(ha_mock=ha)
        resp = client.post("/api/ha/template", json={})
        assert resp.status_code == 422


# ─── GET /api/ha/config ───────────────────────────────────────────────────────


class TestGetConfig:
    def test_returns_config_dict(self):
        ha_config = {"location_name": "My Home", "version": "2024.1.0"}
        ha = _make_ha_mock(get_config=ha_config)
        client = _make_client(ha_mock=ha)
        resp = client.get("/api/ha/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["location_name"] == "My Home"

    def test_empty_config(self):
        ha = _make_ha_mock(get_config={})
        client = _make_client(ha_mock=ha)
        resp = client.get("/api/ha/config")
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_calls_ha_get_config(self):
        ha = _make_ha_mock(get_config={})
        client = _make_client(ha_mock=ha)
        client.get("/api/ha/config")
        ha.get_config.assert_called_once()
