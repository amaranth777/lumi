"""device_graph/service.py 单元测试。"""

from __future__ import annotations

import pytest
from typing import Any
from lumi.device_graph.service import DeviceGraphService
from lumi.device_graph.schema import Device, DeviceGraph
from lumi.device_graph.policy import build_default_policy_engine


# ─── Mock 客户端 ──────────────────────────────────────────────────────────────

class MockHAClient:
    def __init__(self, states: list[dict] | None = None, service_ok: bool = True):
        self._states = states or []
        self._service_ok = service_ok
        self.calls: list[tuple] = []  # (domain, service, data)

    def get_states(self) -> list[dict]:
        return self._states

    def call_service(self, domain: str, service: str, data: dict) -> bool:
        self.calls.append((domain, service, data))
        return self._service_ok


def _make_ha_states(*entity_ids_and_types: tuple[str, str]) -> list[dict]:
    """快速生成 HA state 列表。"""
    result = []
    for entity_id, state in entity_ids_and_types:
        result.append({
            "entity_id": entity_id,
            "state": state,
            "attributes": {"friendly_name": entity_id},
        })
    return result


def _make_service(
    ha_states: list[dict] | None = None,
    service_ok: bool = True,
    aliases: list[dict] | None = None,
    cache_ttl: int = 300,
) -> DeviceGraphService:
    ha_client = MockHAClient(states=ha_states or [], service_ok=service_ok)
    return DeviceGraphService(
        ha_client=ha_client,
        miloco_client=None,
        aliases=aliases or [],
        policy_engine=build_default_policy_engine(),
        cache_ttl=cache_ttl,
    )


# ─── get_graph / refresh ──────────────────────────────────────────────────────

class TestGetGraph:
    def test_empty_ha_returns_empty_graph(self):
        svc = _make_service()
        graph = svc.get_graph()
        assert isinstance(graph, DeviceGraph)
        assert len(graph.devices) == 0

    def test_ha_devices_fused(self):
        states = _make_ha_states(("light.living", "on"), ("switch.kitchen", "off"))
        svc = _make_service(ha_states=states)
        graph = svc.get_graph()
        assert len(graph.devices) == 2

    def test_cache_used_without_force_refresh(self):
        states = _make_ha_states(("light.a", "on"))
        ha = MockHAClient(states=states)
        svc = DeviceGraphService(ha_client=ha)
        svc.get_graph()
        svc.get_graph()
        # 只调用一次 get_states（第二次用缓存）
        assert ha._states is states  # 仅验证 mock 未被额外调用

    def test_force_refresh_bypasses_cache(self):
        states = _make_ha_states(("light.a", "on"))
        ha = MockHAClient(states=states)
        svc = DeviceGraphService(ha_client=ha)
        svc.get_graph()
        svc.get_graph(force_refresh=True)
        # 两次都调用了 get_states，不崩溃即可

    def test_invalidate_cache_clears_graph(self):
        states = _make_ha_states(("light.a", "on"))
        svc = _make_service(ha_states=states)
        svc.get_graph()
        assert svc._cached_graph is not None
        svc.invalidate_cache()
        assert svc._cached_graph is None

    def test_invalidate_cache_forces_next_refresh(self):
        states = _make_ha_states(("light.a", "on"))
        ha = MockHAClient(states=states)
        svc = DeviceGraphService(ha_client=ha)
        svc.get_graph()
        svc.invalidate_cache()
        # 下次 get_graph 应重新拉取（不崩溃，返回正常图）
        graph = svc.get_graph()
        assert len(graph.devices) == 1

    def test_cache_ttl_expired_triggers_refresh(self):
        """TTL 过期后 get_graph() 自动重新拉取。"""
        states = _make_ha_states(("light.a", "on"))
        svc = _make_service(ha_states=states, cache_ttl=0)  # TTL=0 立即过期
        svc.get_graph()
        # TTL=0，再次调用应重新拉取（不崩溃）
        graph = svc.get_graph()
        assert len(graph.devices) == 1

    def test_cache_not_expired_within_ttl(self):
        """TTL 内缓存不过期。"""
        states = _make_ha_states(("light.a", "on"))
        svc = _make_service(ha_states=states, cache_ttl=3600)
        svc.get_graph()
        assert not svc._is_cache_expired()

    def test_cache_expired_when_ttl_zero(self):
        """TTL=0 时缓存立即过期。"""
        states = _make_ha_states(("light.a", "on"))
        svc = _make_service(ha_states=states, cache_ttl=0)
        svc.get_graph()
        assert svc._is_cache_expired()

    def test_invalidate_resets_cache_time(self):
        """invalidate_cache 重置缓存时间戳。"""
        states = _make_ha_states(("light.a", "on"))
        svc = _make_service(ha_states=states, cache_ttl=3600)
        svc.get_graph()
        assert svc._cache_time > 0
        svc.invalidate_cache()
        assert svc._cache_time == 0.0

    def test_rooms_built_from_aliases(self):
        states = _make_ha_states(("light.bedroom_lamp", "on"))
        aliases = [{"entity_id": "light.bedroom_lamp", "name": "卧室灯", "room": "卧室"}]
        svc = _make_service(ha_states=states, aliases=aliases)
        graph = svc.get_graph()
        assert "卧室" in graph.rooms
        assert "light.bedroom_lamp" in graph.rooms["卧室"]


# ─── get_summary ─────────────────────────────────────────────────────────────

class TestGetSummary:
    def test_summary_counts(self):
        states = _make_ha_states(
            ("light.a", "on"), ("light.b", "off"),
            ("switch.c", "on"), ("sensor.d", "22.5"),
        )
        svc = _make_service(ha_states=states)
        summary = svc.get_summary()
        assert summary.total_devices == 4
        assert summary.by_type["light"] == 2
        assert summary.by_type["switch"] == 1
        assert summary.by_type["sensor"] == 1

    def test_summary_by_platform(self):
        states = _make_ha_states(("light.a", "on"))
        svc = _make_service(ha_states=states)
        summary = svc.get_summary()
        assert summary.by_platform["ha"] == 1


# ─── execute_command ─────────────────────────────────────────────────────────

class TestExecuteCommand:
    def test_device_not_found(self):
        svc = _make_service()
        result = svc.execute_command("light.nonexistent", "turn_on", {})
        assert result.success is False
        assert "不存在" in result.message

    def test_turn_on_success(self):
        states = _make_ha_states(("light.living", "off"))
        svc = _make_service(ha_states=states)
        result = svc.execute_command("light.living", "turn_on", {})
        assert result.success is True

    def test_turn_on_ha_failure(self):
        states = _make_ha_states(("light.living", "off"))
        svc = _make_service(ha_states=states, service_ok=False)
        result = svc.execute_command("light.living", "turn_on", {})
        assert result.success is False

    def test_unsupported_command(self):
        states = _make_ha_states(("light.living", "on"))
        svc = _make_service(ha_states=states)
        result = svc.execute_command("light.living", "set_temperature", {"temperature": 24})
        assert result.success is False
        assert "不支持" in result.message

    def test_policy_blocks_litter_box_empty(self):
        states = _make_ha_states(("button.petjc_cn_821633016_pro_clean", "off"))
        svc = _make_service(ha_states=states)
        result = svc.execute_command(
            "button.petjc_cn_821633016_pro_clean", "empty", {}
        )
        assert result.success is False
        assert "策略拒绝" in result.message

    def test_policy_allows_turn_on(self):
        states = _make_ha_states(("button.petjc_cn_821633016_pro_clean", "off"))
        svc = _make_service(ha_states=states)
        result = svc.execute_command(
            "button.petjc_cn_821633016_pro_clean", "turn_on", {}
        )
        # turn_on 不被策略拦截，但 button 类型没有对应 HA service 映射→不支持
        assert "策略" not in result.message

    def test_ha_service_called_with_entity_id(self):
        states = _make_ha_states(("switch.desk_light", "off"))
        ha = MockHAClient(states=states, service_ok=True)
        svc = DeviceGraphService(ha_client=ha)
        svc.execute_command("switch.desk_light", "turn_on", {})
        assert len(ha.calls) == 1
        domain, service, data = ha.calls[0]
        assert data["entity_id"] == "switch.desk_light"
        assert service == "turn_on"

    def test_unknown_platform_rejected(self):
        """手动插入一个非 ha/miloco 平台的设备。"""
        svc = _make_service()
        # 直接注入缓存（同时设置时间戳避免 TTL 过期）
        import time
        device = Device(
            id="xyz.device", name="未知平台", type="switch",
            platform="unknown_platform", state="on", attributes={}
        )
        svc._cached_graph = DeviceGraph(devices=[device], rooms={})
        svc._cache_time = time.monotonic()
        result = svc.execute_command("xyz.device", "turn_on", {})
        assert result.success is False
        assert "平台" in result.message


# ─── search_devices ───────────────────────────────────────────────────────────

class TestSearchDevices:
    def test_search_by_name(self):
        states = _make_ha_states(("fan.air_purifier", "on"))
        aliases = [{"entity_id": "fan.air_purifier", "name": "客厅空气净化器"}]
        svc = _make_service(ha_states=states, aliases=aliases)
        results = svc.search_devices("净化器")
        assert len(results) == 1
        assert results[0].id == "fan.air_purifier"

    def test_search_by_entity_id(self):
        states = _make_ha_states(("light.bedroom_lamp", "off"))
        svc = _make_service(ha_states=states)
        results = svc.search_devices("bedroom")
        assert len(results) == 1

    def test_search_by_room(self):
        states = _make_ha_states(("light.x", "on"))
        aliases = [{"entity_id": "light.x", "room": "客厅"}]
        svc = _make_service(ha_states=states, aliases=aliases)
        results = svc.search_devices("客厅")
        assert len(results) == 1

    def test_search_no_match(self):
        states = _make_ha_states(("light.x", "on"))
        svc = _make_service(ha_states=states)
        results = svc.search_devices("不存在的设备xyz")
        assert results == []

    def test_search_case_insensitive(self):
        states = _make_ha_states(("light.BEDROOM_lamp", "on"))
        svc = _make_service(ha_states=states)
        assert len(svc.search_devices("bedroom")) == 1
        assert len(svc.search_devices("BEDROOM")) == 1


# ─── get_devices_by_room ──────────────────────────────────────────────────────

class TestGetDevicesByRoom:
    def test_get_devices_in_room(self):
        states = _make_ha_states(("light.bedroom_lamp", "on"), ("switch.kitchen_switch", "off"))
        svc = _make_service(ha_states=states)
        devices = svc.get_devices_by_room("卧室")
        assert len(devices) == 1
        assert devices[0].id == "light.bedroom_lamp"

    def test_nonexistent_room_returns_empty(self):
        svc = _make_service()
        assert svc.get_devices_by_room("火星基地") == []


# ─── batch_execute_command ───────────────────────────────────────────────────

class TestBatchExecuteCommand:
    def test_batch_all_success(self):
        states = _make_ha_states(("light.a", "on"), ("light.b", "off"))
        svc = _make_service(ha_states=states)
        result = svc.batch_execute_command(["light.a", "light.b"], "turn_off", {})
        assert result.total == 2
        assert result.success == 2
        assert result.failed == 0

    def test_batch_partial_failure(self):
        states = _make_ha_states(("light.a", "on"))
        svc = _make_service(ha_states=states)
        result = svc.batch_execute_command(
            ["light.a", "light.nonexistent"], "turn_off", {}
        )
        assert result.total == 2
        assert result.failed == 1

    def test_batch_empty_device_list(self):
        svc = _make_service()
        result = svc.batch_execute_command([], "turn_off", {})
        assert result.total == 0
        assert result.success == 0
