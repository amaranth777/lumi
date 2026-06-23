"""FastAPI 依赖注入。"""

from __future__ import annotations

from lumi.config import get_config
from lumi.device_graph.service import DeviceGraphService
from lumi.ha.client import HAClient
from lumi.scenes.store import SceneStore

_ha_client: HAClient | None = None
_device_graph_service: DeviceGraphService | None = None
_scene_store: SceneStore | None = None


def get_ha_client() -> HAClient | None:
    """获取 HA 客户端（单例）。"""
    global _ha_client
    if _ha_client is None:
        config = get_config()
        if config.ha.enabled:
            _ha_client = HAClient(
                base_url=config.ha.base_url,
                token_file=config.ha.token_file,
            )
    return _ha_client


def get_device_graph_service() -> DeviceGraphService:
    """获取设备图服务（单例）。"""
    global _device_graph_service
    if _device_graph_service is None:
        ha_client = get_ha_client()
        config = get_config()
        _device_graph_service = DeviceGraphService(
            ha_client=ha_client,
            aliases=config.device_aliases,
        )
    return _device_graph_service


def get_scene_store() -> SceneStore:
    """获取场景存储（单例）。"""
    global _scene_store
    if _scene_store is None:
        _scene_store = SceneStore()
    return _scene_store
