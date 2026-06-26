"""从 YAML 文件加载自定义规则阈值覆盖。

YAML 格式示例（~/.lumi/rules.yaml）：
rules:
  temperature:
    enabled: true
    max_celsius: 35
    min_celsius: 5
  humidity:
    enabled: true
    max_percent: 90
    min_percent: 20
  litter_box_full:
    enabled: true
  litter_box_low_sand:
    enabled: true
    threshold_kg: 1.0
  device_offline:
    enabled: true
    offline_minutes: 30
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RulesConfig(BaseModel):
    """规则阈值配置。"""

    temperature_max: float = Field(default=35.0, description="温度上限（°C）")
    temperature_min: float = Field(default=5.0, description="温度下限（°C）")
    humidity_max: float = Field(default=90.0, description="湿度上限（%）")
    humidity_min: float = Field(default=20.0, description="湿度下限（%）")
    litter_low_threshold_kg: float = Field(default=1.0, description="猫砂余量告警阈值（kg）")
    device_offline_minutes: int = Field(default=30, description="设备离线告警时间（分钟）")
    disabled_rules: list[str] = Field(default_factory=list, description="禁用的规则名列表")
    battery_low_percent: float = Field(default=20.0, description="电池低电量告警阈值（%）")
    entity_monitors: list[dict[str, Any]] = Field(default_factory=list, description="自定义实体监控规则列表")


def load_rules_config(path: str = "~/.lumi/rules.yaml") -> RulesConfig:
    """从 YAML 加载规则配置，文件不存在或解析失败则返回默认值。"""
    resolved = Path(path).expanduser()
    if not resolved.exists():
        logger.debug("规则配置文件不存在，使用默认值: %s", resolved)
        return RulesConfig()

    try:
        import yaml  # type: ignore
    except ImportError:
        logger.warning("未安装 PyYAML，无法加载规则配置文件，使用默认值")
        return RulesConfig()

    try:
        raw = resolved.read_text(encoding="utf-8")
        data: Any = yaml.safe_load(raw)
    except Exception as e:
        logger.warning("解析规则配置文件失败，使用默认值: %s — %s", resolved, e)
        return RulesConfig()

    if not isinstance(data, dict):
        logger.warning("规则配置文件格式错误（顶层非 dict），使用默认值: %s", resolved)
        return RulesConfig()

    rules_section: dict = data.get("rules", {}) or {}
    if not isinstance(rules_section, dict):
        logger.warning("rules 字段格式错误，使用默认值")
        return RulesConfig()

    kwargs: dict[str, Any] = {}
    disabled: list[str] = []

    # temperature
    temp_cfg = rules_section.get("temperature", {}) or {}
    if isinstance(temp_cfg, dict):
        if temp_cfg.get("enabled") is False:
            disabled.append("temperature")
        if "max_celsius" in temp_cfg:
            kwargs["temperature_max"] = float(temp_cfg["max_celsius"])
        if "min_celsius" in temp_cfg:
            kwargs["temperature_min"] = float(temp_cfg["min_celsius"])

    # humidity
    humi_cfg = rules_section.get("humidity", {}) or {}
    if isinstance(humi_cfg, dict):
        if humi_cfg.get("enabled") is False:
            disabled.append("humidity")
        if "max_percent" in humi_cfg:
            kwargs["humidity_max"] = float(humi_cfg["max_percent"])
        if "min_percent" in humi_cfg:
            kwargs["humidity_min"] = float(humi_cfg["min_percent"])

    # litter_box_full
    lb_full_cfg = rules_section.get("litter_box_full", {}) or {}
    if isinstance(lb_full_cfg, dict):
        if lb_full_cfg.get("enabled") is False:
            disabled.append("litter_box_full")

    # litter_box_low_sand
    lb_sand_cfg = rules_section.get("litter_box_low_sand", {}) or {}
    if isinstance(lb_sand_cfg, dict):
        if lb_sand_cfg.get("enabled") is False:
            disabled.append("litter_box_low_sand")
        if "threshold_kg" in lb_sand_cfg:
            kwargs["litter_low_threshold_kg"] = float(lb_sand_cfg["threshold_kg"])

    # device_offline
    offline_cfg = rules_section.get("device_offline", {}) or {}
    if isinstance(offline_cfg, dict):
        if offline_cfg.get("enabled") is False:
            disabled.append("device_offline")
        if "offline_minutes" in offline_cfg:
            kwargs["device_offline_minutes"] = int(offline_cfg["offline_minutes"])

    # low_battery
    battery_cfg = rules_section.get("low_battery", {}) or {}
    if isinstance(battery_cfg, dict):
        if battery_cfg.get("enabled") is False:
            disabled.append("low_battery")
        if "battery_low_percent" in battery_cfg:
            kwargs["battery_low_percent"] = float(battery_cfg["battery_low_percent"])

    # entity_monitors (top-level key, not under rules)
    entity_monitors = data.get("entity_monitors")
    if isinstance(entity_monitors, list):
        kwargs["entity_monitors"] = entity_monitors

    kwargs["disabled_rules"] = disabled
    return RulesConfig(**kwargs)
