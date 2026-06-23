"""感知事件 + 闭环分析器单元测试。"""

from __future__ import annotations

import pytest
from lumi.perception.events import PerceptionEvent, PerceptionEventType, PerceptionSubject
from lumi.perception.analyzer import PerceptionAnalyzer


# ─── PerceptionEvent.from_miloco_webhook ────────────────────────────────────

class TestPerceptionEventParsing:
    def test_parse_litter_box_full(self) -> None:
        payload = {
            "event_type": "litter_box_full",
            "camera_id": "cam_001",
            "room": "卫生间",
        }
        event = PerceptionEvent.from_miloco_webhook(payload)
        assert event.event_type == PerceptionEventType.LITTER_BOX_FULL
        assert event.camera_id == "cam_001"
        assert event.room == "卫生间"

    def test_parse_pet_detected_with_subject(self) -> None:
        payload = {
            "event_type": "pet_detected",
            "room": "客厅",
            "subjects": [
                {"type": "cat", "name": "猫猫", "confidence": 0.95}
            ],
        }
        event = PerceptionEvent.from_miloco_webhook(payload)
        assert event.event_type == PerceptionEventType.PET_DETECTED
        assert len(event.subjects) == 1
        assert event.subjects[0].name == "猫猫"
        assert event.subjects[0].confidence == 0.95

    def test_parse_unknown_event_type(self) -> None:
        payload = {"event_type": "some_future_event"}
        event = PerceptionEvent.from_miloco_webhook(payload)
        assert event.event_type == PerceptionEventType.UNKNOWN

    def test_primary_subject_highest_confidence(self) -> None:
        payload = {
            "event_type": "pet_detected",
            "subjects": [
                {"type": "cat", "name": "A", "confidence": 0.7},
                {"type": "cat", "name": "B", "confidence": 0.95},
            ],
        }
        event = PerceptionEvent.from_miloco_webhook(payload)
        assert event.primary_subject().name == "B"

    def test_has_subject_type(self) -> None:
        payload = {
            "event_type": "pet_detected",
            "subjects": [{"type": "cat", "confidence": 0.9}],
        }
        event = PerceptionEvent.from_miloco_webhook(payload)
        assert event.has_subject_type("cat") is True
        assert event.has_subject_type("dog") is False


# ─── PerceptionAnalyzer — 猫砂盆场景 ────────────────────────────────────────

class TestAnalyzerLitterBox:
    def setup_method(self) -> None:
        self.analyzer = PerceptionAnalyzer(ha_client=None)

    def test_litter_box_full_no_ha(self) -> None:
        """集便仓满，HA 不可用 → 推微信"""
        event = PerceptionEvent.from_miloco_webhook({"event_type": "litter_box_full"})
        d = self.analyzer.analyze(event)
        assert d.should_notify is True
        assert d.message is not None
        assert "满" in d.message

    def test_pet_at_litter_box_no_ha(self) -> None:
        """宠物进猫砂盆，HA 不可用 → 不通知"""
        event = PerceptionEvent.from_miloco_webhook({"event_type": "pet_at_litter_box"})
        d = self.analyzer.analyze(event)
        assert d.should_notify is False

    def test_pet_left_litter_box_no_ha(self) -> None:
        """宠物离开，HA 不可用 → 不通知"""
        event = PerceptionEvent.from_miloco_webhook({"event_type": "pet_left_litter_box"})
        d = self.analyzer.analyze(event)
        assert d.should_notify is False


# ─── PerceptionAnalyzer — HA 注入场景 ────────────────────────────────────────

class MockHAClient:
    """测试用 HA 客户端 mock。"""
    def __init__(self, states: list) -> None:
        self._states = states

    def get_states(self) -> list:
        return self._states


class TestAnalyzerWithHA:
    def test_litter_box_full_ha_confirms(self) -> None:
        ha = MockHAClient(states=[
            {"entity_id": "binary_sensor.petjc_cn_trash_full", "state": "on", "attributes": {}}
        ])
        analyzer = PerceptionAnalyzer(ha_client=ha)
        event = PerceptionEvent.from_miloco_webhook({"event_type": "litter_box_full"})
        d = analyzer.analyze(event)
        assert d.should_notify is True
        assert "双重确认" in d.reason or d.message is not None

    def test_litter_box_full_ha_disagrees(self) -> None:
        ha = MockHAClient(states=[
            {"entity_id": "binary_sensor.petjc_cn_trash_full", "state": "off", "attributes": {}}
        ])
        analyzer = PerceptionAnalyzer(ha_client=ha)
        event = PerceptionEvent.from_miloco_webhook({"event_type": "litter_box_full"})
        d = analyzer.analyze(event)
        # 感知说满但 HA 不确认，仍通知但降级
        assert d.should_notify is True
        assert "误报" in d.reason

    def test_pet_at_litter_box_is_full(self) -> None:
        ha = MockHAClient(states=[
            {"entity_id": "binary_sensor.petjc_cn_trash_full", "state": "on", "attributes": {}}
        ])
        analyzer = PerceptionAnalyzer(ha_client=ha)
        event = PerceptionEvent.from_miloco_webhook({"event_type": "pet_at_litter_box"})
        d = analyzer.analyze(event)
        assert d.should_notify is True
        assert "满" in (d.message or "")

    def test_pet_at_litter_box_off_mode(self) -> None:
        ha = MockHAClient(states=[
            {"entity_id": "switch.petjc_cn_switch", "state": "off", "attributes": {}}
        ])
        analyzer = PerceptionAnalyzer(ha_client=ha)
        event = PerceptionEvent.from_miloco_webhook({"event_type": "pet_at_litter_box"})
        d = analyzer.analyze(event)
        assert d.should_notify is False

    def test_pet_left_litter_box_bin_full(self) -> None:
        """宠物离开 + 集便仓满 → 通知。"""
        ha = MockHAClient(states=[
            {"entity_id": "binary_sensor.petjc_cn_trash_full", "state": "on", "attributes": {}}
        ])
        analyzer = PerceptionAnalyzer(ha_client=ha)
        event = PerceptionEvent.from_miloco_webhook({"event_type": "pet_left_litter_box"})
        d = analyzer.analyze(event)
        assert d.should_notify is True
        assert "满" in (d.message or "")

    def test_pet_left_litter_box_bin_ok(self) -> None:
        """宠物离开 + 集便仓未满 → 不通知。"""
        ha = MockHAClient(states=[
            {"entity_id": "binary_sensor.petjc_cn_trash_full", "state": "off", "attributes": {}}
        ])
        analyzer = PerceptionAnalyzer(ha_client=ha)
        event = PerceptionEvent.from_miloco_webhook({"event_type": "pet_left_litter_box"})
        d = analyzer.analyze(event)
        assert d.should_notify is False


# ─── PerceptionAnalyzer — 通用感知 ──────────────────────────────────────────

class TestAnalyzerGeneral:
    def setup_method(self) -> None:
        self.analyzer = PerceptionAnalyzer(ha_client=None)

    def test_pet_detected_normal_room(self) -> None:
        event = PerceptionEvent.from_miloco_webhook({
            "event_type": "pet_detected",
            "room": "客厅",
        })
        d = self.analyzer.analyze(event)
        assert d.should_notify is False

    def test_pet_detected_sensitive_room(self) -> None:
        event = PerceptionEvent.from_miloco_webhook({
            "event_type": "pet_detected",
            "room": "门口",
        })
        d = self.analyzer.analyze(event)
        assert d.should_notify is True

    def test_person_detected_known(self) -> None:
        event = PerceptionEvent.from_miloco_webhook({
            "event_type": "person_detected",
            "subjects": [{"type": "person", "name": "张", "confidence": 0.98}],
        })
        d = self.analyzer.analyze(event)
        assert d.should_notify is False

    def test_person_detected_unknown(self) -> None:
        event = PerceptionEvent.from_miloco_webhook({
            "event_type": "person_detected",
            "room": "客厅",
        })
        d = self.analyzer.analyze(event)
        assert d.should_notify is True
        assert "陌生人" in (d.message or "")

    def test_unknown_event_no_notify(self) -> None:
        event = PerceptionEvent.from_miloco_webhook({"event_type": "mystery_event"})
        d = self.analyzer.analyze(event)
        assert d.should_notify is False

    def test_litter_box_cleaned_no_notify(self) -> None:
        event = PerceptionEvent.from_miloco_webhook({"event_type": "litter_box_cleaned"})
        d = self.analyzer.analyze(event)
        assert d.should_notify is False

    def test_anomaly_detected_notify(self) -> None:
        event = PerceptionEvent.from_miloco_webhook({
            "event_type": "anomaly_detected",
            "room": "客厅",
            "subjects": [{"type": "fire", "confidence": 0.9}],
        })
        d = self.analyzer.analyze(event)
        assert d.should_notify is True
        assert "fire" in (d.message or "") or "异常" in (d.message or "")

    def test_motion_detected_no_notify(self) -> None:
        event = PerceptionEvent.from_miloco_webhook({"event_type": "motion_detected"})
        d = self.analyzer.analyze(event)
        assert d.should_notify is False
