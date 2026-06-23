"""设备图服务层。

负责从 HA 拉取数据、融合、缓存、生成摘要。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from lumi.device_graph.fusion import ha_states_to_devices
from lumi.device_graph.schema import Device, DeviceGraph, DeviceGraphSummary

if TYPE_CHECKING:
    from lumi.ha.client import HAClient

logger = logging.getLogger(__name__)


class DeviceGraphService:
    """设备图服务。"""

    def __init__(self, ha_client: HAClient | None = None) -> None:
        self.ha_client = ha_client
        self._cached_graph: DeviceGraph | None = None
        self._last_refresh: datetime | None = None

    def refresh(self) -> DeviceGraph:
        """刷新设备图（从 HA 拉取最新数据）。"""
        devices: list[Device] = []

        if self.ha_client:
            states = self.ha_client.get_states()
            devices.extend(ha_states_to_devices(states))
            logger.info("从 HA 融合了 %d 个设备", len(devices))

        # Phase 1 暂不支持 Miloco / Hermes 数据源

        # 构建房间索引
        rooms: dict[str, list[str]] = {}
        for dev in devices:
            if dev.room:
                rooms.setdefault(dev.room, []).append(dev.id)

        graph = DeviceGraph(
            devices=devices,
            rooms=rooms,
            metadata={
                "last_refresh": datetime.now().isoformat(),
                "source_count": {"ha": len(devices)},
            },
        )
        self._cached_graph = graph
        self._last_refresh = datetime.now()
        return graph

    def get_graph(self, force_refresh: bool = False) -> DeviceGraph:
        """获取设备图（优先返回缓存）。"""
        if force_refresh or self._cached_graph is None:
            return self.refresh()
        return self._cached_graph

    def get_summary(self, force_refresh: bool = False) -> DeviceGraphSummary:
        """生成设备图摘要。"""
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
            by_room={room: len(ids) for room, ids in graph.rooms.items()},
            rooms=sorted(graph.rooms.keys()),
        )
