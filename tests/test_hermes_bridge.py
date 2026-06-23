"""tests/test_hermes_bridge.py — HermesBridge 单元测试。"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from lumi.hermes_bridge import CooldownTracker, HermesBridge, NotifyResult, get_bridge
from lumi.perception.analyzer import PerceptionDecision
from lumi.perception.events import PerceptionEvent, PerceptionEventType


# ─── fixtures ────────────────────────────────────────────────────────────────

def _make_event(
    event_type: PerceptionEventType = PerceptionEventType.ANOMALY_DETECTED,
    room: str | None = "客厅",
) -> PerceptionEvent:
    return PerceptionEvent(event_id="test-001", event_type=event_type, room=room)


def _make_decision(should_notify: bool = True, message: str = "测试通知") -> PerceptionDecision:
    return PerceptionDecision(should_notify=should_notify, message=message, reason="test")


# ─── CooldownTracker ─────────────────────────────────────────────────────────

class TestCooldownTracker:
    def test_initially_cooled_down(self):
        tracker = CooldownTracker(default_cooldown=60)
        assert tracker.is_cooled_down("key1") is True

    def test_not_cooled_after_mark(self):
        tracker = CooldownTracker(default_cooldown=60)
        tracker.mark_sent("key1")
        assert tracker.is_cooled_down("key1") is False

    def test_cooled_after_time_passes(self):
        tracker = CooldownTracker(default_cooldown=1)
        tracker.mark_sent("key1")
        time.sleep(1.1)
        assert tracker.is_cooled_down("key1") is True

    def test_remaining_zero_before_mark(self):
        tracker = CooldownTracker(default_cooldown=60)
        assert tracker.remaining("key1") == 0.0

    def test_remaining_positive_after_mark(self):
        tracker = CooldownTracker(default_cooldown=60)
        tracker.mark_sent("key1")
        remaining = tracker.remaining("key1")
        assert 55 < remaining <= 60

    def test_custom_cooldown_override(self):
        tracker = CooldownTracker(default_cooldown=60)
        tracker.mark_sent("key1")
        # 0 秒冷却 → 已冷却
        assert tracker.is_cooled_down("key1", cooldown=0) is True
        # 3600 秒冷却 → 未冷却
        assert tracker.is_cooled_down("key1", cooldown=3600) is False

    def test_different_keys_independent(self):
        tracker = CooldownTracker(default_cooldown=60)
        tracker.mark_sent("key1")
        assert tracker.is_cooled_down("key1") is False
        assert tracker.is_cooled_down("key2") is True


# ─── HermesBridge.notify — skip cases ────────────────────────────────────────

class TestHermesBridgeSkip:
    def test_skip_when_should_not_notify(self):
        bridge = HermesBridge()
        event = _make_event()
        decision = _make_decision(should_notify=False, message="")
        result = bridge.notify(event, decision)
        assert result.skipped is True
        assert result.success is True

    def test_skip_when_no_message(self):
        bridge = HermesBridge()
        event = _make_event()
        decision = PerceptionDecision(should_notify=True, message=None, reason="no msg")
        result = bridge.notify(event, decision)
        assert result.skipped is True

    def test_skip_during_cooldown(self):
        tracker = CooldownTracker(default_cooldown=3600)
        bridge = HermesBridge(cooldown_tracker=tracker)
        event = _make_event(PerceptionEventType.ANOMALY_DETECTED, room="客厅")
        decision = _make_decision()

        # 先标记已发送（key 格式与 notify() 内部一致）
        tracker.mark_sent(f"{PerceptionEventType.ANOMALY_DETECTED}:客厅")

        result = bridge.notify(event, decision)
        assert result.skipped is True
        assert "冷却中" in result.skip_reason

    def test_force_bypasses_cooldown(self):
        tracker = CooldownTracker(default_cooldown=3600)
        bridge = HermesBridge(cooldown_tracker=tracker)
        event = _make_event(PerceptionEventType.ANOMALY_DETECTED, room="客厅")
        decision = _make_decision()
        tracker.mark_sent("anomaly_detected:客厅")

        with patch("lumi.hermes_bridge._hermes_send", return_value={"ok": True}):
            result = bridge.notify(event, decision, force=True)

        assert result.skipped is False
        assert result.success is True


# ─── HermesBridge.notify — send cases ────────────────────────────────────────

class TestHermesBridgeSend:
    def test_successful_send(self):
        bridge = HermesBridge()
        event = _make_event()
        decision = _make_decision()

        with patch("lumi.hermes_bridge._hermes_send", return_value={"status": "sent"}) as mock_send:
            result = bridge.notify(event, decision)

        assert result.success is True
        assert result.skipped is False
        assert result.message == "测试通知"
        mock_send.assert_called_once_with("测试通知", bridge.target)

    def test_marks_cooldown_after_send(self):
        bridge = HermesBridge()
        event = _make_event(PerceptionEventType.ANOMALY_DETECTED, room="客厅")
        decision = _make_decision()

        with patch("lumi.hermes_bridge._hermes_send", return_value={}):
            bridge.notify(event, decision)

        # 第二次应被限流
        result2 = bridge.notify(event, decision)
        assert result2.skipped is True

    def test_send_failure_returns_error_result(self):
        bridge = HermesBridge()
        event = _make_event()
        decision = _make_decision()

        with patch("lumi.hermes_bridge._hermes_send", side_effect=RuntimeError("连接拒绝")):
            result = bridge.notify(event, decision)

        assert result.success is False
        assert "连接拒绝" in result.error

    def test_send_uses_configured_target(self):
        bridge = HermesBridge(target="telegram")
        event = _make_event()
        decision = _make_decision()

        with patch("lumi.hermes_bridge._hermes_send", return_value={}) as mock_send:
            bridge.notify(event, decision)

        mock_send.assert_called_once_with("测试通知", "telegram")


# ─── 各事件类型冷却时间 ────────────────────────────────────────────────────────

class TestEventCooldowns:
    @pytest.mark.parametrize("event_type,room", [
        (PerceptionEventType.LITTER_BOX_FULL, "卫生间"),
        (PerceptionEventType.PERSON_DETECTED, "门口"),
        (PerceptionEventType.ANOMALY_DETECTED, "客厅"),
        (PerceptionEventType.PET_DETECTED, None),
    ])
    def test_cooldown_applied_after_send(self, event_type, room):
        bridge = HermesBridge()
        event = _make_event(event_type, room)
        decision = _make_decision()

        with patch("lumi.hermes_bridge._hermes_send", return_value={}):
            r1 = bridge.notify(event, decision)

        assert r1.success is True and not r1.skipped

        r2 = bridge.notify(event, decision)
        assert r2.skipped is True


# ─── 日志写入 ─────────────────────────────────────────────────────────────────

class TestBridgeLogging:
    def test_log_written_on_send(self, tmp_path):
        bridge = HermesBridge()
        bridge._log_path = str(tmp_path / "lumi_bridge.log")
        event = _make_event()
        decision = _make_decision()

        with patch("lumi.hermes_bridge._hermes_send", return_value={}):
            bridge.notify(event, decision)

        log_content = (tmp_path / "lumi_bridge.log").read_text()
        entry = json.loads(log_content.strip())
        assert entry["event_type"] == "anomaly_detected"
        assert entry["success"] is True
        assert entry["skipped"] is False

    def test_log_written_on_skip(self, tmp_path):
        bridge = HermesBridge()
        bridge._log_path = str(tmp_path / "lumi_bridge.log")
        event = _make_event()
        decision = _make_decision(should_notify=False, message="")

        bridge.notify(event, decision)

        log_content = (tmp_path / "lumi_bridge.log").read_text()
        entry = json.loads(log_content.strip())
        assert entry["skipped"] is True


# ─── 全局单例 ─────────────────────────────────────────────────────────────────

class TestGetBridge:
    def test_singleton(self):
        import lumi.hermes_bridge as hb
        hb._bridge = None  # reset
        b1 = get_bridge()
        b2 = get_bridge()
        assert b1 is b2

    def test_singleton_reset(self):
        import lumi.hermes_bridge as hb
        hb._bridge = None
        b1 = get_bridge()
        hb._bridge = None
        b2 = get_bridge()
        assert b1 is not b2
