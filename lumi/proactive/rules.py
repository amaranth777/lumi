"""主动巡检规则定义。

定义 ProactiveRule 协议和内置规则。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from lumi.device_graph.schema import Device


# Forward reference — imported lazily to avoid circular imports
def _get_rules_config_type():
    from lumi.proactive.rules_loader import RulesConfig
    return RulesConfig


class Alert(BaseModel):
    """巡检告警。"""

    level: Literal["info", "warning", "critical"]
    device_id: str | None = None
    message: str
    action_hint: str | None = None  # 建议动作
    auto_action: str | None = None
    # 可选自动执行的 lumi_tool action，格式为 "action:device_id:command"
    # 例："control:humidifier.living_room:turn_on"
    # 涉及猫砂盆的永远不写 empty


@runtime_checkable
class ProactiveRule(Protocol):
    """主动巡检规则协议。"""

    name: str

    def check(self, devices: list[Device], ha_states: list[dict]) -> list[Alert]:
        """检查设备列表，返回告警列表。"""
        ...


# ─── 内置规则 ─────────────────────────────────────────────────────────────────


class LitterBoxFullRule:
    """猫砂盆集便仓满告警。

    集便仓 Full 且模式为 Off → warning
    """

    name = "litter_box_full"

    def __init__(self, rules_config=None) -> None:
        self.rules_config = rules_config

    def check(self, devices: list[Device], ha_states: list[dict]) -> list[Alert]:
        alerts: list[Alert] = []
        for dev in devices:
            # 判断是否为猫砂盆类型
            if not _is_litter_box(dev):
                continue
            waste_bin = dev.attributes.get("waste_collection_status", "")
            mode = dev.attributes.get("mode", "")
            # 集便仓 Full + 模式 Off
            if str(waste_bin).lower() == "full" and str(mode).lower() in ("off", "idle", "0"):
                alerts.append(
                    Alert(
                        level="warning",
                        device_id=dev.id,
                        message=f"猫砂盆集便仓已满，建议手动清理（{dev.name}）",
                        action_hint="control litter_box clean",
                    )
                )
        return alerts


class LitterBoxLowSandRule:
    """猫砂余量不足告警。"""

    name = "litter_box_low_sand"

    def __init__(self, litter_low_kg: float = 1.0, rules_config=None) -> None:
        if rules_config is not None:
            self.litter_low_kg = rules_config.litter_low_threshold_kg
        else:
            self.litter_low_kg = litter_low_kg
        self.rules_config = rules_config

    def check(self, devices: list[Device], ha_states: list[dict]) -> list[Alert]:
        alerts: list[Alert] = []
        for dev in devices:
            if not _is_litter_box(dev):
                continue
            # 尝试多种属性名
            sand_kg: float | None = None
            for attr in ("sand_weight", "litter_weight", "sand_remaining_kg", "sand_kg"):
                val = dev.attributes.get(attr)
                if val is not None:
                    try:
                        sand_kg = float(val)
                    except (ValueError, TypeError):
                        pass
                    break
            if sand_kg is not None and sand_kg < self.litter_low_kg:
                alerts.append(
                    Alert(
                        level="warning",
                        device_id=dev.id,
                        message=f"猫砂余量不足（{dev.name}：{sand_kg:.1f}kg < {self.litter_low_kg:.1f}kg）",
                        action_hint=None,
                    )
                )
        return alerts


class TemperatureAnomalyRule:
    """室内温度异常告警（>35°C 或 <5°C）。"""

    name = "temperature"

    def __init__(self, rules_config=None) -> None:
        if rules_config is not None:
            self.temp_max = rules_config.temperature_max
            self.temp_min = rules_config.temperature_min
        else:
            self.temp_max = 35.0
            self.temp_min = 5.0
        self.rules_config = rules_config

    def check(self, devices: list[Device], ha_states: list[dict]) -> list[Alert]:
        alerts: list[Alert] = []
        for dev in devices:
            if not _is_temperature_sensor(dev):
                continue
            temp = _get_numeric_state(dev)
            if temp is None:
                continue
            if temp > self.temp_max:
                alerts.append(
                    Alert(
                        level="warning",
                        device_id=dev.id,
                        message=f"室内温度过高（{dev.name}：{temp:.1f}°C）",
                    )
                )
            elif temp < self.temp_min:
                alerts.append(
                    Alert(
                        level="warning",
                        device_id=dev.id,
                        message=f"室内温度过低（{dev.name}：{temp:.1f}°C）",
                    )
                )
        return alerts


class HumidityAnomalyRule:
    """室内湿度异常告警（>90% 或 <20%）。"""

    name = "humidity"

    def __init__(self, rules_config=None) -> None:
        if rules_config is not None:
            self.humidity_max = rules_config.humidity_max
            self.humidity_min = rules_config.humidity_min
        else:
            self.humidity_max = 90.0
            self.humidity_min = 20.0
        self.rules_config = rules_config

    def check(self, devices: list[Device], ha_states: list[dict]) -> list[Alert]:
        alerts: list[Alert] = []
        for dev in devices:
            if not _is_humidity_sensor(dev):
                continue
            humidity = _get_numeric_state(dev)
            if humidity is None:
                continue
            if humidity > self.humidity_max:
                alerts.append(
                    Alert(
                        level="info",
                        device_id=dev.id,
                        message=f"室内湿度过高（{dev.name}：{humidity:.1f}%）",
                    )
                )
            elif humidity < self.humidity_min:
                alerts.append(
                    Alert(
                        level="info",
                        device_id=dev.id,
                        message=f"室内湿度过低（{dev.name}：{humidity:.1f}%）",
                    )
                )
        return alerts


class DeviceOfflineRule:
    """设备离线告警（unavailable 超过 30 分钟）。"""

    name = "device_offline"

    OFFLINE_THRESHOLD_SECONDS: int = 1800  # 30 分钟

    def __init__(self, rules_config=None) -> None:
        if rules_config is not None:
            self.OFFLINE_THRESHOLD_SECONDS = rules_config.device_offline_minutes * 60
        self.rules_config = rules_config

    def check(self, devices: list[Device], ha_states: list[dict]) -> list[Alert]:
        alerts: list[Alert] = []
        # 构建 ha_states 索引，按 entity_id 查找 last_changed
        state_map: dict[str, dict] = {s.get("entity_id", ""): s for s in ha_states}

        now = time.time()
        for dev in devices:
            if dev.state != "unavailable":
                continue
            # 从 ha_states 中找 last_changed
            state_info = state_map.get(dev.id, {})
            last_changed_str: str | None = state_info.get("last_changed")
            if last_changed_str:
                offline_seconds = _seconds_since_iso(last_changed_str, now)
            else:
                # 属性中也可能有
                offline_seconds = self.OFFLINE_THRESHOLD_SECONDS + 1  # 无时间信息 → 视为超时

            if offline_seconds >= self.OFFLINE_THRESHOLD_SECONDS:
                alerts.append(
                    Alert(
                        level="info",
                        device_id=dev.id,
                        message=f"设备离线（{dev.name}，已离线 {int(offline_seconds // 60)} 分钟）",
                    )
                )
        return alerts


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────


def _is_litter_box(dev: Device) -> bool:
    """判断是否为猫砂盆设备。"""
    type_match = dev.type in ("litter_box", "pet_litter_box")
    name_match = any(kw in dev.name for kw in ("猫砂盆", "猫厕所", "litter"))
    return type_match or name_match


def _is_temperature_sensor(dev: Device) -> bool:
    """判断是否为温度传感器。"""
    if dev.type in ("temperature", "temperature_sensor"):
        return True
    unit = dev.attributes.get("unit_of_measurement", "")
    if unit in ("°C", "°F", "C", "F"):
        return True
    if "temperature" in dev.id.lower() or "温度" in dev.name:
        return True
    device_class = dev.attributes.get("device_class", "")
    return device_class == "temperature"


def _is_humidity_sensor(dev: Device) -> bool:
    """判断是否为湿度传感器。"""
    if dev.type in ("humidity", "humidity_sensor"):
        return True
    unit = dev.attributes.get("unit_of_measurement", "")
    if unit == "%":
        device_class = dev.attributes.get("device_class", "")
        if device_class == "humidity":
            return True
    if "humidity" in dev.id.lower() or "湿度" in dev.name:
        return True
    device_class = dev.attributes.get("device_class", "")
    return device_class == "humidity"


def _get_numeric_state(dev: Device) -> float | None:
    """从设备状态或属性提取数值。"""
    if dev.state is not None:
        try:
            return float(dev.state)
        except (ValueError, TypeError):
            pass
    for attr in ("value", "temperature", "humidity", "current_temperature"):
        val = dev.attributes.get(attr)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
    return None


def _seconds_since_iso(iso_str: str, now: float) -> float:
    """计算 ISO 8601 时间戳距 now 的秒数。"""
    try:
        # 处理带时区的 ISO 字符串
        if iso_str.endswith("Z"):
            iso_str = iso_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            # 无时区信息，假设 UTC
            import calendar
            ts = calendar.timegm(dt.timetuple())
        else:
            ts = dt.timestamp()
        return now - ts
    except Exception:
        return 0.0


class LowBatteryRule:
    """监控所有 battery/battery_level 实体，低于阈值则告警。"""

    name = "low_battery"

    def __init__(self, rules_config=None) -> None:
        if rules_config is not None:
            self.threshold = rules_config.battery_low_percent
        else:
            self.threshold = 20.0

    def check(self, devices: list[Device], ha_states: list[dict]) -> list[Alert]:
        alerts: list[Alert] = []
        for state in ha_states:
            entity_id = state.get("entity_id", "")
            attrs = state.get("attributes", {})
            # 匹配 battery 传感器或有 battery_level 属性
            if not ("battery" in entity_id or "battery_level" in attrs):
                continue
            val = None
            try:
                val = float(state.get("state", ""))
            except (ValueError, TypeError):
                continue
            if val < self.threshold:
                alerts.append(
                    Alert(
                        level="warning",
                        device_id=entity_id,
                        message=f"设备电量低 ({val:.0f}%)",
                        action_hint=f"请尽快给 {attrs.get('friendly_name', entity_id)} 更换电池",
                    )
                )
        return alerts


class EntityValueRule:
    """监控自定义实体状态。从 rules.yaml 的 entity_monitors 列表读取。"""

    name = "entity_monitor"

    def __init__(self, rules_config=None) -> None:
        if rules_config is not None:
            self.monitors: list[dict] = list(rules_config.entity_monitors)
        else:
            self.monitors = []

    def check(self, devices: list[Device], ha_states: list[dict]) -> list[Alert]:
        if not self.monitors:
            return []

        # 构建 ha_states 索引
        state_map: dict[str, dict] = {s.get("entity_id", ""): s for s in ha_states}

        alerts: list[Alert] = []
        for monitor in self.monitors:
            entity_id = monitor.get("entity_id", "")
            condition = monitor.get("condition", "==")
            threshold = monitor.get("threshold")
            message = monitor.get("message", f"{entity_id} 触发告警")
            level = monitor.get("level", "warning")

            state_entry = state_map.get(entity_id)
            if state_entry is None:
                continue

            raw_state = state_entry.get("state", "")

            # 尝试数值比较，失败则字符串比较
            try:
                actual: Any = float(raw_state)
                thresh: Any = float(threshold)
            except (ValueError, TypeError):
                actual = str(raw_state)
                thresh = str(threshold)

            triggered = _compare(actual, condition, thresh)
            if triggered:
                alerts.append(
                    Alert(
                        level=level,
                        device_id=entity_id,
                        message=message,
                    )
                )
        return alerts


def _compare(actual: Any, condition: str, threshold: Any) -> bool:
    """按 condition 比较 actual 和 threshold。"""
    try:
        if condition == ">":
            return actual > threshold
        elif condition == "<":
            return actual < threshold
        elif condition == ">=":
            return actual >= threshold
        elif condition == "<=":
            return actual <= threshold
        elif condition == "==":
            return actual == threshold
        elif condition == "!=":
            return actual != threshold
    except TypeError:
        return False
    return False


# 规则名称 → 类映射（用于按配置实例化）
BUILTIN_RULES: dict[str, type] = {
    "litter_box_full": LitterBoxFullRule,
    "litter_box_low_sand": LitterBoxLowSandRule,
    "temperature": TemperatureAnomalyRule,
    "humidity": HumidityAnomalyRule,
    "device_offline": DeviceOfflineRule,
    "low_battery": LowBatteryRule,
    "entity_monitor": EntityValueRule,
}
