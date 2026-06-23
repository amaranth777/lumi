"""device_graph/commands.py 单元测试。"""

from __future__ import annotations

import pytest
from lumi.device_graph.commands import resolve_command
from lumi.device_graph.schema import Device


def _make_device(device_id: str, dtype: str, platform: str = "ha") -> Device:
    return Device(
        id=device_id,
        name=device_id,
        type=dtype,
        platform=platform,
        state="on",
        attributes={},
    )


# ─── 通用开关（wildcard *） ────────────────────────────────────────────────────

class TestGenericCommands:
    def test_turn_on_any_device(self):
        device = _make_device("switch.test", "switch")
        result = resolve_command(device, "turn_on", {})
        assert result is not None
        domain, service, data = result
        assert domain == "homeassistant"
        assert service == "turn_on"
        assert data["entity_id"] == "switch.test"

    def test_turn_off_any_device(self):
        device = _make_device("light.test", "light")
        domain, service, data = resolve_command(device, "turn_off", {})
        assert service == "turn_off"

    def test_toggle_any_device(self):
        device = _make_device("fan.test", "fan")
        domain, service, data = resolve_command(device, "toggle", {})
        assert service == "toggle"

    def test_unknown_command_returns_none(self):
        device = _make_device("light.test", "light")
        assert resolve_command(device, "nonexistent_cmd", {}) is None


# ─── 灯光命令 ─────────────────────────────────────────────────────────────────

class TestLightCommands:
    def test_set_brightness(self):
        device = _make_device("light.bedroom", "light")
        domain, service, data = resolve_command(device, "set_brightness", {"brightness": 80})
        assert domain == "light"
        assert service == "turn_on"
        assert data["brightness_pct"] == 80
        assert data["entity_id"] == "light.bedroom"

    def test_set_color_temp(self):
        device = _make_device("light.desk", "light")
        domain, service, data = resolve_command(device, "set_color_temp", {"color_temp": 4000})
        assert domain == "light"
        assert data["color_temp_kelvin"] == 4000

    def test_set_brightness_wrong_type_passthrough(self):
        """非 light 类型调用 set_brightness 应返回 None（无 wildcard）。"""
        device = _make_device("switch.test", "switch")
        assert resolve_command(device, "set_brightness", {"brightness": 80}) is None


# ─── 温控命令 ─────────────────────────────────────────────────────────────────

class TestClimateCommands:
    def test_set_temperature(self):
        device = _make_device("climate.ac", "climate")
        domain, service, data = resolve_command(device, "set_temperature", {"temperature": 24})
        assert domain == "climate"
        assert service == "set_temperature"
        assert data["temperature"] == 24

    def test_set_hvac_mode(self):
        device = _make_device("climate.ac", "climate")
        domain, service, data = resolve_command(device, "set_hvac_mode", {"hvac_mode": "cool"})
        assert domain == "climate"
        assert service == "set_hvac_mode"
        assert data["hvac_mode"] == "cool"

    def test_set_mode_for_climate(self):
        device = _make_device("climate.ac", "climate")
        domain, service, data = resolve_command(device, "set_mode", {"mode": "heat"})
        assert service == "set_hvac_mode"
        assert data["hvac_mode"] == "heat"


# ─── 加湿器命令 ───────────────────────────────────────────────────────────────

class TestHumidifierCommands:
    def test_set_humidity(self):
        device = _make_device("humidifier.xiaomi", "humidifier")
        domain, service, data = resolve_command(device, "set_humidity", {"humidity": 60})
        assert domain == "humidifier"
        assert service == "set_humidity"
        assert data["humidity"] == 60

    def test_set_mode_humidifier(self):
        device = _make_device("humidifier.xiaomi", "humidifier")
        domain, service, data = resolve_command(device, "set_mode", {"mode": "auto"})
        assert service == "set_mode"
        assert data["mode"] == "auto"


# ─── 风扇命令 ─────────────────────────────────────────────────────────────────

class TestFanCommands:
    def test_set_percentage(self):
        device = _make_device("fan.purifier", "fan")
        domain, service, data = resolve_command(device, "set_percentage", {"percentage": 50})
        assert domain == "fan"
        assert service == "set_percentage"
        assert data["percentage"] == 50

    def test_set_mode_fan(self):
        device = _make_device("fan.purifier", "fan")
        domain, service, data = resolve_command(device, "set_mode", {"mode": "sleep"})
        assert service == "set_preset_mode"
        assert data["preset_mode"] == "sleep"


# ─── 吸尘器命令 ───────────────────────────────────────────────────────────────

class TestVacuumCommands:
    def test_start(self):
        device = _make_device("vacuum.dreame", "vacuum")
        domain, service, data = resolve_command(device, "start", {})
        assert domain == "vacuum"
        assert service == "start"

    def test_stop(self):
        device = _make_device("vacuum.dreame", "vacuum")
        domain, service, data = resolve_command(device, "stop", {})
        assert service == "stop"


# ─── 窗帘命令 ─────────────────────────────────────────────────────────────────

class TestCoverCommands:
    def test_open(self):
        device = _make_device("cover.curtain", "cover")
        domain, service, data = resolve_command(device, "open", {})
        assert domain == "cover"
        assert service == "open_cover"

    def test_close(self):
        device = _make_device("cover.curtain", "cover")
        domain, service, data = resolve_command(device, "close", {})
        assert service == "close_cover"

    def test_set_position(self):
        device = _make_device("cover.curtain", "cover")
        domain, service, data = resolve_command(device, "set_position", {"position": 50})
        assert service == "set_cover_position"
        assert data["position"] == 50


# ─── entity_id 始终出现在 service_data ───────────────────────────────────────

class TestServiceDataEntityId:
    def test_entity_id_in_all_results(self):
        commands_to_test = [
            ("turn_on", {}),
            ("turn_off", {}),
            ("toggle", {}),
        ]
        device = _make_device("light.kitchen", "light")
        for cmd, params in commands_to_test:
            _, _, data = resolve_command(device, cmd, params)
            assert data["entity_id"] == "light.kitchen", f"entity_id missing for {cmd}"

    def test_extra_params_merged(self):
        """额外的 params 应合并到 service_data。"""
        device = _make_device("light.test", "light")
        _, _, data = resolve_command(device, "turn_on", {"transition": 2})
        assert data["transition"] == 2
        assert data["entity_id"] == "light.test"
