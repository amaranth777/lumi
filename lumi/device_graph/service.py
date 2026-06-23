"""设备图服务层。"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from lumi.device_graph.commands import resolve_command
from lumi.device_graph.fusion import ha_states_to_devices
from lumi.device_graph.policy import PolicyEngine, get_default_policy_engine
from lumi.device_graph.schema import (
    BatchCommandResponse,
    CommandResponse,
    Device,
    DeviceGraph,
    DeviceGraphSummary,
)
from lumi.miloco.fusion import miloco_devices_to_lumi

if TYPE_CHECKING:
    from lumi.ha.client import HAClient
    from lumi.miloco.client import MilocoClient

import time

logger = logging.getLogger(__name__)

# 缓存 TTL（秒）——即使没有 HA 事件触发失效，超过此时间也强制刷新
_CACHE_TTL = int(os.getenv("LUMI_CACHE_TTL", "300"))  # 默认 5 分钟


class DeviceGraphService:
    def __init__(
        self,
        ha_client: HAClient | None = None,
        miloco_client: MilocoClient | None = None,
        aliases: list[dict[str, Any]] | None = None,
        policy_engine: PolicyEngine | None = None,
        cache_ttl: int = _CACHE_TTL,
    ) -> None:
        self.ha_client = ha_client
        self.miloco_client = miloco_client
        self.aliases = aliases or []
        self.policy_engine = policy_engine or get_default_policy_engine()
        self.cache_ttl = cache_ttl
        self._cached_graph: DeviceGraph | None = None
        self._cache_time: float = 0.0  # 最后一次刷新的时间戳

    def refresh(self) -> DeviceGraph:
        devices: list[Device] = []
        if self.ha_client:
            states = self.ha_client.get_states()
            devices.extend(ha_states_to_devices(states, self.aliases))
            logger.info("从 HA 融合了 %d 个设备", len(devices))

        if self.miloco_client:
            miloco_devs = self.miloco_client.get_device_list()
            lumi_devs = miloco_devices_to_lumi(miloco_devs)
            # 去重：如果同一设备已经有 HA 数据，Miloco 补充 room 等元信息
            ha_ids = {d.id for d in devices}
            new_devs = []
            for dev in lumi_devs:
                # Miloco id 是 miloco.<did>，HA 里可能也有对应设备
                if dev.id not in ha_ids:
                    new_devs.append(dev)
                else:
                    # 用 Miloco 的 room 补充 HA 设备（如果 HA 没有识别出房间）
                    ha_dev = next(d for d in devices if d.id == dev.id)
                    if not ha_dev.room and dev.room:
                        ha_dev = ha_dev.model_copy(update={"room": dev.room})
                        devices = [ha_dev if d.id == dev.id else d for d in devices]
            devices.extend(new_devs)
            logger.info("从 Miloco 融合了 %d 个新设备", len(new_devs))

        rooms: dict[str, list[str]] = {}
        for dev in devices:
            if dev.room:
                rooms.setdefault(dev.room, []).append(dev.id)

        graph = DeviceGraph(
            devices=devices,
            rooms=rooms,
            metadata={"last_refresh": datetime.now().isoformat()},
        )
        self._cached_graph = graph
        self._cache_time = time.monotonic()
        return graph

    def _is_cache_expired(self) -> bool:
        """检查缓存是否已超过 TTL。"""
        if self._cached_graph is None:
            return True
        cache_time = getattr(self, "_cache_time", 0.0)
        cache_ttl = getattr(self, "cache_ttl", _CACHE_TTL)
        return (time.monotonic() - cache_time) >= cache_ttl

    def get_graph(self, force_refresh: bool = False) -> DeviceGraph:
        if force_refresh or self._cached_graph is None or self._is_cache_expired():
            return self.refresh()
        return self._cached_graph

    def invalidate_cache(self) -> None:
        """让缓存失效——下次 get_graph() 时会重新从 HA/Miloco 拉取。"""
        self._cached_graph = None
        self._cache_time = 0.0
        logger.debug("设备图缓存已失效")

    def update_device_state(self, entity_id: str, new_state: str) -> bool:
        """增量更新缓存中单个设备的状态，避免全量重拉。

        Returns:
            True 表示缓存更新成功，False 表示设备不在缓存中（需全量刷新）。
        """
        if self._cached_graph is None:
            return False
        for i, device in enumerate(self._cached_graph.devices):
            if device.id == entity_id:
                updated = device.model_copy(update={"state": new_state})
                self._cached_graph.devices[i] = updated
                logger.debug("增量更新设备状态: %s → %s", entity_id, new_state)
                return True
        return False

    def get_summary(self, force_refresh: bool = False) -> DeviceGraphSummary:
        graph = self.get_graph(force_refresh=force_refresh)
        by_type: dict[str, int] = {}
        by_platform: dict[str, int] = {}
        for dev in graph.devices:
            by_type[dev.type] = by_type.get(dev.type, 0) + 1
            by_platform[dev.platform] = by_platform.get(dev.platform, 0) + 1
        return DeviceGraphSummary(
            total_devices=len(graph.devices),
            by_type=by_type,
            by_platform=by_platform,
            by_room={r: len(ids) for r, ids in graph.rooms.items()},
            rooms=sorted(graph.rooms.keys()),
        )

    def execute_command(
        self, device_id: str, command: str, params: dict[str, Any]
    ) -> CommandResponse:
        """执行设备控制命令。"""
        # 找到设备
        graph = self.get_graph()
        device = next((d for d in graph.devices if d.id == device_id), None)
        if not device:
            return CommandResponse(
                success=False,
                message=f"设备不存在: {device_id}",
                device_id=device_id,
                command=command,
            )

        # 策略守卫：执行前检查是否被拦截
        violation = self.policy_engine.evaluate(device, command, params)
        if violation:
            return CommandResponse(
                success=False,
                message=violation.reason,
                device_id=device_id,
                command=command,
            )

        # Miloco (MIoT) 平台控制 — 不走 resolve_command，直接透传
        if device.platform == "miloco":
            if not self.miloco_client:
                return CommandResponse(
                    success=False,
                    message="Miloco client 未初始化",
                    device_id=device_id,
                    command=command,
                )
            return self._execute_miloco_command(device, command, params)

        # 解析命令（HA 平台）
        resolved = resolve_command(device, command, params)
        if not resolved:
            return CommandResponse(
                success=False,
                message=f"不支持的命令: {command} (设备类型: {device.type})",
                device_id=device_id,
                command=command,
            )

        domain, service, service_data = resolved

        # HA 平台控制
        if device.platform == "ha":
            if not self.ha_client:
                return CommandResponse(
                    success=False,
                    message="HA client 未初始化",
                    device_id=device_id,
                    command=command,
                )
            success = self.ha_client.call_service(domain, service, service_data)
            return CommandResponse(
                success=success,
                message="执行成功" if success else "HA service 调用失败",
                device_id=device_id,
                command=command,
            )

        return CommandResponse(
            success=False,
            message=f"平台不支持控制: {device.platform}",
            device_id=device_id,
            command=command,
        )

    def _execute_miloco_command(
        self, device: "Device", command: str, params: dict[str, Any]
    ) -> "CommandResponse":
        """将 Lumi 命令转换为 MIoT set_property / call_action 调用。"""
        from lumi.device_graph.schema import CommandResponse  # 局部避免循环

        did: str = device.attributes.get("did", "")
        if not did:
            return CommandResponse(
                success=False,
                message=f"设备缺少 did: {device.id}",
                device_id=device.id,
                command=command,
            )

        success = False
        # 通用开关 → MIoT prop.2.1 (on/off)
        if command == "turn_on":
            success = self.miloco_client.set_property(did, 2, 1, True)
        elif command == "turn_off":
            success = self.miloco_client.set_property(did, 2, 1, False)
        elif command == "toggle":
            # 先查状态再翻转
            status = self.miloco_client.get_device_status(did)
            props = {p["iid"]: p["value"] for p in status.get("properties", []) if "iid" in p}
            current = props.get("prop.2.1", False)
            success = self.miloco_client.set_property(did, 2, 1, not current)
        elif command == "set_property":
            # 直接透传：params = {siid, piid, value}
            siid = int(params.get("siid", 2))
            piid = int(params.get("piid", 1))
            value = params.get("value")
            success = self.miloco_client.set_property(did, siid, piid, value)
        elif command == "call_action":
            # params = {siid, aiid, params(list)}
            siid = int(params.get("siid", 2))
            aiid = int(params.get("aiid", 1))
            action_params = params.get("params", [])
            success = self.miloco_client.call_action(did, siid, aiid, action_params)
        else:
            return CommandResponse(
                success=False,
                message=f"Miloco 平台不支持命令: {command}",
                device_id=device.id,
                command=command,
            )

        return CommandResponse(
            success=success,
            message="执行成功" if success else "Miloco 调用失败",
            device_id=device.id,
            command=command,
        )

    def batch_execute_command(
        self, device_ids: list[str], command: str, params: dict[str, Any]
    ) -> BatchCommandResponse:
        """批量执行命令。"""
        results = []
        for device_id in device_ids:
            result = self.execute_command(device_id, command, params)
            results.append(result)
        
        success_count = sum(1 for r in results if r.success)
        return BatchCommandResponse(
            total=len(results),
            success=success_count,
            failed=len(results) - success_count,
            results=results,
        )

    def get_devices_by_room(self, room: str) -> list[Device]:
        """按房间查询设备。"""
        graph = self.get_graph()
        device_ids = graph.rooms.get(room, [])
        return [d for d in graph.devices if d.id in device_ids]

    def search_devices(self, query: str) -> list[Device]:
        """搜索设备（name/id/room/type）。"""
        graph = self.get_graph()
        query_lower = query.lower()
        return [
            d for d in graph.devices
            if query_lower in d.name.lower()
            or query_lower in d.id.lower()
            or (d.room and query_lower in d.room.lower())
            or query_lower in d.type.lower()
        ]
