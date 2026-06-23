"""Lumi FastAPI 应用入口。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from lumi.device_graph.router import router as device_graph_router
from lumi.scenes.router import router as scenes_router
from lumi.websocket import router as ws_router, manager as ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期——启动时订阅 HA 事件。"""
    # 延迟导入避免循环
    from lumi.deps import get_ha_client
    from lumi.ha.events import start_ha_event_listener

    ha_client = get_ha_client()
    if ha_client:
        task = asyncio.create_task(
            start_ha_event_listener(ha_client, ws_manager),
            name="ha_event_listener",
        )
        logger.info("HA 事件监听器已启动")
    else:
        task = None
        logger.info("HA 未启用，跳过事件监听")

    yield  # 应用运行期间

    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("HA 事件监听器已停止")


import lumi as _lumi_pkg

app = FastAPI(
    title="Lumi",
    description="统一智能家居设备图与控制层",
    version=_lumi_pkg.__version__,
    lifespan=lifespan,
)

# CORS 配置（前端开发/跨域）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录（前端 build 产物）
# 访问 /ui/ 自动 serve index.html，支持 SPA
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(static_dir), html=True), name="static")

# API 路由
app.include_router(device_graph_router)
app.include_router(scenes_router)
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict:
    """健康检查端点——包含版本、HA 连通性、设备数。"""
    from lumi.deps import get_ha_client, get_miloco_client

    result: dict = {
        "status": "ok",
        "version": app.version,
    }

    # HA 连通性（不抛异常）
    ha_client = get_ha_client()
    if ha_client:
        try:
            states = ha_client.get_states()
            result["ha"] = "ok"
            result["device_count"] = len(states)
        except Exception:
            result["ha"] = "error"
    else:
        result["ha"] = "disabled"

    # Miloco 连通性
    miloco_client = get_miloco_client()
    if miloco_client:
        result["miloco"] = "ok" if miloco_client.is_available() else "error"
    else:
        result["miloco"] = "disabled"

    return result


@app.get("/api/status")
async def status() -> dict:
    """运行时详情端点——包含设备分布、场景数、bridge 冷却状态。"""
    from lumi.deps import get_ha_client, get_miloco_client, get_device_graph_service, get_scene_store

    result: dict = {
        "status": "ok",
        "version": app.version,
    }

    # 设备图摘要
    try:
        svc = get_device_graph_service()
        summary = svc.get_summary()
        result["devices"] = {
            "total": summary.total_devices,
            "by_platform": summary.by_platform,
            "by_type": summary.by_type,
            "rooms": summary.rooms,
        }
    except Exception as e:
        result["devices"] = {"error": str(e)}

    # 场景数
    try:
        store = get_scene_store()
        result["scenes"] = {"count": len(store.list())}
    except Exception as e:
        result["scenes"] = {"error": str(e)}

    # HermesBridge 冷却状态
    try:
        from lumi.hermes_bridge import get_bridge
        bridge = get_bridge()
        cooldown_state = {
            k: round(bridge.cooldown.remaining(k))
            for k in bridge.cooldown._last_sent
            if bridge.cooldown.remaining(k) > 0
        }
        result["bridge"] = {
            "target": bridge.target,
            "active_cooldowns": len(cooldown_state),
            "cooldowns": cooldown_state,
        }
    except Exception as e:
        result["bridge"] = {"error": str(e)}

    # WebSocket 连接数
    try:
        result["websocket"] = {"connections": len(ws_manager.active_connections)}
    except Exception:
        result["websocket"] = {"connections": 0}

    return result


def start_server() -> None:
    """CLI 入口（lumi 命令）。"""
    import uvicorn
    from lumi.config import get_config

    config = get_config()
    uvicorn.run(
        "lumi.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=False,
    )


if __name__ == "__main__":
    start_server()
