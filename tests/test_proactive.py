"""tests/test_proactive.py — 主动巡检引擎单元测试。"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lumi.config import LumiConfig, PetConfig, ProactiveConfig
from lumi.device_graph.schema import Device
from lumi.proactive.analyzer import ProactiveAnalyzer
from lumi.proactive.rules import (
    Alert,
    DeviceOfflineRule,
    HumidityAnomalyRule,
    LitterBoxFullRule,
    LitterBoxLowSandRule,
    TemperatureAnomalyRule,
)
from lumi.proactive.scheduler import ProactiveScheduler


# ─── 辅助工厂 ─────────────────────────────────────────────────────────────────


def _make_device(**kwargs) -> Device:
    defaults = dict(
        id="dev_001",
        name="测试设备",
        type="sensor",
        platform="ha",
        state=None,
        attributes={},
    )
    defaults.update(kwargs)
    return Device(**defaults)


def _make_litter_box(**kwargs) -> Device:
    defaults = dict(
        id="litter_001",
        name="猫砂盆",
        type="litter_box",
        platform="ha",
        state="on",
        attributes={},
    )
    defaults.update(kwargs)
    return Device(**defaults)


def _make_config(**kwargs) -> LumiConfig:
    return LumiConfig(**kwargs)


# ─── LitterBoxFullRule ────────────────────────────────────────────────────────


class TestLitterBoxFullRule:
    def setup_method(self):
        self.rule = LitterBoxFullRule()

    def test_triggers_when_full_and_off(self):
        dev = _make_litter_box(
            attributes={"waste_collection_status": "full", "mode": "off"}
        )
        alerts = self.rule.check([dev], [])
        assert len(alerts) == 1
        assert alerts[0].level == "warning"
        assert "集便仓已满" in alerts[0].message
        assert alerts[0].action_hint == "control litter_box clean"

    def test_triggers_case_insensitive(self):
        dev = _make_litter_box(
            attributes={"waste_collection_status": "Full", "mode": "Off"}
        )
        alerts = self.rule.check([dev], [])
        assert len(alerts) == 1

    def test_no_trigger_when_not_full(self):
        dev = _make_litter_box(
            attributes={"waste_collection_status": "empty", "mode": "off"}
        )
        alerts = self.rule.check([dev], [])
        assert alerts == []

    def test_no_trigger_when_full_but_mode_running(self):
        dev = _make_litter_box(
            attributes={"waste_collection_status": "full", "mode": "cleaning"}
        )
        alerts = self.rule.check([dev], [])
        assert alerts == []

    def test_no_trigger_for_non_litter_box(self):
        dev = _make_device(
            type="light", name="客厅灯",
            attributes={"waste_collection_status": "full", "mode": "off"}
        )
        alerts = self.rule.check([dev], [])
        assert alerts == []

    def test_action_hint_never_contains_empty(self):
        dev = _make_litter_box(
            attributes={"waste_collection_status": "full", "mode": "off"}
        )
        alerts = self.rule.check([dev], [])
        for alert in alerts:
            if alert.action_hint:
                assert "empty" not in alert.action_hint.lower()

    def test_no_alerts_for_empty_list(self):
        assert self.rule.check([], []) == []


# ─── LitterBoxLowSandRule ─────────────────────────────────────────────────────


class TestLitterBoxLowSandRule:
    def setup_method(self):
        self.rule = LitterBoxLowSandRule(litter_low_kg=1.0)

    def test_triggers_when_sand_low(self):
        dev = _make_litter_box(attributes={"sand_weight": 0.5})
        alerts = self.rule.check([dev], [])
        assert len(alerts) == 1
        assert alerts[0].level == "warning"
        assert "余量不足" in alerts[0].message

    def test_triggers_at_threshold_boundary(self):
        dev = _make_litter_box(attributes={"sand_weight": 0.99})
        alerts = self.rule.check([dev], [])
        assert len(alerts) == 1

    def test_no_trigger_when_sand_sufficient(self):
        dev = _make_litter_box(attributes={"sand_weight": 2.0})
        alerts = self.rule.check([dev], [])
        assert alerts == []

    def test_no_trigger_at_exact_threshold(self):
        dev = _make_litter_box(attributes={"sand_weight": 1.0})
        alerts = self.rule.check([dev], [])
        assert alerts == []

    def test_no_trigger_when_no_sand_attribute(self):
        dev = _make_litter_box(attributes={})
        alerts = self.rule.check([dev], [])
        assert alerts == []

    def test_no_trigger_for_non_litter_box(self):
        dev = _make_device(type="sensor", name="普通传感器", attributes={"sand_weight": 0.1})
        alerts = self.rule.check([dev], [])
        assert alerts == []

    def test_custom_threshold(self):
        rule = LitterBoxLowSandRule(litter_low_kg=2.5)
        dev = _make_litter_box(attributes={"sand_weight": 2.0})
        alerts = rule.check([dev], [])
        assert len(alerts) == 1


# ─── TemperatureAnomalyRule ───────────────────────────────────────────────────


class TestTemperatureAnomalyRule:
    def setup_method(self):
        self.rule = TemperatureAnomalyRule()

    def _make_temp_sensor(self, temp: float, **kwargs) -> Device:
        return _make_device(
            id="temp_001",
            name="室内温度",
            type="temperature",
            state=str(temp),
            attributes={"unit_of_measurement": "°C", "device_class": "temperature"},
            **kwargs,
        )

    def test_triggers_when_too_hot(self):
        dev = self._make_temp_sensor(36.0)
        alerts = self.rule.check([dev], [])
        assert len(alerts) == 1
        assert "过高" in alerts[0].message
        assert alerts[0].level == "warning"

    def test_triggers_when_too_cold(self):
        dev = self._make_temp_sensor(3.0)
        alerts = self.rule.check([dev], [])
        assert len(alerts) == 1
        assert "过低" in alerts[0].message
        assert alerts[0].level == "warning"

    def test_no_trigger_normal_temperature(self):
        dev = self._make_temp_sensor(22.0)
        alerts = self.rule.check([dev], [])
        assert alerts == []

    def test_no_trigger_at_boundary_35(self):
        dev = self._make_temp_sensor(35.0)
        alerts = self.rule.check([dev], [])
        assert alerts == []

    def test_no_trigger_at_boundary_5(self):
        dev = self._make_temp_sensor(5.0)
        alerts = self.rule.check([dev], [])
        assert alerts == []

    def test_no_trigger_non_temperature_sensor(self):
        dev = _make_device(type="light", name="灯", state="30")
        alerts = self.rule.check([dev], [])
        assert alerts == []

    def test_detects_by_device_class(self):
        dev = _make_device(
            type="sensor",
            name="传感器",
            state="40.0",
            attributes={"device_class": "temperature"},
        )
        alerts = self.rule.check([dev], [])
        assert len(alerts) == 1


# ─── HumidityAnomalyRule ──────────────────────────────────────────────────────


class TestHumidityAnomalyRule:
    def setup_method(self):
        self.rule = HumidityAnomalyRule()

    def _make_humidity_sensor(self, humidity: float) -> Device:
        return _make_device(
            id="humi_001",
            name="室内湿度",
            type="humidity",
            state=str(humidity),
            attributes={"unit_of_measurement": "%", "device_class": "humidity"},
        )

    def test_triggers_when_too_humid(self):
        dev = self._make_humidity_sensor(92.0)
        alerts = self.rule.check([dev], [])
        assert len(alerts) == 1
        assert "过高" in alerts[0].message
        assert alerts[0].level == "info"

    def test_triggers_when_too_dry(self):
        dev = self._make_humidity_sensor(15.0)
        alerts = self.rule.check([dev], [])
        assert len(alerts) == 1
        assert "过低" in alerts[0].message
        assert alerts[0].level == "info"

    def test_no_trigger_normal_humidity(self):
        dev = self._make_humidity_sensor(55.0)
        alerts = self.rule.check([dev], [])
        assert alerts == []

    def test_no_trigger_at_boundary_90(self):
        dev = self._make_humidity_sensor(90.0)
        alerts = self.rule.check([dev], [])
        assert alerts == []

    def test_no_trigger_at_boundary_20(self):
        dev = self._make_humidity_sensor(20.0)
        alerts = self.rule.check([dev], [])
        assert alerts == []

    def test_no_trigger_non_humidity_sensor(self):
        dev = _make_device(type="light", name="灯", state="95")
        alerts = self.rule.check([dev], [])
        assert alerts == []


# ─── DeviceOfflineRule ────────────────────────────────────────────────────────


class TestDeviceOfflineRule:
    def setup_method(self):
        self.rule = DeviceOfflineRule()

    def _make_ha_state(self, entity_id: str, last_changed_offset_seconds: int) -> dict:
        """构造模拟 HA state，last_changed 为 now - offset 秒。"""
        import datetime
        ts = datetime.datetime.utcnow() - datetime.timedelta(seconds=last_changed_offset_seconds)
        return {
            "entity_id": entity_id,
            "state": "unavailable",
            "last_changed": ts.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        }

    def test_triggers_when_offline_over_30min(self):
        dev = _make_device(id="switch.living_room", name="客厅开关", state="unavailable")
        ha_state = self._make_ha_state("switch.living_room", 1900)  # 31+ min
        alerts = self.rule.check([dev], [ha_state])
        assert len(alerts) == 1
        assert "离线" in alerts[0].message
        assert alerts[0].level == "info"

    def test_no_trigger_when_offline_less_than_30min(self):
        dev = _make_device(id="switch.living_room", name="客厅开关", state="unavailable")
        ha_state = self._make_ha_state("switch.living_room", 600)  # 10 min
        alerts = self.rule.check([dev], [ha_state])
        assert alerts == []

    def test_no_trigger_when_device_online(self):
        dev = _make_device(id="switch.living_room", name="客厅开关", state="on")
        alerts = self.rule.check([dev], [])
        assert alerts == []

    def test_triggers_when_no_ha_state_and_unavailable(self):
        # 没有 ha_state 时间信息，视为超时
        dev = _make_device(id="switch.unknown", name="未知设备", state="unavailable")
        alerts = self.rule.check([dev], [])
        assert len(alerts) == 1

    def test_multiple_offline_devices(self):
        dev1 = _make_device(id="d1", name="设备1", state="unavailable")
        dev2 = _make_device(id="d2", name="设备2", state="unavailable")
        dev3 = _make_device(id="d3", name="设备3", state="on")
        ha_state1 = self._make_ha_state("d1", 2000)
        ha_state2 = self._make_ha_state("d2", 100)  # 离线不足 30min
        alerts = self.rule.check([dev1, dev2, dev3], [ha_state1, ha_state2])
        assert len(alerts) == 1
        assert alerts[0].device_id == "d1"


# ─── ProactiveAnalyzer ────────────────────────────────────────────────────────


class TestProactiveAnalyzer:
    def setup_method(self):
        self.config = _make_config()
        self.rule1 = LitterBoxFullRule()
        self.rule2 = TemperatureAnomalyRule()
        self.analyzer = ProactiveAnalyzer(
            rules=[self.rule1, self.rule2], config=self.config
        )

    def test_analyze_returns_combined_alerts(self):
        litter = _make_litter_box(
            attributes={"waste_collection_status": "full", "mode": "off"}
        )
        temp = _make_device(
            id="temp_001", name="温度", type="temperature",
            state="40.0",
            attributes={"device_class": "temperature"},
        )
        alerts = self.analyzer.analyze([litter, temp], [])
        assert len(alerts) == 2

    def test_analyze_returns_empty_when_no_alerts(self):
        dev = _make_device(type="light", name="灯", state="on")
        alerts = self.analyzer.analyze([dev], [])
        assert alerts == []

    def test_analyze_handles_rule_exception_gracefully(self):
        bad_rule = MagicMock()
        bad_rule.name = "bad_rule"
        bad_rule.check.side_effect = RuntimeError("规则崩溃")
        analyzer = ProactiveAnalyzer(rules=[bad_rule], config=self.config)
        # 不应抛出异常
        alerts = analyzer.analyze([], [])
        assert alerts == []

    def test_analyze_with_empty_devices(self):
        alerts = self.analyzer.analyze([], [])
        assert alerts == []

    def test_analyze_aggregates_from_multiple_rules(self):
        litter = _make_litter_box(
            attributes={"waste_collection_status": "full", "mode": "off"}
        )
        alerts = self.analyzer.analyze([litter], [])
        # litter_box_full 触发，temperature 不触发
        assert len(alerts) == 1
        assert alerts[0].level == "warning"


# ─── format_report ────────────────────────────────────────────────────────────


class TestFormatReport:
    def setup_method(self):
        self.config = _make_config()
        self.analyzer = ProactiveAnalyzer(rules=[], config=self.config)

    def test_empty_alerts_returns_empty_string(self):
        report = self.analyzer.format_report([])
        assert report == ""

    def test_report_contains_warning_emoji(self):
        alerts = [Alert(level="warning", device_id="d1", message="警告消息")]
        report = self.analyzer.format_report(alerts)
        assert "⚠️" in report

    def test_report_contains_critical_emoji(self):
        alerts = [Alert(level="critical", device_id="d1", message="紧急消息")]
        report = self.analyzer.format_report(alerts)
        assert "🚨" in report

    def test_report_contains_info_emoji(self):
        alerts = [Alert(level="info", device_id="d1", message="信息消息")]
        report = self.analyzer.format_report(alerts)
        assert "ℹ️" in report

    def test_report_contains_alert_count(self):
        alerts = [
            Alert(level="warning", device_id="d1", message="告警1"),
            Alert(level="info", device_id="d2", message="告警2"),
        ]
        report = self.analyzer.format_report(alerts)
        assert "2" in report

    def test_report_contains_action_hint(self):
        alerts = [
            Alert(
                level="warning",
                device_id="d1",
                message="猫砂盆集便仓已满",
                action_hint="control litter_box clean",
            )
        ]
        report = self.analyzer.format_report(alerts)
        assert "control litter_box clean" in report

    def test_report_sorted_by_severity(self):
        alerts = [
            Alert(level="info", device_id="d1", message="info消息"),
            Alert(level="critical", device_id="d2", message="critical消息"),
            Alert(level="warning", device_id="d3", message="warning消息"),
        ]
        report = self.analyzer.format_report(alerts)
        # critical 应出现在 warning 之前，warning 在 info 之前
        idx_critical = report.index("critical消息")
        idx_warning = report.index("warning消息")
        idx_info = report.index("info消息")
        assert idx_critical < idx_warning < idx_info

    def test_report_has_header(self):
        alerts = [Alert(level="info", device_id="d1", message="测试")]
        report = self.analyzer.format_report(alerts)
        assert "Lumi" in report


# ─── ProactiveScheduler ───────────────────────────────────────────────────────


class TestProactiveSchedulerRunOnce:
    def _make_scheduler(self, alerts=None, fail_ha=False, fail_graph=False):
        config = _make_config()
        rule = MagicMock()
        rule.name = "mock_rule"
        rule.check.return_value = alerts or []

        analyzer = ProactiveAnalyzer(rules=[rule], config=config)

        device_graph_svc = MagicMock()
        if fail_graph:
            device_graph_svc.get_graph.side_effect = RuntimeError("图获取失败")
        else:
            graph = MagicMock()
            graph.devices = []
            device_graph_svc.get_graph.return_value = graph

        ha_client = MagicMock()
        if fail_ha:
            ha_client.get_states.side_effect = RuntimeError("HA 离线")
        else:
            ha_client.get_states.return_value = []

        hermes_bridge = MagicMock()
        hermes_bridge.send_notification.return_value = MagicMock(success=True)

        scheduler = ProactiveScheduler(
            analyzer=analyzer,
            device_graph_svc=device_graph_svc,
            ha_client=ha_client,
            hermes_bridge=hermes_bridge,
            interval_seconds=300,
            min_alert_interval_seconds=1800,
        )
        return scheduler, hermes_bridge

    def test_no_notification_when_no_alerts(self):
        scheduler, bridge = self._make_scheduler(alerts=[])
        asyncio.run(scheduler.run_once())
        bridge.send_notification.assert_not_called()

    def test_notification_sent_when_alerts_exist(self):
        alerts = [Alert(level="warning", device_id="d1", message="测试告警")]
        scheduler, bridge = self._make_scheduler(alerts=alerts)
        asyncio.run(scheduler.run_once())
        bridge.send_notification.assert_called_once()

    def test_notification_message_contains_alert(self):
        alerts = [Alert(level="warning", device_id="d1", message="特殊告警消息")]
        scheduler, bridge = self._make_scheduler(alerts=alerts)
        asyncio.run(scheduler.run_once())
        call_args = bridge.send_notification.call_args[0][0]
        assert "特殊告警消息" in call_args

    def test_no_crash_when_ha_client_fails(self):
        alerts = [Alert(level="info", device_id="d1", message="离线")]
        scheduler, bridge = self._make_scheduler(alerts=alerts, fail_ha=True)
        # 不应抛出异常
        asyncio.run(scheduler.run_once())

    def test_no_crash_when_device_graph_fails(self):
        scheduler, bridge = self._make_scheduler(fail_graph=True)
        # 图获取失败不应 crash
        asyncio.run(scheduler.run_once())
        bridge.send_notification.assert_not_called()

    def test_no_crash_when_bridge_fails(self):
        alerts = [Alert(level="warning", device_id="d1", message="告警")]
        scheduler, bridge = self._make_scheduler(alerts=alerts)
        bridge.send_notification.side_effect = RuntimeError("推送失败")
        # 不应抛出异常
        asyncio.run(scheduler.run_once())


# ─── 告警去重逻辑 ─────────────────────────────────────────────────────────────


class TestAlertDeduplication:
    def _make_scheduler_with_alert(self, alert: Alert):
        config = _make_config()
        rule = MagicMock()
        rule.name = "mock"
        rule.check.return_value = [alert]
        analyzer = ProactiveAnalyzer(rules=[rule], config=config)

        device_graph_svc = MagicMock()
        graph = MagicMock()
        graph.devices = []
        device_graph_svc.get_graph.return_value = graph

        ha_client = MagicMock()
        ha_client.get_states.return_value = []

        hermes_bridge = MagicMock()
        hermes_bridge.send_notification.return_value = MagicMock(success=True)

        scheduler = ProactiveScheduler(
            analyzer=analyzer,
            device_graph_svc=device_graph_svc,
            ha_client=ha_client,
            hermes_bridge=hermes_bridge,
            interval_seconds=300,
            min_alert_interval_seconds=1800,
        )
        return scheduler, hermes_bridge

    def test_dedup_same_alert_not_sent_twice_within_interval(self):
        alert = Alert(level="warning", device_id="d1", message="重复告警")
        scheduler, bridge = self._make_scheduler_with_alert(alert)

        # 第一次：应推送
        asyncio.run(scheduler.run_once())
        assert bridge.send_notification.call_count == 1

        # 第二次（间隔 < min_alert_interval_seconds）：不应重复推送
        asyncio.run(scheduler.run_once())
        assert bridge.send_notification.call_count == 1

    def test_dedup_different_alerts_both_sent(self):
        config = _make_config()
        alert1 = Alert(level="warning", device_id="d1", message="告警A")
        alert2 = Alert(level="warning", device_id="d2", message="告警B")

        rule = MagicMock()
        rule.name = "mock"
        rule.check.return_value = [alert1, alert2]
        analyzer = ProactiveAnalyzer(rules=[rule], config=config)

        device_graph_svc = MagicMock()
        graph = MagicMock()
        graph.devices = []
        device_graph_svc.get_graph.return_value = graph

        ha_client = MagicMock()
        ha_client.get_states.return_value = []

        hermes_bridge = MagicMock()
        hermes_bridge.send_notification.return_value = MagicMock(success=True)

        scheduler = ProactiveScheduler(
            analyzer=analyzer,
            device_graph_svc=device_graph_svc,
            ha_client=ha_client,
            hermes_bridge=hermes_bridge,
            interval_seconds=300,
            min_alert_interval_seconds=1800,
        )
        asyncio.run(scheduler.run_once())
        # 两条告警都是新的 → 一次推送（合并报告）
        bridge = hermes_bridge
        assert bridge.send_notification.call_count == 1
        report = bridge.send_notification.call_args[0][0]
        assert "告警A" in report
        assert "告警B" in report

    def test_dedup_alert_resent_after_interval_expires(self):
        alert = Alert(level="warning", device_id="d1", message="周期告警")
        scheduler, bridge = self._make_scheduler_with_alert(alert)

        # 第一次发送
        asyncio.run(scheduler.run_once())
        assert bridge.send_notification.call_count == 1

        # 手动将去重时间戳设为过去（超过 min_alert_interval_seconds）
        key = ProactiveScheduler._alert_key(alert)
        scheduler._alert_sent_at[key] = time.time() - 1801

        # 第二次：应再次推送
        asyncio.run(scheduler.run_once())
        assert bridge.send_notification.call_count == 2

    def test_alert_key_uniqueness(self):
        a1 = Alert(level="warning", device_id="d1", message="消息X")
        a2 = Alert(level="warning", device_id="d2", message="消息X")
        a3 = Alert(level="info", device_id="d1", message="消息X")
        assert ProactiveScheduler._alert_key(a1) != ProactiveScheduler._alert_key(a2)
        assert ProactiveScheduler._alert_key(a1) != ProactiveScheduler._alert_key(a3)

    def test_alert_key_same_for_identical_alerts(self):
        a1 = Alert(level="warning", device_id="d1", message="消息X")
        a2 = Alert(level="warning", device_id="d1", message="消息X")
        assert ProactiveScheduler._alert_key(a1) == ProactiveScheduler._alert_key(a2)


# ─── 集成：send_notification 存在于 HermesBridge ──────────────────────────────


class TestHermesBridgeSendNotification:
    def test_send_notification_method_exists(self):
        from lumi.hermes_bridge import HermesBridge
        bridge = HermesBridge.__new__(HermesBridge)
        assert hasattr(bridge, "send_notification")
        assert callable(bridge.send_notification)

    def test_send_notification_calls_hermes_send(self):
        from lumi.hermes_bridge import HermesBridge
        bridge = HermesBridge.__new__(HermesBridge)
        bridge.target = "weixin"
        bridge._log_path = "/tmp/test_bridge.log"

        with patch("lumi.hermes_bridge._hermes_send") as mock_send:
            mock_send.return_value = {"ok": True}
            result = bridge.send_notification("测试推送")
        mock_send.assert_called_once_with("测试推送", "weixin")
        assert result.success is True

    def test_send_notification_handles_error(self):
        from lumi.hermes_bridge import HermesBridge
        bridge = HermesBridge.__new__(HermesBridge)
        bridge.target = "weixin"
        bridge._log_path = "/tmp/test_bridge.log"

        with patch("lumi.hermes_bridge._hermes_send", side_effect=RuntimeError("连接失败")):
            result = bridge.send_notification("测试推送")
        assert result.success is False
        assert "连接失败" in result.error
