"""device_graph/schema.py 数据模型测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lumi.device_graph.schema import (
    Device, DeviceGraph, DeviceGraphSummary,
    CommandRequest, CommandResponse,
    BatchCommandRequest, BatchCommandResponse,
)


# ─── Device ───────────────────────────────────────────────────────────────────

class TestDevice:
    def test_required_fields(self):
        d = Device(id="light.x", name="灯", type="light", platform="ha", state="on", attributes={})
        assert d.id == "light.x"
        assert d.type == "light"

    def test_optional_defaults(self):
        d = Device(id="x", name="x", type="sensor", platform="ha", state=None, attributes={})
        assert d.state is None
        assert d.room is None
        assert d.icon is None
        assert d.capabilities == []
        assert d.metadata == {}

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            Device(name="灯", type="light", platform="ha", state="on", attributes={})

    def test_attributes_dict(self):
        d = Device(id="x", name="x", type="sensor", platform="ha", state="22.5",
                   attributes={"unit": "°C", "friendly_name": "温度"})
        assert d.attributes["unit"] == "°C"

    def test_capabilities_list(self):
        d = Device(id="x", name="x", type="light", platform="ha", state="on",
                   attributes={}, capabilities=["toggle", "brightness"])
        assert "toggle" in d.capabilities

    def test_model_copy_update(self):
        d = Device(id="x", name="原始名", type="light", platform="ha", state="on", attributes={})
        d2 = d.model_copy(update={"name": "新名字", "room": "客厅"})
        assert d2.name == "新名字"
        assert d2.room == "客厅"
        assert d.name == "原始名"  # 原始未变


# ─── DeviceGraph ──────────────────────────────────────────────────────────────

class TestDeviceGraph:
    def test_empty_graph(self):
        g = DeviceGraph()
        assert g.devices == []
        assert g.rooms == {}
        assert g.metadata == {}

    def test_graph_with_devices_and_rooms(self):
        d = Device(id="light.x", name="灯", type="light", platform="ha", state="on", attributes={})
        g = DeviceGraph(
            devices=[d],
            rooms={"客厅": ["light.x"]},
            metadata={"last_refresh": "2026-06-23T12:00:00"}
        )
        assert len(g.devices) == 1
        assert "客厅" in g.rooms
        assert g.metadata["last_refresh"] == "2026-06-23T12:00:00"


# ─── DeviceGraphSummary ───────────────────────────────────────────────────────

class TestDeviceGraphSummary:
    def test_defaults(self):
        s = DeviceGraphSummary()
        assert s.total_devices == 0
        assert s.by_type == {}
        assert s.rooms == []

    def test_with_data(self):
        s = DeviceGraphSummary(
            total_devices=5,
            by_type={"light": 3, "switch": 2},
            by_platform={"ha": 5},
            by_room={"客厅": 2, "卧室": 3},
            rooms=["客厅", "卧室"],
        )
        assert s.total_devices == 5
        assert s.by_type["light"] == 3
        assert "客厅" in s.rooms


# ─── CommandRequest / CommandResponse ────────────────────────────────────────

class TestCommandRequest:
    def test_required_command(self):
        req = CommandRequest(command="turn_on")
        assert req.command == "turn_on"
        assert req.params == {}

    def test_with_params(self):
        req = CommandRequest(command="set_brightness", params={"brightness": 80})
        assert req.params["brightness"] == 80

    def test_missing_command_raises(self):
        with pytest.raises(ValidationError):
            CommandRequest()


class TestCommandResponse:
    def test_success_response(self):
        resp = CommandResponse(success=True, message="执行成功",
                               device_id="light.x", command="turn_on")
        assert resp.success is True

    def test_failure_response(self):
        resp = CommandResponse(success=False, message="策略拒绝",
                               device_id="light.x", command="empty")
        assert resp.success is False
        assert "策略" in resp.message

    def test_default_message(self):
        resp = CommandResponse(success=True, device_id="x", command="toggle")
        assert resp.message == ""


# ─── BatchCommandRequest / BatchCommandResponse ───────────────────────────────

class TestBatchCommandRequest:
    def test_required_fields(self):
        req = BatchCommandRequest(device_ids=["light.a", "light.b"], command="turn_off")
        assert len(req.device_ids) == 2
        assert req.params == {}

    def test_missing_device_ids_raises(self):
        with pytest.raises(ValidationError):
            BatchCommandRequest(command="turn_off")


class TestBatchCommandResponse:
    def test_counts(self):
        r1 = CommandResponse(success=True, device_id="a", command="turn_on")
        r2 = CommandResponse(success=False, device_id="b", command="turn_on")
        resp = BatchCommandResponse(total=2, success=1, failed=1, results=[r1, r2])
        assert resp.total == 2
        assert resp.success == 1
        assert resp.failed == 1
        assert len(resp.results) == 2

    def test_empty_batch(self):
        resp = BatchCommandResponse(total=0, success=0, failed=0)
        assert resp.results == []
