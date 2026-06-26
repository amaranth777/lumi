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


# ─── _execute_miloco_command 分支测试 ─────────────────────────────────────────


from unittest.mock import MagicMock
from lumi.device_graph.service import DeviceGraphService
from lumi.device_graph.schema import Device, CommandResponse
from lumi.device_graph.policy import build_default_policy_engine


def _make_miloco_device_node(
    did: str = "dev_001",
    device_id: str | None = None,
) -> Device:
    """构建一个 Miloco 平台 Device 节点（供 service 测试用）。"""
    return Device(
        id=device_id or f"miloco.{did}",
        name="测试Miloco设备",
        type="light",
        platform="miloco",
        state="online",
        attributes={"did": did},
        capabilities=["toggle"],
    )


def _make_miloco_service(
    miloco_mock: MagicMock | None = None,
    ha_mock: MagicMock | None = None,
    devices: list[Device] | None = None,
) -> DeviceGraphService:
    """构建一个带预填充图的 DeviceGraphService。"""
    from lumi.device_graph.schema import DeviceGraph

    svc = DeviceGraphService(
        ha_client=ha_mock,
        miloco_client=miloco_mock,
        policy_engine=build_default_policy_engine(),
    )
    # 直接注入缓存图，跳过网络调用
    if devices is not None:
        svc._cached_graph = DeviceGraph(devices=devices, rooms={})
        import time
        svc._cache_time = time.monotonic()
    return svc


class TestExecuteMilocoCommand:
    """_execute_miloco_command 各分支的单元测试。"""

    def test_turn_on_calls_set_property(self):
        miloco = MagicMock()
        miloco.set_property.return_value = True
        dev = _make_miloco_device_node(did="dev001")
        svc = _make_miloco_service(miloco_mock=miloco, devices=[dev])

        resp = svc.execute_command("miloco.dev001", "turn_on", {})
        assert resp.success is True
        miloco.set_property.assert_called_once_with("dev001", 2, 1, True)

    def test_turn_off_calls_set_property(self):
        miloco = MagicMock()
        miloco.set_property.return_value = True
        dev = _make_miloco_device_node(did="dev002")
        svc = _make_miloco_service(miloco_mock=miloco, devices=[dev])

        resp = svc.execute_command("miloco.dev002", "turn_off", {})
        assert resp.success is True
        miloco.set_property.assert_called_once_with("dev002", 2, 1, False)

    def test_toggle_reads_status_then_flips(self):
        miloco = MagicMock()
        miloco.get_device_status.return_value = {
            "properties": [{"iid": "prop.2.1", "value": False}]
        }
        miloco.set_property.return_value = True
        dev = _make_miloco_device_node(did="dev003")
        svc = _make_miloco_service(miloco_mock=miloco, devices=[dev])

        resp = svc.execute_command("miloco.dev003", "toggle", {})
        assert resp.success is True
        miloco.get_device_status.assert_called_once_with("dev003")
        # current=False → should toggle to True
        miloco.set_property.assert_called_once_with("dev003", 2, 1, True)

    def test_toggle_flips_from_true_to_false(self):
        miloco = MagicMock()
        miloco.get_device_status.return_value = {
            "properties": [{"iid": "prop.2.1", "value": True}]
        }
        miloco.set_property.return_value = True
        dev = _make_miloco_device_node(did="dev004")
        svc = _make_miloco_service(miloco_mock=miloco, devices=[dev])

        resp = svc.execute_command("miloco.dev004", "toggle", {})
        assert resp.success is True
        miloco.set_property.assert_called_once_with("dev004", 2, 1, False)

    def test_set_property_passes_params(self):
        miloco = MagicMock()
        miloco.set_property.return_value = True
        dev = _make_miloco_device_node(did="dev005")
        svc = _make_miloco_service(miloco_mock=miloco, devices=[dev])

        resp = svc.execute_command(
            "miloco.dev005", "set_property", {"siid": 3, "piid": 2, "value": 50}
        )
        assert resp.success is True
        miloco.set_property.assert_called_once_with("dev005", 3, 2, 50)

    def test_set_property_failure(self):
        miloco = MagicMock()
        miloco.set_property.return_value = False
        dev = _make_miloco_device_node(did="dev006")
        svc = _make_miloco_service(miloco_mock=miloco, devices=[dev])

        resp = svc.execute_command("miloco.dev006", "set_property", {"siid": 2, "piid": 1, "value": 100})
        assert resp.success is False
        assert "失败" in resp.message

    def test_call_action_passes_params(self):
        miloco = MagicMock()
        miloco.call_action.return_value = True
        dev = _make_miloco_device_node(did="dev007")
        svc = _make_miloco_service(miloco_mock=miloco, devices=[dev])

        resp = svc.execute_command(
            "miloco.dev007", "call_action", {"siid": 2, "aiid": 2, "params": [1, 2]}
        )
        assert resp.success is True
        miloco.call_action.assert_called_once_with("dev007", 2, 2, [1, 2])

    def test_call_action_default_params(self):
        miloco = MagicMock()
        miloco.call_action.return_value = True
        dev = _make_miloco_device_node(did="dev008")
        svc = _make_miloco_service(miloco_mock=miloco, devices=[dev])

        resp = svc.execute_command("miloco.dev008", "call_action", {})
        assert resp.success is True
        # default siid=2, aiid=1, params=[]
        miloco.call_action.assert_called_once_with("dev008", 2, 1, [])

    def test_unsupported_command_returns_failure(self):
        miloco = MagicMock()
        dev = _make_miloco_device_node(did="dev009")
        svc = _make_miloco_service(miloco_mock=miloco, devices=[dev])

        resp = svc.execute_command("miloco.dev009", "fly_to_moon", {})
        assert resp.success is False
        assert "不支持" in resp.message

    def test_missing_did_returns_failure(self):
        miloco = MagicMock()
        dev = Device(
            id="miloco.nodid",
            name="无did设备",
            type="light",
            platform="miloco",
            state="online",
            attributes={},  # no did
        )
        svc = _make_miloco_service(miloco_mock=miloco, devices=[dev])

        resp = svc.execute_command("miloco.nodid", "turn_on", {})
        assert resp.success is False
        assert "did" in resp.message

    def test_miloco_no_client_returns_failure(self):
        """miloco 设备但 miloco_client 为 None → 返回失败。"""
        dev = _make_miloco_device_node(did="dev010")
        svc = _make_miloco_service(miloco_mock=None, devices=[dev])
        # service has no miloco_client

        resp = svc.execute_command("miloco.dev010", "turn_on", {})
        assert resp.success is False
        assert "未初始化" in resp.message


class TestMilocoVsHARouting:
    """确保 Miloco 平台设备走 _execute_miloco_command，HA 平台走 HA call_service。"""

    def test_miloco_device_uses_miloco_client(self):
        miloco = MagicMock()
        miloco.set_property.return_value = True
        ha = MagicMock()

        dev = _make_miloco_device_node(did="miloco_dev")
        svc = _make_miloco_service(miloco_mock=miloco, ha_mock=ha, devices=[dev])

        svc.execute_command("miloco.miloco_dev", "turn_on", {})
        miloco.set_property.assert_called_once()
        # HA call_service 不应被调用
        ha.call_service.assert_not_called()

    def test_ha_device_uses_ha_client(self):
        miloco = MagicMock()
        ha = MagicMock()
        ha.call_service.return_value = True

        ha_dev = Device(
            id="light.bedroom",
            name="卧室灯",
            type="light",
            platform="ha",
            state="on",
            attributes={},
        )
        svc = _make_miloco_service(miloco_mock=miloco, ha_mock=ha, devices=[ha_dev])

        svc.execute_command("light.bedroom", "turn_off", {})
        ha.call_service.assert_called_once()
        miloco.set_property.assert_not_called()

    def test_miloco_turn_on_does_not_call_ha(self):
        miloco = MagicMock()
        miloco.set_property.return_value = True
        ha = MagicMock()

        dev = _make_miloco_device_node(did="abc123")
        svc = _make_miloco_service(miloco_mock=miloco, ha_mock=ha, devices=[dev])

        resp = svc.execute_command("miloco.abc123", "turn_on", {})
        assert resp.success is True
        ha.call_service.assert_not_called()

