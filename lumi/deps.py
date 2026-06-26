"""FastAPI 依赖注入。"""

from __future__ import annotations

from lumi.config import get_config
from lumi.device_graph.service import DeviceGraphService
from lumi.ha.client import HAClient
from lumi.miloco.client import MilocoClient
from lumi.scenes.store import SceneStore

_ha_client: HAClient | None = None
_miloco_client: MilocoClient | None = None
_device_graph_service: DeviceGraphService | None = None
_scene_store: SceneStore | None = None
_proactive_scheduler = None  # ProactiveScheduler | None


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


def get_miloco_client() -> MilocoClient | None:
    """获取 Miloco 客户端（单例）。未启用或服务不在线时返回 None。"""
    global _miloco_client
    if _miloco_client is None:
        config = get_config()
        if not config.miloco.enabled:
            return None
        # 优先用显式 token，否则从 token_file 读取
        token = config.miloco.token
        if not token:
            try:
                c = MilocoClient.from_config(config.miloco.token_file)
                token = c._token
            except Exception:
                pass
        _miloco_client = MilocoClient(base_url=config.miloco.base_url, token=token)
    return _miloco_client


def get_device_graph_service() -> DeviceGraphService:
    """获取设备图服务（单例）。"""
    global _device_graph_service
    if _device_graph_service is None:
        ha_client = get_ha_client()
        miloco_client = get_miloco_client()
        config = get_config()
        _device_graph_service = DeviceGraphService(
            ha_client=ha_client,
            miloco_client=miloco_client,
            aliases=config.device_aliases,
            cache_ttl=config.cache_ttl,
            alias_configs=config.device_graph.aliases,
        )
    return _device_graph_service


def get_scene_store() -> SceneStore:
    """获取场景存储（单例）。"""
    global _scene_store
    if _scene_store is None:
        _scene_store = SceneStore()
    return _scene_store


def get_proactive_scheduler():
    """获取主动巡检调度器（单例）。未启用时返回 None。"""
    return _proactive_scheduler


def set_proactive_scheduler(scheduler) -> None:
    """设置主动巡检调度器实例（由 lifespan 调用）。"""
    global _proactive_scheduler
    _proactive_scheduler = scheduler

