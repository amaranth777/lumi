"""tests/test_lumi_tool.py — lumi_tool action 单元测试。

所有测试 mock _lumi_get / _lumi_post，不真实调用 Lumi HTTP API。
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

import lumi.lumi_tool as tool_module
from lumi.lumi_tool import dispatch, _VALID_ACTIONS


# ─── dispatch 基础测试 ────────────────────────────────────────────────────────

class TestDispatch:
    def test_unknown_action_raises(self):
        with pytest.raises(ValueError, match="未知 action"):
            dispatch("nonexistent_action")

    def test_valid_action_dispatches(self):
        with patch("lumi.lumi_tool._lumi_get", return_value={"status": "ok"}):
            result = dispatch("health")
        assert result["status"] == "ok"

    def test_all_valid_actions_exist(self):
        for action in _VALID_ACTIONS:
            assert hasattr(tool_module, action), f"Missing function: {action}"
            assert callable(getattr(tool_module, action))

    def test_dispatch_passes_params(self):
        mock_get = MagicMock(return_value=[{"id": "light.x"}])
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            dispatch("search", {"query": "客厅"})
        mock_get.assert_called_once()
        path = mock_get.call_args[0][0]
        assert "/api/device_graph/search?q=" in path


# ─── 基础 action 测试 ─────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_status(self):
        with patch("lumi.lumi_tool._lumi_get", return_value={"status": "ok", "ha": "ok"}):
            result = tool_module.health()
        assert result["status"] == "ok"

    def test_calls_correct_path(self):
        mock_get = MagicMock(return_value={})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.health()
        mock_get.assert_called_once_with("/health")


class TestStatus:
    def test_returns_dict(self):
        with patch("lumi.lumi_tool._lumi_get", return_value={"devices": {"total": 10}}):
            result = tool_module.status()
        assert result["devices"]["total"] == 10

    def test_calls_correct_path(self):
        mock_get = MagicMock(return_value={})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.status()
        mock_get.assert_called_once_with("/api/status")


class TestSummary:
    def test_returns_summary(self):
        with patch("lumi.lumi_tool._lumi_get", return_value={"total_devices": 5}):
            result = tool_module.summary()
        assert result["total_devices"] == 5

    def test_calls_correct_path(self):
        mock_get = MagicMock(return_value={})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.summary()
        mock_get.assert_called_once_with("/api/device_graph/summary")


class TestTypes:
    def test_returns_types(self):
        with patch("lumi.lumi_tool._lumi_get", return_value={"light": 3}):
            result = tool_module.types()
        assert result["light"] == 3


class TestSearch:
    def test_returns_list(self):
        with patch("lumi.lumi_tool._lumi_get", return_value=[{"id": "light.x"}]):
            result = tool_module.search("客厅")
        assert isinstance(result, list)
        assert result[0]["id"] == "light.x"

    def test_encodes_query(self):
        mock_get = MagicMock(return_value=[])
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.search("猫砂盆")
        path = mock_get.call_args[0][0]
        assert "/api/device_graph/search?q=" in path


class TestRoom:
    def test_returns_devices(self):
        with patch("lumi.lumi_tool._lumi_get", return_value=[{"id": "light.living"}]):
            result = tool_module.room("客厅")
        assert len(result) == 1

    def test_encodes_room_name(self):
        mock_get = MagicMock(return_value=[])
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.room("客厅")
        path = mock_get.call_args[0][0]
        assert "/api/device_graph/rooms/" in path


class TestControl:
    def test_returns_response(self):
        mock_post = MagicMock(return_value={"success": True})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            result = tool_module.control("light.x", "turn_on")
        assert result["success"] is True

    def test_passes_command_and_params(self):
        mock_post = MagicMock(return_value={})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            tool_module.control("light.x", "set_brightness", {"brightness": 80})
        path, body = mock_post.call_args[0]
        assert "light.x" in path
        assert body["command"] == "set_brightness"
        assert body["params"]["brightness"] == 80

    def test_default_empty_params(self):
        mock_post = MagicMock(return_value={})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            tool_module.control("light.x", "turn_on")
        _, body = mock_post.call_args[0]
        assert body["params"] == {}


class TestBatchControl:
    def test_passes_commands(self):
        mock_post = MagicMock(return_value={"results": []})
        cmds = [{"device_id": "light.x", "command": "turn_on", "params": {}}]
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            tool_module.batch_control(cmds)
        path, body = mock_post.call_args[0]
        assert path == "/api/device_graph/batch/command"
        assert body["commands"] == cmds


class TestScenes:
    def test_returns_list(self):
        with patch("lumi.lumi_tool._lumi_get", return_value=[{"id": "s1"}]):
            result = tool_module.scenes()
        assert result[0]["id"] == "s1"

    def test_calls_correct_path(self):
        mock_get = MagicMock(return_value=[])
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.scenes()
        mock_get.assert_called_once_with("/api/scenes")


class TestRunScene:
    def test_calls_execute_endpoint(self):
        mock_post = MagicMock(return_value={"success": True})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            tool_module.run_scene("scene_abc")
        path, _ = mock_post.call_args[0]
        assert path == "/api/scenes/scene_abc/execute"


class TestPerceptionTypes:
    def test_returns_list(self):
        with patch("lumi.lumi_tool._lumi_get", return_value=["pet_detected", "litter_box_full"]):
            result = tool_module.perception_types()
        assert "pet_detected" in result


class TestPerceptionTest:
    def test_calls_dry_run_endpoint(self):
        mock_post = MagicMock(return_value={"analyzed": True})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            tool_module.perception_test("pet_detected")
        path, body = mock_post.call_args[0]
        assert path == "/api/perception/webhook/test"
        assert body["event_type"] == "pet_detected"

    def test_default_subject_and_room(self):
        mock_post = MagicMock(return_value={})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            tool_module.perception_test("pet_detected")
        _, body = mock_post.call_args[0]
        assert body["subjects"][0]["type"] == "cat"
        assert body["room"] == "客厅"


class TestPerceptionSend:
    def test_calls_webhook_endpoint(self):
        mock_post = MagicMock(return_value={"status": "ok"})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            result = tool_module.perception_send("litter_box_full")
        assert result["sent"] is True
        path, _ = mock_post.call_args[0]
        assert path == "/api/perception/webhook"

    def test_returns_sent_false_on_error(self):
        with patch("lumi.lumi_tool._lumi_post", side_effect=Exception("conn error")):
            result = tool_module.perception_send("litter_box_full")
        assert result["sent"] is False
        assert "error" in result


# ─── HA action 测试 ───────────────────────────────────────────────────────────

class TestHaServices:
    def test_calls_correct_path(self):
        mock_get = MagicMock(return_value={"light": {}})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.ha_services()
        mock_get.assert_called_once_with("/api/ha/services")

    def test_returns_dict(self):
        with patch("lumi.lumi_tool._lumi_get", return_value={"light": {}, "switch": {}}):
            result = tool_module.ha_services()
        assert isinstance(result, dict)


class TestHaAutomations:
    def test_calls_correct_path(self):
        mock_get = MagicMock(return_value=[])
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.ha_automations()
        mock_get.assert_called_once_with("/api/ha/automations")

    def test_returns_list(self):
        fake = [{"entity_id": "automation.x", "name": "X", "state": "on"}]
        with patch("lumi.lumi_tool._lumi_get", return_value=fake):
            result = tool_module.ha_automations()
        assert result[0]["entity_id"] == "automation.x"


class TestHaToggleAutomation:
    def test_enable(self):
        mock_post = MagicMock(return_value={"success": True})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            tool_module.ha_toggle_automation("automation.x", True)
        path, body = mock_post.call_args[0]
        assert "automation.x" in path
        assert body["enable"] is True

    def test_disable(self):
        mock_post = MagicMock(return_value={"success": True})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            tool_module.ha_toggle_automation("automation.x", False)
        _, body = mock_post.call_args[0]
        assert body["enable"] is False


class TestHaRunScript:
    def test_calls_run_endpoint(self):
        mock_post = MagicMock(return_value={"success": True})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            tool_module.ha_run_script("script.welcome")
        path, _ = mock_post.call_args[0]
        assert "script.welcome" in path
        assert "/run" in path


class TestHaHistory:
    def test_calls_history_endpoint(self):
        mock_get = MagicMock(return_value={"states": []})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.ha_history("light.x")
        path = mock_get.call_args[0][0]
        assert "light.x" in path
        assert "hours=24" in path

    def test_custom_hours(self):
        mock_get = MagicMock(return_value={"states": []})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.ha_history("light.x", hours=48)
        path = mock_get.call_args[0][0]
        assert "hours=48" in path


class TestHaFireEvent:
    def test_calls_event_endpoint(self):
        mock_post = MagicMock(return_value={"success": True})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            tool_module.ha_fire_event("my_event")
        path, _ = mock_post.call_args[0]
        assert "my_event" in path

    def test_default_empty_event_data(self):
        mock_post = MagicMock(return_value={})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            tool_module.ha_fire_event("evt")
        _, body = mock_post.call_args[0]
        assert body["event_data"] == {}


class TestHaRenderTemplate:
    def test_calls_template_endpoint(self):
        mock_post = MagicMock(return_value={"result": "on"})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            result = tool_module.ha_render_template("{{ states('light.x') }}")
        path, body = mock_post.call_args[0]
        assert path == "/api/ha/template"
        assert "light.x" in body["template"]


class TestHaConfig:
    def test_calls_config_endpoint(self):
        mock_get = MagicMock(return_value={"version": "2024.1"})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            result = tool_module.ha_config()
        mock_get.assert_called_once_with("/api/ha/config")
        assert result["version"] == "2024.1"


# ─── 主动巡检 action 测试 ─────────────────────────────────────────────────────

class TestProactiveStatus:
    def test_calls_status_endpoint(self):
        mock_get = MagicMock(return_value={"enabled": True, "running": True})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            result = tool_module.proactive_status()
        mock_get.assert_called_once_with("/api/proactive/status")
        assert result["enabled"] is True

    def test_returns_disabled_when_not_running(self):
        with patch("lumi.lumi_tool._lumi_get", return_value={"enabled": False}):
            result = tool_module.proactive_status()
        assert result["enabled"] is False


class TestProactiveAlerts:
    def test_calls_check_endpoint(self):
        mock_post = MagicMock(return_value={"count": 2, "alerts": []})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            result = tool_module.proactive_alerts()
        mock_post.assert_called_once_with("/api/proactive/check", {})
        assert result["count"] == 2

    def test_returns_empty_on_no_alerts(self):
        with patch("lumi.lumi_tool._lumi_post", return_value={"count": 0, "alerts": []}):
            result = tool_module.proactive_alerts()
        assert result["count"] == 0


# ─── device_graph / device_refresh action 测试 ───────────────────────────────

class TestDeviceGraph:
    def test_calls_device_graph_endpoint(self):
        mock_get = MagicMock(return_value={"devices": [], "rooms": {}})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.device_graph()
        mock_get.assert_called_once_with("/api/device_graph")

    def test_returns_all_devices_when_no_filter(self):
        devices = [
            {"id": "light.a", "room": "客厅", "type": "light"},
            {"id": "switch.b", "room": "卧室", "type": "switch"},
        ]
        with patch("lumi.lumi_tool._lumi_get", return_value={"devices": devices}):
            result = tool_module.device_graph()
        assert result["total"] == 2
        assert len(result["devices"]) == 2

    def test_filters_by_room(self):
        devices = [
            {"id": "light.a", "room": "客厅", "type": "light"},
            {"id": "switch.b", "room": "卧室", "type": "switch"},
        ]
        with patch("lumi.lumi_tool._lumi_get", return_value={"devices": devices}):
            result = tool_module.device_graph(rooms=["客厅"])
        assert result["total"] == 1
        assert result["devices"][0]["id"] == "light.a"

    def test_filters_by_device_type(self):
        devices = [
            {"id": "light.a", "room": "客厅", "type": "light"},
            {"id": "light.b", "room": "卧室", "type": "light"},
            {"id": "switch.c", "room": "客厅", "type": "switch"},
        ]
        with patch("lumi.lumi_tool._lumi_get", return_value={"devices": devices}):
            result = tool_module.device_graph(device_types=["light"])
        assert result["total"] == 2

    def test_filters_by_room_and_type(self):
        devices = [
            {"id": "light.a", "room": "客厅", "type": "light"},
            {"id": "light.b", "room": "卧室", "type": "light"},
            {"id": "switch.c", "room": "客厅", "type": "switch"},
        ]
        with patch("lumi.lumi_tool._lumi_get", return_value={"devices": devices}):
            result = tool_module.device_graph(rooms=["客厅"], device_types=["light"])
        assert result["total"] == 1
        assert result["devices"][0]["id"] == "light.a"

    def test_handles_non_dict_response(self):
        with patch("lumi.lumi_tool._lumi_get", return_value=None):
            result = tool_module.device_graph()
        assert result["total"] == 0
        assert result["devices"] == []

    def test_in_valid_actions(self):
        assert "device_graph" in _VALID_ACTIONS


class TestDeviceRefresh:
    def test_calls_force_refresh_endpoint(self):
        mock_get = MagicMock(return_value={"devices": [], "rooms": {}})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.device_refresh()
        mock_get.assert_called_once_with("/api/device_graph?force_refresh=true")

    def test_returns_graph_response(self):
        fake = {"devices": [{"id": "light.x"}], "rooms": {}}
        with patch("lumi.lumi_tool._lumi_get", return_value=fake):
            result = tool_module.device_refresh()
        assert "devices" in result

    def test_in_valid_actions(self):
        assert "device_refresh" in _VALID_ACTIONS


# ─── ha_device_summary 测试 ───────────────────────────────────────────────────

class TestHaDeviceSummary:
    def test_calls_correct_endpoint(self):
        mock_get = MagicMock(return_value={"entity_id": "light.living_room", "state": "on"})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.ha_device_summary("light.living_room")
        path = mock_get.call_args[0][0]
        assert "/api/ha/history/light.living_room?hours=1" == path

    def test_url_encodes_entity_id(self):
        mock_get = MagicMock(return_value={})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.ha_device_summary("sensor.some device")
        path = mock_get.call_args[0][0]
        assert " " not in path
        assert "sensor.some%20device" in path

    def test_returns_result(self):
        fake = {"entity_id": "light.x", "state": "on", "attributes": {"brightness": 255}}
        with patch("lumi.lumi_tool._lumi_get", return_value=fake):
            result = tool_module.ha_device_summary("light.x")
        assert result["state"] == "on"
        assert result["attributes"]["brightness"] == 255

    def test_in_valid_actions(self):
        assert "ha_device_summary" in _VALID_ACTIONS

    def test_dispatch(self):
        fake = {"entity_id": "light.x", "state": "off"}
        with patch("lumi.lumi_tool._lumi_get", return_value=fake):
            result = dispatch("ha_device_summary", {"entity_id": "light.x"})
        assert result["state"] == "off"


# ─── home_summary 测试 ────────────────────────────────────────────────────────

class TestHomeSummary:
    def _make_side_effect(self, responses: dict):
        """按调用路径返回不同响应。"""
        def side_effect(path: str):
            for key, val in responses.items():
                if key in path:
                    if isinstance(val, Exception):
                        raise val
                    return val
            return {}
        return side_effect

    def test_returns_all_keys(self):
        mock_get = MagicMock(return_value={})
        mock_post = MagicMock(return_value={"alerts": []})
        with patch("lumi.lumi_tool._lumi_get", mock_get), \
             patch("lumi.lumi_tool._lumi_post", mock_post):
            result = tool_module.home_summary()
        assert set(result.keys()) == {"summary", "alerts", "proactive", "health"}

    def test_partial_failure_still_returns_others(self):
        """proactive_alerts 失败时，其余 key 仍正常返回。"""
        def mock_get(path: str):
            if "/api/device_graph/summary" in path:
                return {"total_devices": 10}
            if "/api/proactive/status" in path:
                return {"running": True}
            if "/health" in path:
                return {"status": "ok"}
            return {}

        def mock_post(path: str, body: dict):
            if "/api/proactive/check" in path:
                raise RuntimeError("proactive check failed")
            return {}

        with patch("lumi.lumi_tool._lumi_get", side_effect=mock_get), \
             patch("lumi.lumi_tool._lumi_post", side_effect=mock_post):
            result = tool_module.home_summary()

        assert "error" in result["alerts"]
        assert result["summary"]["total_devices"] == 10
        assert result["health"]["status"] == "ok"
        assert result["proactive"]["running"] is True

    def test_all_fail_returns_errors(self):
        def mock_get(path: str):
            raise ConnectionError("no server")

        def mock_post(path: str, body: dict):
            raise ConnectionError("no server")

        with patch("lumi.lumi_tool._lumi_get", side_effect=mock_get), \
             patch("lumi.lumi_tool._lumi_post", side_effect=mock_post):
            result = tool_module.home_summary()

        for key in ("summary", "alerts", "proactive", "health"):
            assert "error" in result[key]

    def test_concurrent_execution(self):
        """验证并发：四个任务耗时不超过最慢单个任务的 2 倍。"""
        import time

        call_times: list[float] = []

        def slow_get(path: str):
            call_times.append(time.monotonic())
            time.sleep(0.05)
            return {}

        def slow_post(path: str, body: dict):
            call_times.append(time.monotonic())
            time.sleep(0.05)
            return {"alerts": []}

        start = time.monotonic()
        with patch("lumi.lumi_tool._lumi_get", side_effect=slow_get), \
             patch("lumi.lumi_tool._lumi_post", side_effect=slow_post):
            tool_module.home_summary()
        elapsed = time.monotonic() - start

        # 4 tasks × 0.05s serial = 0.2s; concurrent should finish in < 0.15s
        assert elapsed < 0.15, f"home_summary took {elapsed:.3f}s, expected concurrent execution"

    def test_in_valid_actions(self):
        assert "home_summary" in _VALID_ACTIONS

    def test_dispatch(self):
        mock_get = MagicMock(return_value={})
        mock_post = MagicMock(return_value={"alerts": []})
        with patch("lumi.lumi_tool._lumi_get", mock_get), \
             patch("lumi.lumi_tool._lumi_post", mock_post):
            result = dispatch("home_summary")
        assert isinstance(result, dict)
        assert "health" in result

