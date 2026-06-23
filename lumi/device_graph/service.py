"""设备图服务层。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from lumi.device_graph.fusion import ha_states_to_devices
from lumi.device_graph.schema import Device, DeviceGraph, DeviceGraphSummary

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
