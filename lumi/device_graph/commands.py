"""HA 命令执行器：将 Lumi 标准命令映射到 HA service 调用。"""

from __future__ import annotations

from typing import Any

from lumi.device_graph.schema import Device

# Lumi command → (HA domain, service, extra_data_fn)
# extra_data_fn(params) 返回合并到 service_data 的额外字段
_COMMAND_MAP: dict[str, dict[str, tuple[str, str, Any]]] = {
    # 通用开关
    "turn_on":  {"*": ("homeassistant", "turn_on",  None)},
    "turn_off": {"*": ("homeassistant", "turn_off", None)},
    "toggle":   {"*": ("homeassistant", "toggle",   None)},

    # 亮度 / 色温
    "set_brightness": {
        "light": ("light", "turn_on", lambda p: {"brightness_pct": p["brightness"]}),
    },
    "set_color_temp": {
        "light": ("light", "turn_on", lambda p: {"color_temp_kelvin": p["color_temp"]}),
    },

    # 温控
    "set_temperature": {
        "climate": ("climate", "set_temperature", lambda p: {"temperature": p["temperature"]}),
    },
    "set_hvac_mode": {
        "climate": ("climate", "set_hvac_mode", lambda p: {"hvac_mode": p["hvac_mode"]}),
    },

    # 加湿器
    "set_humidity": {
        "humidifier": ("humidifier", "set_humidity", lambda p: {"humidity": p["humidity"]}),
    },
    "set_mode": {
        "humidifier": ("humidifier", "set_mode", lambda p: {"mode": p["mode"]}),
        "fan":        ("fan",        "set_preset_mode", lambda p: {"preset_mode": p["mode"]}),
        "climate":    ("climate",    "set_hvac_mode",   lambda p: {"hvac_mode": p["mode"]}),
    },

    # 风扇
    "set_percentage": {
        "fan": ("fan", "set_percentage", lambda p: {"percentage": p["percentage"]}),
    },

    # 吸尘器
    "start":  {"vacuum": ("vacuum", "start",  None)},
    "stop":   {"vacuum": ("vacuum", "stop",   None)},
    "locate": {"vacuum": ("vacuum", "locate", None)},
    "return_to_base": {"vacuum": ("vacuum", "return_to_base", None)},

    # 窗帘
    "open":  {"cover": ("cover", "open_cover",  None)},
    "close": {"cover": ("cover", "close_cover", None)},
    "set_position": {
        "cover": ("cover", "set_cover_position", lambda p: {"position": p["position"]}),
    },

    # 门锁
    "lock":   {"lock": ("lock", "lock",   None)},
    "unlock": {"lock": ("lock", "unlock", None)},

    # 媒体播放器
    "media_play":        {"media_player": ("media_player", "media_play",        None)},
    "media_pause":       {"media_player": ("media_player", "media_pause",       None)},
    "media_stop":        {"media_player": ("media_player", "media_stop",        None)},
    "media_next_track":  {"media_player": ("media_player", "media_next_track",  None)},
    "media_prev_track":  {"media_player": ("media_player", "media_previous_track", None)},
    "set_volume": {
        "media_player": ("media_player", "volume_set", lambda p: {"volume_level": p["volume"]}),
    },
    "volume_up":   {"media_player": ("media_player", "volume_up",   None)},
    "volume_down": {"media_player": ("media_player", "volume_down", None)},
    "volume_mute": {
        "media_player": ("media_player", "volume_mute", lambda p: {"is_volume_muted": p.get("mute", True)}),
    },
    "select_source": {
        "media_player": ("media_player", "select_source", lambda p: {"source": p["source"]}),
    },

    # 空气净化器 / 其他 select 设备
    "select_option": {
        "select": ("select", "select_option", lambda p: {"option": p["option"]}),
    },

    # number 实体
    "set_value": {
        "number": ("number", "set_value", lambda p: {"value": p["value"]}),
    },

    # 按钮
    "press": {"button": ("button", "press", None)},
}


def resolve_command(
    device: Device, command: str, params: dict[str, Any]
) -> tuple[str, str, dict[str, Any]] | None:
    """将 Lumi 命令解析为 (domain, service, service_data)。

    Returns None 如果命令不支持。
    """
    cmd_variants = _COMMAND_MAP.get(command)
    if not cmd_variants:
        return None

    # 优先精确匹配设备类型，fallback 到 "*"
    entry = cmd_variants.get(device.type) or cmd_variants.get("*")
    if not entry:
        return None

    domain, service, extra_fn = entry
    service_data: dict[str, Any] = {"entity_id": device.id}
    if extra_fn:
        service_data.update(extra_fn(params))
    service_data.update({k: v for k, v in params.items()
                         if k not in ("entity_id",)})
    return domain, service, service_data
