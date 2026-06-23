"""设备图融合逻辑。

将 HA states 转换为标准化 Device 列表。
Phase 1：只做 HA → Device 映射 + 基础类型推断 + 房间推断。
"""

from __future__ import annotations

import re
from typing import Any

from lumi.device_graph.schema import Device

# HA 域名 → Lumi 设备类型
_DOMAIN_TYPE_MAP: dict[str, str] = {
    "light": "light",
    "switch": "switch",
    "sensor": "sensor",
    "binary_sensor": "binary_sensor",
    "climate": "climate",
    "media_player": "media_player",
    "cover": "cover",
    "fan": "fan",
    "vacuum": "vacuum",
    "camera": "camera",
    "lock": "lock",
    "alarm_control_panel": "alarm",
    "button": "button",
    "select": "select",
    "number": "number",
    "input_boolean": "switch",
    "automation": "automation",
    "script": "script",
    "scene": "scene",
}

# 常见能力映射
_DOMAIN_CAPABILITIES: dict[str, list[str]] = {
    "light": ["toggle", "brightness", "color"],
    "switch": ["toggle"],
    "climate": ["temperature", "hvac_mode"],
    "cover": ["open", "close", "position"],
    "fan": ["toggle", "speed"],
    "vacuum": ["start", "stop", "locate"],
    "lock": ["lock", "unlock"],
    "media_player": ["play", "pause", "volume"],
}

# 中文房间关键词（从 entity_id / friendly_name 推断）
_ROOM_KEYWORDS: list[tuple[str, str]] = [
    (r"living|客厅", "客厅"),
    (r"bedroom|卧室|master", "主卧"),
    (r"kitchen|厨房", "厨房"),
    (r"bathroom|卫生间|toilet", "卫生间"),
    (r"balcony|阳台", "阳台"),
    (r"study|书房|office", "书房"),
    (r"dining|餐厅", "餐厅"),
    (r"entrance|玄关|doorway", "玄关"),
]


def _infer_room(entity_id: str, friendly_name: str) -> str | None:
    text = f"{entity_id} {friendly_name}".lower()
    for pattern, room in _ROOM_KEYWORDS:
        if re.search(pattern, text):
            return room
    return None


def ha_states_to_devices(states: list[dict[str, Any]]) -> list[Device]:
    """将 HA states 列表转换为 Device 列表。"""
    devices: list[Device] = []
    for state in states:
        entity_id: str = state.get("entity_id", "")
        domain = entity_id.split(".")[0] if "." in entity_id else ""
        if not domain:
            continue

        attrs: dict[str, Any] = state.get("attributes", {})
        friendly_name: str = attrs.get("friendly_name", entity_id)

        devices.append(Device(
            id=entity_id,
            name=friendly_name,
            type=_DOMAIN_TYPE_MAP.get(domain, domain),
            platform="ha",
            state=state.get("state"),
            attributes=attrs,
            capabilities=_DOMAIN_CAPABILITIES.get(domain, []),
            room=_infer_room(entity_id, friendly_name),
            icon=attrs.get("icon"),
        ))
    return devices
