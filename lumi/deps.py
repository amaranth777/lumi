"""FastAPI 依赖注入。"""

from __future__ import annotations

from functools import lru_cache

from lumi.config import get_config
from lumi.device_graph.service import DeviceGraphService
from lumi.ha.client import HAClient


@lru_cache
def get_ha_client() -> HAClient | None:
    """获取 HA 客户端（单例）。"""
    config = get_config()
    if not config.ha.enabled:
        return None
    return HAClient(
        base_url=config.ha.base_url,
        token_file=config.ha.token_file,
    )


@lru_cache
def get_device_graph_service() -> DeviceGraphService:
    """获取设备图服务（单例）。"""
    ha_client = get_ha_client()
    return DeviceGraphService(ha_client=ha_client)
