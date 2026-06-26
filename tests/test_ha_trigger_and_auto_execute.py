"""tests/test_ha_trigger_and_auto_execute.py

任务1：ha_trigger_automation 测试
任务2：ProactiveScheduler auto_execute 测试
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

import lumi.lumi_tool as tool_module
from lumi.lumi_tool import _VALID_ACTIONS
from lumi.config import LumiConfig, ProactiveConfig
from lumi.proactive.rules import Alert
from lumi.proactive.scheduler import ProactiveScheduler


# ─── 任务1：ha_trigger_automation ─────────────────────────────────────────────


class TestHaTriggerAutomation:
    def test_in_valid_actions(self):
        assert "ha_trigger_automation" in _VALID_ACTIONS

    def test_calls_trigger_endpoint(self):
        mock_post = MagicMock(return_value={"success": True})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            tool_module.ha_trigger_automation("automation.morning")
        path, body = mock_post.call_args[0]
        assert path == "/api/ha/automations/automation.morning/trigger"
        assert body == {}

    def test_returns_response(self):
        mock_post = MagicMock(return_value={"triggered": True})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            result = tool_module.ha_trigger_automation("automation.test")
        assert result["triggered"] is True

    def test_dispatch_works(self):
        mock_post = MagicMock(return_value={"success": True})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            from lumi.lumi_tool import dispatch
            dispatch("ha_trigger_automation", {"entity_id": "automation.x"})
        path, _ = mock_post.call_args[0]
        assert "automation.x" in path
        assert "/trigger" in path

    def test_mcp_registered(self):
        from lumi.mcp_server import REGISTERED_TOOLS
        assert "lumi_ha_trigger_automation" in REGISTERED_TOOLS


# ─── 任务2：auto_execute 测试 ──────────────────────────────────────────────────


def _make_scheduler(auto_execute: bool = False, alerts=None):
    """构造一个带 config 的 ProactiveScheduler。"""
    proactive_cfg = ProactiveConfig(auto_execute=auto_execute)
    config = LumiConfig(proactive=proactive_cfg)

    rule = MagicMock()
    rule.name = "mock_rule"
    rule.check.return_value = alerts or []

    from lumi.proactive.analyzer import ProactiveAnalyzer
    analyzer = ProactiveAnalyzer(rules=[rule], config=config)

    graph = MagicMock()
    graph.devices = []
    device_graph_svc = MagicMock()
    device_graph_svc.get_graph.return_value = graph

    ha_client = MagicMock()
    ha_client.get_states.return_value = []

    hermes_bridge = MagicMock()
    hermes_bridge.send_notification.return_value = None

    scheduler = ProactiveScheduler(
        analyzer=analyzer,
        device_graph_svc=device_graph_svc,
        ha_client=ha_client,
        hermes_bridge=hermes_bridge,
        interval_seconds=300,
        min_alert_interval_seconds=0,  # 不去重，全部通过
        config=config,
    )
    return scheduler


class TestAutoExecuteDisabled:
    def test_no_execute_when_auto_execute_false(self):
        alert = Alert(
            level="warning",
            device_id="humidifier.living_room",
            message="湿度过低",
            auto_action="control:humidifier.living_room:turn_on",
        )
        scheduler = _make_scheduler(auto_execute=False, alerts=[alert])
        mock_dispatch = MagicMock()
        with patch("lumi.lumi_tool.dispatch", mock_dispatch):
            asyncio.run(scheduler._auto_execute(alert))
        mock_dispatch.assert_not_called()

    def test_no_execute_when_no_config(self):
        alert = Alert(
            level="warning",
            device_id="d1",
            message="test",
            auto_action="control:d1:turn_on",
        )
        from lumi.proactive.analyzer import ProactiveAnalyzer
        analyzer = ProactiveAnalyzer(rules=[], config=LumiConfig())
        scheduler = ProactiveScheduler(
            analyzer=analyzer,
            device_graph_svc=MagicMock(),
            ha_client=MagicMock(),
            hermes_bridge=MagicMock(),
            config=None,
        )
        mock_dispatch = MagicMock()
        with patch("lumi.lumi_tool.dispatch", mock_dispatch):
            asyncio.run(scheduler._auto_execute(alert))
        mock_dispatch.assert_not_called()


class TestAutoExecuteNoAction:
    def test_no_execute_when_auto_action_none(self):
        alert = Alert(level="info", device_id="d1", message="msg", auto_action=None)
        scheduler = _make_scheduler(auto_execute=True)
        mock_dispatch = MagicMock()
        with patch("lumi.lumi_tool.dispatch", mock_dispatch):
            asyncio.run(scheduler._auto_execute(alert))
        mock_dispatch.assert_not_called()

    def test_no_execute_when_auto_action_empty_string(self):
        alert = Alert(level="info", device_id="d1", message="msg", auto_action="")
        scheduler = _make_scheduler(auto_execute=True)
        mock_dispatch = MagicMock()
        with patch("lumi.lumi_tool.dispatch", mock_dispatch):
            asyncio.run(scheduler._auto_execute(alert))
        mock_dispatch.assert_not_called()


class TestAutoExecuteForbidden:
    @pytest.mark.parametrize("auto_action", [
        "empty:litter_box.room:do_it",
        "control:litter_box.room:empty",
        "delete:some.device:delete",
        "restart_ha:ha:now",
        "control:something:restart_ha",
    ])
    def test_forbidden_action_rejected(self, auto_action):
        alert = Alert(level="warning", device_id="d1", message="msg", auto_action=auto_action)
        scheduler = _make_scheduler(auto_execute=True)
        mock_dispatch = MagicMock()
        with patch("lumi.lumi_tool.dispatch", mock_dispatch):
            asyncio.run(scheduler._auto_execute(alert))
        mock_dispatch.assert_not_called()


class TestAutoExecuteLegalControl:
    def test_control_action_dispatched(self):
        alert = Alert(
            level="warning",
            device_id="humidifier.living_room",
            message="湿度过低",
            auto_action="control:humidifier.living_room:turn_on",
        )
        scheduler = _make_scheduler(auto_execute=True)
        mock_dispatch = MagicMock()
        with patch("lumi.lumi_tool.dispatch", mock_dispatch):
            asyncio.run(scheduler._auto_execute(alert))
        mock_dispatch.assert_called_once_with(
            "control",
            {"device_id": "humidifier.living_room", "command": "turn_on"},
        )

    def test_control_called_during_run_once(self):
        alert = Alert(
            level="warning",
            device_id="humidifier.lr",
            message="干燥",
            auto_action="control:humidifier.lr:turn_on",
        )
        scheduler = _make_scheduler(auto_execute=True, alerts=[alert])
        mock_dispatch = MagicMock()
        with patch("lumi.lumi_tool.dispatch", mock_dispatch):
            asyncio.run(scheduler.run_once())
        mock_dispatch.assert_called_once_with(
            "control",
            {"device_id": "humidifier.lr", "command": "turn_on"},
        )


class TestAutoExecuteLegalHaTrigger:
    def test_ha_trigger_automation_dispatched(self):
        alert = Alert(
            level="info",
            device_id=None,
            message="触发自动化",
            auto_action="ha_trigger_automation:automation.morning",
        )
        scheduler = _make_scheduler(auto_execute=True)
        mock_dispatch = MagicMock()
        with patch("lumi.lumi_tool.dispatch", mock_dispatch):
            asyncio.run(scheduler._auto_execute(alert))
        mock_dispatch.assert_called_once_with(
            "ha_trigger_automation",
            {"entity_id": "automation.morning"},
        )

    def test_ha_trigger_called_during_run_once(self):
        alert = Alert(
            level="info",
            device_id=None,
            message="触发",
            auto_action="ha_trigger_automation:automation.night",
        )
        scheduler = _make_scheduler(auto_execute=True, alerts=[alert])
        mock_dispatch = MagicMock()
        with patch("lumi.lumi_tool.dispatch", mock_dispatch):
            asyncio.run(scheduler.run_once())
        mock_dispatch.assert_called_once_with(
            "ha_trigger_automation",
            {"entity_id": "automation.night"},
        )
