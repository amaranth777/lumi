"""Lumi 配置管理。

从环境变量或 ~/.lumi/config.json 加载配置。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class HAConfig(BaseModel):
    """Home Assistant 配置。"""

    enabled: bool = Field(default=False, description="是否启用 HA 集成")
    base_url: str = Field(
        default="http://192.168.5.184:8123",
        description="HA 服务器地址",
    )
    token_file: str = Field(
        default="~/.hermes/ha_token",
        description="HA Long-Lived Access Token 文件路径",
    )


class ServerConfig(BaseModel):
    """Lumi 服务配置。"""

    host: str = Field(default="127.0.0.1", description="监听地址")
    port: int = Field(default=8810, description="监听端口")
    token: str = Field(default="", description="API 鉴权 token")
    ws_heartbeat_seconds: int = Field(default=30, description="WebSocket 心跳间隔（秒）")


class MilocoConfig(BaseModel):
    """Miloco 配置。"""

    enabled: bool = Field(default=False, description="是否启用 Miloco 集成")
    base_url: str = Field(
        default="http://127.0.0.1:1810",
        description="Miloco 服务地址",
    )
    token: str = Field(default="", description="Miloco API token（从 ~/.miloco/config.json 读取）")
    token_file: str = Field(
        default="~/.miloco/config.json",
        description="Miloco 配置文件路径（自动读取 token）",
    )


class DeviceAliasConfig(BaseModel):
    """单个设备别名配置。"""

    canonical_id: str = Field(..., description="规范设备 ID")
    name: str = Field(..., description="覆盖显示名称")
    room: str | None = Field(None, description="覆盖房间")
    miot_match: str | None = Field(None, description="匹配 Miloco did/model 前缀")
    ha_entities: list[str] = Field(default_factory=list, description="绑定的 HA entity_id 列表")
    policies: dict[str, Any] = Field(default_factory=dict, description="forbidden_actions / allowed_actions")


class DeviceGraphConfig(BaseModel):
    """设备图配置（别名等）。"""

    aliases: list[DeviceAliasConfig] = Field(default_factory=list, description="设备别名列表")


class ProactiveConfig(BaseModel):
    """主动巡检配置。"""

    enabled: bool = Field(default=True, description="是否启用主动巡检")
    interval_seconds: int = Field(default=300, description="巡检间隔（秒），默认 5 分钟")
    min_alert_interval_seconds: int = Field(
        default=1800, description="同一告警最短重推间隔（秒），默认 30 分钟"
    )
    rules: list[str] = Field(
        default_factory=lambda: ["litter_box_full", "litter_box_low_sand", "temperature", "humidity"],
        description="启用的规则列表",
    )
    rules_file: str = Field(
        default="~/.lumi/rules.yaml",
        description="自定义规则配置文件路径（可选，文件不存在则跳过）",
    )
    auto_execute: bool = Field(default=False, description="是否允许自动执行纠正动作（默认关闭，需显式开启）")


class CatProfile(BaseModel):
    """单只猫的档案。"""

    name: str = Field(..., description="猫的名字")
    weight_min_kg: float = Field(default=2.0, description="正常体重下限（kg）")
    weight_max_kg: float = Field(default=8.0, description="正常体重上限（kg）")


class PetConfig(BaseModel):
    """宠物相关配置。"""
    name: str = Field(default="猫猫", description="宠物名称")
    weight_min_kg: float = Field(default=2.0, description="体重异常下限（kg）")
    weight_max_kg: float = Field(default=8.0, description="体重异常上限（kg）")
    litter_low_kg: float = Field(default=1.0, description="猫砂余量告警阈值（kg）")
    cats: list[CatProfile] = Field(default_factory=list, description="多猫档案列表，空时用单猫兼容模式")


class LumiConfig(BaseModel):
    """Lumi 全局配置。"""

    server: ServerConfig = Field(default_factory=ServerConfig)
    ha: HAConfig = Field(default_factory=HAConfig)
    miloco: MilocoConfig = Field(default_factory=MilocoConfig)
    pet: PetConfig = Field(default_factory=PetConfig)
    proactive: ProactiveConfig = Field(default_factory=ProactiveConfig)
    device_aliases: list[dict[str, Any]] = Field(
        default_factory=list,
        description="设备手动映射配置",
    )
    cache_ttl: int = Field(
        default=300,
        description="设备图缓存 TTL（秒），默认 5 分钟",
    )
    device_graph: DeviceGraphConfig = Field(
        default_factory=DeviceGraphConfig,
        description="设备图配置（别名等）",
    )


def _load_config_file() -> dict[str, Any]:
    """从 ~/.lumi/config.json 加载配置。"""
    config_path = Path.home() / ".lumi" / "config.json"
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


_config: LumiConfig | None = None


def get_config() -> LumiConfig:
    """获取全局配置（单例）。"""
    global _config
    if _config is None:
        file_data = _load_config_file()
        # 环境变量覆盖
        if "LUMI_HA_BASE_URL" in os.environ:
            file_data.setdefault("ha", {})["base_url"] = os.environ["LUMI_HA_BASE_URL"]
        if "LUMI_HA_TOKEN_FILE" in os.environ:
            file_data.setdefault("ha", {})["token_file"] = os.environ["LUMI_HA_TOKEN_FILE"]
        if "LUMI_SERVER_TOKEN" in os.environ:
            file_data.setdefault("server", {})["token"] = os.environ["LUMI_SERVER_TOKEN"]
        if "LUMI_SERVER_PORT" in os.environ:
            try:
                file_data.setdefault("server", {})["port"] = int(os.environ["LUMI_SERVER_PORT"])
            except ValueError:
                pass
        if "LUMI_SERVER_HOST" in os.environ:
            file_data.setdefault("server", {})["host"] = os.environ["LUMI_SERVER_HOST"]
        if "LUMI_MILOCO_BASE_URL" in os.environ:
            file_data.setdefault("miloco", {})["base_url"] = os.environ["LUMI_MILOCO_BASE_URL"]
        if "LUMI_MILOCO_TOKEN" in os.environ:
            file_data.setdefault("miloco", {})["token"] = os.environ["LUMI_MILOCO_TOKEN"]
        if "LUMI_CACHE_TTL" in os.environ:
            try:
                file_data["cache_ttl"] = int(os.environ["LUMI_CACHE_TTL"])
            except ValueError:
                pass
        _config = LumiConfig(**file_data)
    return _config
