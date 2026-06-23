"""设备图服务层。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from lumi.device_graph.commands import resolve_command
from lumi.device_graph.fusion import ha_states_to_devices
from lumi.device_graph.schema import CommandResponse, Device, DeviceGraph, DeviceGraphSummary

if TYPE_CHECKING:
    from lumi.ha.client import HAClient

logger = logging.getLogger(__name__)


class DeviceGraphService:
    def __init__(
        self,
        ha_client: HAClient | None = None,
        aliases: list[dict[str, Any]] | None = None,
    ) -> None:
        self.ha_client = ha_client
        self.aliases = aliases or []
        self._cached_graph: DeviceGraph | None = None

    def refresh(self) -> DeviceGraph:
        devices: list[Device] = []
        if self.ha_client:
            states = self.ha_client.get_states()
            devices.extend(ha_states_to_devices(states, self.aliases))
            logger.info("从 HA 融合了 %d 个设备", len(devices))

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
        return graph

    def get_graph(self, force_refresh: bool = False) -> DeviceGraph:
        if force_refresh or self._cached_graph is None:
            return self.refresh()
        return self._cached_graph

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

        # 解析命令
        resolved = resolve_command(device, command, params)
        if not resolved:
            return CommandResponse(
                success=False,
                message=f"不支持的命令: {command} (设备类型: {device.type})",
                device_id=device_id,
                command=command,
            )

        domain, service, service_data = resolved

        # 执行（目前只支持 HA）
        if device.platform != "ha" or not self.ha_client:
            return CommandResponse(
                success=False,
                message=f"平台不支持控制: {device.platform}",
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
