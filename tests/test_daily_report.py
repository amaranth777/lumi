"""tests/test_daily_report.py — 全屋日报 + perception_history 单元测试。

所有测试 mock 网络调用，不真实访问 Lumi API / Hermes gateway。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import lumi.lumi_tool as tool_module
from lumi.lumi_tool import dispatch, _VALID_ACTIONS


# ─── DailyReport.generate() ──────────────────────────────────────────────────

class TestDailyReportGenerate:
    """DailyReport.generate() 内容测试。"""

    def _mock_data(self) -> tuple[dict, dict, dict, dict]:
        summary_data = {"total_devices": 42, "online_devices": 38, "room_count": 6}
        alerts_data = {"alerts": []}
        health_data = {"status": "ok", "ha": "ok", "miloco": "connected"}
        perception_data = {"events": [], "total": 0}
        return summary_data, alerts_data, health_data, perception_data

    def test_morning_title(self):
        summary_d, alerts_d, health_d, perc_d = self._mock_data()
        with (
            patch("lumi.lumi_tool._lumi_get", return_value={}),
            patch("lumi.lumi_tool._lumi_post", return_value=alerts_d),
            patch("lumi.reports.daily.summary", return_value=summary_d),
            patch("lumi.reports.daily.proactive_alerts", return_value=alerts_d),
            patch("lumi.reports.daily.health", return_value=health_d),
            patch("lumi.lumi_tool.perception_history", return_value=perc_d),
        ):
            from lumi.reports.daily import DailyReport
            report = DailyReport()
            content = report.generate(report_type="morning")

        assert "☀️ 府上早安" in content
        assert "🌙" not in content

    def test_evening_title(self):
        summary_d, alerts_d, health_d, perc_d = self._mock_data()
        with (
            patch("lumi.reports.daily.summary", return_value=summary_d),
            patch("lumi.reports.daily.proactive_alerts", return_value=alerts_d),
            patch("lumi.reports.daily.health", return_value=health_d),
            patch("lumi.lumi_tool.perception_history", return_value=perc_d),
        ):
            from lumi.reports.daily import DailyReport
            content = DailyReport().generate(report_type="evening")

        assert "🌙 晚间好" in content
        assert "☀️" not in content

    def test_contains_device_section(self):
        summary_d = {"total_devices": 10, "online_devices": 8}
        alerts_d = {"alerts": []}
        health_d = {"status": "ok"}
        perc_d = {"events": [], "total": 0}
        with (
            patch("lumi.reports.daily.summary", return_value=summary_d),
            patch("lumi.reports.daily.proactive_alerts", return_value=alerts_d),
            patch("lumi.reports.daily.health", return_value=health_d),
            patch("lumi.lumi_tool.perception_history", return_value=perc_d),
        ):
            from lumi.reports.daily import DailyReport
            content = DailyReport().generate()

        assert "【全屋设备概况】" in content
        assert "10" in content  # total_devices

    def test_alerts_appear_in_report(self):
        alerts_d = {
            "alerts": [
                {"level": "warning", "message": "客厅温度异常"},
                {"level": "critical", "message": "前门未关"},
            ]
        }
        with (
            patch("lumi.reports.daily.summary", return_value={"total_devices": 5}),
            patch("lumi.reports.daily.proactive_alerts", return_value=alerts_d),
            patch("lumi.reports.daily.health", return_value={"status": "ok"}),
            patch("lumi.lumi_tool.perception_history", return_value={"events": []}),
        ):
            from lumi.reports.daily import DailyReport
            content = DailyReport().generate()

        assert "客厅温度异常" in content
        assert "前门未关" in content
        assert "✅ 无异常告警" not in content

    def test_no_alerts_shows_ok(self):
        with (
            patch("lumi.reports.daily.summary", return_value={"total_devices": 3}),
            patch("lumi.reports.daily.proactive_alerts", return_value={"alerts": []}),
            patch("lumi.reports.daily.health", return_value={"status": "ok"}),
            patch("lumi.lumi_tool.perception_history", return_value={"events": []}),
        ):
            from lumi.reports.daily import DailyReport
            content = DailyReport().generate()

        assert "✅ 无异常告警" in content

    def test_health_section_present(self):
        with (
            patch("lumi.reports.daily.summary", return_value={}),
            patch("lumi.reports.daily.proactive_alerts", return_value={"alerts": []}),
            patch("lumi.reports.daily.health", return_value={"status": "ok", "ha": "ok"}),
            patch("lumi.lumi_tool.perception_history", return_value={"events": []}),
        ):
            from lumi.reports.daily import DailyReport
            content = DailyReport().generate()

        assert "【服务健康状态】" in content
        assert "✅ 服务运行正常" in content

    def test_perception_events_in_report(self):
        perc_d = {
            "total": 5,
            "events": [
                {"event_type": "pet_detected", "room": "客厅"},
                {"event_type": "pet_detected", "room": "卧室"},
                {"event_type": "litter_box_full", "room": "卫生间"},
            ],
        }
        with (
            patch("lumi.reports.daily.summary", return_value={}),
            patch("lumi.reports.daily.proactive_alerts", return_value={"alerts": []}),
            patch("lumi.reports.daily.health", return_value={"status": "ok"}),
            patch("lumi.lumi_tool.perception_history", return_value=perc_d),
        ):
            from lumi.reports.daily import DailyReport
            content = DailyReport().generate()

        assert "【感知事件摘要】" in content
        assert "5" in content  # total

    def test_returns_string(self):
        with (
            patch("lumi.reports.daily.summary", return_value={}),
            patch("lumi.reports.daily.proactive_alerts", return_value={"alerts": []}),
            patch("lumi.reports.daily.health", return_value={"status": "ok"}),
            patch("lumi.lumi_tool.perception_history", return_value={"events": []}),
        ):
            from lumi.reports.daily import DailyReport
            content = DailyReport().generate()

        assert isinstance(content, str)
        assert len(content) > 50

    def test_generate_tolerates_api_errors(self):
        """当 API 调用失败时，日报仍然生成（降级）。"""
        with (
            patch("lumi.reports.daily.summary", side_effect=Exception("连接失败")),
            patch("lumi.reports.daily.proactive_alerts", side_effect=Exception("超时")),
            patch("lumi.reports.daily.health", side_effect=Exception("服务不可用")),
            patch("lumi.lumi_tool.perception_history", side_effect=Exception("无历史")),
        ):
            from lumi.reports.daily import DailyReport
            content = DailyReport().generate()

        # 即使 API 全部失败，仍然能生成有标题的报告
        assert "☀️ 府上早安" in content or "🌙 晚间好" in content


# ─── DailyReport.send() ──────────────────────────────────────────────────────

class TestDailyReportSend:
    """DailyReport.send() 推送测试。"""

    def test_send_calls_hermes_bridge(self):
        mock_result = MagicMock()
        mock_result.success = True
        mock_bridge = MagicMock()
        mock_bridge.send_notification.return_value = mock_result

        with (
            patch("lumi.reports.daily.summary", return_value={"total_devices": 5}),
            patch("lumi.reports.daily.proactive_alerts", return_value={"alerts": []}),
            patch("lumi.reports.daily.health", return_value={"status": "ok"}),
            patch("lumi.lumi_tool.perception_history", return_value={"events": []}),
            patch("lumi.reports.daily.HermesBridge", return_value=mock_bridge),
        ):
            from lumi.reports.daily import DailyReport
            ok = DailyReport().send(report_type="morning")

        assert ok is True
        mock_bridge.send_notification.assert_called_once()
        # 推送内容应包含早报标题
        sent_msg = mock_bridge.send_notification.call_args[0][0]
        assert "☀️ 府上早安" in sent_msg

    def test_send_evening(self):
        mock_result = MagicMock()
        mock_result.success = True
        mock_bridge = MagicMock()
        mock_bridge.send_notification.return_value = mock_result

        with (
            patch("lumi.reports.daily.summary", return_value={}),
            patch("lumi.reports.daily.proactive_alerts", return_value={"alerts": []}),
            patch("lumi.reports.daily.health", return_value={"status": "ok"}),
            patch("lumi.lumi_tool.perception_history", return_value={"events": []}),
            patch("lumi.reports.daily.HermesBridge", return_value=mock_bridge),
        ):
            from lumi.reports.daily import DailyReport
            ok = DailyReport().send(report_type="evening")

        assert ok is True
        sent_msg = mock_bridge.send_notification.call_args[0][0]
        assert "🌙 晚间好" in sent_msg

    def test_send_returns_false_on_bridge_failure(self):
        mock_result = MagicMock()
        mock_result.success = False
        mock_bridge = MagicMock()
        mock_bridge.send_notification.return_value = mock_result

        with (
            patch("lumi.reports.daily.summary", return_value={}),
            patch("lumi.reports.daily.proactive_alerts", return_value={"alerts": []}),
            patch("lumi.reports.daily.health", return_value={"status": "ok"}),
            patch("lumi.lumi_tool.perception_history", return_value={"events": []}),
            patch("lumi.reports.daily.HermesBridge", return_value=mock_bridge),
        ):
            from lumi.reports.daily import DailyReport
            ok = DailyReport().send()

        assert ok is False

    def test_send_returns_false_on_exception(self):
        with (
            patch("lumi.reports.daily.summary", return_value={}),
            patch("lumi.reports.daily.proactive_alerts", return_value={"alerts": []}),
            patch("lumi.reports.daily.health", return_value={"status": "ok"}),
            patch("lumi.lumi_tool.perception_history", return_value={"events": []}),
            patch("lumi.reports.daily.HermesBridge", side_effect=Exception("bridge 不可用")),
        ):
            from lumi.reports.daily import DailyReport
            ok = DailyReport().send()

        assert ok is False


# ─── perception_history action ───────────────────────────────────────────────

class TestPerceptionHistory:
    def test_calls_correct_path_default(self):
        mock_get = MagicMock(return_value={"events": [], "total": 0})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.perception_history()
        path = mock_get.call_args[0][0]
        assert "/api/perception/history" in path
        assert "limit=20" in path
        assert "offset=0" in path

    def test_calls_correct_path_with_params(self):
        mock_get = MagicMock(return_value={"events": []})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.perception_history(limit=5, offset=10)
        path = mock_get.call_args[0][0]
        assert "limit=5" in path
        assert "offset=10" in path

    def test_calls_correct_path_with_event_type(self):
        mock_get = MagicMock(return_value={"events": []})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.perception_history(event_type="pet_detected")
        path = mock_get.call_args[0][0]
        assert "event_type=pet_detected" in path

    def test_event_type_url_encoded(self):
        mock_get = MagicMock(return_value={"events": []})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.perception_history(event_type="litter box full")
        path = mock_get.call_args[0][0]
        assert "litter" in path
        assert " " not in path  # 空格已被 URL 编码

    def test_no_event_type_param_when_none(self):
        mock_get = MagicMock(return_value={"events": []})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            tool_module.perception_history(event_type=None)
        path = mock_get.call_args[0][0]
        assert "event_type" not in path

    def test_dispatch_perception_history(self):
        mock_get = MagicMock(return_value={"events": [], "total": 0})
        with patch("lumi.lumi_tool._lumi_get", mock_get):
            result = dispatch("perception_history", {"limit": 3})
        mock_get.assert_called_once()
        assert "limit=3" in mock_get.call_args[0][0]

    def test_in_valid_actions(self):
        assert "perception_history" in _VALID_ACTIONS


# ─── daily_report action ─────────────────────────────────────────────────────

class TestDailyReportAction:
    def test_daily_report_returns_dict_with_report_key(self):
        with (
            patch("lumi.reports.daily.summary", return_value={"total_devices": 5}),
            patch("lumi.reports.daily.proactive_alerts", return_value={"alerts": []}),
            patch("lumi.reports.daily.health", return_value={"status": "ok"}),
            patch("lumi.lumi_tool.perception_history", return_value={"events": []}),
        ):
            result = tool_module.daily_report(report_type="morning")

        assert "report" in result
        assert result["type"] == "morning"
        assert isinstance(result["report"], str)
        assert "☀️ 府上早安" in result["report"]

    def test_daily_report_evening(self):
        with (
            patch("lumi.reports.daily.summary", return_value={}),
            patch("lumi.reports.daily.proactive_alerts", return_value={"alerts": []}),
            patch("lumi.reports.daily.health", return_value={"status": "ok"}),
            patch("lumi.lumi_tool.perception_history", return_value={"events": []}),
        ):
            result = tool_module.daily_report(report_type="evening")

        assert result["type"] == "evening"
        assert "🌙 晚间好" in result["report"]

    def test_daily_report_in_valid_actions(self):
        assert "daily_report" in _VALID_ACTIONS

    def test_dispatch_daily_report(self):
        with (
            patch("lumi.reports.daily.summary", return_value={}),
            patch("lumi.reports.daily.proactive_alerts", return_value={"alerts": []}),
            patch("lumi.reports.daily.health", return_value={"status": "ok"}),
            patch("lumi.lumi_tool.perception_history", return_value={"events": []}),
        ):
            result = dispatch("daily_report", {"report_type": "morning"})

        assert "report" in result


# ─── send_daily_report action ─────────────────────────────────────────────────

class TestSendDailyReportAction:
    def test_send_daily_report_success(self):
        mock_result = MagicMock()
        mock_result.success = True
        mock_bridge = MagicMock()
        mock_bridge.send_notification.return_value = mock_result

        with (
            patch("lumi.reports.daily.summary", return_value={}),
            patch("lumi.reports.daily.proactive_alerts", return_value={"alerts": []}),
            patch("lumi.reports.daily.health", return_value={"status": "ok"}),
            patch("lumi.lumi_tool.perception_history", return_value={"events": []}),
            patch("lumi.reports.daily.HermesBridge", return_value=mock_bridge),
        ):
            result = tool_module.send_daily_report(report_type="morning")

        assert result["sent"] is True
        assert result["type"] == "morning"

    def test_send_daily_report_failure(self):
        mock_result = MagicMock()
        mock_result.success = False
        mock_bridge = MagicMock()
        mock_bridge.send_notification.return_value = mock_result

        with (
            patch("lumi.reports.daily.summary", return_value={}),
            patch("lumi.reports.daily.proactive_alerts", return_value={"alerts": []}),
            patch("lumi.reports.daily.health", return_value={"status": "ok"}),
            patch("lumi.lumi_tool.perception_history", return_value={"events": []}),
            patch("lumi.reports.daily.HermesBridge", return_value=mock_bridge),
        ):
            result = tool_module.send_daily_report(report_type="evening")

        assert result["sent"] is False
        assert result["type"] == "evening"

    def test_send_daily_report_in_valid_actions(self):
        assert "send_daily_report" in _VALID_ACTIONS

    def test_dispatch_send_daily_report(self):
        mock_result = MagicMock()
        mock_result.success = True
        mock_bridge = MagicMock()
        mock_bridge.send_notification.return_value = mock_result

        with (
            patch("lumi.reports.daily.summary", return_value={}),
            patch("lumi.reports.daily.proactive_alerts", return_value={"alerts": []}),
            patch("lumi.reports.daily.health", return_value={"status": "ok"}),
            patch("lumi.lumi_tool.perception_history", return_value={"events": []}),
            patch("lumi.reports.daily.HermesBridge", return_value=mock_bridge),
        ):
            result = dispatch("send_daily_report", {"report_type": "morning"})

        assert "sent" in result


# ─── MCP server 注册验证 ──────────────────────────────────────────────────────

class TestMcpRegistration:
    def test_mcp_registered_tools_match_valid_actions(self):
        """REGISTERED_TOOLS 与 _VALID_ACTIONS 完全一致（mcp_server 顶层断言的镜像测试）。"""
        from lumi.mcp_server import REGISTERED_TOOLS
        expected = frozenset(f"lumi_{a}" for a in _VALID_ACTIONS)
        assert REGISTERED_TOOLS == expected

    def test_new_tools_in_registered(self):
        from lumi.mcp_server import REGISTERED_TOOLS
        assert "lumi_perception_history" in REGISTERED_TOOLS
        assert "lumi_daily_report" in REGISTERED_TOOLS
        assert "lumi_send_daily_report" in REGISTERED_TOOLS
