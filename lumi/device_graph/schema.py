"""设备图数据模型。

Phase 1 只读模型：Device / DeviceGraph / DeviceGraphSummary
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Device(BaseModel):
    """设备节点。"""

    id: str = Field(..., description="设备唯一标识（内部 UUID 或 HA entity_id）")
    name: str = Field(..., description="设备显示名称（融合后）")
    type: str = Field(..., description="设备类型（light/switch/sensor/climate/...）")
    platform: str = Field(..., description="来源平台（ha/miloco/hermes）")
    state: str | None = Field(None, description="当前状态值")
    attributes: dict[str, Any] = Field(default_factory=dict, description="设备属性")
    capabilities: list[str] = Field(default_factory=list, description="支持的能力列表")
    room: str | None = Field(None, description="所属房间")
    icon: str | None = Field(None, description="图标标识")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元信息")


class DeviceGraph(BaseModel):
    """设备图（完整）。"""

    devices: list[Device] = Field(default_factory=list)
    rooms: dict[str, list[str]] = Field(
        default_factory=dict,
        description="房间 -> 设备 ID 列表映射",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="图级元信息（更新时间、版本等）",
    )


class DeviceGraphSummary(BaseModel):
    """设备图摘要（用于轻量级查询）。"""

    total_devices: int = Field(0, description="设备总数")
    by_type: dict[str, int] = Field(default_factory=dict, description="按类型统计")
    by_platform: dict[str, int] = Field(default_factory=dict, description="按平台统计")
    by_room: dict[str, int] = Field(default_factory=dict, description="按房间统计")
    rooms: list[str] = Field(default_factory=list, description="房间列表")
