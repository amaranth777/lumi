"""tests/test_new_rules.py — LowBatteryRule、EntityValueRule 及相关配置测试。"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from lumi.proactive.rules import EntityValueRule, LowBatteryRule
from lumi.proactive.rules_loader import RulesConfig, load_rules_config
from lumi.proactive.analyzer import ProactiveAnalyzer


# ─── 辅助 ─────────────────────────────────────────────────────────────────────


def _make_state(entity_id: str, state: str, **attrs) -> dict:
    return {"entity_id": entity_id, "state": state, "attributes": attrs}


# ─── LowBatteryRule ───────────────────────────────────────────────────────────


class TestLowBatteryRule:
    def setup_method(self):
        self.rule = LowBatteryRule()  # threshold=20

    def test_triggers_battery_entity_below_threshold(self):
        states = [_make_state("sensor.door_battery", "15", friendly_name="门传感器")]
        alerts = self.rule.check([], states)
        assert len(alerts) == 1
        assert alerts[0].level == "warning"
        assert "15%" in alerts[0].message
        assert "门传感器" in alerts[0].action_hint

    def test_triggers_battery_level_attribute(self):
        states = [_make_state("sensor.some_device", "10", battery_level=10)]
        alerts = self.rule.check([], states)
        assert len(alerts) == 1
        assert "10%" in alerts[0].message

    def test_no_trigger_when_battery_normal(self):
        states = [_make_state("sensor.door_battery", "80")]
        alerts = self.rule.check([], states)
        assert alerts == []

    def test_no_trigger_at_exact_threshold(self):
        states = [_make_state("sensor.door_battery", "20")]
        alerts = self.rule.check([], states)
        assert alerts == []

    def test_no_trigger_for_unrelated_entity(self):
        states = [_make_state("sensor.temperature", "15")]
        alerts = self.rule.check([], states)
        assert alerts == []

    def test_no_trigger_when_state_non_numeric(self):
        states = [_make_state("sensor.door_battery", "unavailable")]
        alerts = self.rule.check([], states)
        assert alerts == []

    def test_custom_threshold_via_rules_config(self):
        cfg = RulesConfig(battery_low_percent=50.0)
        rule = LowBatteryRule(rules_config=cfg)
        states = [_make_state("sensor.door_battery", "45")]
        alerts = rule.check([], states)
        assert len(alerts) == 1

    def test_custom_threshold_no_trigger(self):
        cfg = RulesConfig(battery_low_percent=50.0)
        rule = LowBatteryRule(rules_config=cfg)
        states = [_make_state("sensor.door_battery", "60")]
        alerts = rule.check([], states)
        assert alerts == []

    def test_multiple_low_battery_devices(self):
        states = [
            _make_state("sensor.battery_a", "5"),
            _make_state("sensor.battery_b", "10"),
            _make_state("sensor.battery_c", "90"),
        ]
        alerts = self.rule.check([], states)
        assert len(alerts) == 2

    def test_empty_states(self):
        assert self.rule.check([], []) == []

    def test_device_id_set_correctly(self):
        states = [_make_state("sensor.door_battery", "5")]
        alerts = self.rule.check([], states)
        assert alerts[0].device_id == "sensor.door_battery"

    def test_action_hint_uses_entity_id_when_no_friendly_name(self):
        states = [_make_state("sensor.door_battery", "5")]
        alerts = self.rule.check([], states)
        assert "sensor.door_battery" in alerts[0].action_hint


# ─── EntityValueRule ──────────────────────────────────────────────────────────


class TestEntityValueRule:
    def _make_rule(self, monitors: list[dict]) -> EntityValueRule:
        cfg = RulesConfig(entity_monitors=monitors)
        return EntityValueRule(rules_config=cfg)

    def test_greater_than_triggers(self):
        rule = self._make_rule([
            {"entity_id": "sensor.pm25", "condition": ">", "threshold": 75,
             "message": "PM2.5 超标", "level": "warning"}
        ])
        states = [_make_state("sensor.pm25", "80")]
        alerts = rule.check([], states)
        assert len(alerts) == 1
        assert alerts[0].message == "PM2.5 超标"

    def test_greater_than_no_trigger(self):
        rule = self._make_rule([
            {"entity_id": "sensor.pm25", "condition": ">", "threshold": 75,
             "message": "PM2.5 超标", "level": "warning"}
        ])
        states = [_make_state("sensor.pm25", "70")]
        alerts = rule.check([], states)
        assert alerts == []

    def test_less_than_triggers(self):
        rule = self._make_rule([
            {"entity_id": "sensor.co2", "condition": "<", "threshold": 400,
             "message": "CO2 过低", "level": "info"}
        ])
        states = [_make_state("sensor.co2", "350")]
        alerts = rule.check([], states)
        assert len(alerts) == 1
        assert alerts[0].level == "info"

    def test_less_than_no_trigger(self):
        rule = self._make_rule([
            {"entity_id": "sensor.co2", "condition": "<", "threshold": 400,
             "message": "CO2 过低", "level": "info"}
        ])
        states = [_make_state("sensor.co2", "500")]
        alerts = rule.check([], states)
        assert alerts == []

    def test_equal_string_triggers(self):
        rule = self._make_rule([
            {"entity_id": "binary_sensor.door", "condition": "==", "threshold": "on",
             "message": "门未关闭", "level": "warning"}
        ])
        states = [_make_state("binary_sensor.door", "on")]
        alerts = rule.check([], states)
        assert len(alerts) == 1
        assert alerts[0].message == "门未关闭"

    def test_equal_string_no_trigger(self):
        rule = self._make_rule([
            {"entity_id": "binary_sensor.door", "condition": "==", "threshold": "on",
             "message": "门未关闭", "level": "warning"}
        ])
        states = [_make_state("binary_sensor.door", "off")]
        alerts = rule.check([], states)
        assert alerts == []

    def test_greater_equal_triggers(self):
        rule = self._make_rule([
            {"entity_id": "sensor.temp", "condition": ">=", "threshold": 30,
             "message": "温度偏高", "level": "warning"}
        ])
        states = [_make_state("sensor.temp", "30")]
        alerts = rule.check([], states)
        assert len(alerts) == 1

    def test_less_equal_triggers(self):
        rule = self._make_rule([
            {"entity_id": "sensor.temp", "condition": "<=", "threshold": 10,
             "message": "温度偏低", "level": "warning"}
        ])
        states = [_make_state("sensor.temp", "10")]
        alerts = rule.check([], states)
        assert len(alerts) == 1

    def test_not_equal_triggers(self):
        rule = self._make_rule([
            {"entity_id": "sensor.mode", "condition": "!=", "threshold": "auto",
             "message": "模式异常", "level": "warning"}
        ])
        states = [_make_state("sensor.mode", "manual")]
        alerts = rule.check([], states)
        assert len(alerts) == 1

    def test_entity_not_in_states_no_trigger(self):
        rule = self._make_rule([
            {"entity_id": "sensor.nonexistent", "condition": ">", "threshold": 0,
             "message": "test", "level": "warning"}
        ])
        alerts = rule.check([], [])
        assert alerts == []

    def test_no_monitors_returns_empty(self):
        rule = EntityValueRule()
        states = [_make_state("sensor.pm25", "100")]
        assert rule.check([], states) == []

    def test_multiple_monitors_independent(self):
        rule = self._make_rule([
            {"entity_id": "sensor.pm25", "condition": ">", "threshold": 75,
             "message": "PM2.5 超标", "level": "warning"},
            {"entity_id": "binary_sensor.door", "condition": "==", "threshold": "on",
             "message": "门未关闭", "level": "warning"},
        ])
        states = [
            _make_state("sensor.pm25", "100"),
            _make_state("binary_sensor.door", "off"),
        ]
        alerts = rule.check([], states)
        assert len(alerts) == 1
        assert alerts[0].message == "PM2.5 超标"

    def test_device_id_set_correctly(self):
        rule = self._make_rule([
            {"entity_id": "sensor.pm25", "condition": ">", "threshold": 75,
             "message": "PM2.5 超标", "level": "warning"}
        ])
        states = [_make_state("sensor.pm25", "80")]
        alerts = rule.check([], states)
        assert alerts[0].device_id == "sensor.pm25"


# ─── load_rules_config ────────────────────────────────────────────────────────


class TestLoadRulesConfigNewFields:
    def test_parses_battery_low_percent(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            rules:
              low_battery:
                battery_low_percent: 30
        """)
        cfg_file = tmp_path / "rules.yaml"
        cfg_file.write_text(yaml_content)
        cfg = load_rules_config(str(cfg_file))
        assert cfg.battery_low_percent == 30.0

    def test_default_battery_low_percent(self, tmp_path):
        cfg_file = tmp_path / "rules.yaml"
        cfg_file.write_text("rules: {}\n")
        cfg = load_rules_config(str(cfg_file))
        assert cfg.battery_low_percent == 20.0

    def test_parses_entity_monitors(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            entity_monitors:
              - entity_id: sensor.air_quality_pm25
                condition: ">"
                threshold: 75
                message: "PM2.5 超标"
                level: warning
              - entity_id: binary_sensor.door_sensor
                condition: "=="
                threshold: "on"
                message: "门未关闭"
                level: warning
        """)
        cfg_file = tmp_path / "rules.yaml"
        cfg_file.write_text(yaml_content)
        cfg = load_rules_config(str(cfg_file))
        assert len(cfg.entity_monitors) == 2
        assert cfg.entity_monitors[0]["entity_id"] == "sensor.air_quality_pm25"
        assert cfg.entity_monitors[1]["threshold"] == "on"

    def test_default_entity_monitors_empty(self, tmp_path):
        cfg_file = tmp_path / "rules.yaml"
        cfg_file.write_text("rules: {}\n")
        cfg = load_rules_config(str(cfg_file))
        assert cfg.entity_monitors == []

    def test_low_battery_disabled_via_config(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            rules:
              low_battery:
                enabled: false
        """)
        cfg_file = tmp_path / "rules.yaml"
        cfg_file.write_text(yaml_content)
        cfg = load_rules_config(str(cfg_file))
        assert "low_battery" in cfg.disabled_rules


# ─── ProactiveAnalyzer 包含新规则 ─────────────────────────────────────────────


class TestProactiveAnalyzerNewRules:
    def test_default_rules_include_low_battery(self):
        analyzer = ProactiveAnalyzer()
        names = analyzer.active_rule_names()
        assert "low_battery" in names

    def test_entity_monitor_not_included_without_config(self):
        analyzer = ProactiveAnalyzer()
        names = analyzer.active_rule_names()
        assert "entity_monitor" not in names

    def test_entity_monitor_included_with_entity_monitors(self):
        cfg = RulesConfig(entity_monitors=[
            {"entity_id": "sensor.pm25", "condition": ">", "threshold": 75,
             "message": "PM2.5 超标", "level": "warning"}
        ])
        analyzer = ProactiveAnalyzer(rules_config=cfg)
        names = analyzer.active_rule_names()
        assert "entity_monitor" in names

    def test_low_battery_triggers_through_analyzer(self):
        analyzer = ProactiveAnalyzer()
        states = [{"entity_id": "sensor.door_battery", "state": "5", "attributes": {}}]
        alerts = analyzer.analyze([], states)
        battery_alerts = [a for a in alerts if "电量低" in a.message]
        assert len(battery_alerts) == 1

    def test_entity_monitor_triggers_through_analyzer(self):
        cfg = RulesConfig(entity_monitors=[
            {"entity_id": "sensor.pm25", "condition": ">", "threshold": 75,
             "message": "PM2.5 超标", "level": "warning"}
        ])
        analyzer = ProactiveAnalyzer(rules_config=cfg)
        states = [{"entity_id": "sensor.pm25", "state": "100", "attributes": {}}]
        alerts = analyzer.analyze([], states)
        pm_alerts = [a for a in alerts if "PM2.5" in a.message]
        assert len(pm_alerts) == 1
