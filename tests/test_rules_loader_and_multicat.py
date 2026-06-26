"""tests/test_rules_loader_and_multicat.py

测试：
- RulesConfig 加载（文件存在/不存在/格式错误）
- ProactiveAnalyzer disabled_rules 过滤
- reload_rules 热重载
- 多猫 CatProfile 模型
- PerceptionAnalyzer 多猫匹配
- /api/proactive/reload 端点
- proactive_reload lumi_tool
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from lumi.main import app

client = TestClient(app)


# ─── 辅助 ─────────────────────────────────────────────────────────────────────


def _make_perception_event(weight_kg: float, cat_name: str | None = None):
    """构建最小 PerceptionEvent for pet_weighed。"""
    from lumi.perception.events import PerceptionEvent, PerceptionEventType
    ctx: dict = {"weight_kg": weight_kg}
    if cat_name:
        ctx["cat_name"] = cat_name
    return PerceptionEvent(
        event_type=PerceptionEventType.PET_WEIGHED,
        subjects=[],
        room="卧室",
        context=ctx,
    )


# ─── RulesConfig 默认值 ───────────────────────────────────────────────────────


class TestRulesConfigDefaults:
    def test_default_temperature_max(self):
        from lumi.proactive.rules_loader import RulesConfig
        cfg = RulesConfig()
        assert cfg.temperature_max == 35.0

    def test_default_temperature_min(self):
        from lumi.proactive.rules_loader import RulesConfig
        cfg = RulesConfig()
        assert cfg.temperature_min == 5.0

    def test_default_humidity_max(self):
        from lumi.proactive.rules_loader import RulesConfig
        cfg = RulesConfig()
        assert cfg.humidity_max == 90.0

    def test_default_humidity_min(self):
        from lumi.proactive.rules_loader import RulesConfig
        cfg = RulesConfig()
        assert cfg.humidity_min == 20.0

    def test_default_litter_low(self):
        from lumi.proactive.rules_loader import RulesConfig
        cfg = RulesConfig()
        assert cfg.litter_low_threshold_kg == 1.0

    def test_default_device_offline_minutes(self):
        from lumi.proactive.rules_loader import RulesConfig
        cfg = RulesConfig()
        assert cfg.device_offline_minutes == 30

    def test_default_disabled_rules_empty(self):
        from lumi.proactive.rules_loader import RulesConfig
        cfg = RulesConfig()
        assert cfg.disabled_rules == []


# ─── load_rules_config：文件不存在 ────────────────────────────────────────────


class TestLoadRulesConfigMissing:
    def test_returns_default_when_file_missing(self, tmp_path):
        from lumi.proactive.rules_loader import load_rules_config, RulesConfig
        result = load_rules_config(str(tmp_path / "nonexistent.yaml"))
        assert isinstance(result, RulesConfig)
        assert result.temperature_max == 35.0

    def test_disabled_rules_empty_when_file_missing(self, tmp_path):
        from lumi.proactive.rules_loader import load_rules_config
        result = load_rules_config(str(tmp_path / "nonexistent.yaml"))
        assert result.disabled_rules == []


# ─── load_rules_config：文件存在 ─────────────────────────────────────────────


class TestLoadRulesConfigPresent:
    def _write_yaml(self, tmp_path, content: str) -> str:
        p = tmp_path / "rules.yaml"
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return str(p)

    def test_loads_temperature_max(self, tmp_path):
        from lumi.proactive.rules_loader import load_rules_config
        path = self._write_yaml(tmp_path, """
            rules:
              temperature:
                enabled: true
                max_celsius: 40
                min_celsius: 3
        """)
        cfg = load_rules_config(path)
        assert cfg.temperature_max == 40.0
        assert cfg.temperature_min == 3.0

    def test_loads_humidity(self, tmp_path):
        from lumi.proactive.rules_loader import load_rules_config
        path = self._write_yaml(tmp_path, """
            rules:
              humidity:
                enabled: true
                max_percent: 85
                min_percent: 25
        """)
        cfg = load_rules_config(path)
        assert cfg.humidity_max == 85.0
        assert cfg.humidity_min == 25.0

    def test_loads_litter_threshold(self, tmp_path):
        from lumi.proactive.rules_loader import load_rules_config
        path = self._write_yaml(tmp_path, """
            rules:
              litter_box_low_sand:
                enabled: true
                threshold_kg: 2.5
        """)
        cfg = load_rules_config(path)
        assert cfg.litter_low_threshold_kg == 2.5

    def test_loads_offline_minutes(self, tmp_path):
        from lumi.proactive.rules_loader import load_rules_config
        path = self._write_yaml(tmp_path, """
            rules:
              device_offline:
                enabled: true
                offline_minutes: 60
        """)
        cfg = load_rules_config(path)
        assert cfg.device_offline_minutes == 60

    def test_disabled_rule_via_enabled_false(self, tmp_path):
        from lumi.proactive.rules_loader import load_rules_config
        path = self._write_yaml(tmp_path, """
            rules:
              temperature:
                enabled: false
              humidity:
                enabled: false
        """)
        cfg = load_rules_config(path)
        assert "temperature" in cfg.disabled_rules
        assert "humidity" in cfg.disabled_rules

    def test_litter_full_disabled(self, tmp_path):
        from lumi.proactive.rules_loader import load_rules_config
        path = self._write_yaml(tmp_path, """
            rules:
              litter_box_full:
                enabled: false
        """)
        cfg = load_rules_config(path)
        assert "litter_box_full" in cfg.disabled_rules

    def test_device_offline_disabled(self, tmp_path):
        from lumi.proactive.rules_loader import load_rules_config
        path = self._write_yaml(tmp_path, """
            rules:
              device_offline:
                enabled: false
        """)
        cfg = load_rules_config(path)
        assert "device_offline" in cfg.disabled_rules

    def test_enabled_true_not_in_disabled(self, tmp_path):
        from lumi.proactive.rules_loader import load_rules_config
        path = self._write_yaml(tmp_path, """
            rules:
              temperature:
                enabled: true
        """)
        cfg = load_rules_config(path)
        assert "temperature" not in cfg.disabled_rules


# ─── load_rules_config：格式错误 ──────────────────────────────────────────────


class TestLoadRulesConfigInvalid:
    def test_returns_default_on_invalid_yaml(self, tmp_path):
        from lumi.proactive.rules_loader import load_rules_config
        p = tmp_path / "rules.yaml"
        p.write_text(": invalid: yaml: {{{", encoding="utf-8")
        cfg = load_rules_config(str(p))
        assert cfg.temperature_max == 35.0

    def test_returns_default_when_not_dict(self, tmp_path):
        from lumi.proactive.rules_loader import load_rules_config
        p = tmp_path / "rules.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        cfg = load_rules_config(str(p))
        assert cfg.temperature_max == 35.0

    def test_returns_default_on_empty_file(self, tmp_path):
        from lumi.proactive.rules_loader import load_rules_config
        p = tmp_path / "rules.yaml"
        p.write_text("", encoding="utf-8")
        cfg = load_rules_config(str(p))
        assert cfg.temperature_max == 35.0


# ─── ProactiveAnalyzer disabled_rules 过滤 ───────────────────────────────────


class TestProactiveAnalyzerDisabledRules:
    def test_disabled_rule_not_in_active_list(self):
        from lumi.proactive.analyzer import ProactiveAnalyzer
        from lumi.proactive.rules_loader import RulesConfig
        from lumi.config import LumiConfig
        cfg = LumiConfig()
        rules_cfg = RulesConfig(disabled_rules=["temperature"])
        analyzer = ProactiveAnalyzer(rules_config=rules_cfg, lumi_config=cfg)
        assert "temperature" not in analyzer.active_rule_names()

    def test_enabled_rule_in_active_list(self):
        from lumi.proactive.analyzer import ProactiveAnalyzer
        from lumi.proactive.rules_loader import RulesConfig
        from lumi.config import LumiConfig
        cfg = LumiConfig()
        rules_cfg = RulesConfig(disabled_rules=[])
        analyzer = ProactiveAnalyzer(rules_config=rules_cfg, lumi_config=cfg)
        assert "temperature" in analyzer.active_rule_names()

    def test_multiple_disabled_rules(self):
        from lumi.proactive.analyzer import ProactiveAnalyzer
        from lumi.proactive.rules_loader import RulesConfig
        from lumi.config import LumiConfig
        cfg = LumiConfig()
        rules_cfg = RulesConfig(disabled_rules=["temperature", "humidity"])
        analyzer = ProactiveAnalyzer(rules_config=rules_cfg, lumi_config=cfg)
        names = analyzer.active_rule_names()
        assert "temperature" not in names
        assert "humidity" not in names
        assert "litter_box_full" in names

    def test_all_rules_disabled(self):
        from lumi.proactive.analyzer import ProactiveAnalyzer
        from lumi.proactive.rules_loader import RulesConfig
        from lumi.config import LumiConfig
        cfg = LumiConfig()
        rules_cfg = RulesConfig(disabled_rules=[
            "litter_box_full", "litter_box_low_sand", "temperature", "humidity"
        ])
        analyzer = ProactiveAnalyzer(rules_config=rules_cfg, lumi_config=cfg)
        assert analyzer.active_rule_names() == []

    def test_disabled_rule_produces_no_alerts(self):
        """禁用 temperature 后，温度异常设备不产生告警。"""
        from lumi.proactive.analyzer import ProactiveAnalyzer
        from lumi.proactive.rules_loader import RulesConfig
        from lumi.config import LumiConfig
        from lumi.device_graph.schema import Device
        cfg = LumiConfig()
        rules_cfg = RulesConfig(disabled_rules=["temperature", "humidity"])
        analyzer = ProactiveAnalyzer(rules_config=rules_cfg, lumi_config=cfg)
        dev = Device(
            id="temp_001", name="室内温度", type="temperature",
            platform="ha", state="40.0",
            attributes={"device_class": "temperature"},
        )
        alerts = analyzer.analyze([dev], [])
        assert alerts == []


# ─── reload_rules 热重载 ──────────────────────────────────────────────────────


class TestReloadRules:
    def test_reload_changes_thresholds(self):
        from lumi.proactive.analyzer import ProactiveAnalyzer
        from lumi.proactive.rules_loader import RulesConfig
        from lumi.config import LumiConfig
        from lumi.device_graph.schema import Device
        cfg = LumiConfig()
        analyzer = ProactiveAnalyzer(lumi_config=cfg)

        # 默认阈值 35°C，40°C 应触发
        dev = Device(
            id="t1", name="温度", type="temperature",
            platform="ha", state="40.0",
            attributes={"device_class": "temperature"},
        )
        alerts_before = analyzer.analyze([dev], [])
        assert len(alerts_before) == 1

        # 热重载：把上限改为 45°C，40°C 不应触发
        new_cfg = RulesConfig(temperature_max=45.0, temperature_min=0.0)
        analyzer.reload_rules(new_cfg)
        alerts_after = analyzer.analyze([dev], [])
        assert alerts_after == []

    def test_reload_enables_previously_disabled(self):
        from lumi.proactive.analyzer import ProactiveAnalyzer
        from lumi.proactive.rules_loader import RulesConfig
        from lumi.config import LumiConfig
        cfg = LumiConfig()
        disabled_cfg = RulesConfig(disabled_rules=["temperature"])
        analyzer = ProactiveAnalyzer(rules_config=disabled_cfg, lumi_config=cfg)
        assert "temperature" not in analyzer.active_rule_names()

        enabled_cfg = RulesConfig(disabled_rules=[])
        analyzer.reload_rules(enabled_cfg)
        assert "temperature" in analyzer.active_rule_names()

    def test_reload_disables_previously_enabled(self):
        from lumi.proactive.analyzer import ProactiveAnalyzer
        from lumi.proactive.rules_loader import RulesConfig
        from lumi.config import LumiConfig
        cfg = LumiConfig()
        analyzer = ProactiveAnalyzer(lumi_config=cfg)
        assert "temperature" in analyzer.active_rule_names()

        analyzer.reload_rules(RulesConfig(disabled_rules=["temperature"]))
        assert "temperature" not in analyzer.active_rule_names()

    def test_reload_updates_rules_config_attribute(self):
        from lumi.proactive.analyzer import ProactiveAnalyzer
        from lumi.proactive.rules_loader import RulesConfig
        from lumi.config import LumiConfig
        analyzer = ProactiveAnalyzer(lumi_config=LumiConfig())
        new_cfg = RulesConfig(temperature_max=50.0)
        analyzer.reload_rules(new_cfg)
        assert analyzer.rules_config is new_cfg


# ─── CatProfile 模型测试 ──────────────────────────────────────────────────────


class TestCatProfile:
    def test_cat_profile_requires_name(self):
        from lumi.config import CatProfile
        with pytest.raises(Exception):
            CatProfile()  # name 必填

    def test_cat_profile_default_weight(self):
        from lumi.config import CatProfile
        cat = CatProfile(name="麻薯")
        assert cat.weight_min_kg == 2.0
        assert cat.weight_max_kg == 8.0

    def test_cat_profile_custom_weight(self):
        from lumi.config import CatProfile
        cat = CatProfile(name="麻薯", weight_min_kg=3.0, weight_max_kg=5.0)
        assert cat.weight_min_kg == 3.0
        assert cat.weight_max_kg == 5.0

    def test_pet_config_cats_default_empty(self):
        from lumi.config import PetConfig
        pet = PetConfig()
        assert pet.cats == []

    def test_pet_config_cats_list(self):
        from lumi.config import PetConfig, CatProfile
        pet = PetConfig(cats=[CatProfile(name="麻薯", weight_min_kg=3.0, weight_max_kg=5.0)])
        assert len(pet.cats) == 1
        assert pet.cats[0].name == "麻薯"

    def test_pet_config_from_dict(self):
        from lumi.config import PetConfig
        data = {
            "name": "麻薯",
            "weight_min_kg": 3.0,
            "weight_max_kg": 5.0,
            "litter_low_kg": 1.0,
            "cats": [{"name": "麻薯", "weight_min_kg": 3.0, "weight_max_kg": 5.0}],
        }
        pet = PetConfig(**data)
        assert pet.cats[0].name == "麻薯"


# ─── PerceptionAnalyzer 多猫匹配 ──────────────────────────────────────────────


class TestPerceptionAnalyzerMultiCat:
    def _make_config(self, cats=None):
        from lumi.config import LumiConfig, PetConfig, CatProfile
        cat_list = [CatProfile(**c) for c in (cats or [])]
        pet = PetConfig(name="猫猫", weight_min_kg=2.0, weight_max_kg=8.0, cats=cat_list)
        return LumiConfig(pet=pet)

    def test_single_cat_mode_normal(self):
        """单猫模式，体重正常不通知。"""
        from lumi.perception.analyzer import PerceptionAnalyzer
        analyzer = PerceptionAnalyzer()
        event = _make_perception_event(4.0)
        with patch("lumi.perception.analyzer.get_config", return_value=self._make_config()):
            decision = analyzer.analyze(event)
        assert not decision.should_notify

    def test_single_cat_mode_abnormal(self):
        """单猫模式，体重异常通知。"""
        from lumi.perception.analyzer import PerceptionAnalyzer
        analyzer = PerceptionAnalyzer()
        event = _make_perception_event(10.0)
        with patch("lumi.perception.analyzer.get_config", return_value=self._make_config()):
            decision = analyzer.analyze(event)
        assert decision.should_notify

    def test_multi_cat_match_by_name(self):
        """多猫模式，按 cat_name 精确匹配。"""
        from lumi.perception.analyzer import PerceptionAnalyzer
        analyzer = PerceptionAnalyzer()
        cats = [
            {"name": "麻薯", "weight_min_kg": 3.0, "weight_max_kg": 5.0},
            {"name": "团子", "weight_min_kg": 2.5, "weight_max_kg": 4.5},
        ]
        event = _make_perception_event(4.0, cat_name="麻薯")
        with patch("lumi.perception.analyzer.get_config", return_value=self._make_config(cats)):
            decision = analyzer.analyze(event)
        assert not decision.should_notify

    def test_multi_cat_match_by_name_abnormal(self):
        """多猫模式，按名字匹配后，体重超出范围触发告警。"""
        from lumi.perception.analyzer import PerceptionAnalyzer
        analyzer = PerceptionAnalyzer()
        cats = [
            {"name": "麻薯", "weight_min_kg": 3.0, "weight_max_kg": 5.0},
        ]
        event = _make_perception_event(7.0, cat_name="麻薯")
        with patch("lumi.perception.analyzer.get_config", return_value=self._make_config(cats)):
            decision = analyzer.analyze(event)
        assert decision.should_notify
        assert "麻薯" in decision.message

    def test_multi_cat_fuzzy_match_by_weight(self):
        """多猫模式，无名字时按体重范围模糊匹配。"""
        from lumi.perception.analyzer import PerceptionAnalyzer
        analyzer = PerceptionAnalyzer()
        cats = [
            {"name": "麻薯", "weight_min_kg": 3.0, "weight_max_kg": 5.0},
            {"name": "团子", "weight_min_kg": 1.5, "weight_max_kg": 2.5},
        ]
        # 体重 2.0，落在团子的范围
        event = _make_perception_event(2.0)
        with patch("lumi.perception.analyzer.get_config", return_value=self._make_config(cats)):
            decision = analyzer.analyze(event)
        assert not decision.should_notify
        assert "团子" in decision.reason

    def test_multi_cat_fallback_first_cat(self):
        """多猫模式，名字和体重都不匹配时用第一只猫兜底。"""
        from lumi.perception.analyzer import PerceptionAnalyzer
        analyzer = PerceptionAnalyzer()
        cats = [
            {"name": "麻薯", "weight_min_kg": 3.0, "weight_max_kg": 5.0},
            {"name": "团子", "weight_min_kg": 1.5, "weight_max_kg": 2.5},
        ]
        # 体重 6.0，不在任何猫范围内，兜底麻薯
        event = _make_perception_event(6.0)
        with patch("lumi.perception.analyzer.get_config", return_value=self._make_config(cats)):
            decision = analyzer.analyze(event)
        # 6.0 超出麻薯 3-5 范围，应告警
        assert decision.should_notify
        assert "麻薯" in decision.message

    def test_multi_cat_alert_contains_cat_name(self):
        """多猫模式，告警消息包含猫名。"""
        from lumi.perception.analyzer import PerceptionAnalyzer
        analyzer = PerceptionAnalyzer()
        cats = [{"name": "麻薯", "weight_min_kg": 3.0, "weight_max_kg": 5.0}]
        event = _make_perception_event(9.0, cat_name="麻薯")
        with patch("lumi.perception.analyzer.get_config", return_value=self._make_config(cats)):
            decision = analyzer.analyze(event)
        assert decision.should_notify
        assert "麻薯" in decision.message

    def test_multi_cat_unknown_name_falls_back_to_weight(self):
        """多猫模式，cat_name 无法匹配时按体重匹配。"""
        from lumi.perception.analyzer import PerceptionAnalyzer
        analyzer = PerceptionAnalyzer()
        cats = [
            {"name": "麻薯", "weight_min_kg": 3.0, "weight_max_kg": 5.0},
        ]
        # cat_name 不在列表里，体重 4.0 在麻薯范围
        event = _make_perception_event(4.0, cat_name="未知猫")
        with patch("lumi.perception.analyzer.get_config", return_value=self._make_config(cats)):
            decision = analyzer.analyze(event)
        assert not decision.should_notify


# ─── /api/proactive/reload 端点 ───────────────────────────────────────────────


class TestProactiveReloadEndpoint:
    def test_returns_200(self):
        scheduler = MagicMock()
        scheduler.analyzer.active_rule_names.return_value = ["litter_box_full", "temperature"]
        scheduler.analyzer.reload_rules.return_value = None
        with patch("lumi.deps.get_proactive_scheduler", return_value=scheduler), \
             patch("lumi.proactive.router.load_rules_config") as mock_load, \
             patch("lumi.proactive.router.get_config") as mock_cfg:
            from lumi.proactive.rules_loader import RulesConfig
            mock_load.return_value = RulesConfig()
            mock_cfg.return_value = MagicMock(proactive=MagicMock(rules_file="~/.lumi/rules.yaml"))
            resp = client.post("/api/proactive/reload")
        assert resp.status_code == 200

    def test_returns_ok_true(self):
        scheduler = MagicMock()
        scheduler.analyzer.active_rule_names.return_value = ["litter_box_full"]
        scheduler.analyzer.reload_rules.return_value = None
        with patch("lumi.deps.get_proactive_scheduler", return_value=scheduler), \
             patch("lumi.proactive.router.load_rules_config") as mock_load, \
             patch("lumi.proactive.router.get_config") as mock_cfg:
            from lumi.proactive.rules_loader import RulesConfig
            mock_load.return_value = RulesConfig()
            mock_cfg.return_value = MagicMock(proactive=MagicMock(rules_file="~/.lumi/rules.yaml"))
            resp = client.post("/api/proactive/reload")
        assert resp.json()["ok"] is True

    def test_returns_active_rules(self):
        scheduler = MagicMock()
        scheduler.analyzer.active_rule_names.return_value = ["litter_box_full", "temperature"]
        scheduler.analyzer.reload_rules.return_value = None
        with patch("lumi.deps.get_proactive_scheduler", return_value=scheduler), \
             patch("lumi.proactive.router.load_rules_config") as mock_load, \
             patch("lumi.proactive.router.get_config") as mock_cfg:
            from lumi.proactive.rules_loader import RulesConfig
            mock_load.return_value = RulesConfig()
            mock_cfg.return_value = MagicMock(proactive=MagicMock(rules_file="~/.lumi/rules.yaml"))
            resp = client.post("/api/proactive/reload")
        data = resp.json()
        assert "active_rules" in data
        assert "litter_box_full" in data["active_rules"]

    def test_returns_disabled_rules(self):
        scheduler = MagicMock()
        scheduler.analyzer.active_rule_names.return_value = ["litter_box_full"]
        scheduler.analyzer.reload_rules.return_value = None
        with patch("lumi.deps.get_proactive_scheduler", return_value=scheduler), \
             patch("lumi.proactive.router.load_rules_config") as mock_load, \
             patch("lumi.proactive.router.get_config") as mock_cfg:
            from lumi.proactive.rules_loader import RulesConfig
            mock_load.return_value = RulesConfig(disabled_rules=["temperature"])
            mock_cfg.return_value = MagicMock(proactive=MagicMock(rules_file="~/.lumi/rules.yaml"))
            resp = client.post("/api/proactive/reload")
        data = resp.json()
        assert "disabled_rules" in data
        assert "temperature" in data["disabled_rules"]

    def test_no_scheduler_returns_error(self):
        with patch("lumi.deps.get_proactive_scheduler", return_value=None):
            resp = client.post("/api/proactive/reload")
        assert resp.status_code == 200
        assert resp.json()["ok"] is False
        assert "error" in resp.json()

    def test_calls_reload_rules_on_analyzer(self):
        scheduler = MagicMock()
        scheduler.analyzer.active_rule_names.return_value = []
        with patch("lumi.deps.get_proactive_scheduler", return_value=scheduler), \
             patch("lumi.proactive.router.load_rules_config") as mock_load, \
             patch("lumi.proactive.router.get_config") as mock_cfg:
            from lumi.proactive.rules_loader import RulesConfig
            rc = RulesConfig()
            mock_load.return_value = rc
            mock_cfg.return_value = MagicMock(proactive=MagicMock(rules_file="~/.lumi/rules.yaml"))
            client.post("/api/proactive/reload")
        scheduler.analyzer.reload_rules.assert_called_once_with(rc)


# ─── proactive_reload lumi_tool ───────────────────────────────────────────────


class TestProactiveReloadLumiTool:
    def test_proactive_reload_calls_post(self):
        import lumi.lumi_tool as tool_module
        mock_post = MagicMock(return_value={"ok": True, "active_rules": []})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            result = tool_module.proactive_reload()
        mock_post.assert_called_once_with("/api/proactive/reload", {})
        assert result["ok"] is True

    def test_proactive_reload_in_valid_actions(self):
        from lumi.lumi_tool import _VALID_ACTIONS
        assert "proactive_reload" in _VALID_ACTIONS

    def test_proactive_reload_dispatchable(self):
        import lumi.lumi_tool as tool_module
        from lumi.lumi_tool import dispatch
        mock_post = MagicMock(return_value={"ok": True, "active_rules": ["temperature"]})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            result = dispatch("proactive_reload")
        assert result["ok"] is True

    def test_proactive_reload_in_mcp_registered_tools(self):
        from lumi.mcp_server import REGISTERED_TOOLS
        assert "lumi_proactive_reload" in REGISTERED_TOOLS

    def test_mcp_registered_tools_matches_valid_actions(self):
        """REGISTERED_TOOLS 与 _VALID_ACTIONS 严格一致（mcp_server 顶层断言的回归测试）。"""
        from lumi.mcp_server import REGISTERED_TOOLS
        from lumi.lumi_tool import _VALID_ACTIONS
        expected = frozenset(f"lumi_{a}" for a in _VALID_ACTIONS)
        assert REGISTERED_TOOLS == expected
