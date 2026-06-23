"""策略守卫层单元测试。"""

from __future__ import annotations

import pytest
from lumi.device_graph.policy import (
    BlockedCommandRule,
    PolicyEngine,
    PolicyViolation,
    build_default_policy_engine,
)
from lumi.device_graph.schema import Device


def _make_device(device_id: str, dtype: str = "sensor", platform: str = "ha") -> Device:
    return Device(
        id=device_id,
        name=device_id,
        type=dtype,
        platform=platform,
        state="on",
        attributes={},
    )


# ─── 猫砂盆 empty 拦截 ─────────────────────────────────────────────────────────

class TestLitterBoxPolicy:
    def setup_method(self) -> None:
        self.engine = build_default_policy_engine()
        self.litter_box = _make_device("sensor.petjc_cn_821633016_pro_litter_box")

    def test_empty_command_blocked(self) -> None:
        v = self.engine.evaluate(self.litter_box, "empty", {})
        assert v is not None
        assert v.blocked is True
        assert "Empty" in v.reason or "empty" in v.reason.lower()

    def test_Empty_command_blocked(self) -> None:
        v = self.engine.evaluate(self.litter_box, "Empty", {})
        assert v is not None
        assert v.blocked is True

    def test_call_action_aiid3_blocked(self) -> None:
        v = self.engine.evaluate(self.litter_box, "call_action", {"siid": 2, "aiid": 3})
        assert v is not None
        assert v.blocked is True

    def test_empty_override_with_keyword(self) -> None:
        v = self.engine.evaluate(self.litter_box, "empty", {"_force": "CONFIRM_EMPTY"})
        assert v is None  # 强制覆盖放行

    def test_call_action_other_aiid_via_override(self) -> None:
        # call_action 被 litter_box_no_action_3 拦截，需要 override
        v = self.engine.evaluate(self.litter_box, "call_action", {"aiid": 1, "_force": "CONFIRM_EMPTY"})
        assert v is None  # override 放行

    def test_clean_command_allowed(self) -> None:
        v = self.engine.evaluate(self.litter_box, "turn_on", {})
        assert v is None

    def test_turn_off_allowed(self) -> None:
        v = self.engine.evaluate(self.litter_box, "turn_off", {})
        assert v is None


# ─── 非猫砂盆设备不受影响 ──────────────────────────────────────────────────────

class TestNonLitterBoxDevices:
    def setup_method(self) -> None:
        self.engine = build_default_policy_engine()

    def test_light_empty_command_allowed(self) -> None:
        light = _make_device("light.living_room", "light")
        v = self.engine.evaluate(light, "empty", {})
        assert v is None

    def test_vacuum_call_action_allowed(self) -> None:
        vacuum = _make_device("vacuum.dreame_s10", "vacuum")
        v = self.engine.evaluate(vacuum, "call_action", {"siid": 2, "aiid": 3})
        assert v is None


# ─── BlockedCommandRule 独立测试 ──────────────────────────────────────────────

class TestBlockedCommandRule:
    def test_fragment_no_match(self) -> None:
        rule = BlockedCommandRule(
            name="test", description="test",
            device_id_fragment="petjc",
            blocked_commands=["empty"],
        )
        device = _make_device("sensor.other_device")
        assert rule.check(device, "empty", {}) is None

    def test_command_no_match(self) -> None:
        rule = BlockedCommandRule(
            name="test", description="test",
            device_id_fragment="petjc",
            blocked_commands=["empty"],
        )
        device = _make_device("sensor.petjc_device")
        assert rule.check(device, "turn_on", {}) is None

    def test_both_match_blocked(self) -> None:
        rule = BlockedCommandRule(
            name="test", description="test",
            device_id_fragment="petjc",
            blocked_commands=["empty"],
        )
        device = _make_device("sensor.petjc_device")
        v = rule.check(device, "empty", {})
        assert v is not None
        assert v.blocked is True
        assert v.rule_name == "test"


# ─── 空引擎放行所有 ───────────────────────────────────────────────────────────

def test_empty_engine_allows_everything() -> None:
    engine = PolicyEngine(rules=[])
    device = _make_device("sensor.petjc_cn_821633016_pro")
    assert engine.evaluate(device, "empty", {}) is None
    assert engine.evaluate(device, "call_action", {"aiid": 3}) is None
