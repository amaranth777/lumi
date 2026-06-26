"""tests/test_mcp_server.py — Lumi MCP Server 单元测试。"""

from __future__ import annotations

import importlib
import json
from unittest.mock import patch, MagicMock


# ─── 导入测试 ─────────────────────────────────────────────────────────────────


class TestMcpServerImport:
    def test_module_importable(self):
        mod = importlib.import_module("lumi.mcp_server")
        assert mod is not None

    def test_mcp_instance_exists(self):
        mod = importlib.import_module("lumi.mcp_server")
        assert hasattr(mod, "mcp")

    def test_main_callable(self):
        mod = importlib.import_module("lumi.mcp_server")
        assert callable(mod.main)


# ─── 注册工具测试 ─────────────────────────────────────────────────────────────


class TestRegisteredTools:
    def _get_tool_names(self) -> set[str]:
        mod = importlib.import_module("lumi.mcp_server")
        return set(mod.REGISTERED_TOOLS)

    def test_registered_tools_set_exists(self):
        mod = importlib.import_module("lumi.mcp_server")
        assert hasattr(mod, "REGISTERED_TOOLS")

    def test_all_valid_actions_have_tool(self):
        from lumi.lumi_tool import _VALID_ACTIONS
        tool_names = self._get_tool_names()
        for action in _VALID_ACTIONS:
            expected = f"lumi_{action}"
            assert expected in tool_names, f"Missing MCP tool for action '{action}'"

    def test_tool_name_format(self):
        tool_names = self._get_tool_names()
        for name in tool_names:
            assert name.startswith("lumi_"), f"Tool '{name}' does not start with 'lumi_'"

    def test_tool_count_matches_valid_actions(self):
        from lumi.lumi_tool import _VALID_ACTIONS
        tool_names = self._get_tool_names()
        assert len(tool_names) == len(_VALID_ACTIONS)

    def test_no_extra_tools(self):
        from lumi.lumi_tool import _VALID_ACTIONS
        tool_names = self._get_tool_names()
        expected = {f"lumi_{a}" for a in _VALID_ACTIONS}
        extra = tool_names - expected
        assert not extra, f"Extra tools registered: {extra}"


# ─── tool 函数 callable 测试 ──────────────────────────────────────────────────


class TestToolFunctions:
    def _mod(self):
        return importlib.import_module("lumi.mcp_server")

    def test_lumi_health_callable(self):
        assert callable(self._mod().lumi_health)

    def test_lumi_status_callable(self):
        assert callable(self._mod().lumi_status)

    def test_lumi_summary_callable(self):
        assert callable(self._mod().lumi_summary)

    def test_lumi_types_callable(self):
        assert callable(self._mod().lumi_types)

    def test_lumi_search_callable(self):
        assert callable(self._mod().lumi_search)

    def test_lumi_room_callable(self):
        assert callable(self._mod().lumi_room)

    def test_lumi_control_callable(self):
        assert callable(self._mod().lumi_control)

    def test_lumi_batch_control_callable(self):
        assert callable(self._mod().lumi_batch_control)

    def test_lumi_scenes_callable(self):
        assert callable(self._mod().lumi_scenes)

    def test_lumi_run_scene_callable(self):
        assert callable(self._mod().lumi_run_scene)

    def test_lumi_perception_types_callable(self):
        assert callable(self._mod().lumi_perception_types)

    def test_lumi_perception_test_callable(self):
        assert callable(self._mod().lumi_perception_test)

    def test_lumi_perception_send_callable(self):
        assert callable(self._mod().lumi_perception_send)

    def test_lumi_ha_services_callable(self):
        assert callable(self._mod().lumi_ha_services)

    def test_lumi_ha_automations_callable(self):
        assert callable(self._mod().lumi_ha_automations)

    def test_lumi_ha_toggle_automation_callable(self):
        assert callable(self._mod().lumi_ha_toggle_automation)

    def test_lumi_ha_run_script_callable(self):
        assert callable(self._mod().lumi_ha_run_script)

    def test_lumi_ha_history_callable(self):
        assert callable(self._mod().lumi_ha_history)

    def test_lumi_ha_fire_event_callable(self):
        assert callable(self._mod().lumi_ha_fire_event)

    def test_lumi_ha_render_template_callable(self):
        assert callable(self._mod().lumi_ha_render_template)

    def test_lumi_ha_config_callable(self):
        assert callable(self._mod().lumi_ha_config)

    def test_lumi_proactive_status_callable(self):
        assert callable(self._mod().lumi_proactive_status)

    def test_lumi_proactive_alerts_callable(self):
        assert callable(self._mod().lumi_proactive_alerts)


# ─── tool 返回值测试（patch lumi.lumi_tool.*）────────────────────────────────


class TestToolReturnValues:
    def _mod(self):
        return importlib.import_module("lumi.mcp_server")

    def test_lumi_health_returns_json(self):
        mod = self._mod()
        with patch("lumi.lumi_tool.health", return_value={"status": "ok"}):
            result = mod.lumi_health()
        assert json.loads(result)["status"] == "ok"

    def test_lumi_summary_returns_json(self):
        mod = self._mod()
        with patch("lumi.lumi_tool.summary", return_value={"total_devices": 5}):
            result = mod.lumi_summary()
        assert json.loads(result)["total_devices"] == 5

    def test_lumi_search_passes_query(self):
        mod = self._mod()
        mock_fn = MagicMock(return_value=[{"id": "light.x"}])
        with patch("lumi.lumi_tool.search", mock_fn):
            result = mod.lumi_search("客厅")
        mock_fn.assert_called_once_with(query="客厅")
        assert json.loads(result)[0]["id"] == "light.x"

    def test_lumi_control_passes_args(self):
        mod = self._mod()
        mock_fn = MagicMock(return_value={"success": True})
        with patch("lumi.lumi_tool.control", mock_fn):
            mod.lumi_control("light.x", "turn_on", {"brightness": 80})
        mock_fn.assert_called_once_with(device_id="light.x", command="turn_on", params={"brightness": 80})

    def test_lumi_ha_services_returns_json(self):
        mod = self._mod()
        with patch("lumi.lumi_tool.ha_services", return_value={"domains": ["light"]}):
            result = mod.lumi_ha_services()
        assert json.loads(result)["domains"] == ["light"]

    def test_lumi_ha_automations_returns_json(self):
        mod = self._mod()
        fake = [{"entity_id": "automation.x", "name": "X", "state": "on"}]
        with patch("lumi.lumi_tool.ha_automations", return_value=fake):
            result = mod.lumi_ha_automations()
        assert len(json.loads(result)) == 1

    def test_lumi_ha_toggle_automation_passes_args(self):
        mod = self._mod()
        mock_fn = MagicMock(return_value={"success": True})
        with patch("lumi.lumi_tool.ha_toggle_automation", mock_fn):
            result = mod.lumi_ha_toggle_automation("automation.x", True)
        mock_fn.assert_called_once_with(entity_id="automation.x", enable=True)
        assert json.loads(result)["success"] is True

    def test_lumi_ha_history_default_hours(self):
        mod = self._mod()
        mock_fn = MagicMock(return_value={"count": 0, "states": [], "entity_id": "light.x", "hours": 24})
        with patch("lumi.lumi_tool.ha_history", mock_fn):
            mod.lumi_ha_history("light.x")
        mock_fn.assert_called_once_with(entity_id="light.x", hours=24)

    def test_lumi_ha_fire_event_default_data(self):
        mod = self._mod()
        mock_fn = MagicMock(return_value={"success": True})
        with patch("lumi.lumi_tool.ha_fire_event", mock_fn):
            mod.lumi_ha_fire_event("my_evt")
        mock_fn.assert_called_once_with(event_type="my_evt", event_data=None)

    def test_lumi_perception_send_passes_args(self):
        mod = self._mod()
        mock_fn = MagicMock(return_value={"sent": True, "response": {}})
        with patch("lumi.lumi_tool.perception_send", mock_fn):
            mod.lumi_perception_send("pet_detected", room_name="客厅")
        mock_fn.assert_called_once_with(
            event_type="pet_detected",
            event_id="",
            camera_id=None,
            room_name="客厅",
            context=None,
            image_url=None,
            thumbnail_url=None,
        )

    def test_lumi_proactive_status_returns_json(self):
        mod = self._mod()
        with patch("lumi.lumi_tool.proactive_status", return_value={"enabled": False}):
            result = mod.lumi_proactive_status()
        assert json.loads(result)["enabled"] is False

    def test_lumi_proactive_alerts_returns_json(self):
        mod = self._mod()
        with patch("lumi.lumi_tool.proactive_alerts", return_value={"count": 0, "alerts": []}):
            result = mod.lumi_proactive_alerts()
        assert json.loads(result)["count"] == 0
