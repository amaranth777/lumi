"""Miloco 设备融合：将 Miloco 设备列表转换为标准 Device 模型。"""

from __future__ import annotations

from typing import Any

from lumi.device_graph.schema import Device

# Miloco 设备 category → Lumi 类型
_CATEGORY_TYPE_MAP: dict[str, str] = {
    "light": "light",
    "switch": "switch",
    "outlet": "switch",
    "sensor": "sensor",
    "climate": "climate",
    "air_conditioner": "climate",
    "fan": "fan",
    "air_purifier": "fan",
    "humidifier": "humidifier",
    "vacuum": "vacuum",
    "cover": "cover",
    "curtain": "cover",
    "lock": "lock",
    "camera": "camera",
    "gateway": "gateway",
    "speaker": "media_player",
    "tv": "media_player",
    "washing_machine": "appliance",
    "dryer": "appliance",
    "refrigerator": "appliance",
    "dishwasher": "appliance",
    "oven": "appliance",
    "water_purifier": "appliance",
    "pet_feeder": "appliance",
    "pet_water_dispenser": "appliance",
}

_CATEGORY_CAPABILITIES: dict[str, list[str]] = {
    "light": ["toggle", "brightness", "color"],
    "switch": ["toggle"],
    "outlet": ["toggle"],
    "fan": ["toggle", "speed"],
    "air_purifier": ["toggle", "speed", "set_mode"],
    "humidifier": ["toggle", "set_humidity", "set_mode"],
    "climate": ["toggle", "set_temperature", "set_hvac_mode"],
    "vacuum": ["start", "stop"],
    "cover": ["open", "close", "set_position"],
    "lock": ["lock", "unlock"],
}


def miloco_devices_to_lumi(
    miloco_devices: list[dict[str, Any]],
) -> list[Device]:
    """将 Miloco 设备列表转换为 Lumi Device 列表。"""
    devices: list[Device] = []

    for raw in miloco_devices:
        did: str = raw.get("did", "")
        if not did:
            continue

        name: str = raw.get("name", did)
        category: str = raw.get("category", "")
        room_name: str | None = raw.get("room_name") or None
        online: bool = raw.get("online", False)
        model: str = raw.get("model", "")

        dev_type = _CATEGORY_TYPE_MAP.get(category, category or "unknown")
        capabilities = _CATEGORY_CAPABILITIES.get(category, [])

        devices.append(Device(
            id=f"miloco.{did}",
            name=name,
            type=dev_type,
            platform="miloco",
            state="online" if online else "offline",
            attributes={
                "did": did,
                "model": model,
                "category": category,
                "online": online,
                "home_name": raw.get("home_name", ""),
            },
            capabilities=capabilities,
            room=room_name,
            icon=None,
            metadata={"source": "miloco"},
        ))

    return devices
