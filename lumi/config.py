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


class LumiConfig(BaseModel):
    """Lumi 全局配置。"""

    server: ServerConfig = Field(default_factory=ServerConfig)
    ha: HAConfig = Field(default_factory=HAConfig)
    miloco: MilocoConfig = Field(default_factory=MilocoConfig)
    device_aliases: list[dict[str, Any]] = Field(
        default_factory=list,
        description="设备手动映射配置",
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
        _config = LumiConfig(**file_data)
    return _config
