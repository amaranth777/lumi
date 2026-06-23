"""miloco/fusion.py 单元测试。"""

from __future__ import annotations

import pytest
from lumi.miloco.fusion import miloco_devices_to_lumi


def _make_miloco_device(
    did: str = "123456",
    name: str = "测试设备",
    category: str = "light",
    online: bool = True,
    model: str = "xiaomi.light.xx",
    home_name: str = "我的家",
) -> dict:
    return {
        "did": did,
        "name": name,
        "category": category,
        "online": online,
        "model": model,
        "home_name": home_name,
    }


# ─── 基础转换 ─────────────────────────────────────────────────────────────────

class TestMilocoDevicesToLumi:
    def test_basic_light(self):
        devs = miloco_devices_to_lumi([_make_miloco_device(category="light")])
        assert len(devs) == 1
        d = devs[0]
        assert d.id == "miloco.123456"
        assert d.type == "light"
        assert d.platform == "miloco"
        assert d.state == "online"
        assert "toggle" in d.capabilities

    def test_offline_device(self):
        devs = miloco_devices_to_lumi([_make_miloco_device(online=False)])
        assert devs[0].state == "offline"

    def test_skips_empty_did(self):
        raw = {"did": "", "name": "空did设备", "category": "light", "online": True}
        devs = miloco_devices_to_lumi([raw])
        assert len(devs) == 0

    def test_skips_missing_did(self):
        raw = {"name": "无did设备", "category": "light", "online": True}
        devs = miloco_devices_to_lumi([raw])
        assert len(devs) == 0

    def test_empty_input(self):
        assert miloco_devices_to_lumi([]) == []

    def test_multiple_devices(self):
        devs = miloco_devices_to_lumi([
            _make_miloco_device("1", category="light"),
            _make_miloco_device("2", category="fan"),
            _make_miloco_device("3", category="sensor"),
        ])
        assert len(devs) == 3
        ids = {d.id for d in devs}
        assert ids == {"miloco.1", "miloco.2", "miloco.3"}

    def test_attributes_populated(self):
        devs = miloco_devices_to_lumi([_make_miloco_device(
            did="abc", model="xiaomi.light.bla", home_name="我家"
        )])
        attrs = devs[0].attributes
        assert attrs["did"] == "abc"
        assert attrs["model"] == "xiaomi.light.bla"
        assert attrs["home_name"] == "我家"
        assert attrs["online"] is True

    def test_room_inferred_from_name(self):
        """设备名包含房间关键词时应推断出房间。"""
        devs = miloco_devices_to_lumi([_make_miloco_device(name="卧室灯")])
        assert devs[0].room == "卧室"

    def test_room_none_when_no_keyword(self):
        """设备名无房间关键词时 room 为 None。"""
        devs = miloco_devices_to_lumi([_make_miloco_device(name="神秘设备")])
        assert devs[0].room is None

    def test_room_living_room(self):
        devs = miloco_devices_to_lumi([_make_miloco_device(name="客厅空调")])
        assert devs[0].room == "客厅"

    def test_metadata_source(self):
        devs = miloco_devices_to_lumi([_make_miloco_device()])
        assert devs[0].metadata.get("source") == "miloco"


# ─── 类型映射 ─────────────────────────────────────────────────────────────────

class TestCategoryTypeMapping:
    @pytest.mark.parametrize("category,expected_type", [
        ("light", "light"),
        ("switch", "switch"),
        ("outlet", "switch"),
        ("air_purifier", "fan"),
        ("humidifier", "humidifier"),
        ("climate", "climate"),
        ("air_conditioner", "climate"),
        ("fan", "fan"),
        ("vacuum", "vacuum"),
        ("cover", "cover"),
        ("curtain", "cover"),
        ("camera", "camera"),
        ("speaker", "media_player"),
        ("tv", "media_player"),
        ("pet_feeder", "appliance"),
        ("washing_machine", "appliance"),
        ("gateway", "gateway"),
    ])
    def test_category_to_type(self, category, expected_type):
        devs = miloco_devices_to_lumi([_make_miloco_device(category=category)])
        assert devs[0].type == expected_type

    def test_unknown_category_preserved(self):
        devs = miloco_devices_to_lumi([_make_miloco_device(category="future_device")])
        assert devs[0].type == "future_device"

    def test_empty_category(self):
        devs = miloco_devices_to_lumi([_make_miloco_device(category="")])
        assert devs[0].type == "unknown"


# ─── 能力映射 ─────────────────────────────────────────────────────────────────

class TestCapabilities:
    def test_light_capabilities(self):
        devs = miloco_devices_to_lumi([_make_miloco_device(category="light")])
        caps = devs[0].capabilities
        assert "toggle" in caps
        assert "brightness" in caps

    def test_climate_capabilities(self):
        devs = miloco_devices_to_lumi([_make_miloco_device(category="climate")])
        caps = devs[0].capabilities
        assert "toggle" in caps
        assert "set_temperature" in caps

    def test_sensor_no_capabilities(self):
        devs = miloco_devices_to_lumi([_make_miloco_device(category="sensor")])
        assert devs[0].capabilities == []

    def test_lock_capabilities(self):
        devs = miloco_devices_to_lumi([_make_miloco_device(category="lock")])
        assert "lock" in devs[0].capabilities
        assert "unlock" in devs[0].capabilities
