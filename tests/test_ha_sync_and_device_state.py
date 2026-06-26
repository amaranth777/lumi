"""tests/test_ha_sync_and_device_state.py

Tests for:
- POST /api/ha/sync_automations  (任务1)
- execute_scene with HA automation metadata  (任务1)
- device_state lumi_tool action  (任务2)
- ha_sync_automations lumi_tool action  (任务3)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import lumi.lumi_tool as tool_module
from lumi.scenes.store import Scene, SceneStore


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_store(*scenes: Scene) -> SceneStore:
    store = SceneStore.__new__(SceneStore)
    store._path = None
    store._scenes = {s.id: s for s in scenes}
    store._save = lambda: None
    return store


def _make_ha_mock(**kwargs: Any) -> MagicMock:
    mock = MagicMock()
    for k, v in kwargs.items():
        setattr(mock, k, MagicMock(return_value=v))
    return mock


def _make_app_with_ha(ha_mock, store=None):
    """Build a FastAPI test app with HA router and scenes router mounted."""
    from fastapi import FastAPI
    from lumi.ha.router import router as ha_router
    from lumi.scenes.router import router as scenes_router
    import lumi.deps as _deps

    _deps._ha_client = ha_mock
    if store is not None:
        _deps._scene_store = store

    from lumi.main import app
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(autouse=True)
def reset_deps():
    yield
    import lumi.deps as _deps
    _deps._ha_client = None
    _deps._scene_store = None
    _deps._device_graph_service = None


# ─── 任务1：POST /api/ha/sync_automations ─────────────────────────────────────

class TestSyncAutomations:
    def _automations(self):
        return [
            {
                "entity_id": "automation.morning_lights",
                "state": "on",
                "attributes": {"friendly_name": "晨间灯光"},
            },
            {
                "entity_id": "automation.night_mode",
                "state": "on",
                "attributes": {"friendly_name": "夜间模式"},
            },
        ]

    def test_sync_creates_correct_count(self):
        store = _make_store()
        ha_mock = _make_ha_mock(get_automations=self._automations())
        client = _make_app_with_ha(ha_mock, store)
        resp = client.post("/api/ha/sync_automations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["synced"] == 2
        assert data["skipped"] == 0

    def test_sync_creates_scenes_in_store(self):
        store = _make_store()
        ha_mock = _make_ha_mock(get_automations=self._automations())
        client = _make_app_with_ha(ha_mock, store)
        client.post("/api/ha/sync_automations")
        scene = store.get("ha_auto_automation.morning_lights")
        assert scene is not None
        assert scene.name == "晨间灯光"
        assert scene.description == "HA 自动化"
        assert scene.metadata["source"] == "ha_automation"
        assert scene.metadata["ha_entity_id"] == "automation.morning_lights"

    def test_sync_uses_entity_id_as_name_when_no_friendly_name(self):
        store = _make_store()
        automations = [
            {"entity_id": "automation.no_name", "state": "on", "attributes": {}},
        ]
        ha_mock = _make_ha_mock(get_automations=automations)
        client = _make_app_with_ha(ha_mock, store)
        client.post("/api/ha/sync_automations")
        scene = store.get("ha_auto_automation.no_name")
        assert scene is not None
        assert scene.name == "automation.no_name"

    def test_sync_skips_entries_without_entity_id(self):
        store = _make_store()
        automations = [
            {"entity_id": "", "state": "on", "attributes": {}},
            {"state": "on", "attributes": {}},
            {"entity_id": "automation.valid", "state": "on", "attributes": {"friendly_name": "有效"}},
        ]
        ha_mock = _make_ha_mock(get_automations=automations)
        client = _make_app_with_ha(ha_mock, store)
        resp = client.post("/api/ha/sync_automations")
        data = resp.json()
        assert data["synced"] == 1
        assert data["skipped"] == 2

    def test_sync_upserts_existing_scene(self):
        existing = Scene(
            id="ha_auto_automation.morning_lights",
            name="旧名字",
            actions=[],
            metadata={"ha_entity_id": "automation.morning_lights", "source": "ha_automation"},
        )
        store = _make_store(existing)
        ha_mock = _make_ha_mock(get_automations=self._automations())
        client = _make_app_with_ha(ha_mock, store)
        client.post("/api/ha/sync_automations")
        scene = store.get("ha_auto_automation.morning_lights")
        assert scene.name == "晨间灯光"

    def test_sync_503_when_no_ha_client(self):
        import lumi.deps as _deps
        _deps._ha_client = None
        from lumi.main import app
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post("/api/ha/sync_automations")
        assert resp.status_code == 503

    def test_synced_scene_has_empty_actions(self):
        store = _make_store()
        ha_mock = _make_ha_mock(get_automations=self._automations())
        client = _make_app_with_ha(ha_mock, store)
        client.post("/api/ha/sync_automations")
        scene = store.get("ha_auto_automation.night_mode")
        assert scene.actions == []


# ─── 任务1：execute_scene with HA automation metadata ─────────────────────────

class TestExecuteHAAutomationScene:
    def _make_ha_scene(self, entity_id: str = "automation.morning_lights") -> Scene:
        return Scene(
            id=f"ha_auto_{entity_id}",
            name="晨间灯光",
            description="HA 自动化",
            actions=[],
            metadata={"ha_entity_id": entity_id, "source": "ha_automation"},
        )

    def test_execute_calls_trigger_automation(self):
        scene = self._make_ha_scene()
        store = _make_store(scene)
        ha_mock = MagicMock()
        ha_mock.trigger_automation.return_value = True
        client = _make_app_with_ha(ha_mock, store)
        resp = client.post(f"/api/scenes/{scene.id}/execute")
        assert resp.status_code == 200
        ha_mock.trigger_automation.assert_called_once_with("automation.morning_lights")

    def test_execute_returns_batch_response_success(self):
        scene = self._make_ha_scene()
        store = _make_store(scene)
        ha_mock = MagicMock()
        ha_mock.trigger_automation.return_value = True
        client = _make_app_with_ha(ha_mock, store)
        resp = client.post(f"/api/scenes/{scene.id}/execute")
        data = resp.json()
        assert data["total"] == 1
        assert data["success"] == 1
        assert data["failed"] == 0

    def test_execute_returns_failure_when_trigger_fails(self):
        scene = self._make_ha_scene()
        store = _make_store(scene)
        ha_mock = MagicMock()
        ha_mock.trigger_automation.return_value = False
        client = _make_app_with_ha(ha_mock, store)
        resp = client.post(f"/api/scenes/{scene.id}/execute")
        data = resp.json()
        assert data["total"] == 1
        assert data["success"] == 0
        assert data["failed"] == 1

    def test_execute_ha_scene_does_not_call_device_service(self):
        """HA 场景执行时不调用设备控制命令。"""
        scene = self._make_ha_scene()
        store = _make_store(scene)
        ha_mock = MagicMock()
        ha_mock.trigger_automation.return_value = True
        client = _make_app_with_ha(ha_mock, store)
        # execute_command would fail since no device service set up — but it should NOT be called
        resp = client.post(f"/api/scenes/{scene.id}/execute")
        assert resp.status_code == 200
        ha_mock.call_service.assert_not_called()


# ─── 任务1：普通场景执行不受影响 ──────────────────────────────────────────────

class TestExecuteNormalSceneUnaffected:
    def test_normal_scene_uses_device_service(self):
        from lumi.device_graph.schema import Device, DeviceGraph
        from lumi.device_graph.service import DeviceGraphService
        from lumi.deps import get_device_graph_service
        import lumi.deps as _deps
        import time

        scene = Scene(
            id="normal_scene",
            name="普通场景",
            actions=[],
            metadata={},
        )
        store = _make_store(scene)
        ha_mock = MagicMock()
        ha_mock.trigger_automation.return_value = True

        _deps._ha_client = ha_mock
        _deps._scene_store = store

        from lumi.main import app
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post("/api/scenes/normal_scene/execute")
        assert resp.status_code == 200
        # No actions means trigger_automation was NOT called
        ha_mock.trigger_automation.assert_not_called()
        data = resp.json()
        assert data["total"] == 0

    def test_normal_scene_without_ha_metadata_not_routed_to_trigger(self):
        """metadata 无 source=ha_automation 的场景走普通路径。"""
        scene = Scene(
            id="movie_mode",
            name="电影模式",
            actions=[],
            metadata={"source": "user"},
        )
        store = _make_store(scene)
        ha_mock = MagicMock()
        _make_app_with_ha(ha_mock, store)

        import lumi.deps as _deps
        from lumi.main import app
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post("/api/scenes/movie_mode/execute")
        assert resp.status_code == 200
        ha_mock.trigger_automation.assert_not_called()


# ─── 任务2：device_state lumi_tool action ─────────────────────────────────────

class TestDeviceState:
    def test_returns_device_data_when_found(self):
        device_data = {"id": "light.living", "name": "客厅灯", "state": "on"}
        with patch("lumi.lumi_tool._lumi_get", return_value=[device_data]):
            result = tool_module.device_state(device_id="light.living")
        assert result == device_data

    def test_returns_error_when_not_found(self):
        with patch("lumi.lumi_tool._lumi_get", return_value=[]):
            result = tool_module.device_state(device_id="nonexistent_device")
        assert "error" in result
        assert "nonexistent_device" in result["error"]

    def test_returns_error_when_response_not_list(self):
        with patch("lumi.lumi_tool._lumi_get", return_value={"unexpected": "dict"}):
            result = tool_module.device_state(device_id="light.x")
        assert "error" in result

    def test_calls_correct_path(self):
        mock_get = MagicMock(return_value=[{"id": "light.x"}])
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.device_state(device_id="light.x")
        path = mock_get.call_args[0][0]
        assert "/api/device_graph/search?q=" in path

    def test_device_state_in_valid_actions(self):
        from lumi.lumi_tool import _VALID_ACTIONS
        assert "device_state" in _VALID_ACTIONS

    def test_dispatch_device_state(self):
        device_data = {"id": "light.x", "name": "灯"}
        with patch("lumi.lumi_tool._lumi_get", return_value=[device_data]):
            from lumi.lumi_tool import dispatch
            result = dispatch("device_state", {"device_id": "light.x"})
        assert result == device_data


# ─── 任务3：ha_sync_automations lumi_tool action ───────────────────────────────

class TestHaSyncAutomationsAction:
    def test_calls_correct_path(self):
        mock_post = MagicMock(return_value={"synced": 3, "skipped": 0})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            result = tool_module.ha_sync_automations()
        mock_post.assert_called_once_with("/api/ha/sync_automations", {})
        assert result["synced"] == 3

    def test_ha_sync_automations_in_valid_actions(self):
        from lumi.lumi_tool import _VALID_ACTIONS
        assert "ha_sync_automations" in _VALID_ACTIONS

    def test_dispatch_ha_sync_automations(self):
        mock_post = MagicMock(return_value={"synced": 1, "skipped": 0})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            from lumi.lumi_tool import dispatch
            result = dispatch("ha_sync_automations")
        assert result["synced"] == 1


# ─── mcp_server registration check ───────────────────────────────────────────

class TestMcpRegistration:
    def test_device_state_registered(self):
        from lumi.mcp_server import REGISTERED_TOOLS
        assert "lumi_device_state" in REGISTERED_TOOLS

    def test_ha_sync_automations_registered(self):
        from lumi.mcp_server import REGISTERED_TOOLS
        assert "lumi_ha_sync_automations" in REGISTERED_TOOLS

    def test_registered_tools_match_valid_actions(self):
        from lumi.mcp_server import REGISTERED_TOOLS
        from lumi.lumi_tool import _VALID_ACTIONS
        expected = frozenset(f"lumi_{a}" for a in _VALID_ACTIONS)
        assert REGISTERED_TOOLS == expected
