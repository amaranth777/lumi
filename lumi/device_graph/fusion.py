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
# 优先级从上到下，匹配到第一个就停止
_ROOM_KEYWORDS: list[tuple[str, str]] = [
    (r"卧室|bedroom|master_bedroom", "卧室"),
    (r"客厅|living", "客厅"),
    (r"厨房|kitchen", "厨房"),
    (r"卫生间|bathroom|toilet|restroom|washroom", "卫生间"),
    (r"阳台|balcony", "阳台"),
    (r"书房|study|office", "书房"),
    (r"餐厅|dining", "餐厅"),
    (r"玄关|entrance|doorway|hallway", "玄关"),
    (r"次卧|second_bedroom|guest_room", "次卧"),
    (r"儿童房|kids_room|children", "儿童房"),
    (r"衣帽间|wardrobe|cloakroom", "衣帽间"),
    (r"储藏室|storage|storeroom", "储藏室"),
    (r"露台|terrace|rooftop", "露台"),
    (r"车库|garage", "车库"),
    (r"地下室|basement", "地下室"),
]


def _infer_room(entity_id: str, friendly_name: str) -> str | None:
    text = f"{entity_id} {friendly_name}".lower()
    for pattern, room in _ROOM_KEYWORDS:
        if re.search(pattern, text):
            return room
    return None


def ha_states_to_devices(
    states: list[dict[str, Any]],
    aliases: list[dict[str, Any]] | None = None,
) -> list[Device]:
    """将 HA states 列表转换为 Device 列表。
    
    Args:
        states: HA /api/states 返回的状态列表
        aliases: 手动配置的别名映射列表，每项格式：
            {
                "entity_id": "fan.zhimi_airpurifier_ma2",
                "name": "客厅空气净化器",
                "room": "客厅",
                "icon": "mdi:air-purifier"  # 可选
            }
    """
    # 构建别名查找表
    alias_map: dict[str, dict[str, Any]] = {}
    if aliases:
        for alias in aliases:
            eid = alias.get("entity_id")
            if eid:
                alias_map[eid] = alias

    devices: list[Device] = []
    for state in states:
        entity_id: str = state.get("entity_id", "")
        domain = entity_id.split(".")[0] if "." in entity_id else ""
        if not domain:
            continue

        attrs: dict[str, Any] = state.get("attributes", {})
        friendly_name: str = attrs.get("friendly_name", entity_id)

        # 应用别名覆盖
        alias = alias_map.get(entity_id, {})
        name = alias.get("name", friendly_name)
        room = alias.get("room") or _infer_room(entity_id, friendly_name)
        icon = alias.get("icon") or attrs.get("icon")

        devices.append(Device(
            id=entity_id,
            name=name,
            type=_DOMAIN_TYPE_MAP.get(domain, domain),
            platform="ha",
            state=state.get("state"),
            attributes=attrs,
            capabilities=_DOMAIN_CAPABILITIES.get(domain, []),
            room=room,
            icon=icon,
        ))
    return devices
