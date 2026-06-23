"""device_graph/fusion.py 单元测试。"""

from __future__ import annotations

import pytest
from lumi.device_graph.fusion import ha_states_to_devices, infer_room as _infer_room


# ─── _infer_room ─────────────────────────────────────────────────────────────

class TestInferRoom:
    def test_chinese_room_from_entity_id(self):
        assert _infer_room("light.卧室_ceiling", "") == "卧室"

    def test_english_room_from_entity_id(self):
        assert _infer_room("light.living_room_lamp", "") == "客厅"

    def test_room_from_friendly_name(self):
        assert _infer_room("light.unknown_abc", "客厅吸顶灯") == "客厅"

    def test_bathroom_variants(self):
        assert _infer_room("sensor.bathroom_humidity", "") == "卫生间"
        assert _infer_room("sensor.toilet_sensor", "") == "卫生间"

    def test_no_match_returns_none(self):
        assert _infer_room("sensor.petjc_cn_litter_box", "") is None

    def test_priority_first_match_wins(self):
        # "master_bedroom" 匹配卧室，不会匹配到其他
        assert _infer_room("light.master_bedroom_lamp", "") == "卧室"

    def test_storage_room(self):
        assert _infer_room("switch.storage_light", "") == "储藏室"


# ─── ha_states_to_devices — 基础转换 ─────────────────────────────────────────

def _make_state(entity_id: str, state: str = "on", attrs: dict | None = None) -> dict:
    return {
        "entity_id": entity_id,
        "state": state,
        "attributes": attrs or {},
    }


class TestHaStatesToDevices:
    def test_basic_light(self):
        states = [_make_state("light.living_room", "on", {"friendly_name": "客厅灯"})]
        devices = ha_states_to_devices(states)
        assert len(devices) == 1
        d = devices[0]
        assert d.id == "light.living_room"
        assert d.type == "light"
        assert d.platform == "ha"
        assert d.state == "on"
        assert d.name == "客厅灯"
        assert "toggle" in d.capabilities
        assert "brightness" in d.capabilities

    def test_unknown_domain_preserved(self):
        states = [_make_state("custom_domain.my_device", "idle")]
        devices = ha_states_to_devices(states)
        assert len(devices) == 1
        assert devices[0].type == "custom_domain"

    def test_skips_empty_entity_id(self):
        states = [{"entity_id": "", "state": "on", "attributes": {}}]
        devices = ha_states_to_devices(states)
        assert len(devices) == 0

    def test_room_inferred_from_entity_id(self):
        states = [_make_state("sensor.bedroom_temperature", "22.5")]
        devices = ha_states_to_devices(states)
        assert devices[0].room == "卧室"

    def test_room_inferred_from_friendly_name(self):
        states = [_make_state("sensor.abc_123", "on", {"friendly_name": "厨房传感器"})]
        devices = ha_states_to_devices(states)
        assert devices[0].room == "厨房"

    def test_no_room_when_no_match(self):
        states = [_make_state("sensor.petjc_cn_litter_box", "off")]
        devices = ha_states_to_devices(states)
        assert devices[0].room is None

    def test_fan_capabilities(self):
        states = [_make_state("fan.air_purifier", "off")]
        devices = ha_states_to_devices(states)
        assert "toggle" in devices[0].capabilities
        assert "speed" in devices[0].capabilities

    def test_vacuum_capabilities(self):
        states = [_make_state("vacuum.dreame", "docked")]
        devices = ha_states_to_devices(states)
        assert "start" in devices[0].capabilities
        assert "stop" in devices[0].capabilities

    def test_empty_states_returns_empty(self):
        assert ha_states_to_devices([]) == []

    def test_multiple_devices(self):
        states = [
            _make_state("light.a", "on"),
            _make_state("switch.b", "off"),
            _make_state("sensor.c", "22.5"),
        ]
        devices = ha_states_to_devices(states)
        assert len(devices) == 3
        types = {d.type for d in devices}
        assert types == {"light", "switch", "sensor"}


# ─── aliases 覆盖 ─────────────────────────────────────────────────────────────

class TestAliases:
    def test_alias_overrides_name(self):
        states = [_make_state("fan.zhimi_airpurifier_ma2", "off", {"friendly_name": "米家净化器"})]
        aliases = [{"entity_id": "fan.zhimi_airpurifier_ma2", "name": "客厅空气净化器"}]
        devices = ha_states_to_devices(states, aliases=aliases)
        assert devices[0].name == "客厅空气净化器"

    def test_alias_overrides_room(self):
        states = [_make_state("sensor.unknown_sensor", "on")]
        aliases = [{"entity_id": "sensor.unknown_sensor", "room": "卫生间"}]
        devices = ha_states_to_devices(states, aliases=aliases)
        assert devices[0].room == "卫生间"

    def test_alias_overrides_icon(self):
        states = [_make_state("fan.purifier", "on")]
        aliases = [{"entity_id": "fan.purifier", "icon": "mdi:air-purifier"}]
        devices = ha_states_to_devices(states, aliases=aliases)
        assert devices[0].icon == "mdi:air-purifier"

    def test_alias_partial_override(self):
        """只覆盖 name，room 仍从 entity_id 推断。"""
        states = [_make_state("light.bedroom_lamp", "on", {"friendly_name": "原始名"})]
        aliases = [{"entity_id": "light.bedroom_lamp", "name": "卧室主灯"}]
        devices = ha_states_to_devices(states, aliases=aliases)
        assert devices[0].name == "卧室主灯"
        assert devices[0].room == "卧室"  # 从 entity_id 推断

    def test_alias_for_nonexistent_entity_ignored(self):
        states = [_make_state("light.real_device", "on")]
        aliases = [{"entity_id": "light.ghost_device", "name": "幽灵设备"}]
        devices = ha_states_to_devices(states, aliases=aliases)
        assert len(devices) == 1
        assert devices[0].id == "light.real_device"

    def test_empty_aliases(self):
        states = [_make_state("light.test", "on", {"friendly_name": "测试灯"})]
        devices = ha_states_to_devices(states, aliases=[])
        assert devices[0].name == "测试灯"
